#!/usr/bin/env python3
"""
EVA Restaurant — Central error & logging system
=================================================
Goal: no error should ever be silent. Every exception anywhere in the stack
(desktop app, background Flask thread, HTTP API, or the browser front-ends)
ends up in two places:

  1. A rotating log file on disk: data/logs/eva_restaurant.log
  2. The `error_logs` database table, browsable from
     Settings → گزارش خطاها (Error Log) inside the desktop app.

Usage
-----
    from error_logger import get_logger, log_exception, safe_call, install_qt_excepthook

    logger = get_logger(__name__)
    logger.info("server starting")

    try:
        risky()
    except Exception as e:
        log_exception("orders.create", e)          # logs + persists, never raises

    @safe_call("food_menu.save")                     # decorator form
    def save_food(...):
        ...
"""

import functools
import logging
import logging.handlers
import sys
import traceback

from eva_restaurant.core import LOG_DIR, log_error

_LOG_FILE = LOG_DIR / "eva_restaurant.log"

_configured = False


def _configure_root():
    global _configured
    if _configured:
        return
    handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)

    root = logging.getLogger("eva")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(console)
    root.propagate = False
    _configured = True


def get_logger(name: str = "eva") -> logging.Logger:
    _configure_root()
    if not name.startswith("eva"):
        name = f"eva.{name}"
    return logging.getLogger(name)


def log_exception(source: str, exc: Exception, level: str = "ERROR", context: dict = None):
    """Write an exception to the file log AND persist it to the database."""
    logger = get_logger(source.split(".")[0] if "." in source else source)
    logger.error("[%s] %s", source, exc, exc_info=True)
    log_error(source, str(exc), exc=exc, level=level, context=context)


def log_message(source: str, message: str, level: str = "WARNING", context: dict = None):
    """Record a non-exception condition worth reviewing later (e.g. a
    validation failure, a bad settings file, a suspicious input)."""
    logger = get_logger(source.split(".")[0] if "." in source else source)
    getattr(logger, level.lower(), logger.warning)("[%s] %s", source, message)
    log_error(source, message, level=level, context=context)


def safe_call(source: str, reraise: bool = True, default=None):
    """Decorator: wrap a function so any exception is logged centrally.

    By default the exception is re-raised after logging so callers (e.g. a
    Flask route) can still return the right HTTP status — logging should
    never silently swallow a real bug. Pass reraise=False for background/UI
    callbacks where crashing is worse than skipping the action.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                log_exception(f"{source}.{fn.__name__}", e)
                if reraise:
                    raise
                return default
        return wrapper
    return deco


def install_qt_excepthook(app_name: str = "eva_kitchen"):
    """Catch every otherwise-uncaught exception in the desktop app.

    Without this, an exception raised inside a Qt slot/signal handler is
    printed to stderr and the app keeps running in a broken state (or
    silently does nothing) — the user never finds out. With this hook the
    error is logged centrally and, if a QApplication exists, a friendly
    message box is shown instead of a silent failure or a hard crash.
    """
    def _hook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log_exception(app_name, exc_value if isinstance(exc_value, Exception) else RuntimeError(str(exc_value)))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance()
            if app is not None:
                box = QMessageBox()
                box.setIcon(QMessageBox.Critical)
                box.setWindowTitle("خطای غیرمنتظره")
                box.setText(
                    "یک خطای غیرمنتظره رخ داد و به‌طور خودکار ثبت شد.\n"
                    "برنامه به کار خود ادامه می‌دهد. اگر مشکل تکرار شد، "
                    "از بخش تنظیمات → گزارش خطاها جزئیات را بررسی کنید."
                )
                box.setDetailedText(tb_text)
                box.exec()
        except Exception:
            # If even the fallback dialog fails, we already wrote to the DB
            # and log file above, so there is nothing more we can safely do.
            pass

    sys.excepthook = _hook


def install_flask_error_handlers(app, source_prefix: str = "server"):
    """Attach global error handlers to a Flask app.

    - Any unhandled exception in a route returns a clean JSON 500 instead of
      leaking a stack trace to the client, and is logged centrally with the
      request path/method/body for diagnosis.
    - 404s on unknown API routes return JSON instead of an HTML page.
    """
    from flask import jsonify, request

    @app.errorhandler(Exception)
    def _handle_any_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify({"ok": False, "error": e.description}), e.code

        context = {
            "path": request.path,
            "method": request.method,
            "remote_addr": request.remote_addr,
        }
        try:
            if request.is_json:
                context["body"] = request.get_json(silent=True)
        except Exception:
            pass
        log_exception(f"{source_prefix}.{request.path}", e, context=context)
        return jsonify({
            "ok": False,
            "error": "خطای داخلی سرور رخ داد. این خطا ثبت شد.",
        }), 500

    @app.errorhandler(404)
    def _handle_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "not found"}), 404
        return e

    return app
