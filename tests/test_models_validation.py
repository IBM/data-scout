# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import logging
from src.models import UserArgs
from src.limits import RECURSION_DEPTH_LIMIT, MAX_RESULTS_PER_QUERY_LIMIT


class TestUserArgsValidModes:
    def test_query_mode(self):
        args = UserArgs(mode="query", input="test topic")
        assert args.mode == "query"
        assert args.input == "test topic"

    def test_topic_mode(self):
        args = UserArgs(mode="topic", input="mathematics")
        assert args.mode == "topic"

    def test_keyword_mode(self):
        args = UserArgs(mode="keyword", input="machine learning")
        assert args.mode == "keyword"

    def test_search_mode(self):
        args = UserArgs(mode="search", input="test", perform_search=True)
        assert args.mode == "search"

    def test_invalid_mode_rejected(self):
        with pytest.raises(Exception):
            UserArgs(mode="invalid", input="test")


class TestUserArgsDefaults:
    def test_default_values(self):
        args = UserArgs(mode="query", input="test")
        assert args.output_folder_name == "searchresults"
        assert args.recursion_depth == 1
        assert args.max_results_per_query == 20
        assert args.output_format == "jsonl"
        assert args.perform_search is False
        assert args.annotations == ["donotcrawl", "relevancy"]
        assert args.filter_results is False


class TestUserArgsInputFile:
    def test_input_file_cleared_for_non_search_mode(self):
        args = UserArgs(mode="query", input="test", input_file="some_file.jsonl")
        assert args.input_file is None

    def test_input_file_kept_for_search_mode(self):
        args = UserArgs(mode="search", input="test", input_file="some_file.jsonl", perform_search=True)
        assert args.input_file == "some_file.jsonl"


class TestUserArgsRecursionDepth:
    def test_valid_depth_in_topic_mode(self):
        args = UserArgs(mode="topic", input="test", recursion_depth=RECURSION_DEPTH_LIMIT)
        assert args.recursion_depth == RECURSION_DEPTH_LIMIT

    def test_exceeds_limit_raises(self):
        with pytest.raises(ValueError, match="recursion_depth"):
            UserArgs(mode="topic", input="test", recursion_depth=RECURSION_DEPTH_LIMIT + 1)

    def test_non_topic_mode_resets_depth(self):
        args = UserArgs(mode="query", input="test", recursion_depth=5)
        assert args.recursion_depth == 1


class TestUserArgsMaxResults:
    def test_valid_max_results(self):
        args = UserArgs(mode="query", input="test", perform_search=True, max_results_per_query=50)
        assert args.max_results_per_query == 50

    def test_exceeds_limit_raises(self):
        with pytest.raises(ValueError, match="max_results_per_query"):
            UserArgs(
                mode="query",
                input="test",
                perform_search=True,
                max_results_per_query=MAX_RESULTS_PER_QUERY_LIMIT + 1,
            )


class TestUserArgsWarnings:
    def test_annotations_warning_when_no_search(self, caplog):
        logger = logging.getLogger("pipeline_logger")
        logger.propagate = True
        with caplog.at_level(logging.WARNING, logger="pipeline_logger"):
            args = UserArgs(mode="query", input="test", perform_search=False, annotations=["relevancy"])
        assert "annotations will be ignored" in caplog.text

    def test_filter_warning_when_no_search(self, caplog):
        logger = logging.getLogger("pipeline_logger")
        logger.propagate = True
        with caplog.at_level(logging.WARNING, logger="pipeline_logger"):
            args = UserArgs(mode="query", input="test", perform_search=False, filter_results=True)
        assert "filter_results will be ignored" in caplog.text
