# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""The download size cap must be enforced while reading, not after.

`response.content` materialises the whole body first, so checking its length only
discarded an oversized response once it was already in memory. With
MAX_DOWNLOAD_WORKERS fetching search results in parallel, one very large document
was enough to exhaust memory.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.processing import text_extraction
from src.processing.text_extraction import MAX_DOWNLOAD_BYTES, download


def _response(chunks, headers=None, url="https://example.com/doc"):
    response = MagicMock()
    response.url = url
    response.headers = headers or {}
    response.iter_content.return_value = iter(chunks)
    # content must never be touched: reading it defeats the whole fix
    type(response).content = property(
        lambda self: pytest.fail("download() read response.content instead of streaming")
    )
    return response


@pytest.fixture
def public_host():
    with patch.object(text_extraction, "_is_private_ip", return_value=False):
        yield


class TestStreamingCap:
    def test_small_response_is_returned_whole(self, public_host):
        with patch.object(text_extraction.requests, "get", return_value=_response([b"abc", b"def"])):
            assert download("https://example.com/doc") == b"abcdef"

    def test_request_is_streamed(self, public_host):
        with patch.object(text_extraction.requests, "get",
                          return_value=_response([b"x"])) as get:
            download("https://example.com/doc")

        assert get.call_args.kwargs.get("stream") is True

    def test_oversized_body_is_rejected(self, public_host):
        chunk = b"x" * (1024 * 1024)
        chunks = [chunk] * (MAX_DOWNLOAD_BYTES // len(chunk) + 2)

        with patch.object(text_extraction.requests, "get", return_value=_response(chunks)):
            assert download("https://example.com/doc") is None

    def test_stops_reading_once_over_the_cap(self, public_host):
        """It must abort mid-stream, not consume the whole body first."""
        consumed = []

        def chunks():
            for _ in range(1000):
                consumed.append(1)
                yield b"y" * (1024 * 1024)

        response = _response(chunks())
        with patch.object(text_extraction.requests, "get", return_value=response):
            assert download("https://example.com/doc") is None

        assert len(consumed) < 1000, "the entire body was read before aborting"
        assert sum(consumed) * 1024 * 1024 <= MAX_DOWNLOAD_BYTES + 1024 * 1024

    def test_response_is_closed(self, public_host):
        response = _response([b"a"])
        with patch.object(text_extraction.requests, "get", return_value=response):
            download("https://example.com/doc")

        response.close.assert_called_once()


class TestContentLengthShortCircuit:
    def test_oversized_content_length_is_rejected_without_reading(self, public_host):
        response = _response([], headers={"Content-Length": str(MAX_DOWNLOAD_BYTES + 1)})

        with patch.object(text_extraction.requests, "get", return_value=response):
            assert download("https://example.com/doc") is None

        response.iter_content.assert_not_called()

    def test_missing_content_length_still_streams(self, public_host):
        with patch.object(text_extraction.requests, "get", return_value=_response([b"ok"])):
            assert download("https://example.com/doc") == b"ok"

    def test_absurd_content_length_header_is_not_trusted_alone(self, public_host):
        """A lying header must not let a big body through: the running count is
        still the real guard."""
        chunk = b"z" * (1024 * 1024)
        chunks = [chunk] * (MAX_DOWNLOAD_BYTES // len(chunk) + 2)
        response = _response(chunks, headers={"Content-Length": "10"})

        with patch.object(text_extraction.requests, "get", return_value=response):
            assert download("https://example.com/doc") is None


class TestRedirectCheckPrecedesTheBody:
    def test_redirect_to_private_ip_is_blocked_before_reading(self):
        response = _response([b"secret"], url="http://169.254.169.254/latest/meta-data")

        with patch.object(text_extraction, "_is_private_ip", side_effect=[False, True]), \
             patch.object(text_extraction.requests, "get", return_value=response):
            assert download("https://example.com/redirector") is None

        response.iter_content.assert_not_called()
