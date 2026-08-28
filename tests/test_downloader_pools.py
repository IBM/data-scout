import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.pipeline.downloader import DocumentDownloader

HTML = "<html><body><article><p>Some extracted body text for the test.</p></article></body></html>"


def _downloader():
    settings = SimpleNamespace(max_download_workers=2, max_extract_workers=2)
    return DocumentDownloader(settings, MagicMock())


class TestExtractExecutorChoice:
    def test_uses_processes_when_allowed(self):
        with _downloader()._extract_executor(2) as executor:
            assert isinstance(executor, ProcessPoolExecutor)

    def test_falls_back_to_threads_in_a_daemonic_process(self):
        """A Celery prefork worker runs tasks in a daemonic process, which is
        not allowed to start children -- a process pool there aborts the run
        after all the documents have already been downloaded."""
        with patch(
            "src.pipeline.downloader.multiprocessing.current_process",
            return_value=SimpleNamespace(daemon=True),
        ):
            with _downloader()._extract_executor(2) as executor:
                assert isinstance(executor, ThreadPoolExecutor)

    def test_reports_the_fallback(self):
        downloader = _downloader()
        with patch(
            "src.pipeline.downloader.multiprocessing.current_process",
            return_value=SimpleNamespace(daemon=True),
        ):
            downloader._extract_executor(2).shutdown()

        assert downloader.notify.called
        assert "thread pool" in downloader.notify.call_args[0][0]

    def test_fallback_is_logged_at_debug_not_shown_to_the_user(self):
        """Only `info` reaches the job's progress feed. This message named a
        daemonic process that "cannot start worker processes", which read as a
        failure mid-run even though the fallback is expected under Celery
        prefork and the run succeeds."""
        downloader = _downloader()
        with patch(
            "src.pipeline.downloader.multiprocessing.current_process",
            return_value=SimpleNamespace(daemon=True),
        ):
            downloader._extract_executor(2).shutdown()

        assert downloader.notify.call_args.kwargs.get("level") == "debug"


def _extract_in_daemonic_child(queue):
    """Runs in a daemonic child, as a Celery prefork task does."""
    try:
        downloader = _downloader()
        with downloader._extract_executor(2) as executor:
            futures = [executor.submit(DocumentDownloader._safe_extract, i, "http://x", HTML) for i in range(2)]
            results = [f.result() for f in futures]
        queue.put(("ok", [status for _, _, status in results]))
    except Exception as e:  # pragma: no cover - only on regression
        queue.put(("raised", f"{type(e).__name__}: {e}"))


class TestExtractionInsideADaemonicProcess:
    def test_extraction_runs_without_spawning_children(self):
        queue = multiprocessing.Queue()
        child = multiprocessing.Process(target=_extract_in_daemonic_child, args=(queue,))
        child.daemon = True
        child.start()
        child.join(timeout=60)

        outcome, detail = queue.get(timeout=10)
        assert outcome == "ok", f"extraction failed inside a daemonic process: {detail}"
        assert detail == ["Success", "Success"]
