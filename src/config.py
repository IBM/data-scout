from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict
from pathlib import Path
from src import constants


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
    cors_origins: list[str] = Field(default=["http://localhost:3000"], alias="CORS_ORIGINS")

    # File names
    log_file: str = "pipeline.log"
    metrics_file: str = "metrics.json"
    topics_file: str = "topics.jsonl"

    # Results
    results_dir: str = "results"

    # Prompt templates
    prompt_templates: dict = constants.PROMPT_TEMPLATES

    # Crawl policy locations
    policy_dir: str = "src/processing/crawl_policy"
    allowed_path: Path = Path("src/processing/crawl_policy/allowed.txt")
    not_allowed_path: Path = Path("src/processing/crawl_policy/not_allowed.txt")
    reasoning_path: Path = Path("src/processing/crawl_policy/reasoning.jsonl")
    error_log_path: Path = Path("src/processing/crawl_policy/malformed_lines.log")

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

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",
    )
