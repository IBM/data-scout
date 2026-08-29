# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import multiprocessing

import pytest
import pandas as pd
import json
import math
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.processing.utils import (
    split_queries,
    response_to_bool,
    parse_sub_category,
    extract_json_objects,
    classify_domain,
    dedupe_df_by_column,
    clean_invalid_unicode,
    sanitize_for_json,
    clean_unicode,
    is_pdf,
    extract_pdf,
    extract_simple_document,
    chunked,
    append_lines_to_file,
    zip_folder,
)


class TestSplitQueries:
    def test_parses_markdown_plus_format(self):
        response = '+ "query one"\n+ "query two"\n+ "query three"'
        result = split_queries(response)
        assert result == ["query one", "query two", "query three"]

    def test_ignores_lines_without_plus(self):
        response = 'Some intro text\n+ "actual query"\nSome outro'
        result = split_queries(response)
        assert result == ["actual query"]

    def test_ignores_plus_lines_without_quotes(self):
        response = '+ no quotes here\n+ "with quotes"'
        result = split_queries(response)
        assert result == ["with quotes"]

    def test_empty_response(self):
        assert split_queries("") == []

    def test_multiline_with_mixed_content(self):
        response = """Here are some queries:
+ "machine learning basics"
+ "deep learning tutorial"
Some text in between
+ "neural networks explained"
"""
        result = split_queries(response)
        assert len(result) == 3
        assert "machine learning basics" in result


class TestResponseToBool:
    def test_none_input(self):
        assert response_to_bool(None) is None

    def test_json_yes(self):
        assert response_to_bool('{"relevant": "Yes"}') is True

    def test_json_no(self):
        assert response_to_bool('{"relevant": "No"}') is False

    def test_json_true_string(self):
        assert response_to_bool('{"relevant": "true"}') is True

    def test_json_false_string(self):
        assert response_to_bool('{"relevant": "false"}') is False

    def test_json_relevancy_key(self):
        assert response_to_bool('{"relevancy": "Yes"}') is True

    def test_json_is_relevant_key(self):
        assert response_to_bool('{"is_relevant": "No"}') is False

    def test_plain_text_yes(self):
        assert response_to_bool("Yes, this document is relevant.") is True

    def test_plain_text_no(self):
        assert response_to_bool("No, this is not relevant.") is False

    def test_ambiguous_both(self):
        assert response_to_bool("Yes and No") is None

    def test_ambiguous_neither(self):
        assert response_to_bool("maybe") is None

    def test_word_boundary(self):
        # "nobody" should not match "no"
        assert response_to_bool("Yes, nobody disagrees") is True


class TestParseSubCategory:
    def test_none_input(self):
        assert parse_sub_category(None) is None

    def test_direct_json(self):
        assert parse_sub_category('{"sub_category": "Algebra"}') == "Algebra"

    def test_json_none_value(self):
        assert parse_sub_category('{"sub_category": "None"}') is None

    def test_json_null_value(self):
        assert parse_sub_category('{"sub_category": null}') is None

    def test_embedded_json(self):
        response = 'Here is the answer:\n{"sub_category": "Calculus"}\nDone.'
        assert parse_sub_category(response) == "Calculus"

    def test_regex_fallback(self):
        response = 'The sub_category is "Geometry" based on the content.'
        # The regex looks for "sub_category": "X" pattern
        assert parse_sub_category('"sub_category": "Geometry"') == "Geometry"

    def test_no_match(self):
        assert parse_sub_category("completely unrelated text") is None


class TestExtractJsonObjects:
    def test_single_json_object(self):
        text = '{"domain": "example.com", "status": "OK"}'
        result = extract_json_objects(text)
        assert len(result) == 1
        assert result[0]["domain"] == "example.com"

    def test_multiple_json_objects(self):
        text = '{"a": 1}\n{"b": 2}'
        result = extract_json_objects(text)
        assert len(result) == 2

    def test_code_block_wrapped(self):
        text = "```json\n{\"key\": \"value\"}\n```"
        result = extract_json_objects(text)
        assert len(result) == 1
        assert result[0]["key"] == "value"

    def test_malformed_tracking(self):
        malformed = []
        text = '{"valid": true}\n{invalid json}\n{"also_valid": true}'
        result = extract_json_objects(text, malformed_lines=malformed)
        assert len(result) == 2
        assert len(malformed) == 1

    def test_empty_string(self):
        assert extract_json_objects("") == []


class TestClassifyDomain:
    def test_allowed_domain(self):
        allowed = {"example.com"}
        not_allowed = {"spam.com"}
        assert classify_domain("example.com", allowed, not_allowed) is True

    def test_not_allowed_domain(self):
        allowed = {"example.com"}
        not_allowed = {"spam.com"}
        assert classify_domain("spam.com", allowed, not_allowed) is False

    def test_unlisted_domain(self):
        allowed = {"example.com"}
        not_allowed = {"spam.com"}
        assert classify_domain("unknown.com", allowed, not_allowed) is None

    def test_unlisted_set_tracking(self):
        unlisted = set()
        classify_domain("new.com", set(), set(), unlisted_set=unlisted)
        assert "new.com" in unlisted

    def test_case_insensitive(self):
        allowed = {"example.com"}
        # The function lowercases domain before comparing to set
        assert classify_domain("Example.Com", allowed, set()) is True
        assert classify_domain("EXAMPLE.COM", allowed, set()) is True
        assert classify_domain("example.com", allowed, set()) is True

    def test_non_string_domain(self):
        assert classify_domain(None, {"a"}, {"b"}) is None
        assert classify_domain(123, {"a"}, {"b"}) is None


class TestDedupedfByColumn:
    def test_basic_dedup(self):
        df = pd.DataFrame({"link": ["a", "b", "a", "c"], "value": [1, 2, 3, 4]})
        result = dedupe_df_by_column(df, "link")
        assert len(result) == 3
        assert result["value"].tolist() == [1, 2, 4]

    def test_missing_column(self):
        df = pd.DataFrame({"a": [1, 2]})
        with pytest.raises(ValueError, match="Column 'missing'"):
            dedupe_df_by_column(df, "missing")

    def test_no_duplicates(self):
        df = pd.DataFrame({"link": ["a", "b", "c"]})
        result = dedupe_df_by_column(df, "link")
        assert len(result) == 3


class TestCleanInvalidUnicode:
    def test_valid_strings_unchanged(self):
        df = pd.DataFrame({"text": ["hello", "world"]})
        result = clean_invalid_unicode(df)
        assert result["text"].tolist() == ["hello", "world"]

    def test_non_string_values_unchanged(self):
        df = pd.DataFrame({"num": [1, 2, 3]})
        result = clean_invalid_unicode(df)
        assert result["num"].tolist() == [1, 2, 3]


class TestSanitizeForJson:
    def test_nan_replaced_with_none(self):
        result = sanitize_for_json({"key": float("nan")})
        assert result["key"] is None

    def test_nested_dict(self):
        result = sanitize_for_json({"outer": {"inner": float("nan")}})
        assert result["outer"]["inner"] is None

    def test_list_with_nan(self):
        result = sanitize_for_json([1, float("nan"), 3])
        assert result == [1, None, 3]

    def test_normal_values_unchanged(self):
        data = {"a": 1, "b": "hello", "c": [1, 2]}
        assert sanitize_for_json(data) == data


class TestCleanUnicode:
    def test_valid_string(self):
        assert clean_unicode("hello") == "hello"

    def test_non_string(self):
        assert clean_unicode(123) == 123
        assert clean_unicode(None) is None


class TestIsPdf:
    def test_pdf_bytes(self):
        assert is_pdf(b"%PDF-1.4 some content") is True

    def test_non_pdf_bytes(self):
        assert is_pdf(b"<html>not a pdf</html>") is False

    def test_non_bytes(self):
        assert is_pdf("not bytes") is False
        assert is_pdf(None) is False


class TestExtractPdf:
    def test_extracts_text(self):
        # Create a minimal valid PDF for testing
        from pypdf import PdfWriter
        from io import BytesIO

        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        buf = BytesIO()
        writer.write(buf)
        pdf_bytes = buf.getvalue()

        result = extract_pdf(pdf_bytes)
        assert isinstance(result, str)


class TestExtractSimpleDocument:
    def test_pdf_dispatch(self):
        with patch("src.processing.text_extraction.extract_pdf") as mock_pdf:
            mock_pdf.return_value = "pdf text"
            result = extract_simple_document(b"%PDF-1.4 content")
            mock_pdf.assert_called_once()
            assert result == "pdf text"

    def test_html_dispatch(self):
        with patch("src.processing.text_extraction.trafilatura.extract") as mock_traf:
            mock_traf.return_value = "html text"
            result = extract_simple_document(b"<html><body>content</body></html>")
            mock_traf.assert_called_once()
            assert result == "html text"


class TestChunked:
    def test_even_split(self):
        result = list(chunked([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_uneven_split(self):
        result = list(chunked([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_single_chunk(self):
        result = list(chunked([1, 2, 3], 10))
        assert result == [[1, 2, 3]]


class TestAppendLinesToFile:
    def test_creates_file_if_missing(self, tmp_path):
        filepath = tmp_path / "test.txt"
        append_lines_to_file(filepath, ["line1", "line2"])
        content = filepath.read_text()
        assert "line1\n" in content
        assert "line2\n" in content

    def test_appends_to_existing(self, tmp_path):
        filepath = tmp_path / "test.txt"
        filepath.write_text("existing\n")
        append_lines_to_file(filepath, ["new_line"])
        content = filepath.read_text()
        assert "existing\n" in content
        assert "new_line\n" in content

    def test_ensures_newline_before_append(self, tmp_path):
        filepath = tmp_path / "test.txt"
        filepath.write_text("no_trailing_newline")
        append_lines_to_file(filepath, ["next"])
        content = filepath.read_text()
        assert content == "no_trailing_newline\nnext\n"


class TestZipFolder:
    def test_creates_zip(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file1.txt").write_text("hello")
        (src / "file2.txt").write_text("world")

        dest = tmp_path / "dest"
        result = zip_folder(str(src), str(dest), "test.zip")

        assert result is not None
        assert Path(result).exists()

    def test_nonexistent_source_creates_empty_zip(self, tmp_path):
        # os.walk on nonexistent path yields nothing, so an empty zip is created
        result = zip_folder("/nonexistent/path", str(tmp_path), "test.zip")
        assert result is not None
        assert Path(result).exists()


def _slow_append_worker(path_str, tag, barrier_dir):
    """Append with a deliberately slow read-modify-write.

    The window between the newline fix-up and the writes is what the lock exists
    to close. Widening it here turns mutual exclusion into something measurable:
    each process records when it entered and left the critical section, and with
    a lock held those intervals cannot overlap.
    """
    import time
    from pathlib import Path
    from src.processing import file_ops

    original = file_ops.ensure_ends_with_newline

    def slow(path):
        Path(barrier_dir, f"{tag}.enter").write_text(str(time.time()))
        time.sleep(0.4)
        original(path)

    file_ops.ensure_ends_with_newline = slow
    file_ops.append_lines_to_file(Path(path_str), [f"{tag}-0"])
    Path(barrier_dir, f"{tag}.exit").write_text(str(time.time()))


class TestAppendsAreMutuallyExclusive:
    """Celery workers are separate processes appending to the same cache files.

    Note: a plain volume test does NOT catch this -- 20k lines x 200 chars across
    four processes produces no corruption either way, because POSIX makes each
    write() under O_APPEND atomic. What the lock actually protects is the
    read-modify-write around `ensure_ends_with_newline`, so this test measures
    mutual exclusion directly rather than hoping for a splice.
    """

    def test_critical_sections_do_not_overlap(self, tmp_path):
        target = tmp_path / "allowed.txt"
        barrier = tmp_path / "barrier"
        barrier.mkdir()

        tags = ("aaa", "bbb", "ccc")
        procs = [
            multiprocessing.Process(target=_slow_append_worker,
                                    args=(str(target), tag, str(barrier)))
            for tag in tags
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)

        intervals = sorted(
            (float((barrier / f"{tag}.enter").read_text()),
             float((barrier / f"{tag}.exit").read_text()))
            for tag in tags
        )
        overlaps = [
            (a, b) for (a, _), (b, _) in zip(intervals, intervals[1:])
            if b < dict(intervals).get(a, 0)
        ]
        for (start_a, end_a), (start_b, _) in zip(intervals, intervals[1:]):
            assert start_b >= end_a - 0.05, (
                "two processes were inside the append critical section at once: "
                f"{start_b} started before {end_a} finished"
            )

        # and nothing was lost
        lines = [ln for ln in target.read_text().splitlines() if ln.strip()]
        assert set(lines) == {f"{tag}-0" for tag in tags}


class TestNestedJsonObjects:
    """`line.endswith("}")` ended the block at the first nested object, so the
    outer object was never parsed."""

    def test_nested_object_as_the_last_key_is_parsed_whole(self):
        """The nested brace must be the LAST character on its line to trigger it.
        With a trailing comma (`},`) the old code happened to work, which is why
        the shape here matters."""
        text = '{\n  "domain": "example.com",\n  "meta": {\n    "score": 1\n  }\n}'

        assert extract_json_objects(text) == [
            {"domain": "example.com", "meta": {"score": 1}}
        ]

    def test_nested_object_followed_by_more_keys(self):
        text = '{\n  "meta": {\n    "score": 1\n  }\n  ,"allowed": true\n}'

        assert extract_json_objects(text) == [{"meta": {"score": 1}, "allowed": True}]

    def test_flat_objects_still_work(self):
        assert extract_json_objects('{"a": 1}\n{"b": 2}') == [{"a": 1}, {"b": 2}]

    def test_brace_inside_a_string_is_not_counted(self):
        assert extract_json_objects('{"tip": "use } carefully", "n": 2}') == [
            {"tip": "use } carefully", "n": 2}
        ]

    def test_malformed_input_is_still_collected(self):
        malformed = []
        extract_json_objects('{"a": 1,}', malformed_lines=malformed)

        assert malformed
