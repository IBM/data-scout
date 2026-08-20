import json
from pathlib import Path
import pandas as pd
from src.llm.generator import LLMClient
from src.search.google_search import GoogleSearchClient
from src.search.tavily_search import TavilySearchClient
from src.processing import utils
from src.processing.annotations import Annotations, AnnotationType
from src.processing.filter import Filter
from src.processing.topic_tree import TopicNode
from src.pipeline.query_generator import QueryGenerator
from src.pipeline.downloader import DocumentDownloader
from src.pipeline.result_handler import ResultHandler
import uuid
import time
from datetime import datetime, timezone
from src.logging_config import setup_logger
from typing import Callable, Optional
import signal

class GracefulInterruptException(Exception):
    pass

class SearchPipeline:
    def __init__(self, user_config: dict, settings, run_id=None, progress_callback: Optional[Callable[[str], None]] = None, metrics_callback: Optional[Callable[[str], None]] = None):
        self.progress_callback = progress_callback
        self.metrics_callback = metrics_callback
        self.run_id = run_id or uuid.uuid4().hex

        def get(key):
            val = user_config.get(key, None)
            if val is not None:
                return val
            return getattr(settings, key, None)

        self.mode = get("mode")
        self.input = get("input")
        self.input_file = get("input_file")

        self.max_results_per_query = get("max_results_per_query")
        self.recursion_depth = get("recursion_depth") or 0
        self.output_base = get("output_folder_name")
        self.output_format = get("output_format")
        self.annotations = get("annotations") or []
        self.filter_results = get("filter_results") or False
        self.do_perform_search = get("perform_search") or False

        if self.mode == "search":
            self.do_perform_search = True

        self.settings = settings

        self.output_folder = self._prepare_output_folder()

        log_path = self.output_folder / self.settings.log_file
        self.logger = setup_logger(log_path)
        self.notify("Logger initialized")

        self.notify(f"Saving run outputs to: {self.output_folder}")
        if self.settings.storage_upload:
            self.notify(f"Prepared storage upload prefix: {self.storage_upload_prefix}")

        self.llm = LLMClient(
            model=self.settings.llm_model_name,
            base_url=self.settings.llm_base_url,
            api_key=self.settings.llm_api_key,
            extra_headers=self.settings.llm_extra_headers or None,
        )
        self.query_gen = QueryGenerator(self.llm, self.settings, self.notify)
        self.downloader = DocumentDownloader(self.settings, self.notify)
        self.result_handler = ResultHandler(
            output_folder=self.output_folder,
            output_base=self.output_base,
            output_format=self.output_format,
            settings=self.settings,
            notify_fn=self.notify,
            metrics_callback=self.metrics_callback,
        )
        search_provider = get("search_provider") or self.settings.search_provider
        if search_provider == "tavily":
            self.search_client = TavilySearchClient(self.settings.tavily_api_key, search_depth=self.settings.tavily_search_depth)
        else:
            self.search_client = GoogleSearchClient(self.settings.google_api_key, self.settings.cx_key, excluded_sites=self.settings.excluded_sites)
        self.annotations_obj = Annotations(settings=self.settings, llm=self.llm, input=self.input)
        self.filter_obj = Filter()

        self.save_run_config()



    def set_progress_callback(self, callback: Callable[[str], None]):
        self.progress_callback = callback

    def _notify_progress(self, message: str):
        if self.progress_callback:
            self.progress_callback(message)

    def _notify_metrics(self, metrics: dict):
        if self.metrics_callback:
            self.metrics_callback(metrics)


    def notify(self, message: str, level: str = "info"):
        level = level.lower()

        if level == "info":
            self._notify_progress(message)
            self.logger.info(message)
        elif level == "debug":
            self.logger.debug(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "critical":
            self.logger.critical(message)

    def _prepare_output_folder(self):
        # Sanitize output_base to prevent path traversal
        safe_base = Path(self.output_base).name
        if not safe_base or safe_base in (".", ".."):
            safe_base = "output"
        base_path = Path(self.settings.results_dir) / safe_base

        output_path = base_path / self.run_id
        output_path.mkdir(parents=True, exist_ok=False)

        if getattr(self.settings, "storage_upload", False):
            self.storage_upload_prefix = str(Path(self.settings.storage_upload_dir) / self.output_base / self.run_id)
        else:
            self.storage_upload_prefix = ""

        return output_path

    def zip_run_outputs(self):
        self.result_handler.zip_run_outputs(self.run_id)

    def upload_run_outputs(self):
        self.result_handler.upload_run_outputs(self.storage_upload_prefix)

    def save_run_config(self):
        config = {
            "mode": self.mode,
            "input": self.input,
            "input_file": self.input_file,
            "max_results_per_query": self.max_results_per_query,
            "recursion_depth": self.recursion_depth,
            "output_base": self.output_base,
            "output_format": self.output_format,
            "annotations": self.annotations,
            "filter_results": self.filter_results,
            "perform_search": self.do_perform_search,
            "model_name": self.settings.llm_model_name,
            "generation_params": self.settings.generation_params[self.mode],
            "output_folder": str(self.output_folder.resolve())
        }

        if self.settings.storage_upload:
            config["storage_upload_prefix"] = self.storage_upload_prefix

        if "relevancy" in self.annotations:
            config["relevancy_params"] = self.settings.generation_params["relevancy"]

        if "donotcrawl" in self.annotations:
            config["crawlable_params"] = self.settings.generation_params["crawlable"]

        self.result_handler.save_run_config(config)

    def format_prompt(self, template_key: str, input_text: str, context: list = None) -> str:
        return self.query_gen.format_prompt(template_key, input_text, context)

    def generate_queries(self, input_text: str, template_key: str = "query", context: list = None):
        return self.query_gen.generate_queries(input_text, mode=self.mode, template_key=template_key, context=context)

    def generate_queries_batch(self, nodes: list[TopicNode], template_key: str) -> list[tuple[TopicNode, list[str]]]:
        return self.query_gen.generate_queries_batch(nodes, template_key=template_key, mode=self.mode)

    def expand_nodes(self, nodes: list[TopicNode], template_key: str) -> list[TopicNode]:
        return self.query_gen.expand_nodes(nodes, template_key=template_key, mode=self.mode)

    def perform_search(self, queries):
        results = self.search_client.perform_search(queries, self.max_results_per_query)
        if not queries:
            raise RuntimeError("No queries were generated after expansion.")
        return results

    def download_and_extract_texts(self, df: pd.DataFrame):
        return self.downloader.download_and_extract_texts(df)

    def annotate_results(self, df):
        return self.annotations_obj.apply(df, annotations=[AnnotationType(a) for a in self.annotations])


    def filter_results_df(self, df):
        return self.filter_obj.apply(df, annotations=[AnnotationType(a) for a in self.annotations])

    def print_result_metrics(self, df: pd.DataFrame) -> dict:
        return self.result_handler.print_result_metrics(df)

    def save_metrics(self, new_metrics: dict):
        self.result_handler.save_metrics(new_metrics)

    def save_results(self, results):
        self.result_handler.output_format = self.output_format
        self.result_handler.save_results(results)

    def compute_annotation_metrics(self, df: pd.DataFrame, base_metrics: dict) -> dict:
        return self.result_handler.compute_annotation_metrics(df, base_metrics)

    def process_search_results(self, queries):
        if not queries:
            raise RuntimeError("No queries provided for search.")

        metrics = {}
        timing = {}
        start = time.time()

        # --- 1. Perform Search ---
        t0 = time.time()
        self.notify("Performing search...")
        results = self.perform_search(queries)
        timing["performing_search"] = time.time() - t0
        metrics["raw_results"] = len(results)

        # --- 2. Deduplicate ---
        df = pd.DataFrame(results)
        df = utils.dedupe_df_by_column(df, "link")
        metrics["deduped_results"] = len(df)

        # --- 3 & 4. Download & Extract ---
        t1 = time.time()
        df, download_metrics, download_timing = self.download_and_extract_texts(df)
        metrics.update(download_metrics)
        timing.update(download_timing)

        # --- 5. Annotate ---
        if self.annotations:
            t3 = time.time()
            self.notify(f"Applying annotations: {self.annotations}")
            df = self.annotate_results(df)
            timing["annotations"] = time.time() - t3

            annotation_metrics = self.compute_annotation_metrics(df, base_metrics=metrics)
            metrics.update(annotation_metrics)
        else:
            self.notify("No annotations applied.")

        # --- 6. Filter ---
        if self.filter_results:
            t4 = time.time()
            self.notify("Filtering results based on annotations.")
            filtered_df = self.filter_results_df(df)
            timing["filtering"] = time.time() - t4
            self.notify(f"{len(filtered_df)} results remain after filtering.")
            metrics["after_filtering"] = len(filtered_df)
        else:
            self.notify("No filtering applied, returning all annotated results.")
            filtered_df = df

        filtered_df = utils.clean_invalid_unicode(filtered_df)

        # --- 7. Save Core Metrics & Timing ---
        total_time = time.time() - start
        timing["search_and_processing"] = total_time

        # --- 8. Save Final Results ---
        self.save_results(filtered_df.to_dict(orient="records"))

        return metrics, timing

    def run(self):
        def handle_interrupt(signum, frame):
            self.notify("Process interrupted by signal. Attempting graceful shutdown...", level="error")
            if self.settings.storage_upload:
                try:
                    self.zip_run_outputs()
                    self.upload_run_outputs()
                    self.notify("Storage upload completed after interruption.")
                except Exception as e:
                    self.notify(f"Failed storage upload on interrupt: {e}", level="error")

            raise GracefulInterruptException("Pipeline interrupted by signal.")

        signal.signal(signal.SIGINT, handle_interrupt)
        signal.signal(signal.SIGTERM, handle_interrupt)

        start_time = time.time()
        start_timestamp = datetime.now(timezone.utc).isoformat()
        self.notify(f"Starting pipeline run: mode={self.mode}, input={self.input}")

        timing = {}
        queries = []

        try:
            # === Initial Query Generation ===
            t_initial_start = time.time()
            if self.mode == "search":
                if self.input_file and Path(self.input_file).exists():
                    input_path = Path(self.input_file).expanduser().resolve()
                    try:
                        queries = []
                        with open(input_path, "r", encoding="utf-8") as f:
                            for i, line in enumerate(f):
                                try:
                                    obj = json.loads(line)
                                    if isinstance(obj.get("search_queries"), list):
                                        queries.extend(obj["search_queries"])
                                except json.JSONDecodeError as line_error:
                                    self.notify(f"Skipping invalid JSON on line {i + 1}: {line_error}", level="error")
                        self.notify(f"Loaded {len(queries)} queries from file: {input_path}")
                    except Exception as e:
                        self.notify(f"Failed to read queries from file {input_path}: {e}", level="error")
                        queries = []
                elif isinstance(self.input, str):
                    queries = [q.strip() for q in self.input.split(",") if q.strip()]
                    self.notify(f"Parsed queries from string input: {queries}")
                else:
                    raise RuntimeError(f"Unsupported input type for search mode: {type(self.input)}")

            else:
                context = [] if self.mode in ("query", "topic", "keyword") else None
                queries = self.generate_queries(self.input, template_key=self.mode, context=context)
                if self.mode == "topic":
                    self.notify(f"Recursion 1 topic count: {len(queries)}")
                    self.save_metrics({"topics_after_recursion_1": len(queries)})
                elif self.mode == "keyword":
                    self.notify(f"Initial keyword count: {len(queries)}")
                    self.save_metrics({"initial_keyword_generation": len(queries)})
            t_initial_end = time.time()
            timing['initial_query_generation'] = t_initial_end - t_initial_start

            recursion_time = 0
            expansion_time = 0

            if self.mode != "search":
                root = TopicNode(self.input)
                for q in queries:
                    root.add_child(q)

                current_leaves = root.children

                if self.mode == "topic" and self.recursion_depth > 1:
                    t_recursion_start = time.time()
                    for i in range(self.recursion_depth - 1):
                        self.notify(f"[Recursion {i+2}] Expanding {len(current_leaves)} leaf nodes...")
                        current_leaves = self.expand_nodes(current_leaves, template_key="topic")
                        self.save_metrics({f"topics_after_recursion_{i+2}": len(current_leaves)})
                    t_recursion_end = time.time()
                    recursion_time = t_recursion_end - t_recursion_start
                    timing['recursion'] = recursion_time

                if self.mode in ("topic", "keyword"):
                    t_expansion_start = time.time()
                    self.notify(f"Converting {self.mode}s into google search queries")
                    current_leaves = self.expand_nodes(current_leaves, template_key="expand")
                    t_expansion_end = time.time()
                    expansion_time = t_expansion_end - t_expansion_start
                    timing['conversion_to_queries'] = expansion_time

                rows = root.to_jsonl_rows()
                with open(self.output_folder / self.settings.topics_file, "w") as f:
                    for row in rows:
                        f.write(json.dumps(row) + "\n")

                queries = root.get_leaves()
                self.notify(f"Total queries after expansion: {len(queries)}")
                self.save_metrics({"generated_queries": len(queries)})

            if self.do_perform_search:
                search_metrics, search_timing = self.process_search_results(queries)
                self.save_metrics(search_metrics)
                timing.update(search_timing)

        except Exception as e:
            self.notify(f"Pipeline failed with error: {str(e)}", level="error")
            self.save_metrics({"error": str(e)})

        finally:
            if self.settings.storage_upload:
                try:
                    t_upload_start = time.time()
                    self.zip_run_outputs()
                    self.upload_run_outputs()
                    t_upload_end = time.time()
                    timing['storage_upload'] = t_upload_end - t_upload_start
                    self.notify(f"Storage upload completed in {timing['storage_upload']:.2f} seconds")
                except Exception as upload_err:
                    self.notify(f"Storage upload failed: {upload_err}", level="error")
            else:
                self.notify("Storage upload skipped as per settings")

            end_time = time.time()
            end_timestamp = datetime.now(timezone.utc).isoformat()

            overall_metrics = {
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
                "elapsed_times": timing
            }

            self.save_metrics(overall_metrics)
            self.notify(f"Pipeline run completed in {end_time - start_time:.2f} seconds")
