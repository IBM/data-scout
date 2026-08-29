# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import pandas as pd
from src.pipeline.pipeline import SearchPipeline

def test_annotation_metrics_computation(settings):
    df = pd.DataFrame({
        "link": ["url1", "url2", "url3"],
        "relevancy": [True, False, True],
        "crawlable": [True, True, False]
    })

    pipeline = SearchPipeline(user_config={"output_folder_name": "dummy", "mode": "query", "input": "test"}, settings=settings)

    base = {"raw_results": 3}
    metrics = pipeline.compute_annotation_metrics(df, base_metrics=base)

    assert metrics["relevant_results"] == 2
    assert metrics["crawlable_results"] == 2
    assert metrics["relevant_and_crawlable"] == 1
