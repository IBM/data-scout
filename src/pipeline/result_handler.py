import json
from pathlib import Path
import pandas as pd
from typing import Callable, Optional

from src.processing.dataframe_ops import sanitize_for_json
from src.processing.file_ops import zip_folder
from src.storage import create_storage_backend


class ResultHandler:
    def __init__(
        self,
        output_folder: Path,
        output_base: str,
        output_format: str,
        settings,
        notify_fn: Callable[[str, str], None],
        metrics_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.output_folder = output_folder
        self.output_base = output_base
        self.output_format = output_format
        self.settings = settings
        self.notify = notify_fn
        self.metrics_callback = metrics_callback

    def save_results(self, results):
        output_path = self.output_folder / f"{self.output_base}.{self.output_format}"

        if self.output_format == "jsonl":
            with open(output_path, "w", encoding="utf-8") as f:
                for item in results:
                    sanitized_item = sanitize_for_json(item)
                    f.write(json.dumps(sanitized_item) + "\n")

        elif self.output_format == "parquet":
            df = pd.DataFrame(results)

            def sanitize_value(val):
                if isinstance(val, dict) and not val:
                    return None
                if isinstance(val, list) and not val:
                    return None
                if isinstance(val, (dict, list)):
                    return json.dumps(val)
                return val

            for col in df.columns:
                df[col] = df[col].apply(sanitize_value)

            df.to_parquet(output_path, index=False)

        else:
            raise ValueError(f"Unsupported format: {self.output_format}")

        self.notify(f"Saved {len(results)} results to {output_path}")

    def save_metrics(self, new_metrics: dict):
        if self.metrics_callback:
            self.metrics_callback(new_metrics)

        output_path = self.output_folder / self.settings.metrics_file

        if output_path.exists():
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    existing_metrics = json.load(f)
            except Exception as e:
                self.notify(f"Could not load existing metrics: {e}", level="warning")
                existing_metrics = {}
        else:
            existing_metrics = {}

        merged_metrics = {**existing_metrics, **new_metrics}

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(merged_metrics, f, indent=2)
            self.notify(f"Metrics saved to {output_path}")
        except Exception as e:
            self.notify(f"Failed to save metrics: {e}", level="error")

    def save_run_config(self, config_data: dict):
        config_path = self.output_folder / "run_config.json"
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
            self.notify(f"Run config saved to {config_path}")
        except Exception as e:
            self.notify(f"Failed to save run config: {e}", level="error")

    def compute_annotation_metrics(self, df: pd.DataFrame, base_metrics: dict) -> dict:
        metrics = base_metrics.copy()

        relevant = None
        crawlable = None

        if "relevancy" in df.columns:
            relevant = df["relevancy"].fillna(False).astype(bool)
            metrics["relevant_results"] = int(relevant.sum())

        if "crawlable" in df.columns:
            crawlable = df["crawlable"].fillna(False).astype(bool)
            metrics["crawlable_results"] = int(crawlable.sum())

        if relevant is not None and crawlable is not None:
            condition = relevant & crawlable
            metrics["relevant_and_crawlable"] = int(condition.sum())
        elif relevant is not None:
            condition = relevant
        elif crawlable is not None:
            condition = crawlable
        else:
            condition = pd.Series([True] * len(df), index=df.index)

        if "domain" in df.columns:
            top_domains = df[condition]["domain"].value_counts().head(10).to_dict()
            metrics["top_10_domains"] = top_domains

        self.notify("[METRICS]")
        for k, v in metrics.items():
            self.notify(f"{k.replace('_', ' ').capitalize()}: {v}")

        return metrics

    def zip_run_outputs(self, run_id: str):
        zip_file_name = f"{self.output_base}_{run_id}.zip"
        zip_dest_folder = self.output_folder

        zip_path = zip_folder(self.output_folder, zip_dest_folder, zip_file_name)
        if zip_path:
            self.notify(f"Created zip archive at {zip_path}")
        else:
            self.notify("Failed to create zip archive", level="error")

    def upload_run_outputs(self, storage_upload_prefix: str):
        try:
            storage = create_storage_backend(self.settings)
            src_folder = self.output_folder
            dest_prefix = storage_upload_prefix

            self.notify(f"Starting storage upload from {src_folder} to {dest_prefix}...")

            success = storage.upload_folder(src_folder, dest_prefix)

            if success:
                self.notify(f"Successfully uploaded run outputs to: {dest_prefix}")
            else:
                self.notify("Failed to upload run outputs", level="error")

        except Exception as e:
            self.notify(f"Exception during storage upload: {e}", level="error")

    def print_result_metrics(self, df: pd.DataFrame) -> dict:
        total = len(df)
        metrics = {
            "total_results": total
        }

        if "relevancy" in df.columns:
            relevant = df["relevancy"].fillna(False).astype(bool)
            metrics["relevant_results"] = int(relevant.sum())

        if "crawlable" in df.columns:
            crawlable = df["crawlable"].fillna(False).astype(bool)
            metrics["crawlable_results"] = int(crawlable.sum())

        if "relevancy" in df.columns and "crawlable" in df.columns:
            both = relevant & crawlable
            metrics["relevant_and_crawlable"] = int(both.sum())

        self.notify("[METRICS]")
        for k, v in metrics.items():
            self.notify(f"{k.replace('_', ' ').capitalize()}: {v}")

        return metrics
