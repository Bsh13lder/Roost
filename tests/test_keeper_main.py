"""``roost.keeper.__main__`` wiring: must bind the keeper's own port
(18801), never the gateway's ``config.port`` (18800) — the two are
separate processes, and a copy-paste of the wrong field would silently
make the keeper unreachable on its contract port. Also: the egress
proxy (Task 7) must be started alongside uvicorn, on ``config.host`` /
``config.proxy_port``, and stopped once uvicorn finishes serving.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import roost.keeper.__main__ as keeper_main
from roost.config import RoostConfig
from roost.constants import KEEPER_PORT


def test_main_runs_uvicorn_on_the_keeper_port_and_starts_the_egress_proxy(tmp_path):
    config = RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret="y" * 32,
        port=18800,  # the gateway's port — must NOT be what we bind to
    )

    mock_proxy = MagicMock()
    mock_proxy.start = AsyncMock()
    mock_proxy.stop = AsyncMock()

    with (
        patch("roost.keeper.__main__.load_config", return_value=config) as mock_load_config,
        patch("roost.keeper.__main__.EgressProxy", return_value=mock_proxy) as mock_proxy_cls,
        patch("roost.keeper.__main__.uvicorn.Server") as mock_server_cls,
    ):
        mock_server_cls.return_value.serve = AsyncMock()
        keeper_main.main()

    mock_load_config.assert_called_once()

    mock_proxy_cls.assert_called_once_with(
        host="127.0.0.1", port=config.proxy_port, database_dir=config.database_dir
    )
    mock_proxy.start.assert_awaited_once()
    mock_proxy.stop.assert_awaited_once()

    assert mock_server_cls.call_count == 1
    (uvicorn_config,), _ = mock_server_cls.call_args
    assert uvicorn_config.host == "127.0.0.1"
    assert uvicorn_config.port == KEEPER_PORT
    assert uvicorn_config.port != config.port
    mock_server_cls.return_value.serve.assert_awaited_once()
