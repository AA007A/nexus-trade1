import logging, sys
import os


def get_logger(name: str) -> logging.Logger:
    level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO"), logging.INFO)
    logger = logging.getLogger(f"nexus7.{name}")
    if not logger.handlers:
        logger.setLevel(level)
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(h)
        logger.propagate = False
    return logger
