# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""The crawl policy is a runtime cache and is not committed, so a fresh
checkout has neither the files nor their directory. Everything must work from
that state."""

import json
import pandas as pd
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.processing.annotations import Annotations, AnnotationType
from src.processing import utils


@pytest.fixture
def policy_dir(tmp_path):
    """A path whose directory does not exist yet, as on a fresh clone."""
    return tmp_path / "crawl_policy"


@pytest.fixture
def settings(policy_dir):
    return SimpleNamespace(
        policy_dir=str(policy_dir),
        allowed_path=policy_dir / "allowed.txt",
        not_allowed_path=policy_dir / "not_allowed.txt",
        reasoning_path=policy_dir / "reasoning.jsonl",
        error_log_path=policy_dir / "malformed_lines.log",
        generation_params={"crawlable": {"temperature": 0, "max_tokens": 64}},
        prompt_templates={"crawlable_annotation": "Classify: {input}"},
    )


@pytest.fixture
def df():
    return pd.DataFrame({"domain": ["example.com", "blocked.test"]})


def _llm_returning(records):
    llm = MagicMock()
    llm.chat_sync = MagicMock(return_value=["\n".join(json.dumps(r) for r in records)])
    return llm


class TestColdCache:
    def test_missing_files_do_not_raise(self, settings, df):
        """Previously this raised "Failed to load crawl policy: ... does not
        exist", so the donotcrawl annotation failed on every fresh checkout."""
        llm = _llm_returning([
            {"domain": "example.com", "status": "ok", "reason": "fine"},
            {"domain": "blocked.test", "status": "no", "reason": "disallowed"},
        ])
        annotations = Annotations(settings, llm=llm)

        result = annotations.apply(df, [AnnotationType.DONOTCRAWL])

        assert "crawlable" in result.columns

    def test_every_domain_is_treated_as_unlisted(self, settings, df):
        llm = _llm_returning([
            {"domain": "example.com", "status": "ok", "reason": "fine"},
            {"domain": "blocked.test", "status": "no", "reason": "disallowed"},
        ])
        annotations = Annotations(settings, llm=llm)

        annotations.apply(df, [AnnotationType.DONOTCRAWL])

        assert llm.chat_sync.called
        prompt = llm.chat_sync.call_args[0][0][0]
        assert "example.com" in prompt and "blocked.test" in prompt

    def test_cache_files_and_directory_are_created(self, settings, policy_dir, df):
        llm = _llm_returning([
            {"domain": "example.com", "status": "ok", "reason": "fine"},
            {"domain": "blocked.test", "status": "no", "reason": "disallowed"},
        ])
        annotations = Annotations(settings, llm=llm)

        annotations.apply(df, [AnnotationType.DONOTCRAWL])

        assert policy_dir.is_dir(), "the cache directory was not created"
        assert settings.allowed_path.read_text().strip() == "example.com"
        assert settings.not_allowed_path.read_text().strip() == "blocked.test"
        assert "disallowed" in settings.reasoning_path.read_text()


class TestAppendCreatesParents:
    def test_append_into_a_missing_directory(self, tmp_path):
        """append_lines_to_file used to touch() without creating the parent."""
        target = tmp_path / "nested" / "deeper" / "cache.txt"

        utils.append_lines_to_file(target, ["example.com"])

        assert target.read_text() == "example.com\n"
