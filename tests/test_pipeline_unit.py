import pytest
import json
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace
from src.pipeline.pipeline import SearchPipeline


@pytest.fixture
def pipeline_settings(tmp_path):
    return SimpleNamespace(
        results_dir=str(tmp_path),
        llm_model_name="test/model",
        llm_base_url="http://fake/v1",
        llm_api_key="fake-key",
        llm_extra_headers={},
        google_api_key="fake-google",
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
            "topic": "Break down topic: {input} Context: {context}",
            "expand": "Expand: {input} Context: {context}",
            "keyword": "Keywords for: {input}",
        },
        policy_dir="src/processing/crawl_policy",
        allowed_path=Path("src/processing/crawl_policy/allowed.txt"),
        not_allowed_path=Path("src/processing/crawl_policy/not_allowed.txt"),
        reasoning_path=Path("src/processing/crawl_policy/reasoning.jsonl"),
        error_log_path=Path("src/processing/crawl_policy/malformed_lines.log"),
    )


@pytest.fixture
def pipeline(pipeline_settings):
    with patch("src.pipeline.pipeline.LLMClient") as mock_llm, \
         patch("src.pipeline.pipeline.GoogleSearchClient") as mock_google, \
         patch("src.pipeline.pipeline.TavilySearchClient"):
        mock_llm_instance = MagicMock()
        mock_llm_instance.chat_sync = MagicMock(return_value=['+ "generated query"'])
        mock_llm.return_value = mock_llm_instance
        mock_google_instance = MagicMock()
        mock_google.return_value = mock_google_instance

        user_config = {
            "mode": "query",
            "input": "test topic",
            "output_folder_name": "test_output",
            "perform_search": False,
        }
        p = SearchPipeline(user_config=user_config, settings=pipeline_settings)
        return p


class TestPipelineInit:
    def test_creates_output_folder(self, pipeline):
        assert pipeline.output_folder.exists()

    def test_stores_mode_and_input(self, pipeline):
        assert pipeline.mode == "query"
        assert pipeline.input == "test topic"

    def test_records_a_storage_prefix_without_uploads(self, pipeline):
        """The API addresses a run's files by this prefix, so it has to point
        somewhere even when storage_upload is off -- otherwise the file listing
        and viewing endpoints report every output as missing."""
        assert pipeline.storage_upload_prefix == str(pipeline.output_folder)

    def test_storage_prefix_resolves_through_the_local_backend(self, pipeline):
        from src.storage.local import LocalStorageBackend

        backend = LocalStorageBackend()
        prefix = pipeline.storage_upload_prefix

        info = backend.get_file_info(f"{prefix}/run_config.json")
        assert info is not None and info["size_bytes"] > 0

    def test_saves_run_config(self, pipeline):
        config_path = pipeline.output_folder / "run_config.json"
        assert config_path.exists()
        with open(config_path) as f:
            config = json.load(f)
        assert config["mode"] == "query"
        assert config["input"] == "test topic"


class TestFormatPrompt:
    def test_query_template(self, pipeline):
        result = pipeline.format_prompt("query", "machine learning")
        assert "machine learning" in result

    def test_topic_template_with_context(self, pipeline):
        result = pipeline.format_prompt("topic", "algebra", context=["math", "algebra"])
        assert "algebra" in result
        assert "math" in result

    def test_expand_template_with_context(self, pipeline):
        result = pipeline.format_prompt("expand", "calculus", context=["math", "calculus"])
        assert "calculus" in result

    def test_invalid_template_key(self, pipeline):
        with pytest.raises(ValueError, match="Unsupported"):
            pipeline.format_prompt("nonexistent", "test")


class TestGenerateQueries:
    def test_calls_llm_and_parses(self, pipeline):
        pipeline.llm.chat_sync = MagicMock(return_value=['+ "query one"\n+ "query two"'])
        queries = pipeline.generate_queries("test topic")
        assert queries == ["query one", "query two"]

    def test_empty_response(self, pipeline):
        pipeline.llm.chat_sync = MagicMock(return_value=["no valid format here"])
        queries = pipeline.generate_queries("test")
        assert queries == []


class TestGenerateQueriesBatch:
    def test_batch_generation(self, pipeline):
        from src.processing.topic_tree import TopicNode

        root = TopicNode("math")
        child1 = root.add_child("algebra")
        child2 = root.add_child("geometry")

        pipeline.llm.chat_sync = MagicMock(return_value=[
            '+ "algebra query 1"\n+ "algebra query 2"',
            '+ "geometry query 1"',
        ])
        results = pipeline.generate_queries_batch([child1, child2], "expand")
        assert len(results) == 2
        assert results[0][0] == child1
        assert "algebra query 1" in results[0][1]


class TestSaveMetrics:
    def test_saves_to_file(self, pipeline):
        metrics = {"generated_queries": 10, "elapsed_times": {"step1": 1.5}}
        pipeline.save_metrics(metrics)

        metrics_path = pipeline.output_folder / "metrics.json"
        assert metrics_path.exists()
        with open(metrics_path) as f:
            saved = json.load(f)
        assert saved["generated_queries"] == 10

    def test_merges_with_existing(self, pipeline):
        first = {"a": 1}
        pipeline.save_metrics(first)

        second = {"b": 2}
        pipeline.save_metrics(second)

        metrics_path = pipeline.output_folder / "metrics.json"
        with open(metrics_path) as f:
            saved = json.load(f)
        assert saved["a"] == 1
        assert saved["b"] == 2


class TestComputeAnnotationMetrics:
    def test_all_columns_present(self, pipeline):
        df = pd.DataFrame({
            "relevancy": [True, False, True],
            "crawlable": [True, True, False],
        })
        metrics = pipeline.compute_annotation_metrics(df, base_metrics={"raw": 3})
        assert metrics["relevant_results"] == 2
        assert metrics["crawlable_results"] == 2
        assert metrics["relevant_and_crawlable"] == 1

    def test_only_relevancy(self, pipeline):
        df = pd.DataFrame({
            "relevancy": [True, False, True],
        })
        metrics = pipeline.compute_annotation_metrics(df, base_metrics={})
        assert metrics["relevant_results"] == 2
        assert "crawlable_results" not in metrics

    def test_only_crawlable(self, pipeline):
        df = pd.DataFrame({
            "crawlable": [True, False, True],
        })
        metrics = pipeline.compute_annotation_metrics(df, base_metrics={})
        assert metrics["crawlable_results"] == 2
        assert "relevant_results" not in metrics


class TestSaveResults:
    def test_saves_jsonl(self, pipeline):
        pipeline.output_format = "jsonl"
        results = [
            {"link": "http://a.com", "text": "hello"},
            {"link": "http://b.com", "text": "world"},
        ]
        pipeline.save_results(results)

        output_file = pipeline.output_folder / f"{pipeline.output_base}.jsonl"
        assert output_file.exists()
        with open(output_file) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_saves_parquet(self, pipeline):
        pipeline.output_format = "parquet"
        results = [
            {"link": "http://a.com", "text": "hello"},
            {"link": "http://b.com", "text": "world"},
        ]
        pipeline.save_results(results)

        output_file = pipeline.output_folder / f"{pipeline.output_base}.parquet"
        assert output_file.exists()


class TestPipelineRun:
    def test_query_mode_no_search(self, pipeline):
        pipeline.llm.chat_sync = MagicMock(return_value=['+ "generated query 1"\n+ "generated query 2"'])
        pipeline.run()

        metrics_path = pipeline.output_folder / "metrics.json"
        assert metrics_path.exists()
        with open(metrics_path) as f:
            metrics = json.load(f)
        assert "elapsed_times" in metrics
        assert "start_timestamp" in metrics


class TestRunFailureReporting:
    """A run that dies mid-way must not look like a successful one."""

    def test_run_reraises_the_failure(self, pipeline):
        pipeline.generate_queries = MagicMock(side_effect=RuntimeError("extraction exploded"))

        with pytest.raises(RuntimeError, match="extraction exploded"):
            pipeline.run()

    def test_failure_is_recorded_in_metrics(self, pipeline):
        pipeline.generate_queries = MagicMock(side_effect=RuntimeError("extraction exploded"))

        with pytest.raises(RuntimeError):
            pipeline.run()

        metrics = json.loads((pipeline.output_folder / "metrics.json").read_text())
        assert metrics["error"] == "extraction exploded"

    def test_finally_block_still_writes_timings(self, pipeline):
        """Whatever the run did manage to produce still gets recorded."""
        pipeline.generate_queries = MagicMock(side_effect=RuntimeError("extraction exploded"))

        with pytest.raises(RuntimeError):
            pipeline.run()

        metrics = json.loads((pipeline.output_folder / "metrics.json").read_text())
        assert "start_timestamp" in metrics and "end_timestamp" in metrics

    def test_failure_is_not_logged_as_completed(self, pipeline):
        messages = []
        pipeline.notify = lambda message, level="info": messages.append(message)
        pipeline.generate_queries = MagicMock(side_effect=RuntimeError("extraction exploded"))

        with pytest.raises(RuntimeError):
            pipeline.run()

        assert not any("run completed" in m for m in messages)
        assert any("run failed" in m for m in messages)
