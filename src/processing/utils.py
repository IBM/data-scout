"""Re-export facade — preserves backward compatibility for all consumers."""
from src.processing.text_extraction import download, extract_simple_document, extract_pdf, is_pdf
from src.processing.parsing import split_queries, response_to_bool, parse_sub_category, extract_json_objects
from src.processing.dataframe_ops import dedupe_df_by_column, clean_invalid_unicode, sanitize_for_json
from src.processing.file_ops import (
    append_lines_to_file, ensure_ends_with_newline, zip_folder,
    classify_domain, chunked, clean_unicode, get_default_logger
)
