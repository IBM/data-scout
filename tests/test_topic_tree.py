# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from src.processing.topic_tree import TopicNode


class TestTopicNodeInit:
    def test_default_path(self):
        node = TopicNode("root")
        assert node.value == "root"
        assert node.path == ["root"]
        assert node.children == []

    def test_custom_path(self):
        node = TopicNode("child", path=["root", "child"])
        assert node.path == ["root", "child"]

    def test_seen_set_initialized(self):
        node = TopicNode("root")
        assert "root" in node.seen

    def test_parent_shares_seen(self):
        parent = TopicNode("parent")
        child = TopicNode("child", parent=parent)
        assert child.seen is parent.seen
        assert "child" in parent.seen


class TestAddChild:
    def test_adds_child(self):
        root = TopicNode("math")
        child = root.add_child("algebra")
        assert child is not None
        assert child.value == "algebra"
        assert child.path == ["math", "algebra"]
        assert len(root.children) == 1

    def test_deduplication_case_insensitive(self):
        root = TopicNode("math")
        root.add_child("Algebra")
        duplicate = root.add_child("algebra")
        assert duplicate is None
        assert len(root.children) == 1

    def test_deduplication_strips_whitespace(self):
        root = TopicNode("math")
        root.add_child("algebra")
        duplicate = root.add_child("  algebra  ")
        assert duplicate is None

    def test_multiple_children(self):
        root = TopicNode("math")
        root.add_child("algebra")
        root.add_child("geometry")
        root.add_child("calculus")
        assert len(root.children) == 3

    def test_root_value_is_deduplicated(self):
        root = TopicNode("math")
        result = root.add_child("math")
        assert result is None


class TestGetLeaves:
    def test_leaf_node(self):
        node = TopicNode("leaf")
        assert node.get_leaves() == ["leaf"]

    def test_one_level(self):
        root = TopicNode("root")
        root.add_child("a")
        root.add_child("b")
        leaves = root.get_leaves()
        assert set(leaves) == {"a", "b"}

    def test_two_levels(self):
        root = TopicNode("root")
        child = root.add_child("mid")
        child.add_child("leaf1")
        child.add_child("leaf2")
        leaves = root.get_leaves()
        assert set(leaves) == {"leaf1", "leaf2"}


class TestFlatten:
    def test_single_node(self):
        node = TopicNode("root")
        result = node.flatten()
        assert result == [("root", ["root"])]

    def test_tree(self):
        root = TopicNode("math")
        child = root.add_child("algebra")
        child.add_child("linear algebra")
        result = root.flatten()
        assert len(result) == 3
        values = [v for v, _ in result]
        assert "math" in values
        assert "algebra" in values
        assert "linear algebra" in values


class TestToJsonlRows:
    def test_basic_structure(self):
        root = TopicNode("science")
        topic = root.add_child("physics")
        topic.add_child("query about gravity")
        topic.add_child("query about motion")

        rows = root.to_jsonl_rows()
        assert len(rows) == 1
        assert rows[0]["topic"] == "physics"
        assert set(rows[0]["search_queries"]) == {"query about gravity", "query about motion"}
        assert rows[0]["parents"] == ["science"]

    def test_multiple_topics(self):
        root = TopicNode("math")
        t1 = root.add_child("algebra")
        t1.add_child("q1")
        t1.add_child("q2")
        t2 = root.add_child("geometry")
        t2.add_child("q3")

        rows = root.to_jsonl_rows()
        assert len(rows) == 2
        topics = [r["topic"] for r in rows]
        assert "algebra" in topics
        assert "geometry" in topics


class TestRebuildFromJsonlRows:
    def test_round_trip(self):
        root = TopicNode("science")
        physics = root.add_child("physics")
        physics.add_child("gravity query")
        physics.add_child("motion query")
        chem = root.add_child("chemistry")
        chem.add_child("bonds query")

        rows = root.to_jsonl_rows()
        rebuilt = TopicNode.rebuild_from_jsonl_rows(rows)

        assert rebuilt.value == "science"
        rebuilt_rows = rebuilt.to_jsonl_rows()
        assert len(rebuilt_rows) == len(rows)

        original_topics = {r["topic"] for r in rows}
        rebuilt_topics = {r["topic"] for r in rebuilt_rows}
        assert original_topics == rebuilt_topics

    def test_empty_rows_raises(self):
        with pytest.raises(ValueError):
            TopicNode.rebuild_from_jsonl_rows([])


class TestFlattenUniqueTopics:
    def test_returns_all_seen(self):
        root = TopicNode("a")
        root.add_child("b")
        root.add_child("c")
        unique = root.flatten_unique_topics()
        assert set(unique) == {"a", "b", "c"}


class TestGetNonLeafCount:
    def test_leaf_only(self):
        node = TopicNode("leaf")
        assert node.get_non_leaf_count() == 0

    def test_one_parent(self):
        root = TopicNode("root")
        root.add_child("child")
        assert root.get_non_leaf_count() == 1

    def test_nested(self):
        root = TopicNode("root")
        mid = root.add_child("mid")
        mid.add_child("leaf")
        assert root.get_non_leaf_count() == 2


class TestToDict:
    def test_structure(self):
        root = TopicNode("root")
        root.add_child("child")
        d = root.to_dict()
        assert d["value"] == "root"
        assert d["path"] == ["root"]
        assert len(d["children"]) == 1
        assert d["children"][0]["value"] == "child"

    def test_from_dict_round_trip(self):
        root = TopicNode("root")
        root.add_child("child")
        d = root.to_dict()
        rebuilt = TopicNode.from_dict(d)
        assert rebuilt.value == "root"
        assert len(rebuilt.children) == 1
        assert rebuilt.children[0].value == "child"
