from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_directory: Path) -> Path:
    log_directory.mkdir(parents=True, exist_ok=True)
    path = log_directory / "keyrhythm.log"
    handler = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    def report_exception(exception_type, value, traceback) -> None:
        logging.getLogger("keyrhythm.crash").critical("uncaught exception", exc_info=(exception_type, value, traceback))
        sys.__excepthook__(exception_type, value, traceback)

    sys.excepthook = report_exception
    return path

