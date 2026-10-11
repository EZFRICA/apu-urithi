"""Central logging, imported by every module."""

import logging
import os
import sys

from apu import config

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%H:%M:%S"


class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[90m",     # Gray
        logging.INFO: "\033[94m",      # Blue
        logging.WARNING: "\033[93m",   # Yellow
        logging.ERROR: "\033[91m",     # Red
        logging.CRITICAL: "\033[1;91m" # Bold Red
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def configure_root_logger():
    """Configure the root logger with the colored formatter."""
    root_logger = logging.getLogger()

    # Avoid duplicate handlers if already configured
    if root_logger.handlers:
        return

    root_logger.setLevel(logging.DEBUG)

    # Reduce noise from external libraries. Model clients log full request options at
    # DEBUG, prompts included, which does not belong in a runtime log.
    # The names carry the major version of the vendored client, so "httpx" alone leaves
    # httpx2 and httpcore2 at DEBUG: that is every request and response header of every
    # model call, which is what buries this log.
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    # The Neo4j driver logs every server notification at INFO, "index already exists"
    # included, one paragraph each. Warnings still come through.
    logging.getLogger("neo4j").setLevel(logging.WARNING)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    formatter = ColoredFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    console_handler.setFormatter(formatter)

    # File handler, no colors, under the data directory rather than the working directory:
    # it is per-machine state like the rest.
    #
    # INFO, never DEBUG: this file outlives the process, and DEBUG carries prompts, which
    # hold what the expert said about their work. Raise it deliberately, for a session, when
    # debugging something you cannot reproduce otherwise.
    os.makedirs(config.LOG_DIR, exist_ok=True)
    file_handler = logging.FileHandler(
        os.path.join(config.LOG_DIR, "urithi.log"), mode="a", encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    clean_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    file_handler.setFormatter(clean_formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Returns a configured logger for the module `name`."""
    configure_root_logger()
    return logging.getLogger(name.split(".")[-1])
