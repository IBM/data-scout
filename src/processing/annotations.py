# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import pandas as pd
from enum import Enum
from typing import List
from src.processing import utils
import json

class AnnotationType(str, Enum):
    DONOTCRAWL = "donotcrawl"
    RELEVANCY = "relevancy"
    SUB_CATEGORIZATION = "sub_categorization"

class Annotations:
    def __init__(self, settings, llm=None, input=None):
        """
        settings: config class
        llm: an instance of LLMClient
        input: original user input
        """
        self.llm = llm
        self.input = input
        self.settings = settings
        self.logger = utils.get_default_logger()

    def apply(self, df: pd.DataFrame, annotations: List[AnnotationType]) -> pd.DataFrame:
        for annotation in annotations:
            if annotation == AnnotationType.DONOTCRAWL:
                df = self._apply_donotcrawl(df)
            elif annotation == AnnotationType.RELEVANCY:
                df = self._apply_relevancy(df)
            elif annotation == AnnotationType.SUB_CATEGORIZATION:
                df = self._apply_sub_categorization(df)
            else:
                raise ValueError(f"Unknown annotation: {annotation}")
        return df

    def _apply_donotcrawl(self, df: pd.DataFrame) -> pd.DataFrame:

        def load_domains(path):
            # The crawl policy is a cache, not shipped data: it starts empty on a
            # fresh checkout and fills in as domains get classified. A missing
            # file means "nothing cached yet", so every domain is treated as
            # unlisted and classified below.
            if not path.exists():
                self.logger.info(f"No crawl policy cache at {path} yet; starting empty")
                return set()
            with open(path, "r", encoding="utf-8") as f:
                return set(line.strip().lower() for line in f if line.strip())

        allowed = load_domains(self.settings.allowed_path)
        not_allowed = load_domains(self.settings.not_allowed_path)
        self.unlisted_domains = set()

        df = df.copy()
        df["crawlable"] = df["domain"].apply(
            lambda d: utils.classify_domain(
                d, allowed, not_allowed, unlisted_set=self.unlisted_domains)
                )

        if self.unlisted_domains:
            prompts = []
            batch_domains = list(sorted(self.unlisted_domains))
            for batch in utils.chunked(batch_domains, 5):
                input_str = "\n".join(batch)
                prompt = self.settings.prompt_templates["crawlable_annotation"].format(input=input_str)
                prompts.append(prompt)

            responses = self.llm.chat_sync(prompts, params=self.settings.generation_params["crawlable"])

            # Domains are classified in batches of 5, so a run with 50 unlisted
            # domains makes 10 calls. Gating on responses[0] alone threw away all
            # ten batches whenever the *first* came back empty; keep whichever
            # ones did answer.
            responses = [r for r in (responses or []) if r]
            if not responses:
                self.logger.warning("[!] No usable response from LLM for unlisted domains")
                return df

            reasoning_lines = []
            newly_allowed = set()
            newly_not_allowed = set()
            malformed_lines = []

            for response_text in responses:
                parsed_objects = utils.extract_json_objects(response_text, malformed_lines=malformed_lines)
                for record in parsed_objects:
                    domain = record.get("domain", "").strip().lower()
                    status = record.get("status", "").strip().lower()

                    if not domain:
                        continue

                    if domain in allowed or domain in not_allowed:
                        self.logger.warning(f"[!] Warning: Domain '{domain}' already exists in cache — skipping.")
                        continue

                    reasoning_lines.append(json.dumps(record, ensure_ascii=False))

                    if status == "ok":
                        newly_allowed.add(domain)
                    else:
                        newly_not_allowed.add(domain)

            if malformed_lines:
                utils.append_lines_to_file(self.settings.error_log_path, malformed_lines)

            if reasoning_lines:
                utils.append_lines_to_file(self.settings.reasoning_path, reasoning_lines)

            if newly_allowed:
                utils.append_lines_to_file(self.settings.allowed_path, list(newly_allowed))

            if newly_not_allowed:
                utils.append_lines_to_file(self.settings.not_allowed_path, list(newly_not_allowed))

            df.loc[df["crawlable"].isna(), "crawlable"] = df.loc[df["crawlable"].isna(), "domain"].apply(
                lambda d: utils.classify_domain(d, newly_allowed, newly_not_allowed))

            self.logger.info(f"Newly classified domains: {len(newly_allowed)} allowed, {len(newly_not_allowed)} not allowed.")

        return df

    def _apply_relevancy(self, df: pd.DataFrame) -> pd.DataFrame:

        if self.llm is None:
            raise ValueError("LLM instance required for relevancy annotation")
        if self.input is None:
            raise ValueError("Input must be provided for relevancy annotation")

        texts = df["extracted_text"].fillna("").tolist()
        prompts = [
            self.settings.prompt_templates["relevancy_annotation"].format(input=self.input, text=text[:1024])
            for text in texts
        ]

        responses = self.llm.chat_sync(prompts, params=self.settings.generation_params["relevancy"])

        relevancy_flags = [utils.response_to_bool(response) for response in responses]

        df = df.copy()
        df["relevancy"] = relevancy_flags

        return df

    def _apply_sub_categorization(self, df: pd.DataFrame) -> pd.DataFrame:

        if self.llm is None:
            raise ValueError("LLM instance required for sub-categorization annotation")
        if self.input is None:
            raise ValueError("Input must be provided for sub-categorization annotation")

        sub_categories_str = "\n".join(self.settings.sub_categories) if self.settings.sub_categories else "None configured"

        texts = df["extracted_text"].fillna("").tolist()
        prompts = [
            self.settings.prompt_templates["sub_category_annotation"].format(
                input=self.input, text=text[:1024], sub_categories=sub_categories_str
            )
            for text in texts
        ]

        responses = self.llm.chat_sync(prompts, params=self.settings.generation_params["sub_categorization"])

        sub_categories = [utils.parse_sub_category(response) for response in responses]

        df = df.copy()
        df["sub_category"] = sub_categories

        return df
