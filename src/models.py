from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Literal, Self
import logging
from src.limits import RECURSION_DEPTH_LIMIT, MAX_RESULTS_PER_QUERY_LIMIT

logger = logging.getLogger("pipeline_logger")

class UserArgs(BaseModel):
    mode: Literal["query", "topic", "keyword", "search"]
    input: str
    input_file: Optional[str] = ""
    output_folder_name: Optional[str] = "searchresults"

    recursion_depth: Optional[int] = 1
    max_results_per_query: Optional[int] = 20
    output_format: Optional[Literal["jsonl", "parquet"]] = "jsonl"

    perform_search: bool = False
    search_provider: Optional[Literal["google", "tavily"]] = None
    annotations: Optional[List[Literal["donotcrawl", "relevancy", "sub_categorization"]]] = ["donotcrawl", "relevancy"]
    filter_results: Optional[bool] = False

    @model_validator(mode="after")
    def validate_args(self) -> Self:

        if self.mode != "search" and self.input_file:
            logger.warning("input_file is only utilized when --mode=search")
            self.input_file = None

        if self.mode == "topic":
            if self.recursion_depth > RECURSION_DEPTH_LIMIT:
                raise ValueError(
                    f"recursion_depth must not be greater than {RECURSION_DEPTH_LIMIT} (set by admin)."
                )
        elif self.recursion_depth != 1:
            logger.warning("recursion_depth is only utilized when mode='topic'; ignoring value.")
            self.recursion_depth = 1

        if not self.perform_search and self.mode != "search":
            if self.annotations:
                logger.warning("annotations will be ignored since perform_search is False.")
            if self.filter_results:
                logger.warning("filter_results will be ignored since perform_search is False.")
            if self.max_results_per_query:
                logger.warning("max_results_per_query will be ignored since perform_search is False.")
        else:
            if self.max_results_per_query is not None and self.max_results_per_query > MAX_RESULTS_PER_QUERY_LIMIT:
                raise ValueError(f"max_results_per_query must not exceed {MAX_RESULTS_PER_QUERY_LIMIT} (set by admin).")

        return self
