import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from typing import Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
ERROR_LOG_PATH = os.path.join(PROJECT_ROOT, "error.log")
OPERATIONS_LOG_PATH = os.path.join(LOG_DIR, "operations.log")

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        return record.levelno <= self.max_level


def ensure_directories() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(ERROR_LOG_PATH):
        open(ERROR_LOG_PATH, "a", encoding="utf-8").close()


def configure_logging() -> logging.Logger:
    ensure_directories()

    logger = logging.getLogger("flytbase_bot")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    info_handler = TimedRotatingFileHandler(
        filename=OPERATIONS_LOG_PATH,
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(MaxLevelFilter(logging.WARNING))
    info_handler.setFormatter(formatter)

    error_handler = logging.FileHandler(ERROR_LOG_PATH, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    logger.addHandler(stream_handler)

    return logger


LOGGER = configure_logging()


def scrub_sensitive(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: ("***" if "token" in key.lower() else scrub_sensitive(value))
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [scrub_sensitive(item) for item in data]
    return data


def log_operation(message: str, **context: Any) -> None:
    if context:
        LOGGER.info("%s | %s", message, json.dumps(scrub_sensitive(context), ensure_ascii=False))
    else:
        LOGGER.info(message)


def log_error(message: str, **context: Any) -> None:
    if context:
        LOGGER.error("%s | %s", message, json.dumps(scrub_sensitive(context), ensure_ascii=False))
    else:
        LOGGER.error(message)


__all__ = [
    "ERROR_LOG_PATH",
    "LOGGER",
    "configure_logging",
    "log_error",
    "log_operation",
    "scrub_sensitive",
]
