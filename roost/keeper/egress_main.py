"""Entry point of the ``roost-egress`` container (``docker/egress/Dockerfile``).

Computers sit on internal Docker networks with no route out. This proxy is the one thing attached to those
networks and to ``roost-out``. It binds ``0.0.0.0:3128`` *inside its own network namespace*; no port is published,
so the Mac never sees it. Its address policy (``roost.keeper.proxy``) refuses every private range, so a computer
cannot reach another computer, the gateway or the keeper through it. It refuses to start anywhere else.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from roost.constants import EGRESS_PORT
from roost.keeper.proxy import EgressProxy

_GUARD_ENV = "ROOST_IN_EGRESS"
_LISTEN_HOST = "0.0.0.0"   # inside the container only; see the module docstring


async def serve(stop: asyncio.Event) -> None:
    proxy = EgressProxy(host=_LISTEN_HOST, port=EGRESS_PORT, database_dir=None)
    await proxy.start()
    try:
        await stop.wait()
    finally:
        await proxy.stop()


def main() -> int:
    if os.environ.get(_GUARD_ENV) != "1":
        sys.stderr.write("roost-egress: this proxy only runs inside the roost-egress container.\n")
        return 2
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    async def run() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await serve(stop)

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
