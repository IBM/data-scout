import json
import os
import pickle
import signal
import subprocess
import sys
import tempfile
import time
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.processing.text_extraction import download

# Extraction is bounded work; this only stops a wedged parser holding a run open
# forever. Generous, because a chunk holds many documents.
EXTRACT_CHUNK_TIMEOUT = 600

# Named so a test can substitute a child that crashes on purpose -- there is no
# other way to exercise the crash-recovery path, since a real segfault depends on
# a specific malformed document we do not have.
EXTRACT_WORKER_MODULE = "src.pipeline.extract_worker"


def _die_with_parent():
    """preexec_fn: ask the kernel to SIGKILL this child if its parent dies.

    The interrupt endpoint revokes with SIGKILL, which the Celery worker child
    cannot catch, so it gets no chance to clean anything up. Without this the
    extraction subprocess would simply be reparented and keep running after the
    user pressed interrupt -- the button would report success while work carried
    on. PR_SET_PDEATHSIG is Linux-only; see _extract_popen_kwargs.
    """
    import ctypes

    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.prctl(1, signal.SIGKILL, 0, 0, 0)  # PR_SET_PDEATHSIG


def _extract_popen_kwargs():
    """PDEATHSIG where the kernel supports it (Linux containers), nothing on macOS.

    On macOS there is no equivalent, so an interrupt during extraction can leave
    a child running until it finishes its chunk. Local dev only -- every
    deployment target is Linux.
    """
    if sys.platform.startswith("linux"):
        return {"preexec_fn": _die_with_parent}
    return {}


class DocumentDownloader:
    def __init__(self, settings, notify_fn):
        self.settings = settings
        self.notify = notify_fn

    @staticmethod
    def _safe_download(i, link, notify):
        try:
            time.sleep(1)
            content = download(link)
            return i, content, "Success"
        except Exception as e:
            msg = str(e)
            notify(f"Download failed for {link}: {msg}", level="error")
            return i, "", f"Error: {msg}"

    def _run_extract_chunk(self, items):
        """Extract `items` in a child process. Returns (results, crashed_index).

        results is whatever the child finished before exiting, so a crash still
        yields the documents parsed up to that point. crashed_index is the
        document being parsed when it died, or None on a clean exit.
        """
        tmpdir = tempfile.mkdtemp(prefix="ds-extract-")
        in_path = os.path.join(tmpdir, "in.pkl")
        out_path = os.path.join(tmpdir, "out.jsonl")
        progress_path = os.path.join(tmpdir, "progress")

        try:
            with open(in_path, "wb") as fh:
                pickle.dump(items, fh)
            open(out_path, "w").close()
            open(progress_path, "w").close()

            completed = subprocess.run(
                [sys.executable, "-m", EXTRACT_WORKER_MODULE,
                 in_path, out_path, progress_path],
                capture_output=True,
                timeout=EXTRACT_CHUNK_TIMEOUT,
                **_extract_popen_kwargs(),
            )
            returncode = completed.returncode
            stderr = completed.stderr.decode("utf-8", "replace").strip()
        except subprocess.TimeoutExpired:
            # Treated exactly like a crash: the progress file still names the
            # document that hung, so it gets skipped on the retry.
            returncode, stderr = -1, f"timed out after {EXTRACT_CHUNK_TIMEOUT}s"

        try:
            results = {}
            with open(out_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        record = json.loads(line)
                        results[record["i"]] = (record["text"], record["status"])

            crashed_index = None
            if returncode != 0:
                done = set(results)
                with open(progress_path, encoding="utf-8") as fh:
                    attempted = [int(x) for x in fh.read().split()]
                pending = [i for i in attempted if i not in done]
                crashed_index = pending[-1] if pending else None
                self.notify(
                    f"Extraction subprocess exited with {returncode} "
                    f"({stderr or 'no stderr'})",
                    level="error",
                )

            return results, crashed_index
        finally:
            for path in (in_path, out_path, progress_path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass

    def _extract_chunk_with_recovery(self, indices, links, contents):
        """Extract these indices, skipping any single document that crashes.

        Each crash costs one more subprocess launch and skips exactly one
        document, so a chunk cannot loop: `pending` strictly shrinks every pass.
        """
        results = {}
        pending = list(indices)

        while pending:
            items = [(i, contents[i]) for i in pending]
            finished, crashed_index = self._run_extract_chunk(items)
            results.update(finished)

            if crashed_index is None:
                break

            # Name the document in the run log: this is the only record of which
            # URL kills the parser, and is what makes the crash reproducible.
            self.notify(
                f"Extraction crashed on {links[crashed_index]} -- skipping it "
                f"and continuing with the rest of this batch",
                level="error",
            )
            results[crashed_index] = ("", "Error: extraction crashed the parser")
            pending = [i for i in pending if i not in results]

        return results

    def _extract_documents(self, links, contents, max_workers):
        """Extract every document, in child processes, concurrently.

        Threads only supervise subprocesses here, so the GIL is irrelevant and
        the daemonic-process restriction that used to force a thread pool for the
        parsing itself no longer applies.
        """
        texts = [None] * len(contents)
        statuses = [""] * len(contents)

        workers = max(1, min(max_workers, len(contents))) if contents else 1
        chunks = [list(range(start, len(contents), workers)) for start in range(workers)]
        chunks = [c for c in chunks if c]

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._extract_chunk_with_recovery, chunk, links, contents)
                for chunk in chunks
            ]
            for future in tqdm(as_completed(futures), total=len(futures),
                               desc="Extracting", unit="batch"):
                for index, (text, status) in future.result().items():
                    texts[index] = text
                    statuses[index] = status

        # A chunk that died without even writing a progress line leaves holes.
        for i, status in enumerate(statuses):
            if not status:
                texts[i] = ""
                statuses[i] = "Error: extraction produced no result"

        return texts, statuses

    def download_and_extract_texts(self, df: pd.DataFrame):
        links = df["link"].fillna("").to_list()
        max_download_workers = self.settings.max_download_workers
        max_extract_workers = self.settings.max_extract_workers

        self.notify("Downloading documents...")
        download_start = time.time()
        contents = [None] * len(links)
        download_status = [""] * len(links)

        with ThreadPoolExecutor(max_workers=max_download_workers) as executor:
            futures = [
                executor.submit(self._safe_download, i, link, self.notify)
                for i, link in enumerate(links)
            ]

            for f in tqdm(as_completed(futures), total=len(futures), desc="Downloading", unit="file"):
                i, content, status = f.result()
                contents[i] = content
                download_status[i] = status

        download_elapsed = time.time() - download_start
        downloaded_count = sum(1 for c in contents if c is not None)
        self.notify(f"{downloaded_count} URLs were downloaded")

        self.notify("Extracting text...")
        extract_start = time.time()

        texts, extract_status = self._extract_documents(links, contents, max_extract_workers)

        extract_elapsed = time.time() - extract_start
        extracted_count = sum(1 for t in texts if t)

        self.notify(f"{extracted_count} documents were extracted")

        df = df.copy()
        df["extracted_text"] = texts
        df["download_status"] = download_status
        df["extract_status"] = extract_status

        metrics = {
            "downloaded": downloaded_count,
            "extracted": extracted_count,
        }

        timing = {
            "downloading": download_elapsed,
            "extraction": extract_elapsed,
        }

        return df, metrics, timing
