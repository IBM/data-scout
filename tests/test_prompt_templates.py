"""Every mode and annotation must resolve a prompt template.

A missing key is a KeyError at runtime for an input the models already accept,
which typically only shows up when someone picks the less common mode.
"""
import pytest

from src import constants
from src.processing import annotations as annotations_module


class TestModeTemplates:
    """`pipeline.run` calls generate_queries(template_key=self.mode), so the
    template key has to match the mode name exactly."""

    @pytest.mark.parametrize("mode", ["query", "topic", "keyword"])
    def test_mode_has_a_template_named_after_it(self, mode):
        assert mode in constants.PROMPT_TEMPLATES

    def test_search_mode_is_deliberately_absent(self):
        """"search" prompts no LLM: it reads queries from input_file or splits a
        comma-separated string, so it needs no template."""
        assert "search" not in constants.PROMPT_TEMPLATES

    def test_recursive_expansion_template_exists(self):
        """topic mode recurses through `expand` beyond the first level."""
        assert "expand" in constants.PROMPT_TEMPLATES


class TestAnnotationTemplates:
    """The keys annotations.py actually looks up, read from the source rather than
    duplicated here -- a renamed template would otherwise pass."""

    def test_keys_used_by_annotations_all_exist(self):
        import inspect
        import re

        source = inspect.getsource(annotations_module)
        used = set(re.findall(r'prompt_templates\["(\w+)"\]', source))

        assert used, "no template lookups found -- did the access pattern change?"
        missing = used - set(constants.PROMPT_TEMPLATES)
        assert not missing, f"annotations.py looks up templates that do not exist: {missing}"

    @pytest.mark.parametrize("key", [
        "crawlable_annotation", "relevancy_annotation", "sub_category_annotation",
    ])
    def test_each_annotation_template_is_present(self, key):
        assert key in constants.PROMPT_TEMPLATES


class TestTemplateContent:
    def test_no_template_is_empty(self):
        for key, template in constants.PROMPT_TEMPLATES.items():
            assert template and template.strip(), f"{key} template is empty"

    @pytest.mark.parametrize("key", ["query", "topic", "keyword", "expand"])
    def test_input_placeholder_is_present(self, key):
        assert "{input}" in constants.PROMPT_TEMPLATES[key], f"{key} lost its {{input}}"

    def test_relevancy_template_takes_the_document_text(self):
        assert "{text}" in constants.PROMPT_TEMPLATES["relevancy_annotation"]
