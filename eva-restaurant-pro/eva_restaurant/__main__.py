#!/usr/bin/env python3
"""Desktop application entry point."""
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from eva_restaurant.core import load_settings
from eva_restaurant.i18n import set_language, tr
from eva_restaurant.logging.error_logger import get_logger, install_qt_excepthook, log_exception
from eva_restaurant.ui.main_window import MainWindow
from eva_restaurant.ui.styles import build_stylesheet

logger = get_logger("kitchen")


def main():
    install_qt_excepthook("eva_kitchen")
    logger.info("EVA Restaurant desktop app starting")
    app = QApplication(sys.argv)
    app.setApplicationName("EvaRestaurant")
    app.setOrganizationName("RezaMahyar")
    app.setStyle("Fusion")
    try:
        settings = load_settings()
        set_language(settings.get("language", "fa"))
        app.setStyleSheet(build_stylesheet(settings))
        win = MainWindow()
        win.setWindowTitle(tr("app_title"))
        win.show()
    except Exception as e:
        log_exception("kitchen.main", e)
        QMessageBox.critical(None, "خطای راه‌اندازی", f"برنامه راه‌اندازی نشد:\n{e}")
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
