"""
Centralized logging configuration for Music Suggest Bot.
Every module should call `log = logging.getLogger(__name__)` and rely on this
setup so logs are consistent across the app (bot.py, webhook_app.py, tests).
"""
import logging
import os
import sys

CONSOLE_FMT = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"
FILE_FMT = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"

_configured = False


def setup_logging(level: int = logging.INFO, log_file: str = "bot.log") -> None:
    """Configure root logging once. Safe to call multiple times.

    Args:
        level: minimum level to emit.
        log_file: optional path to also write logs to. Set to None/"" to
            disable file output.
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = []  # clear any duplicate handlers (e.g. from prior imports)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(CONSOLE_FMT))
    root.addHandler(console)

    if log_file and log_file.strip():
        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(FILE_FMT))
            root.addHandler(fh)
        except Exception as e:  # pragma: no cover - file may be read-only
            root.warning("Could not attach file logger %s: %s", log_file, e)

    # Quiet down noisy third-party loggers so the bot's own logs are readable.
    for noisy in ("urllib3", "aiohttp", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def setup_logging_for_tests() -> None:
    """File+console logging tuned for debugging runs (INFO level, log to stderr)."""
    setup_logging(level=logging.INFO, log_file="")