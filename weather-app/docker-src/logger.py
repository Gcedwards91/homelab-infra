import logging
import os
import sys

from pythonjsonlogger.json import JsonFormatter


def get_logger(name: str = "app") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d",
        json_ensure_ascii=False,
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # File logging when running outside a container (local dev only)
    in_container = os.path.exists("/.dockerenv") or os.getenv("DOCKERIZED") == "1"
    if not in_container:
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.FileHandler("logs/app.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
