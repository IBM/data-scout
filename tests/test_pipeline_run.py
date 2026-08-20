from src.pipeline.pipeline import SearchPipeline
import json

def test_run_pipeline_saves_timing(monkeypatch, settings):
    user_config = {
        "mode": "query",
        "input": "test query",
        "output_folder_name": "test_timing",
        "perform_search": False
    }

    pipeline = SearchPipeline(user_config=user_config, settings=settings)

    # monkeypatching methods to avoid real LLM and API calls
    monkeypatch.setattr(pipeline, "generate_queries", lambda *args, **kwargs: ["query 1", "query 2"])

    pipeline.run()

    metrics_path = pipeline.output_folder / "metrics.json"
    assert metrics_path.exists()

    with open(metrics_path) as f:
        metrics = json.load(f)

    assert "elapsed_times" in metrics
    assert "initial_query_generation" in metrics["elapsed_times"]
    assert "start_timestamp" in metrics
    assert "end_timestamp" in metrics
