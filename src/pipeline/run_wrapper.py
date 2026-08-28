from dotenv import load_dotenv
from src.pipeline.pipeline import SearchPipeline
from src.config import SearchConfig
from src.models import UserArgs
from typing import Optional

def run_pipeline_from_args_dict(user_args: dict, run_id: Optional[str] = None, progress_callback=None, metrics_callback=None, tracker=None):
    """
    Runs the pipeline using a provided dictionary of arguments.
    """
    validated_args = UserArgs(**user_args)
    load_dotenv()
    config = SearchConfig()
    pipeline = SearchPipeline(user_config=validated_args.model_dump(exclude_unset=True), settings=config, run_id=run_id, progress_callback=progress_callback, metrics_callback=metrics_callback)

    if tracker:
        tracker.set_storage_upload_folder(pipeline.storage_upload_prefix)
        tracker.set_storage_filename("logs", pipeline.settings.log_file)
        tracker.set_storage_filename("metrics", pipeline.settings.metrics_file)
        tracker.set_storage_filename("zip", f"{pipeline.output_base}_{pipeline.run_id}.zip")
        tracker.set_storage_filename("topics", pipeline.settings.topics_file)
        tracker.set_storage_filename("results", f"{pipeline.output_base}.{pipeline.output_format}")

    pipeline.run()

    if tracker:
        tracker.clear_logs()

    return pipeline.output_folder
