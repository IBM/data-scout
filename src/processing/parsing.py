# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import re
import json


def parse_sub_category(response: str):
    if response is None:
        return None

    response = response.strip()

    # 1. Try direct JSON parse
    try:
        data = json.loads(response)
        val = data.get("sub_category", None)
        if val is None:
            return None
        val = val.strip()

        if val.lower() == "none":
            return None

        return val
    except Exception:
        pass

    # 2. Extract JSON object from text using regex
    match = re.search(r'\{[\s\S]*?\}', response)
    if match:
        try:
            data = json.loads(match.group(0))
            val = data.get("sub_category", None)
            if val is None:
                return None
            val = val.strip()
            if val.lower() == "none":
                return None
            return val
        except Exception:
            pass

    # 3. Fallback — try to find "sub_category": "X"
    match = re.search(r'"sub_category"\s*:\s*"([^"]+)"', response)
    if match:
        val = match.group(1).strip()
        if val.lower() == "none":
            return None
        return val

    return None


def response_to_bool(response: str):
    if response is None:
        return None

    # 1) Try parsing as JSON
    try:
        data = json.loads(response)

        for key in ["relevant", "relevancy", "is_relevant"]:
            if key in data:
                val = str(data[key]).strip().lower()
                if val in ("yes", "true"):
                    return True
                if val in ("no", "false"):
                    return False
                return None
    except Exception:
        pass

    # 2) Normalize response for text matching
    text = response.lower()

    yes_match = re.search(r"\byes\b", text)
    no_match = re.search(r"\bno\b", text)

    if bool(yes_match) == bool(no_match):
        return None

    return bool(yes_match)


def split_queries(response):
    lines = response.splitlines()
    search_queries = []
    for line in lines:
        line = line.strip()
        if line.startswith('+'):
            match = re.search(r'"([^"]*)"', line)
            if match:
                search_queries.append(match.group(1))
    return search_queries


def _brace_delta(line: str) -> int:
    """Net change in nesting depth for one line, ignoring braces inside strings."""
    delta = 0
    in_string = False
    escaped = False
    for char in line:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "{":
                delta += 1
            elif char == "}":
                delta -= 1
    return delta


def extract_json_objects(text: str, malformed_lines: list = None):
    """
    Extracts all valid JSON objects from a text blob that may include Markdown-style formatting.
    """
    json_blocks = []
    current_block = []
    inside_code_block = False
    depth = 0

    for line in text.splitlines():
        line = line.strip()

        if line.startswith("```"):
            inside_code_block = not inside_code_block
            continue

        if inside_code_block or current_block or line.startswith("{"):
            current_block.append(line)

            # Track nesting instead of ending the block at the first line that
            # happens to close with "}". A nested object terminated the block
            # early, so the outer object was never parsed and its remaining lines
            # were treated as the start of a new one.
            depth += _brace_delta(line)

            if depth <= 0:
                try:
                    obj = json.loads("\n".join(current_block))
                    json_blocks.append(obj)
                except json.JSONDecodeError:
                    if malformed_lines is not None:
                        malformed_lines.append("\n".join(current_block))
                current_block = []
                depth = 0

    return json_blocks
