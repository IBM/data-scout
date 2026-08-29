# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""The run log handler must be bounded."""
import inspect





class TestRunLogIsBounded:
    def test_run_log_handler_rotates(self):
        """A plain FileHandler appended every run to one file with no bound."""
        import src.logging_config as lc

        assert "RotatingFileHandler" in inspect.getsource(lc.setup_logger)
