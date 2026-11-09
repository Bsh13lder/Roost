"""Entry point: ``python -m roost.voice_host`` — the voice service on ``127.0.0.1:18804`` (run by launchd as
``app.roost.voice``, see ``roost/voice_host/launchd.py``). ``ROOST_VOICE=fake`` serves the fake engine instead of the
models, for trying the wiring without them."""

from __future__ import annotations

import logging

import uvicorn

from roost.config import load_config
from roost.constants import VOICE_PORT
from roost.log_rotation import install_process_log, logs_dir_for
from roost.voice_host.app import TIMING_LOGGER, create_app
from roost.voice_host.engine import Engine, FakeEngine

_LOOPBACK = "127.0.0.1"


def _engine(mode: str) -> Engine:
    if mode == "fake":
        return FakeEngine()
    from roost.voice_host.mlx_engine import MlxEngine

    return MlxEngine()


def main() -> None:
    config = load_config()
    install_process_log(logs_dir_for(config.database_dir), "voice-app.log", config.log_level,
                        fallback_dir=config.database_dir / "logs")
    logging.getLogger(TIMING_LOGGER).setLevel(logging.INFO)   # heard/spoke/warm timings, whatever the log level
    app = create_app(config.voice_secret, _engine(config.voice_mode))
    uvicorn.run(app, host=_LOOPBACK, port=VOICE_PORT, log_level=config.log_level.lower())


if __name__ == "__main__":
    main()
