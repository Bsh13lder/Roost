"""Entry point: ``uv run python -m roost.keeper``.

Runs the keeper's FastAPI app under uvicorn on ``127.0.0.1:18801`` and
the egress proxy on ``127.0.0.1:18803`` (``config.proxy_port``) side by
side in the same process and the same asyncio event loop — a separate
host process from the gateway (``127.0.0.1:18800``). The proxy is
started first (so it's already listening before any desk route could
hand a bot a browser to launch) and stopped only after uvicorn's own
server has finished serving.
"""

from __future__ import annotations

import asyncio
import os

import uvicorn

from roost.config import load_config
from roost.constants import KEEPER_PORT
from roost.keeper.app import create_app
from roost.keeper.awake import keep_awake
from roost.log_rotation import install_process_log, logs_dir_for
from roost.keeper.proxy import EgressProxy


async def _run() -> None:
    config = load_config()
    install_process_log(logs_dir_for(config.database_dir), "keeper-app.log", config.log_level,
                        fallback_dir=config.database_dir / "logs")
    keep_awake(os.getpid())          # the Mac stays up (idle sleep off) while the keeper runs
    app = create_app(config)
    proxy = EgressProxy(host=config.host, port=config.proxy_port, database_dir=config.database_dir)
    await proxy.start()
    try:
        server = uvicorn.Server(
            uvicorn.Config(app, host=config.host, port=KEEPER_PORT, log_level=config.log_level.lower())
        )
        await server.serve()
    finally:
        await proxy.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
