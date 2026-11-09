"""Size-based log rotation for the gateway, the keeper and the proxy refusal log."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def rotating_handler(path: Path) -> RotatingFileHandler:
    """A RotatingFileHandler on ``path`` (its folder is created)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")


def install_process_log(logs_dir: Path, filename: str, level: str, *, fallback_dir: Path | None = None) -> None:
    """Send the root and uvicorn loggers to ``logs_dir/filename`` too. Safe to call twice.

    Logging must never stop Roost from starting: when ``logs_dir`` can't be written (inside the gateway
    container ``/data``'s parent is read-only), ``fallback_dir`` is tried, and with neither the process
    just keeps its stderr logging."""
    root = logging.getLogger()
    for folder in (logs_dir, fallback_dir):
        if folder is None:
            continue
        target = str((folder / filename).resolve())
        if any(isinstance(h, RotatingFileHandler) and h.baseFilename == target for h in root.handlers):
            return
        try:
            handler = rotating_handler(folder / filename)
        except OSError:
            continue
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
        if root.level == logging.NOTSET or root.level > logging.getLevelName(level.upper()):
            root.setLevel(level.upper())
        for name in _SERVER_LOGGERS:
            logging.getLogger(name).addHandler(handler)
        return
    logging.getLogger(__name__).warning("No writable logs folder; logging to stderr only.")


def logs_dir_for(database_dir: Path) -> Path:
    """``~/Roost/logs`` next to the data folder (launchd's keeper.log lives there too)."""
    return database_dir.parent / "logs"
