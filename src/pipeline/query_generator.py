# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

from src.processing.parsing import split_queries
from src.processing.topic_tree import TopicNode


class QueryGenerator:
    def __init__(self, llm, settings, notify_fn):
        self.llm = llm
        self.settings = settings
        self.notify = notify_fn

    def format_prompt(self, template_key: str, input_text: str, context: list = None) -> str:
        if template_key not in self.settings.prompt_templates:
            raise ValueError(f"Unsupported prompt template key: {template_key}")

        prompt_template = self.settings.prompt_templates[template_key]

        if template_key in ("topic", "expand"):
            context_str = " -> ".join(context) if context else ""
            return prompt_template.format(input=input_text, context=context_str)

        return prompt_template.format(input=input_text)

    def generate_queries(self, input_text: str, mode: str, template_key: str = "query", context: list = None):
        prompt = self.format_prompt(template_key, input_text, context)
        responses = self.llm.chat_sync([prompt], params=self.settings.generation_params[mode])
        response = responses[0] if responses else None

        # chat_sync returns None for a prompt once its retries are exhausted, and
        # this is the first step of query/topic/keyword mode -- so an unreachable
        # endpoint, a bad key or a wrong model name used to surface here as
        # `AttributeError: 'NoneType' has no attribute 'splitlines'` from inside
        # split_queries. Fail with the actual cause instead.
        if not response:
            raise RuntimeError(
                "The LLM returned no response for the initial "
                f"{mode!r} prompt. Check LLM_BASE_URL, LLM_API_KEY and "
                "LLM_MODEL_NAME, and see the run log for the per-attempt errors."
            )

        return split_queries(response)

    def generate_queries_batch(self, nodes: list[TopicNode], template_key: str, mode: str) -> list[tuple[TopicNode, list[str]]]:
        prompts = [self.format_prompt(template_key, node.value, node.path) for node in nodes]
        try:
            responses = self.llm.chat_sync(prompts, params=self.settings.generation_params[mode])
        except Exception as e:
            self.notify(f"LLM batch call failed: {e}", level="error")
            return []

        result = []
        for node, response in zip(nodes, responses):
            if response:
                subtopics = split_queries(response)
                result.append((node, subtopics))
            else:
                self.notify(f"No response for node '{node.value}'", level="warning")
        return result

    def expand_nodes(self, nodes: list[TopicNode], template_key: str, mode: str) -> list[TopicNode]:
        expanded = self.generate_queries_batch(nodes, template_key=template_key, mode=mode)
        next_leaves = []
        for node, subtopics in expanded:
            for sub in subtopics:
                child = node.add_child(sub)
                if child:
                    next_leaves.append(child)
        return next_leaves
