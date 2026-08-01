"""Centralized logging setup for the FAA Part 107 agent.

Console gets INFO+ (what a user running the CLI should see); a rotating-free
file under logs/agent.log gets DEBUG+ (full detail for diagnosing a failed
generation attempt after the fact).
"""

import logging
import os

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
LOG_FILE = os.path.join(LOG_DIR, "agent.log")


def setup_logging(console_level=logging.INFO, file_level=logging.DEBUG, log_to_file=True):
    root = logging.getLogger()
    root.setLevel(min(console_level, file_level) if log_to_file else console_level)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    if log_to_file:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
