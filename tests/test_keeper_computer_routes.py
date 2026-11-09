"""The keeper's computer routes over TestClient: a fake docker runner and in-memory pipes, no docker."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from roost.config import RoostConfig
from roost.desk.signing import signed_headers
from roost.keeper import computers
from roost.keeper.app import create_app
from roost.keeper.computer_room import ComputerRoom
from roost.keeper.computers import ComputerManager
from roost.keeper.workspaces import _RunOutcome

_SECRET = "k" * 32
BOT = str(uuid.uuid4())
OTHER = str(uuid.uuid4())
PLENTY_MB = 6000


class DockerFake:
    """Answers every docker call; boots at once; reports plenty of free memory."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fail: dict[str, _RunOutcome] = {}

    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        argv = list(argv)
        self.calls.append(argv)
        if argv[1] == "info":
            return _RunOutcome(0, f"{8000 * 1024 * 1024}\n".encode(), b"", False)
        if argv[1] == "stats":
            return _RunOutcome(0, f"{8000 - PLENTY_MB}MiB / 8GiB\n".encode(), b"", False)
        for key, outcome in self.fail.items():
            if key in " ".join(argv):
                return outcome
        return _RunOutcome(0, b"", b"", False)


class FakeNetworks:
    async def ensure_egress(self) -> None: ...
    async def ensure_bot_network(self, bot_id: str) -> None: ...
    async def remove_bot_network(self, bot_id: str) -> None: ...


class MemPipe:
    """An ExecPipe stand-in: what the keeper writes lands in ``written``; ``feed`` is what the computer says."""

    def __init__(self, argv) -> None:
        self.argv = list(argv)
        self.written: list[bytes] = []
        self.closed = False
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    def feed(self, data: bytes) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    async def write(self, data: bytes) -> None:
        self.written.append(data)

    async def read(self) -> bytes:
        return await self._queue.get()

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret=_SECRET)


@pytest.fixture
def docker() -> DockerFake:
    return DockerFake()


@pytest.fixture
def pipes() -> list[MemPipe]:
    return []


@pytest.fixture
def client(config, docker, pipes) -> TestClient:
    app = create_app(config)
    app.state.computers = ComputerManager(config, FakeNetworks(), runner=docker)
    app.state.room = ComputerRoom(app.state.computers, runner=docker)

    async def open_pipe(argv):
        pipe = MemPipe(argv)
        pipes.append(pipe)
        return pipe

    app.state.open_pipe = open_pipe
    return TestClient(app)


def _post(client: TestClient, path: str, payload: dict | bytes = b"{}", *, sign: bool = True):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = signed_headers(_SECRET, "POST", path, body) if sign else {}
    return client.post(path, headers=headers, content=body)


def _start(client: TestClient, bot_id: str = BOT, busy: list[str] | None = None):
    return _post(client, f"/desks/{bot_id}/computer/start", {"busy": busy or []})


def _audit(config: RoostConfig) -> list[dict]:
    path = config.database_dir / "keeper-audit.log"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _closed_with(connect) -> int:
    with pytest.raises(WebSocketDisconnect) as caught:
        with connect() as ws:
            ws.receive_bytes()
    return caught.value.code


@pytest.mark.parametrize("verb", ["start", "attach", "pause", "stop"])
def test_unsigned_is_401(client, verb):
    assert _post(client, f"/desks/{BOT}/computer/{verb}", sign=False).status_code == 401


@pytest.mark.parametrize("verb", ["start", "attach", "pause", "stop"])
def test_a_bad_bot_id_is_400(client, verb):
    assert _post(client, f"/desks/not-a-uuid/computer/{verb}").status_code == 400


def test_an_extra_field_is_422(client):
    assert _post(client, f"/desks/{BOT}/computer/start", {"busy": [], "image": "evil"}).status_code == 422
    assert _post(client, f"/desks/{BOT}/computer/pause", {"x": 1}).status_code == 422
    assert _post(client, f"/desks/{BOT}/computer/start", {"busy": ["nope"]}).status_code == 422
    assert _post(client, f"/desks/{BOT}/computer/start", {"busy": [OTHER] * 51}).status_code == 422


def test_start_answers_tokens(client):
    response = _start(client, busy=[OTHER])
    assert response.status_code == 200
    body = response.json()
    assert body["computer"] == "running" and body["cdp_token"] and body["vnc_token"]
    attached = _post(client, f"/desks/{BOT}/computer/attach").json()
    assert attached["cdp_token"] == body["cdp_token"] and attached["vnc_token"] != body["vnc_token"]


def test_start_answers_no_room_with_409(client, docker):
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for bot_id in ids:
        assert _start(client, bot_id).status_code == 200
    response = _start(client, BOT, busy=ids)
    assert (response.status_code, response.json()) == (409, {"detail": "no_room"})
    # without busy bots the least recently used one gives way
    assert _start(client, BOT).status_code == 200
    assert client.app.state.computers.state(ids[0]) == "stopped"


def test_a_failed_docker_run_is_a_plain_500(client, docker):
    docker.fail["docker run"] = _RunOutcome(1, b"", b"secret detail", False)
    response = _start(client)
    assert response.status_code == 500 and "secret detail" not in response.text


def test_attach_never_wakes_a_paused_computer(client, docker):
    _start(client)
    assert _post(client, f"/desks/{BOT}/computer/pause").json() == {"computer": "paused"}
    docker.calls.clear()
    response = _post(client, f"/desks/{BOT}/computer/attach")
    assert (response.status_code, response.json()["detail"]) == (409, "asleep")
    assert not [c for c in docker.calls if c[1] in ("unpause", "start", "run")]


def test_pause_and_stop_answer_the_state(client):
    _start(client)
    assert _post(client, f"/desks/{BOT}/computer/stop").json() == {"computer": "stopped"}
    assert _post(client, f"/desks/{BOT}/computer/pause").json() == {"computer": "stopped"}
    assert _post(client, f"/desks/{OTHER}/computer/stop").json() == {"computer": "absent"}


def test_the_desk_status_says_the_computer_state(client):
    path = f"/desks/{BOT}"
    get = lambda: client.get(path, headers=signed_headers(_SECRET, "GET", path, b""))  # noqa: E731
    assert get().json()["computer"] == "absent"
    _start(client)
    assert get().json()["computer"] == "running"


def _vnc(client, token, bot_id=BOT):
    return client.websocket_connect(f"/desks/{bot_id}/computer/vnc", headers={"x-roost-desk-token": token})


def test_vnc_socket_refuses_a_wrong_token_with_4401(client):
    _start(client)
    assert _closed_with(lambda: _vnc(client, "wrong")) == 4401
    assert _closed_with(lambda: client.websocket_connect(f"/desks/{BOT}/computer/vnc")) == 4401


def test_sockets_refuse_a_bad_id_with_4400_and_a_sleeping_computer_with_4404(client):
    assert _closed_with(lambda: _vnc(client, "x", "nope")) == 4400
    assert _closed_with(lambda: _vnc(client, "x")) == 4404
    token = _start(client).json()["vnc_token"]
    _post(client, f"/desks/{BOT}/computer/pause")
    assert _closed_with(lambda: _vnc(client, token)) == 4404


def test_the_other_bots_token_does_not_open_this_bots_computer(client):
    _start(client)
    other_token = _start(client, OTHER).json()["vnc_token"]
    assert _closed_with(lambda: _vnc(client, other_token)) == 4401


def test_vnc_socket_relays_bytes_both_ways(client, pipes):
    token = _start(client).json()["vnc_token"]
    with _vnc(client, token) as ws:
        ws.send_bytes(b"RFB 003.008\n\x00\xff")
        for _ in range(100):
            if pipes and pipes[0].written:
                break
            time.sleep(0.02)
        assert pipes[0].written == [b"RFB 003.008\n\x00\xff"]
        assert pipes[0].argv == computers.build_pipe_argv(BOT, "vnc")
        pipes[0].feed(b"\x01\x02\x03")
        assert ws.receive_bytes() == b"\x01\x02\x03"
    for _ in range(100):
        if pipes[0].closed:
            break
        time.sleep(0.02)
    assert pipes[0].closed
    assert BOT not in client.app.state.room.held()


def test_the_relay_only_ever_execs_into_the_target_bots_container(client, pipes):
    token = _start(client).json()["vnc_token"]
    _start(client, OTHER)
    with _vnc(client, token):
        pass
    for pipe in pipes:
        assert f"roost-computer-{BOT}" in pipe.argv and f"roost-computer-{OTHER}" not in pipe.argv


def _ticket(client, bot_id=BOT) -> str:
    return _post(client, f"/desks/{bot_id}/computer/attach").json()["vnc_token"]


def test_a_fourth_vnc_socket_is_refused_with_4429(client):
    _start(client)
    with _vnc(client, _ticket(client)), _vnc(client, _ticket(client)), _vnc(client, _ticket(client)):
        assert _closed_with(lambda: _vnc(client, _ticket(client))) == 4429


def test_a_vnc_ticket_opens_one_socket_only(client):
    ticket = _start(client).json()["vnc_token"]
    with _vnc(client, ticket):
        pass
    assert _closed_with(lambda: _vnc(client, ticket)) == 4401


def test_every_attach_mints_a_new_ticket(client):
    _start(client)
    assert _ticket(client) != _ticket(client)


def test_an_expired_vnc_ticket_is_4401(client):
    ticket = _start(client).json()["vnc_token"]
    clock = client.app.state.computers._clock
    client.app.state.computers._clock = lambda: clock() + 3600
    assert _closed_with(lambda: _vnc(client, ticket)) == 4401


def test_cdp_socket_relays_nul_framed_messages_as_text(client, pipes):
    token = _start(client).json()["cdp_token"]
    headers = {"x-roost-desk-token": token}
    with client.websocket_connect(f"/desks/{BOT}/computer/cdp", headers=headers) as ws:
        ws.send_text('{"id":1,"method":"Browser.getVersion"}')
        for _ in range(100):
            if pipes and pipes[0].written:
                break
            time.sleep(0.02)
        assert pipes[0].written == [b'{"id":1,"method":"Browser.getVersion"}\0']
        pipes[0].feed(b'{"id":1,"res')
        pipes[0].feed(b'ult":{}}\0{"method":"x"}\0')
        assert ws.receive_text() == '{"id":1,"result":{}}'
        assert ws.receive_text() == '{"method":"x"}'


def test_cdp_socket_wrong_token_4401_and_the_vnc_token_does_not_fit(client):
    tokens = _start(client).json()
    for token in ("bad", tokens["vnc_token"]):
        headers = {"x-roost-desk-token": token}
        assert _closed_with(lambda: client.websocket_connect(f"/desks/{BOT}/computer/cdp", headers=headers)) == 4401


def test_a_newer_cdp_client_takes_over_with_4409(client):
    token = _start(client).json()["cdp_token"]
    headers = {"x-roost-desk-token": token}
    with client.websocket_connect(f"/desks/{BOT}/computer/cdp", headers=headers) as first:
        with client.websocket_connect(f"/desks/{BOT}/computer/cdp", headers=headers) as second:
            with pytest.raises(WebSocketDisconnect) as caught:
                first.receive_text()
            assert caught.value.code == 4409
            # let each handler unwind before the harness force-cancels it (as test_pipe_relay does)
            first.close()
            time.sleep(0.2)
            second.close()
            time.sleep(0.2)


def test_retire_removes_the_computer_too(client, docker):
    _start(client)
    docker.calls.clear()
    path = f"/desks/{BOT}"
    response = client.delete(path, headers=signed_headers(_SECRET, "DELETE", path, b""))
    assert response.status_code == 200
    assert computers.build_remove_argv(BOT) in docker.calls
    assert computers.build_volume_remove_argv(BOT) in docker.calls
    assert client.app.state.computers.state(BOT) == "absent"


def test_retire_fails_loudly_when_the_computer_cannot_be_removed(client, docker):
    docker.fail["docker volume rm"] = _RunOutcome(1, b"", b"volume is in use", False)
    path = f"/desks/{BOT}"
    response = client.delete(path, headers=signed_headers(_SECRET, "DELETE", path, b""))
    assert response.status_code == 500 and "volume is in use" not in response.text


def test_the_audit_has_no_bytes(client, config, pipes):
    tokens = _start(client).json()
    with _vnc(client, tokens["vnc_token"]) as ws:
        ws.send_bytes(b"SECRET-KEYSTROKES")
        time.sleep(0.2)
    time.sleep(0.2)
    text = (config.database_dir / "keeper-audit.log").read_text()
    for forbidden in ("SECRET-KEYSTROKES", tokens["vnc_token"], tokens["cdp_token"], _SECRET):
        assert forbidden not in text
    entries = _audit(config)
    assert {"action": "computer_start", "bot_id": BOT, "result": "ok"}.items() <= next(
        e for e in entries if e["action"] == "computer_start").items()
    assert [e["result"] for e in entries if e["action"] == "computer_vnc"] == ["connected", "closed"]
    assert all(set(e) <= {"action", "bot_id", "result", "ts"} for e in entries)
