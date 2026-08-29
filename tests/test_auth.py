"""API key verification -- the security boundary, previously untested.

Both helpers exist because `APIKeyHeader` and `Request` are HTTP-only and cannot
be dependencies on a WebSocket route, so the two paths are separate code and can
drift apart. These tests pin both.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, WebSocketException

from src.api.auth import verify_api_key, verify_api_key_ws

KEY = "s3cret-key"


def _request(configured_key):
    request = MagicMock()
    request.app.state.api_key = configured_key
    return request


def _connection(configured_key, sent_key):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(api_key=configured_key)),
        headers={"X-API-Key": sent_key} if sent_key is not None else {},
    )


class TestHttpKeyVerification:
    def test_correct_key_is_accepted(self):
        assert verify_api_key(_request(KEY), api_key=KEY) is None

    def test_wrong_key_is_rejected_with_401(self):
        with pytest.raises(HTTPException) as excinfo:
            verify_api_key(_request(KEY), api_key="wrong")

        assert excinfo.value.status_code == 401

    def test_missing_key_is_rejected(self):
        """auto_error=False means a missing header arrives as None rather than
        raising, so this has to be handled here."""
        with pytest.raises(HTTPException) as excinfo:
            verify_api_key(_request(KEY), api_key=None)

        assert excinfo.value.status_code == 401

    def test_empty_key_is_rejected_when_one_is_configured(self):
        with pytest.raises(HTTPException):
            verify_api_key(_request(KEY), api_key="")

    def test_auth_is_open_when_no_key_is_configured(self):
        """API_KEY defaults to empty, which deliberately disables auth."""
        assert verify_api_key(_request(""), api_key=None) is None

    def test_a_key_is_ignored_when_none_is_configured(self):
        assert verify_api_key(_request(""), api_key="anything") is None

    def test_comparison_is_exact(self):
        for candidate in (KEY + " ", " " + KEY, KEY.upper(), KEY[:-1]):
            with pytest.raises(HTTPException):
                verify_api_key(_request(KEY), api_key=candidate)


class TestWebSocketKeyVerification:
    def test_correct_key_is_accepted(self):
        assert verify_api_key_ws(_connection(KEY, KEY)) is None

    def test_wrong_key_closes_with_policy_violation(self):
        """1008 is what the frontend keys off to stop retrying forever."""
        with pytest.raises(WebSocketException) as excinfo:
            verify_api_key_ws(_connection(KEY, "wrong"))

        assert excinfo.value.code == 1008

    def test_missing_header_is_rejected(self):
        with pytest.raises(WebSocketException):
            verify_api_key_ws(_connection(KEY, None))

    def test_open_when_no_key_is_configured(self):
        assert verify_api_key_ws(_connection("", None)) is None

    def test_both_paths_agree_on_acceptance(self):
        """The HTTP and WebSocket checks are separate code; they must not drift."""
        for configured, sent in (("", None), ("", "x"), (KEY, KEY)):
            http_ok = ws_ok = True
            try:
                verify_api_key(_request(configured), api_key=sent)
            except HTTPException:
                http_ok = False
            try:
                verify_api_key_ws(_connection(configured, sent))
            except WebSocketException:
                ws_ok = False
            assert http_ok == ws_ok, f"disagreement for configured={configured!r} sent={sent!r}"
