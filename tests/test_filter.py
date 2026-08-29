# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import pandas as pd
from src.processing.filter import Filter


class TestFilterDonotcrawl:
    def test_removes_non_crawlable(self):
        df = pd.DataFrame({
            "link": ["a", "b", "c"],
            "crawlable": [True, False, True]
        })
        f = Filter()
        result = f.apply(df, annotations=["donotcrawl"])
        assert len(result) == 2
        assert list(result["link"]) == ["a", "c"]

    def test_no_crawlable_column(self):
        df = pd.DataFrame({"link": ["a", "b"]})
        f = Filter()
        result = f.apply(df, annotations=["donotcrawl"])
        assert len(result) == 2


class TestFilterRelevancy:
    def test_removes_irrelevant(self):
        df = pd.DataFrame({
            "link": ["a", "b", "c"],
            "relevancy": [True, False, True]
        })
        f = Filter()
        result = f.apply(df, annotations=["relevancy"])
        assert len(result) == 2
        assert list(result["link"]) == ["a", "c"]

    def test_removes_none_relevancy(self):
        df = pd.DataFrame({
            "link": ["a", "b", "c"],
            "relevancy": [True, None, False]
        })
        f = Filter()
        result = f.apply(df, annotations=["relevancy"])
        assert len(result) == 1

    def test_no_relevancy_column(self):
        df = pd.DataFrame({"link": ["a", "b"]})
        f = Filter()
        result = f.apply(df, annotations=["relevancy"])
        assert len(result) == 2


class TestFilterCombined:
    def test_both_annotations(self):
        df = pd.DataFrame({
            "link": ["a", "b", "c", "d"],
            "crawlable": [True, True, False, True],
            "relevancy": [True, False, True, True]
        })
        f = Filter()
        result = f.apply(df, annotations=["donotcrawl", "relevancy"])
        assert len(result) == 2
        assert set(result["link"]) == {"a", "d"}


class TestFilterEmpty:
    def test_no_annotations(self):
        df = pd.DataFrame({"link": ["a", "b", "c"]})
        f = Filter()
        result = f.apply(df, annotations=[])
        assert len(result) == 3

    def test_none_annotations(self):
        df = pd.DataFrame({"link": ["a", "b", "c"]})
        f = Filter()
        result = f.apply(df, annotations=None)
        assert len(result) == 3


class TestFilterConstructor:
    def test_constructor_annotations_used(self):
        df = pd.DataFrame({
            "link": ["a", "b"],
            "crawlable": [True, False]
        })
        f = Filter(annotations=["donotcrawl"])
        result = f.apply(df)
        assert len(result) == 1
