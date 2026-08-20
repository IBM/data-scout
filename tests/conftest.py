import pytest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture(autouse=True)
def _patch_external_clients():
    """Patch LLM and search clients globally so pipeline tests never hit real services."""
    with patch("src.pipeline.pipeline.LLMClient") as mock_llm, \
         patch("src.pipeline.pipeline.GoogleSearchClient") as mock_google, \
         patch("src.pipeline.pipeline.TavilySearchClient") as mock_tavily:
        mock_llm_instance = MagicMock()
        mock_llm_instance.chat = AsyncMock(return_value=['+ "generated query"'])
        mock_llm_instance.chat_sync = MagicMock(return_value=['+ "generated query"'])
        mock_llm.return_value = mock_llm_instance
        mock_google.return_value = MagicMock()
        mock_tavily.return_value = MagicMock()
        yield


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(
        results_dir=str(tmp_path),
        llm_model_name="test-model",
        llm_base_url="http://fake-endpoint/v1",
        llm_api_key="fake-key",
        llm_extra_headers={},
        google_api_key="fake-api",
        cx_key="fake-cx",
        tavily_api_key="fake-tavily",
        search_provider="google",
        tavily_search_depth="basic",
        excluded_sites=["reddit.com", "medium.com"],
        storage_upload=False,
        storage_upload_dir="fake-storage-dir",
        storage_backend="local",
        log_file="pipeline.log",
        metrics_file="metrics.json",
        topics_file="topics.jsonl",
        max_download_workers=2,
        max_extract_workers=2,
        sub_categories=[],
        generation_params={
            "query": {"temperature": 0.3, "max_tokens": 512},
            "topic": {"temperature": 0.3, "max_tokens": 512},
            "keyword": {"temperature": 0.3, "max_tokens": 512},
            "search": {"temperature": 0.3, "max_tokens": 512},
            "relevancy": {"temperature": 0, "max_tokens": 512},
            "crawlable": {"temperature": 0, "max_tokens": 512},
            "sub_categorization": {"temperature": 0, "max_tokens": 512},
        },
        prompt_templates={
            "query": "Generate queries for: {input}",
            "topic": "Generate topics for: {input} Context: {context}",
            "expand": "Expand this for search: {input} Context: {context}",
            "keyword": "Keywords for: {input}",
        },
        policy_dir="src/processing/crawl_policy",
        allowed_path=Path("src/processing/crawl_policy/allowed.txt"),
        not_allowed_path=Path("src/processing/crawl_policy/not_allowed.txt"),
        reasoning_path=Path("src/processing/crawl_policy/reasoning.jsonl"),
        error_log_path=Path("src/processing/crawl_policy/malformed_lines.log"),
    )
