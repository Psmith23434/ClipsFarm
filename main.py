"""
main.py
Entry point for ClipsFarm — Twitch CS2 Clip Collector.

Usage:
    python main.py

Requirements:
    pip install -r requirements.txt

Make sure your .env file contains:
    TWITCH_CLIENT_ID=...
    TWITCH_CLIENT_SECRET=...
"""

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from config import cfg
from database import db
from gui.main_window import MainWindow


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting %s v%s", cfg.APP_NAME, cfg.APP_VERSION)

    # Init DB (creates tables if needed)
    db.init()

    app = QApplication(sys.argv)
    app.setApplicationName(cfg.APP_NAME)
    app.setApplicationVersion(cfg.APP_VERSION)
    app.setOrganizationName("ClipsFarm")

    # High-DPI scaling (PySide6 handles this automatically on Qt6)
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    window = MainWindow()
    window.show()

    logger.info("GUI ready.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
