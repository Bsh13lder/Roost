"""Log files rotate by size and keep a few old copies."""

import logging
from logging.handlers import RotatingFileHandler

from roost.keeper.proxy import EgressProxy
from roost.log_rotation import LOG_BACKUP_COUNT, LOG_MAX_BYTES, install_process_log, rotating_handler


def test_rotating_handler_config(tmp_path):
    handler = rotating_handler(tmp_path / "logs" / "x.log")
    try:
        assert isinstance(handler, RotatingFileHandler)
        assert handler.maxBytes == LOG_MAX_BYTES > 0
        assert handler.backupCount == LOG_BACKUP_COUNT >= 2
        assert (tmp_path / "logs").is_dir()
    finally:
        handler.close()


def test_install_process_log_is_idempotent_and_writes(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        install_process_log(tmp_path, "gateway.log", "INFO")
        install_process_log(tmp_path, "gateway.log", "INFO")
        added = [h for h in root.handlers if h not in before]
        assert len(added) == 1 and isinstance(added[0], RotatingFileHandler)
        logging.getLogger("roost.test").info("hello rotating")
        added[0].flush()
        assert "hello rotating" in (tmp_path / "gateway.log").read_text()
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()


def test_proxy_refusal_log_rotates(tmp_path):
    proxy = EgressProxy(database_dir=tmp_path)
    handler = proxy._refusal_handler
    assert isinstance(handler, RotatingFileHandler)
    assert handler.maxBytes == LOG_MAX_BYTES
    proxy._log_refusal("evil.test", ["10.0.0.1"], 443, "private")
    assert '"host": "evil.test"' in (tmp_path / "proxy.log").read_text()
    handler.close()


def test_logs_dir_sits_next_to_data(tmp_path):
    from roost.log_rotation import logs_dir_for

    assert logs_dir_for(tmp_path / "data") == tmp_path / "logs"
