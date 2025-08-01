import logging
import os
import sys
from pythonjsonlogger import jsonlogger


def get_logger(name="app"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    logHandler = logging.StreamHandler(sys.stdout)

    # Customize fields for observability
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d",
        json_ensure_ascii=False,
    )

    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)

    # Optional: add file logging outside container
    if not (os.path.exists("/.dockerenv") or os.environ.get("DOCKERIZED") == "1"):
        fileHandler = logging.FileHandler("logs/app.log")
        fileHandler.setFormatter(formatter)
        logger.addHandler(fileHandler)

    return logger
