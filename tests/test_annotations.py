# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import Mock
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from pathlib import Path
from src.processing.annotations import Annotations, AnnotationType


@pytest.fixture
def settings(tmp_path):
    allowed_path = tmp_path / "allowed.txt"
    not_allowed_path = tmp_path / "not_allowed.txt"
    reasoning_path = tmp_path / "reasoning.jsonl"
    error_log_path = tmp_path / "malformed.log"

    allowed_path.write_text("example\ngoodsite\n")
    not_allowed_path.write_text("spam\nadult\n")

    return SimpleNamespace(
        allowed_path=allowed_path,
        not_allowed_path=not_allowed_path,
        reasoning_path=reasoning_path,
        error_log_path=error_log_path,
        sub_categories=["Algebra", "Calculus", "Geometry"],
        prompt_templates={
            "crawlable_annotation": "Classify: {input}",
            "relevancy_annotation": "Is this relevant? Topic: {input} Text: {text}",
            "sub_category_annotation": "Classify sub-category. Topic: {input} Text: {text} Categories: {sub_categories}",
        },
        generation_params={
            "crawlable": {"temperature": 0},
            "relevancy": {"temperature": 0},
            "sub_categorization": {"temperature": 0},
        },
    )


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    return llm


class TestApplyDonotcrawl:
    def test_classifies_known_allowed(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://example.com/page"],
            "domain": ["example"],
        })
        ann = Annotations(settings=settings, llm=mock_llm, input="test")
        result = ann._apply_donotcrawl(df)
        assert result["crawlable"].iloc[0] == True

    def test_classifies_known_not_allowed(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://spam.com/page"],
            "domain": ["spam"],
        })
        ann = Annotations(settings=settings, llm=mock_llm, input="test")
        result = ann._apply_donotcrawl(df)
        assert result["crawlable"].iloc[0] == False

    def test_unlisted_triggers_llm(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://newsite.com/page"],
            "domain": ["newsite"],
        })

        mock_llm.chat_sync = MagicMock(
            return_value=['{"domain": "newsite", "reason": "seems ok", "status": "OK"}']
        )

        ann = Annotations(settings=settings, llm=mock_llm, input="test")
        result = ann._apply_donotcrawl(df)
        assert result["crawlable"].iloc[0] is True

    def test_unlisted_not_ok_classified_false(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://badnew.com/page"],
            "domain": ["badnew"],
        })

        mock_llm.chat_sync = MagicMock(
            return_value=['{"domain": "badnew", "reason": "adult content", "status": "Adult"}']
        )

        ann = Annotations(settings=settings, llm=mock_llm, input="test")
        result = ann._apply_donotcrawl(df)
        assert result["crawlable"].iloc[0] is False


class TestApplyRelevancy:
    def test_marks_relevant(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://example.com"],
            "extracted_text": ["This is about machine learning and neural networks."],
        })

        mock_llm.chat_sync = MagicMock(return_value=['{"relevant": "Yes"}'])

        ann = Annotations(settings=settings, llm=mock_llm, input="machine learning")
        result = ann._apply_relevancy(df)
        assert result["relevancy"].iloc[0] == True

    def test_marks_not_relevant(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://example.com"],
            "extracted_text": ["This is about cooking recipes."],
        })

        mock_llm.chat_sync = MagicMock(return_value=['{"relevant": "No"}'])

        ann = Annotations(settings=settings, llm=mock_llm, input="quantum physics")
        result = ann._apply_relevancy(df)
        assert result["relevancy"].iloc[0] == False

    def test_requires_llm(self, settings):
        df = pd.DataFrame({"extracted_text": ["text"]})
        ann = Annotations(settings=settings, llm=None, input="test")
        with pytest.raises(ValueError, match="LLM instance required"):
            ann._apply_relevancy(df)

    def test_requires_input(self, settings, mock_llm):
        df = pd.DataFrame({"extracted_text": ["text"]})
        ann = Annotations(settings=settings, llm=mock_llm, input=None)
        with pytest.raises(ValueError, match="Input must be provided"):
            ann._apply_relevancy(df)

    def test_truncates_text_to_1024(self, settings, mock_llm):
        long_text = "x" * 2000
        df = pd.DataFrame({
            "link": ["http://example.com"],
            "extracted_text": [long_text],
        })

        mock_llm.chat_sync = MagicMock(return_value=['{"relevant": "Yes"}'])

        ann = Annotations(settings=settings, llm=mock_llm, input="test")
        ann._apply_relevancy(df)

        prompts_arg = mock_llm.chat_sync.call_args[0][0]
        assert long_text not in prompts_arg[0]
        assert len(prompts_arg[0]) < 1024 + 200


class TestApplySubCategorization:
    def test_assigns_category(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://example.com"],
            "extracted_text": ["Integration and differentiation methods."],
        })

        mock_llm.chat_sync = MagicMock(return_value=['{"sub_category": "Calculus"}'])

        ann = Annotations(settings=settings, llm=mock_llm, input="mathematics")
        result = ann._apply_sub_categorization(df)
        assert result["sub_category"].iloc[0] == "Calculus"

    def test_none_category(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://example.com"],
            "extracted_text": ["Unrelated content"],
        })

        mock_llm.chat_sync = MagicMock(return_value=['{"sub_category": "None"}'])

        ann = Annotations(settings=settings, llm=mock_llm, input="math")
        result = ann._apply_sub_categorization(df)
        assert result["sub_category"].iloc[0] is None


class TestApplyChaining:
    def test_multiple_annotations(self, settings, mock_llm):
        df = pd.DataFrame({
            "link": ["http://example.com/page", "http://spam.com/page"],
            "domain": ["example", "spam"],
            "extracted_text": ["relevant text", "spam text"],
        })

        mock_llm.chat_sync = MagicMock(
            side_effect=lambda prompts, **kwargs: ['{"relevant": "Yes"}'] * len(prompts)
        )

        ann = Annotations(settings=settings, llm=mock_llm, input="test topic")
        result = ann.apply(df, annotations=[AnnotationType.DONOTCRAWL, AnnotationType.RELEVANCY])

        assert "crawlable" in result.columns
        assert "relevancy" in result.columns
        assert result["crawlable"].iloc[0] == True
        assert result["crawlable"].iloc[1] == False
        assert result["relevancy"].iloc[0] == True

    def test_unknown_annotation_raises(self, settings, mock_llm):
        df = pd.DataFrame({"link": ["a"]})
        ann = Annotations(settings=settings, llm=mock_llm, input="test")
        with pytest.raises(ValueError, match="Unknown annotation"):
            ann.apply(df, annotations=["nonexistent"])


@pytest.fixture
def ann_settings(tmp_path):
    """Crawl-policy settings pointed at tmp_path so nothing touches the real cache."""
    return SimpleNamespace(
        allowed_path=tmp_path / "allowed.txt",
        not_allowed_path=tmp_path / "not_allowed.txt",
        reasoning_path=tmp_path / "reasoning.jsonl",
        error_log_path=tmp_path / "malformed.log",
        sub_categories=[],
        prompt_templates={"crawlable_annotation": "Classify: {input}"},
        generation_params={"crawlable": {"temperature": 0}},
    )


class TestPartialBatchResponses:
    """#5 -- an empty first batch discarded every other batch's classifications."""

    class _FirstBatchEmptyLLM:
        def chat_sync(self, prompts, params=None, **kw):
            good = '{"domain": "good", "status": "ok"}'
            return [None] + [good] * (len(prompts) - 1)

    def test_later_batches_survive_an_empty_first_batch(self, ann_settings, tmp_path):
        ann_settings.allowed_path = tmp_path / "allowed.txt"
        ann_settings.not_allowed_path = tmp_path / "not_allowed.txt"
        ann_settings.reasoning_path = tmp_path / "reasoning.jsonl"
        ann_settings.error_log_path = tmp_path / "malformed.log"

        # 10 unlisted domains -> batches of 5 -> 2 prompts, the first empty.
        df = pd.DataFrame({"domain": [f"d{i}" for i in range(10)]})
        ann = Annotations(settings=ann_settings, llm=self._FirstBatchEmptyLLM(), input="topic")
        out = ann.apply(df, annotations=[AnnotationType.DONOTCRAWL])

        assert (tmp_path / "allowed.txt").exists(), \
            "the surviving batch's classification was discarded"
        assert "good" in (tmp_path / "allowed.txt").read_text()
        assert "crawlable" in out.columns

    def test_all_batches_empty_still_returns_df(self, ann_settings, tmp_path):
        ann_settings.allowed_path = tmp_path / "allowed.txt"
        ann_settings.not_allowed_path = tmp_path / "not_allowed.txt"
        ann_settings.reasoning_path = tmp_path / "reasoning.jsonl"
        ann_settings.error_log_path = tmp_path / "malformed.log"

        class AllEmpty:
            def chat_sync(self, prompts, params=None, **kw):
                return [None] * len(prompts)

        df = pd.DataFrame({"domain": ["a", "b"]})
        ann = Annotations(settings=ann_settings, llm=AllEmpty(), input="t")
        out = ann.apply(df, annotations=[AnnotationType.DONOTCRAWL])
        assert len(out) == 2
        assert not (tmp_path / "allowed.txt").exists()
