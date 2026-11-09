"""Open in your main Brave, keeper side (stuck flow, Task 6; design §3, R8).

``POST /desks/{bot_id}/main-browser/open`` is exercised against the real
keeper app over ``TestClient``, with a recording runner in place of
``/usr/bin/open``. No test here ever opens a real browser (Global
Constraints: "Tests never run it: they inject a fake runner"). The
``MainBrowserOpener`` tests at the bottom cover the opener itself. They
include its real default runner, with ``asyncio.create_subprocess_exec``
patched out, plus one plain ``sleep`` to prove a hung process is killed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import roost.keeper.main_browser as main_browser_module
from roost.config import RoostConfig
from roost.constants import MAIN_BROWSER_OPEN_TIMEOUT_S, MAIN_BROWSER_URL_MAX_CHARS
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app
from roost.keeper.main_browser import MainBrowserOpener, MainBrowserOpenError, _run_open

_SECRET = "k" * 32
_VALID_BOT_ID = "77777777-7777-4777-8777-777777777777"
_OPEN_PATH = f"/desks/{_VALID_BOT_ID}/main-browser/open"
_URL = "https://example.com/"
_OPEN_ARGV = ["/usr/bin/open", "-a", "Brave Browser"]


class _RecordingRunner:
    """Stands in for ``/usr/bin/open``. It records each ``(argv, timeout)``
    and answers ``exit_code``, or raises ``error`` when one is given. It never
    runs anything."""

    def __init__(self, exit_code: int = 0, error: BaseException | None = None) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self._exit_code = exit_code
        self._error = error

    async def __call__(self, argv, timeout_s):
        self.calls.append((list(argv), timeout_s))
        if self._error is not None:
            raise self._error
        return self._exit_code


class _FakeProcess:
    """What the patched ``asyncio.create_subprocess_exec`` hands back.
    ``wait()`` answers ``returncode`` at once, or, with ``hang``, only
    after ``kill()``."""

    def __init__(self, returncode: int = 0, *, hang: bool = False) -> None:
        self.returncode = returncode
        self.killed = False
        self._done = asyncio.Event()
        if not hang:
            self._done.set()

    async def wait(self) -> int:
        await self._done.wait()
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._done.set()


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
    )


@pytest.fixture
def runner() -> _RecordingRunner:
    return _RecordingRunner()


def _client(config: RoostConfig, runner: _RecordingRunner) -> TestClient:
    app = create_app(config)
    app.state.main_browser = MainBrowserOpener(runner=runner)
    return TestClient(app)


@pytest.fixture
def client(config: RoostConfig, runner: _RecordingRunner) -> TestClient:
    return _client(config, runner)


def _signed_post(client: TestClient, path: str, payload: dict | bytes):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = signed_headers(_SECRET, "POST", path, body)
    return client.post(path, headers=headers, content=body)


def _audit_entries(config: RoostConfig) -> list[dict]:
    path = config.database_dir / "keeper-audit.log"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [json.loads(line) for line in lines]


def _main_browser_results(config: RoostConfig) -> list[str]:
    return [entry["result"] for entry in _audit_entries(config) if entry["action"] == "main_browser_open"]


def _patch_exec(monkeypatch: pytest.MonkeyPatch, process: _FakeProcess) -> list[tuple[tuple, dict]]:
    calls: list[tuple[tuple, dict]] = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return process

    monkeypatch.setattr(main_browser_module.asyncio, "create_subprocess_exec", fake_exec)
    return calls


# -- the route -----------------------------------------------------------------


def test_open_runs_open_a_brave_browser_with_the_checked_url(
    client: TestClient, runner: _RecordingRunner, config: RoostConfig
):
    response = _signed_post(client, _OPEN_PATH, {"url": _URL})
    assert (response.status_code, response.json()) == (200, {"opened": True})
    assert runner.calls == [([*_OPEN_ARGV, _URL], MAIN_BROWSER_OPEN_TIMEOUT_S)]
    assert _main_browser_results(config) == ["ok"]


def test_open_passes_on_the_canonical_address_not_the_raw_one(client: TestClient, runner: _RecordingRunner):
    response = _signed_post(client, _OPEN_PATH, {"url": "https://EXAMPLE.com/Path?q=1"})
    assert response.status_code == 200
    assert runner.calls[0][0] == [*_OPEN_ARGV, "https://example.com/Path?q=1"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "http://127.0.0.1/"])
def test_a_refused_address_is_400_and_never_opened(
    client: TestClient, runner: _RecordingRunner, config: RoostConfig, url: str
):
    response = _signed_post(client, _OPEN_PATH, {"url": url})
    assert (response.status_code, response.json()) == (400, {"detail": "that address can't be opened"})
    assert runner.calls == []
    assert _main_browser_results(config) == ["refused"]


def test_open_is_signed(client: TestClient, runner: _RecordingRunner):
    response = client.post(_OPEN_PATH, content=json.dumps({"url": _URL}).encode())
    assert response.status_code == 401
    assert runner.calls == []


def test_an_extra_body_field_is_422_and_never_opened(client: TestClient, runner: _RecordingRunner):
    response = _signed_post(client, _OPEN_PATH, {"url": _URL, "app": "Safari"})
    assert response.status_code == 422
    assert runner.calls == []


@pytest.mark.parametrize("payload", [{}, {"url": ""}, b"not json", b""])
def test_a_missing_or_empty_address_is_422(client: TestClient, runner: _RecordingRunner, payload):
    response = _signed_post(client, _OPEN_PATH, payload)
    assert response.status_code == 422
    assert runner.calls == []


def test_an_address_over_the_limit_is_422_and_never_echoed_back(client: TestClient, runner: _RecordingRunner):
    url = "https://example.com/" + "a" * MAIN_BROWSER_URL_MAX_CHARS
    response = _signed_post(client, _OPEN_PATH, {"url": url})
    assert response.status_code == 422
    assert "example.com" not in response.text
    assert runner.calls == []


def test_a_bad_bot_id_is_400(client: TestClient, runner: _RecordingRunner):
    response = _signed_post(client, "/desks/..etc/main-browser/open", {"url": _URL})
    assert (response.status_code, response.json()) == (400, {"detail": "bot_id must be a UUID4"})
    assert runner.calls == []


def test_a_failing_open_is_a_clean_500_with_a_fixed_detail(config: RoostConfig):
    response = _signed_post(_client(config, _RecordingRunner(exit_code=1)), _OPEN_PATH, {"url": _URL})
    assert (response.status_code, response.json()) == (500, {"detail": "failed to open the main browser"})
    assert _main_browser_results(config) == ["error"]


def test_the_audit_log_and_the_logs_never_hold_the_address(config: RoostConfig, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG)
    private_url = "https://private-bank.example/statement?id=12345"
    working = _client(config, _RecordingRunner())
    _signed_post(working, _OPEN_PATH, {"url": private_url})
    _signed_post(working, _OPEN_PATH, {"url": "javascript:alert('private-bank')"})
    _signed_post(_client(config, _RecordingRunner(exit_code=1)), _OPEN_PATH, {"url": private_url})

    audit_text = (config.database_dir / "keeper-audit.log").read_text(encoding="utf-8")
    assert _main_browser_results(config) == ["ok", "refused", "error"]
    assert "private-bank" not in audit_text
    assert "private-bank" not in caplog.text
    assert all(set(entry) == {"action", "bot_id", "result", "ts"} for entry in _audit_entries(config))


# -- MainBrowserOpener ---------------------------------------------------------


async def test_the_opener_runs_the_fixed_argv_plus_the_address_with_its_timeout():
    runner = _RecordingRunner()
    await MainBrowserOpener(runner=runner).open(_URL)
    assert runner.calls == [([*_OPEN_ARGV, _URL], MAIN_BROWSER_OPEN_TIMEOUT_S)]


async def test_a_non_zero_exit_is_an_open_error():
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener(runner=_RecordingRunner(exit_code=1)).open(_URL)


async def test_a_timeout_is_an_open_error():
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener(runner=_RecordingRunner(error=asyncio.TimeoutError())).open(_URL)


async def test_an_open_that_cannot_start_is_an_open_error():
    missing = FileNotFoundError(2, "No such file or directory", "/usr/bin/open")
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener(runner=_RecordingRunner(error=missing)).open(_URL)


async def test_the_default_runner_execs_an_argv_list_with_no_shell(monkeypatch: pytest.MonkeyPatch):
    calls = _patch_exec(monkeypatch, _FakeProcess(returncode=0))
    await MainBrowserOpener().open(_URL)
    assert calls == [
        ((*_OPEN_ARGV, _URL), {"stdout": asyncio.subprocess.DEVNULL, "stderr": asyncio.subprocess.DEVNULL})
    ]


async def test_the_default_runner_reports_a_failed_open(monkeypatch: pytest.MonkeyPatch):
    _patch_exec(monkeypatch, _FakeProcess(returncode=1))
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener().open(_URL)


async def test_the_default_runner_kills_open_when_it_hangs(monkeypatch: pytest.MonkeyPatch):
    process = _FakeProcess(hang=True)
    _patch_exec(monkeypatch, process)
    monkeypatch.setattr(main_browser_module, "MAIN_BROWSER_OPEN_TIMEOUT_S", 0.05)
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener().open(_URL)
    assert process.killed is True


async def test_the_default_runner_turns_a_missing_open_into_an_open_error(monkeypatch: pytest.MonkeyPatch):
    async def missing(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "/usr/bin/open")

    monkeypatch.setattr(main_browser_module.asyncio, "create_subprocess_exec", missing)
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener().open(_URL)


async def test_the_real_default_runner_kills_a_process_that_hangs():
    """A plain system command, never ``open`` or Brave. This is the same style
    as ``test_run_docker_kills_and_reports_timed_out_on_a_slow_command``."""
    with pytest.raises(asyncio.TimeoutError):
        await _run_open(["sleep", "5"], 0.1)
