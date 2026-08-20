import pandas as pd

class Filter:
    def __init__(self, annotations=None):
        self.annotations = annotations or []

    def apply(self, df: pd.DataFrame, annotations: list = None) -> pd.DataFrame:
        annotations = annotations or self.annotations
        if not annotations:
            return df  # nothing to filter

        filtered_df = df.copy()

        for ann in annotations:
            if ann == "donotcrawl":
                # Remove rows where crawlable is false
                if "crawlable" in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df["crawlable"] == True]
            elif ann == "relevancy":
                # Remove rows where relevancy is False or None (keep only True)
                if "relevancy" in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df["relevancy"] == True]
            else:
                # Default: keep rows where filter column is True
                col = f"filter_{ann}"
                if col in filtered_df.columns:
                    filtered_df = filtered_df[filtered_df[col]]

        return filtered_df
