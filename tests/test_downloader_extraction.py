# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""Extraction runs in a child process so a native parser crash is survivable.

trafilatura parses via libxml2, and a malformed document can segfault it. When
extraction ran in a thread pool inside the Celery worker, that SIGSEGV killed the
worker mid-run and discarded every document already downloaded -- twice in one
afternoon on 2026-08-28, each time after ~190 documents had been fetched.
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline import downloader as downloader_module
from src.pipeline.downloader import DocumentDownloader, _extract_popen_kwargs
from tests.crashing_extract_worker import CRASH_MARKER

HTML = ("<html><body><article>"
        + "<p>Some body text long enough for trafilatura to keep it.</p>" * 5
        + "</article></body></html>").encode()


def _downloader(workers=2):
    settings = SimpleNamespace(max_download_workers=2, max_extract_workers=workers)
    return DocumentDownloader(settings, MagicMock())


class TestExtractionWorks:
    """The subprocess path must still extract normally."""

    def test_real_documents_are_extracted(self):
        dl = _downloader()
        texts, statuses = dl._extract_documents(["http://a", "http://b"], [HTML, HTML], 2)

        assert statuses == ["Success", "Success"]
        assert all("body text" in t for t in texts)

    def test_missing_content_is_not_an_error(self):
        dl = _downloader()
        texts, statuses = dl._extract_documents(["http://a"], [None], 1)

        assert texts == [""]
        assert statuses == ["Success: No content to extract"]

    def test_every_document_gets_a_result(self):
        dl = _downloader()
        contents = [HTML, None, HTML, HTML, None]
        texts, statuses = dl._extract_documents([f"http://{i}" for i in range(5)], contents, 3)

        assert len(texts) == 5 and len(statuses) == 5
        assert all(s for s in statuses), "a document was left with no status"


class TestCrashIsSurvived:
    """The point of the change: one poisoned document must not end the run."""

    @pytest.fixture
    def crashing_worker(self):
        with patch.object(downloader_module, "EXTRACT_WORKER_MODULE",
                          "tests.crashing_extract_worker"):
            yield

    def test_a_segfault_does_not_take_down_the_caller(self, crashing_worker):
        dl = _downloader()
        texts, statuses = dl._extract_documents(["http://boom"], [CRASH_MARKER], 1)

        # We are still here, which is the assertion that matters.
        assert statuses == ["Error: extraction crashed the parser"]
        assert texts == [""]

    def test_the_other_documents_in_the_batch_still_extract(self, crashing_worker):
        dl = _downloader(workers=1)  # one chunk, so all 4 share the crashing child
        links = ["http://a", "http://boom", "http://c", "http://d"]
        contents = [HTML, CRASH_MARKER, HTML, HTML]

        texts, statuses = dl._extract_documents(links, contents, 1)

        assert statuses[1] == "Error: extraction crashed the parser"
        assert [statuses[i] for i in (0, 2, 3)] == ["Success"] * 3, \
            "documents either side of the crash were lost"

    def test_the_offending_url_is_reported(self, crashing_worker):
        """Without this the run log goes silent at 'Extracting text...' and the
        document that killed the parser can never be identified."""
        dl = _downloader(workers=1)
        dl._extract_documents(["http://a", "http://boom"], [HTML, CRASH_MARKER], 1)

        logged = " ".join(str(c) for c in dl.notify.call_args_list)
        assert "http://boom" in logged

    def test_two_crashes_in_one_batch_both_get_skipped(self, crashing_worker):
        dl = _downloader(workers=1)
        links = ["http://a", "http://boom1", "http://c", "http://boom2"]
        contents = [HTML, CRASH_MARKER, HTML, CRASH_MARKER]

        texts, statuses = dl._extract_documents(links, contents, 1)

        crashed = [i for i, s in enumerate(statuses) if "crashed" in s]
        assert crashed == [1, 3]
        assert [statuses[i] for i in (0, 2)] == ["Success"] * 2


class TestInterruptIsNotWeakened:
    """The interrupt endpoint revokes with SIGKILL, which the worker cannot catch,
    so it never gets to clean up. Without PR_SET_PDEATHSIG an extraction child is
    reparented and keeps running after the user pressed interrupt."""

    def test_pdeathsig_is_requested_on_linux(self):
        with patch.object(sys, "platform", "linux"):
            assert "preexec_fn" in _extract_popen_kwargs()

    def test_no_preexec_on_macos(self):
        """There is no PDEATHSIG equivalent on darwin; must not crash local dev."""
        with patch.object(sys, "platform", "darwin"):
            assert _extract_popen_kwargs() == {}
