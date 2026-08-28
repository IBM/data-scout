from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from pathlib import Path
import os
from src import constants


# Anchored to this file: <repo>/src/processing/crawl_policy when run from a
# clone, and the installed package's directory otherwise.
_DEFAULT_POLICY_DIR = str(Path(__file__).resolve().parent / "processing" / "crawl_policy")


class SearchConfig(BaseSettings):
    # LLM (OpenAI-compatible)
    llm_api_key: str = Field("", alias="LLM_API_KEY")
    llm_base_url: str = Field("", alias="LLM_BASE_URL")
    llm_model_name: str = Field("", alias="LLM_MODEL_NAME")
    llm_extra_headers: dict = Field(default_factory=dict, alias="LLM_EXTRA_HEADERS")

    # Search
    google_api_key: str = ""
    cx_key: str = ""
    tavily_api_key: str = ""
    search_provider: str = "tavily"
    tavily_search_depth: str = "basic"
    excluded_sites: list[str] = ["reddit.com", "medium.com"]

    # General pipeline
    temperature: float = 0.3
    max_tokens: int = 512
    recursion_depth: int = 1
    output_format: str = "jsonl"
    max_results_per_query: int = 20
    output_folder_name: str = "search_results"

    # Storage
    storage_backend: str = "local"
    storage_upload: bool = False
    storage_upload_dir: str = "results"
    storage_access_key_id: str = Field("", alias="STORAGE_ACCESS_KEY_ID")
    storage_secret_access_key: str = Field("", alias="STORAGE_SECRET_ACCESS_KEY")
    storage_endpoint: str = Field("", alias="STORAGE_ENDPOINT")
    storage_region: str = Field("us-east-1", alias="STORAGE_REGION")
    storage_bucket: str = Field("", alias="STORAGE_BUCKET")

    # Infrastructure
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    max_download_workers: int = 10
    max_extract_workers: int = 8

    # API
    api_key: str = Field("", alias="API_KEY")
    # Off by default: error text from this codebase can carry absolute paths, a
    # Redis URL including credentials, and raw S3 error bodies. Turn it on in
    # development to get the real cause into the HTTP response; the cause is
    # written to the server log either way.
    debug_errors: bool = Field(False, alias="DEBUG_ERRORS")
    cors_origins: list[str] = Field(default=["http://localhost:3000"], alias="CORS_ORIGINS")

    # File names
    log_file: str = "pipeline.log"
    metrics_file: str = "metrics.json"
    topics_file: str = "topics.jsonl"

    # Results
    results_dir: str = "results"

    # Prompt templates
    prompt_templates: dict = constants.PROMPT_TEMPLATES

    # Crawl policy locations.
    #
    # Absolute, and anchored to this file rather than the working directory. As
    # relative paths they resolved against the CWD, so running from anywhere but
    # the repository root silently created a fresh, empty
    # `src/processing/crawl_policy/` tree there and never found the real cache.
    # POLICY_DIR overrides the location, which is what to set if the install
    # directory is not writable.
    policy_dir: str = Field(_DEFAULT_POLICY_DIR, alias="POLICY_DIR")
    allowed_path: Path = Path(_DEFAULT_POLICY_DIR) / "allowed.txt"
    not_allowed_path: Path = Path(_DEFAULT_POLICY_DIR) / "not_allowed.txt"
    reasoning_path: Path = Path(_DEFAULT_POLICY_DIR) / "reasoning.jsonl"
    error_log_path: Path = Path(_DEFAULT_POLICY_DIR) / "malformed_lines.log"

    @model_validator(mode="after")
    def _anchor_policy_paths(self):
        """Keep the four file paths under policy_dir when POLICY_DIR is set.

        Only the paths still sitting at their default are moved, so an explicit
        override of an individual path is preserved.
        """
        base = Path(self.policy_dir)
        for field, name in (
            ("allowed_path", "allowed.txt"),
            ("not_allowed_path", "not_allowed.txt"),
            ("reasoning_path", "reasoning.jsonl"),
            ("error_log_path", "malformed_lines.log"),
        ):
            if getattr(self, field) == Path(_DEFAULT_POLICY_DIR) / name:
                setattr(self, field, base / name)
        return self

    # Prompt params
    generation_params: dict = {
        "query": {"temperature": 0.3, "max_tokens": 512},
        "topic": {"temperature": 0.3, "max_tokens": 512},
        "search": {"temperature": 0.3, "max_tokens": 512},
        "keyword": {"temperature": 0.3, "max_tokens": 512},
        "relevancy": {"temperature": 0, "max_tokens": 512},
        "sub_categorization": {"temperature": 0, "max_tokens": 512},
        "crawlable": {"temperature": 0, "max_tokens": 512},
    }

    # Sub-categories (empty = disabled)
    sub_categories: list[str] = []

    # SettingsConfigDict, not ConfigDict: the latter is not the settings type,
    # and silently ignored settings-only keys such as env_file typos.
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
