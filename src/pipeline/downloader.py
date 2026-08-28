import multiprocessing
import time
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from src.processing.text_extraction import download, extract_simple_document


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

    @staticmethod
    def _safe_extract(i, link, content):
        if content is None:
            return i, "", "Success: No content to extract"

        try:
            text = extract_simple_document(content)
            return i, text or "", "Success"
        except Exception as e:
            return i, "", f"Error: {str(e)}"

    def _extract_executor(self, max_workers: int):
        """Pick a pool that can actually run here.

        Extraction is CPU-bound, so processes are preferred. But a Celery
        prefork worker executes tasks in a *daemonic* child process, and Python
        refuses to let those start children of their own -- a process pool there
        raises "daemonic processes are not allowed to have children" and takes
        the whole run down after the documents have already been downloaded.
        Threads are slower under the GIL but always available, so they are the
        fallback rather than a failed run.
        """
        if multiprocessing.current_process().daemon:
            # debug, not info: info reaches the job's progress feed, where this
            # read as a failure ("cannot start worker processes") in the middle
            # of a healthy run. The feed already says "Extracting text...", and
            # the pool choice changes only the speed, not the outcome. Note the
            # run logger is set up at INFO with no override, so this is dropped
            # from the console and run log as well; raise setup_logger's
            # log_level to DEBUG to see it while diagnosing slow extraction.
            self.notify(
                "Extracting with a thread pool: this process is daemonic "
                "(Celery prefork) and cannot start worker processes",
                level="debug",
            )
            return ThreadPoolExecutor(max_workers=max_workers)

        return ProcessPoolExecutor(max_workers=max_workers)

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
        texts = [None] * len(contents)
        extract_status = [""] * len(contents)

        with self._extract_executor(max_extract_workers) as executor:
            futures = [
                executor.submit(self._safe_extract, i, links[i], contents[i])
                for i in range(len(contents))
            ]

            for f in tqdm(as_completed(futures), total=len(futures), desc="Extracting", unit="file"):
                i, text, status = f.result()
                texts[i] = text
                extract_status[i] = status

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
