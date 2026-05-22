"""Application bootstrap for src."""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtWidgets import QApplication

from src.core.config import USER_CONFIG_DIR
from src.ui.window import MainWindow

__all__ = ["BOOTSTRAP_ONLY_ENV", "BOOTSTRAP_ONLY_VALUE", "create_application", "run"]

BOOTSTRAP_ONLY_ENV = "CHUNITOOLS_BOOTSTRAP_ONLY"
BOOTSTRAP_ONLY_VALUE = "1"
LOGS_DIR_NAME = "logs"
LOG_FILE_NAME = "debug.log"


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create the QApplication instance for the desktop app."""
    return QApplication(argv or sys.argv)


def _configure_logging() -> None:
    log_dir = USER_CONFIG_DIR / LOGS_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    debug_handler = logging.FileHandler(log_dir / LOG_FILE_NAME, mode="w", encoding="utf-8")
    debug_handler.setFormatter(formatter)
    debug_handler.setLevel(logging.WARNING)
    root_logger.addHandler(debug_handler)

    dedicated_loggers = {
        "chartloading": "chartloading.log",
        "ui.3dview": "3dview.log",
        "ui.timelineview": "timelineview.log",
    }

    for logger_name, file_name in dedicated_loggers.items():
        handler = logging.FileHandler(log_dir / file_name, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        handler.setLevel(logging.WARNING)
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)
        logger.addHandler(handler)
        logger.propagate = False


def _is_bootstrap_only() -> bool:
    return os.getenv(BOOTSTRAP_ONLY_ENV) == BOOTSTRAP_ONLY_VALUE


def run() -> int:
    """Run the application event loop."""
    _configure_logging()
    app = create_application()
    if _is_bootstrap_only():
        return 0
    window = MainWindow()
    window.show()
    return app.exec()
