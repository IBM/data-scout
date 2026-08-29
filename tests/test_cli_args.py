# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""run.py argument parsing: choices that were unreachable and dead branches."""
from pathlib import Path





class TestAnnotationChoices:
    def test_cli_offers_sub_categorization(self):
        """models.py accepts it and annotations.py implements it, but the CLI
        choices omitted it, so it was unreachable from the command line."""
        source = Path("run.py").read_text()

        assert '"sub_categorization"' in source


class TestDeadBranches:
    def test_unreachable_search_branch_is_gone(self):
        """`mode != "topic"` already errors for "search", so a second branch for
        it could never run."""
        source = Path("run.py").read_text()

        assert "--recursion_depth is not allowed when --mode is 'search'" not in source
