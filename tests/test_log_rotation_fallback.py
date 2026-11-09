"""Logging can never stop Roost from starting (the gateway crash-looped on an unwritable /logs)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from roost.log_rotation import install_process_log


def _detach(path):
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, RotatingFileHandler) and h.baseFilename.startswith(str(path)):
            root.removeHandler(h)
            h.close()


def test_an_unwritable_logs_dir_falls_back_to_the_data_dir(tmp_path, monkeypatch):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    data = tmp_path / "data"
    data.mkdir()
    try:
        install_process_log(locked / "logs", "gateway.log", "INFO", fallback_dir=data / "logs")
        assert (data / "logs" / "gateway.log").exists()
    finally:
        locked.chmod(0o700)
        _detach(tmp_path)


def test_no_writable_dir_at_all_never_raises(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        install_process_log(locked / "a", "gateway.log", "INFO", fallback_dir=locked / "b")
    finally:
        locked.chmod(0o700)
        _detach(tmp_path)
