import pytest
from pathlib import Path
import json
import shutil

from src.pipeline.run_wrapper import run_pipeline_from_args_dict

BASE_OUTPUT = "pytest_output"

@pytest.fixture
def valid_args():
    return {
        "mode": "query",
        "input": "renewable energy",
        "output": BASE_OUTPUT,
        "output_format": "jsonl",
        "perform_search": False,
    }

def test_pipeline_creates_expected_files_without_search(valid_args):
    output_folder = run_pipeline_from_args_dict(valid_args)

    assert output_folder.exists(), "Output folder does not exist"

    expected_files = ["topics.jsonl", "run_config.json", "metrics.json", "pipeline.log"]
    for fname in expected_files:
        fpath = output_folder / fname
        assert fpath.exists(), f"Expected file not found: {fname}"

    log_path = output_folder / "pipeline.log"
    log_content = log_path.read_text(encoding="utf-8")
    assert "Logger initialized" in log_content, "Log file does not contain expected content"

    topics_path = output_folder / "topics.jsonl"
    with open(topics_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) > 0, "topics.jsonl is empty"
        try:
            json.loads(lines[0])
        except json.JSONDecodeError:
            pytest.fail("topics.jsonl contains invalid JSON")

    # Clean up
    #shutil.rmtree(output_folder.parent)


