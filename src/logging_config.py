import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

def setup_logger(log_file: Path, log_level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger("pipeline_logger")
    logger.setLevel(log_level)
    logger.propagate = False

    # Remove previous file handlers
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()

    # Add console handler if missing
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_format = logging.Formatter(
            "%(asctime)s | [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)

    # Add new file handler for this run
    log_file.parent.mkdir(parents=True, exist_ok=True)
    # Rotating, not plain: a long-lived deployment appending every run to one
    # file had no bound at all. 10 MB x 3 keeps recent history without growth.
    file_handler = RotatingFileHandler(
        log_file, mode="a", encoding="utf-8", maxBytes=10 * 1024 * 1024, backupCount=3
    )
    file_handler.setLevel(log_level)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    logger.info(f"Logger initialized for run log: {log_file}")

    return logger

