import logging
import json
import os
from datetime import datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        return json.dumps(log_entry)


def get_logger(name="weather_logger", log_file="logs/weather.log"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = JSONFormatter()

    # Detect container: look for /.dockerenv or env var you set in Dockerfile
    is_container = os.path.exists("/.dockerenv") or os.environ.get("DOCKERIZED") == "1"

    if is_container:
        handler = logging.StreamHandler()  # logs to STDOUT
    else:
        handler = logging.FileHandler(log_file)

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
