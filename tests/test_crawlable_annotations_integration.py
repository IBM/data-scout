# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import pandas as pd
from src.processing.annotations import Annotations, AnnotationType
from src.llm.generator import LLMClient
from src.config import SearchConfig
import tldextract

# Read the same source the test does: LLM_API_KEY usually arrives via .env rather
# than the process environment, so os.getenv would miss it and skip needlessly.
_HAS_LLM_CREDENTIALS = bool(SearchConfig().llm_api_key)


@pytest.mark.integration
@pytest.mark.skipif(
    not _HAS_LLM_CREDENTIALS,
    reason="needs LLM_API_KEY; set it in .env or the environment to run this test",
)
def test_apply_donotcrawl_with_real_llm(tmp_path):
    settings = SearchConfig()
    
    # Redirect storage to tmp_path
    settings.allowed_path = tmp_path / "allowed.txt"
    settings.not_allowed_path = tmp_path / "not_allowed.txt"
    settings.reasoning_path = tmp_path / "reasoning.jsonl"
    settings.error_log_path = tmp_path / "malformed.log"

    for file_path in [
        settings.allowed_path,
        settings.not_allowed_path,
        settings.reasoning_path,
        settings.error_log_path,
    ]:
        file_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the dir exists
        file_path.touch()

    # List all files in tmp_path
    print(f"Files in tmp_path: {[p.name for p in tmp_path.iterdir()]}")

    llm = LLMClient(settings.llm_model_name, settings.llm_base_url, settings.llm_api_key, extra_headers=settings.llm_extra_headers or None)

    # === Input real domains ===
    test_domains = [
        "nytimes.com",         # Copyright-heavy
        "xvideos.com",         # Adult
        "cnn.com",             # Copyright-heavy
        "github.com",          # Not OK
        "spamdomain.example",  # Spammy name
        "example.com",         # OK
        "geeksforgeeks.com"    # OK
    ]

    core_domains = [tldextract.extract(d).domain for d in test_domains]
    df = pd.DataFrame({"domain": core_domains})

    # === Annotate ===
    annotator = Annotations(settings=settings, llm=llm)
    result_df = annotator.apply(df, annotations=[AnnotationType.DONOTCRAWL])

    # === Assertions ===
    print(f"RESULTS DF: \n {result_df}")

    # Ensure crawlable column is filled with boolean or None
    assert "crawlable" in result_df.columns
    assert result_df["crawlable"].notna().any(), "No crawlable annotations were returned – check LLM response"

    # Check that reasoning and results got saved
    assert settings.reasoning_path.exists()
    assert settings.reasoning_path.read_text().strip() != ""

    print("Allowed domains file contents:")
    print(settings.allowed_path.read_text())

    print("Not allowed domains file contents:")
    print(settings.not_allowed_path.read_text())

    print("Reasoning file contents:")
    print(settings.reasoning_path.read_text())

    print("Error log file contents:")
    print(settings.error_log_path.read_text())
