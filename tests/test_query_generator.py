# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""QueryGenerator behaviour when the LLM returns nothing.

This is the first pipeline step, so a bad key or a wrong model name surfaces
here -- it used to be an `AttributeError: 'NoneType' has no attribute
'splitlines'` from inside split_queries."""
from types import SimpleNamespace

import pytest

from src.pipeline.query_generator import QueryGenerator


@pytest.fixture
def qg_settings():
    """Minimal settings for QueryGenerator: one template, one param set."""
    return SimpleNamespace(
        prompt_templates={"query": "Generate queries for: {input}"},
        generation_params={"query": {"temperature": 0.3, "max_tokens": 512}},
    )


class TestNoLLMResponse:
    """#2 -- split_queries(None) raised AttributeError on the first pipeline step."""

    class _NullLLM:
        def chat_sync(self, prompts, params=None, **kw):
            return [None] * len(prompts)

    class _EmptyLLM:
        def chat_sync(self, prompts, params=None, **kw):
            return []

    def _qg(self, llm, settings):
        return QueryGenerator(llm, settings, lambda m, level="info": None)

    def test_none_response_raises_actionable_error(self, qg_settings):
        qg = self._qg(self._NullLLM(), qg_settings)
        with pytest.raises(RuntimeError, match="LLM_MODEL_NAME"):
            qg.generate_queries("x", mode="query", template_key="query")

    def test_empty_response_list_raises_too(self, qg_settings):
        qg = self._qg(self._EmptyLLM(), qg_settings)
        with pytest.raises(RuntimeError):
            qg.generate_queries("x", mode="query", template_key="query")

    def test_not_attribute_error(self, qg_settings):
        """The old failure mode, pinned so it cannot come back."""
        qg = self._qg(self._NullLLM(), qg_settings)
        with pytest.raises(Exception) as exc:
            qg.generate_queries("x", mode="query", template_key="query")
        assert not isinstance(exc.value, AttributeError)
