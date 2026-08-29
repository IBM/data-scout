# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from src.pipeline.pipeline import SearchPipeline

def test_metrics_saved(tmp_path, settings):
    user_config = {
        "mode": "query",
        "input": "water pollution",
        "output_folder_name": "test_metrics"
    }

    pipeline = SearchPipeline(user_config=user_config, settings=settings)
    dummy_metrics = {
        "generated_queries": 10,
        "elapsed_times": {
            "initial_query_generation": 0.5
        }
    }

    pipeline.save_metrics(dummy_metrics)

    metrics_path = pipeline.output_folder / "metrics.json"
    assert metrics_path.exists(), "metrics.json was not saved."

    with open(metrics_path, "r") as f:
        data = json.load(f)

    assert "generated_queries" in data
    assert data["generated_queries"] == 10
    assert "elapsed_times" in data
