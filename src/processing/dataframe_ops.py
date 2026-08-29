# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import math


def dedupe_df_by_column(df, column_name: str):
    """
    Remove duplicate rows from a DataFrame based on values in a specific column.
    """
    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found in DataFrame.")

    deduped_df = df.drop_duplicates(subset=column_name, keep="first")
    return deduped_df


def clean_invalid_unicode(df):
    def clean_text(val):
        if isinstance(val, str):
            return val.encode("utf-8", "replace").decode("utf-8")
        return val

    return df.map(clean_text)


def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float) and math.isnan(obj):
        return None
    else:
        return obj
