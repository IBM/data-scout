"""Exception text must not reach clients unless DEBUG_ERRORS is set.

Error text in this codebase carries absolute filesystem paths, Redis URLs
including credentials, and raw S3/boto error bodies. Returning it verbatim was
deliberate -- it is how the real cause got past the CORS layer into the UI -- so
it is gated rather than removed, and the cause is always logged.
"""
import logging
from unittest.mock import MagicMock, patch

import pytest

from src.api import routes
from src.api.routes import _safe_detail

# What a real failure here looks like: a path and a credentialed Redis URL.
SECRET = "redis://:sup3rs3cret@10.0.0.5:6379/0"
BOOM = RuntimeError(f"connection to {SECRET} failed from /Users/someone/data-scout/src")


def _detail(debug):
    with patch.object(routes._config, "debug_errors", debug):
        try:
            raise BOOM
        except RuntimeError as e:
            return _safe_detail("Failed to fetch log file", e)


class TestDefaultWithholdsTheCause:
    def test_credentials_do_not_reach_the_client(self):
        detail = _detail(False)

        assert SECRET not in detail
        assert "sup3rs3cret" not in detail

    def test_filesystem_paths_do_not_reach_the_client(self):
        assert "/Users/someone" not in _detail(False)

    def test_the_client_still_learns_which_operation_failed(self):
        """A bare "Internal server error" would make the UI useless for triage."""
        detail = _detail(False)

        assert "Failed to fetch log file" in detail
        assert "server log" in detail


class TestDebugFlagRestoresIt:
    def test_cause_is_included_when_debug_errors_is_set(self):
        detail = _detail(True)

        assert SECRET in detail
        assert "Failed to fetch log file" in detail


@pytest.fixture
def pipeline_log_records():
    """Capture on the logger itself rather than through caplog.

    setup_logger sets `propagate = False` on "pipeline_logger", so once any other
    test has configured it, caplog's root handler sees nothing and these
    assertions would pass or fail depending on test order.
    """
    logger = logging.getLogger("pipeline_logger")
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture(level=logging.DEBUG)
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


class TestCauseIsAlwaysLogged:
    """Gating the response must not cost the operator the diagnosis -- none of
    these handlers logged at all before this change."""

    @pytest.mark.parametrize("debug", [False, True])
    def test_traceback_is_logged_either_way(self, debug, pipeline_log_records):
        _detail(debug)

        assert any(r.exc_info for r in pipeline_log_records), "no traceback was logged"
        logged = " ".join(
            r.getMessage() + str(r.exc_info[1]) for r in pipeline_log_records if r.exc_info
        )
        assert SECRET in logged, "the cause is missing from the log"


class TestDefaultIsOff:
    def test_debug_errors_defaults_to_false(self):
        """A deployment that never sets DEBUG_ERRORS must not leak."""
        from src.config import SearchConfig

        assert SearchConfig(_env_file=None).debug_errors is False
