import json
import pytest
from pathlib import Path
from src.pipeline.pipeline import SearchPipeline

def test_run_config_saved(tmp_path, settings):
    user_config = {
        "mode": "query",
        "input": "climate change",
        "output_folder_name": "test_output"
    }

    pipeline = SearchPipeline(user_config=user_config, settings=settings)
    config_path = pipeline.output_folder / "run_config.json"

    assert config_path.exists(), "Run config file was not saved."

    with open(config_path, "r") as f:
        config_data = json.load(f)

    assert config_data["mode"] == "query"
    assert config_data["input"] == "climate change"
    assert "model_name" in config_data