"""Real-desk smoke test — ``make smoke`` (Task 13).

Boots a REAL keeper (real Brave browser over CDP, real Docker workspace
containers, real egress proxy) and a real gateway, end to end, with no
pytest involved: register the single account, create a bot, start its
browser, run one real turn loop whose model is scripted to call
``open_page("https://example.com")``, exec a workspace command, delete
the bot, and confirm its desk (container + on-disk directory) is really
gone. Prints a PASS/FAIL table and exits 1 if anything failed.

Never run by pytest: this touches a real Brave window, the real Docker
daemon, and (for the one ``open_page`` call) the real network — tests
use ``ROOST_DESK=fake``/``ROOST_MODEL=scripted`` exclusively
(``tests/conftest.py``) and never import this module.

Ruling 5 (controller, 2026-10-13): what proves the page's real text
reached the model is not the bot's reply text (the model is free to say
whatever it wants back) but the model's SECOND request — recorded by
``_RecordingScriptedModel`` below, which wraps the real ``ScriptedModel``
from ``roost.llm.scripted`` rather than reimplementing it — actually
carrying "Example Domain" inside the tool-result turn the first step's
``open_page`` call produced. Taintedness is checked on the STORED
message's ``tainted`` flag, not on the reply text. If this environment
has no outbound internet, that one check fails loudly (never faked as a
pass) while every other step still runs and is reported on its own.

Both servers run as real ``uvicorn`` listeners on the real ports
(18800/18801, plus the egress proxy on 18803) inside THIS process rather
than as separate subprocesses — the keeper's own real ``BraveLauncher``/
``WorkspaceManager``/``EgressProxy`` still spawn a real Brave process and
real Docker containers either way; running both apps in one process just
means this script can inject a model instance directly (see above) and
tear everything down deterministically in one place.

The page the bot opens and the text expected back from it can both be
overridden with env vars, for running the same real-desk steps against a
different target without editing this file:

  * ``ROOST_SMOKE_URL`` — the page ``open_page`` is told to visit
    (default ``https://example.com``).
  * ``ROOST_SMOKE_EXPECT`` — the substring Ruling 5's check looks for in
    the model's second request (default ``"Example Domain"``).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

import httpx
import uvicorn

# So `uv run python scripts/smoke.py` finds the `roost` package without
# needing it importable from the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roost.config import load_config
from roost.constants import GATEWAY_PORT, KEEPER_PORT, KEEPER_RETIRE_REQUEST_TIMEOUT_S, PROXY_PORT
from roost.dev_guards import check_data_isolation
from roost.gateway.app import create_app as create_gateway_app
from roost.keeper.app import create_app as create_keeper_app
from roost.keeper.proxy import EgressProxy
from roost.llm.scripted import ScriptedModel
from roost.llm.types import ModelEvent, ModelRequest, TextDelta, ToolCallRequested, TurnDone
from roost.talk.runner import TurnRunner

# Overridable per the module docstring above -- defaults preserve the
# original "real example.com" smoke run.
_SMOKE_URL = os.environ.get("ROOST_SMOKE_URL", "https://example.com")
_SMOKE_EXPECT = os.environ.get("ROOST_SMOKE_EXPECT", "Example Domain")
_PORTS_TO_CHECK = (GATEWAY_PORT, KEEPER_PORT, PROXY_PORT)
_FORBIDDEN_PORTS = (18789, 9222)  # the old app and its Brave bridge — never these
_USERNAME = "smoke"
_PASSWORD = "smoke-test-password-1"
_AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}
_TURN_TIMEOUT_S = 40.0
_OVERALL_TIMEOUT_S = 240.0
_SERVER_READY_TIMEOUT_S = 10.0
_SERVER_SHUTDOWN_TIMEOUT_S = 10.0

T = TypeVar("T")


class SmokeFailure(RuntimeError):
    """A single smoke step's assertion failed — caught by ``_check``/
    ``_check_sync`` and turned into one FAIL row, never left to crash
    the rest of the run."""


@dataclass(frozen=True)
class _Result:
    name: str
    ok: bool
    detail: str = ""


class _RecordingScriptedModel(ScriptedModel):
    """``ScriptedModel`` (``roost.llm.scripted`` — the same model every
    test and ``ROOST_MODEL=scripted`` run uses), but keeping every
    ``ModelRequest`` it was asked to stream for. The turn loop
    (``roost/talk/turn.py``) calls ``model.stream()`` once per step, each
    time with the conversation so far — so ``requests[1]`` is the request
    built AFTER the first step's tool call result was folded back in,
    which is what Ruling 5 checks for the real page's text."""

    def __init__(self, script: list[tuple[ModelEvent, ...]]) -> None:
        super().__init__(script=script, echo=False)
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest):
        self.requests.append(request)
        async for event in super().stream(request):
            yield event


@dataclass
class _Ctx:
    """Everything one smoke run needs to carry from setup through the
    steps to teardown — one instance per run, never shared/reused."""

    data_dir: Path
    desks_dir: Path
    proxy: EgressProxy
    keeper_server: uvicorn.Server
    keeper_task: "asyncio.Task[None]"
    gateway_server: uvicorn.Server
    gateway_task: "asyncio.Task[None]"
    client: httpx.AsyncClient
    model: _RecordingScriptedModel
    results: list[_Result] = field(default_factory=list)
    bot_id: str | None = None
    bot_deleted: bool = False


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def _require_ports_free() -> None:
    assert not set(_PORTS_TO_CHECK) & set(_FORBIDDEN_PORTS), "a Roost port collides with a forbidden one"
    busy = [p for p in _PORTS_TO_CHECK if not _port_is_free("127.0.0.1", p)]
    if busy:
        raise SmokeFailure(
            f"port(s) {busy} already in use — refusing to start (never reuse "
            f"{list(_FORBIDDEN_PORTS)} either; this is a safety abort, not a retry loop)"
        )


def _assert_isolated(data_dir: Path, desks_dir: Path, env: dict[str, str]) -> None:
    """Reuses ``roost.dev_guards`` (the same tripwire ``tests/conftest.py``
    runs for pytest) so this script can never silently fall back onto a
    real data directory either."""
    violation = check_data_isolation(data_dir, desks_dir, load_config=lambda: load_config(env))
    if violation is not None:
        raise SmokeFailure(f"refusing to run: {violation}")


async def _wait_until_listening(host: str, port: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _port_is_free(host, port):
            return
        await asyncio.sleep(0.05)
    raise SmokeFailure(f"{host}:{port} never started listening within {timeout}s")


# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------


def _build_script() -> list[tuple[ModelEvent, ...]]:
    """Two scripted steps: call ``open_page`` on the real URL, then (once
    the tool result is back in context) answer and stop — never more
    than one tool call, so the turn loop's step limit is never a factor."""
    return [
        (ToolCallRequested(id="call-1", name="open_page", arguments={"url": _SMOKE_URL}), TurnDone("tool_use")),
        (TextDelta("Checked the page."), TurnDone("end_turn")),
    ]


async def _setup() -> _Ctx:
    """Starts every real resource one smoke run needs, in order -- but if
    any step after the first fails (e.g. ``_wait_until_listening`` times
    out waiting for the keeper, with the proxy already bound, or for the
    gateway, with the proxy AND keeper already bound), nothing already
    started is left behind.

    Fix round 1, finding 1: this used to start the proxy and the
    keeper's/gateway's real ``uvicorn.Server`` one at a time with no
    cleanup on a partial failure -- a timed-out ``_wait_until_listening``
    propagated straight out of here, ``main()`` never got a ``_Ctx`` to
    call ``_teardown()`` on, and the already-bound ports/processes leaked
    with no record anywhere. ``AsyncExitStack`` tracks exactly what was
    started so far; on any exception it unwinds everything already
    pushed (most-recent first) before the exception propagates. On
    success, ``pop_all()`` empties the stack without running any of it --
    ownership of that same cleanup work passes to the returned ``_Ctx``,
    which ``main()``'s ``finally`` always hands to ``_teardown()``.
    """
    _require_ports_free()

    data_dir = Path(tempfile.mkdtemp(prefix="roost-smoke-data-"))
    desks_dir = Path(tempfile.mkdtemp(prefix="roost-smoke-desks-"))

    async with contextlib.AsyncExitStack() as cleanup_on_failure:
        cleanup_on_failure.callback(shutil.rmtree, data_dir, ignore_errors=True)
        cleanup_on_failure.callback(shutil.rmtree, desks_dir, ignore_errors=True)

        env = {
            "ROOST_DATA_DIR": str(data_dir),
            "ROOST_DESKS_DIR": str(desks_dir),
            "ROOST_HOST": "127.0.0.1",
            "ROOST_PORT": str(GATEWAY_PORT),
            "ROOST_KEEPER_URL": f"http://127.0.0.1:{KEEPER_PORT}",
            "ROOST_PROXY_PORT": str(PROXY_PORT),
            "ROOST_MODEL": "scripted",
            "ROOST_DESK": "keeper",  # the real desk -- this IS the real-desk smoke
            "ROOST_LOG_LEVEL": "WARNING",
        }
        _assert_isolated(data_dir, desks_dir, env)
        config = load_config(env)

        proxy = EgressProxy(host=config.host, port=config.proxy_port, database_dir=config.database_dir)
        await proxy.start()
        cleanup_on_failure.push_async_callback(proxy.stop)

        keeper_app = create_keeper_app(config)
        keeper_server = uvicorn.Server(
            uvicorn.Config(keeper_app, host=config.host, port=KEEPER_PORT, log_level="warning", access_log=False)
        )
        keeper_task = asyncio.create_task(keeper_server.serve())
        cleanup_on_failure.push_async_callback(_stop_server, keeper_server, keeper_task)
        await _wait_until_listening(config.host, KEEPER_PORT, _SERVER_READY_TIMEOUT_S)

        gateway_app = create_gateway_app(config)
        model = _RecordingScriptedModel(_build_script())
        # Swap in a TurnRunner built around OUR recording model, reusing every
        # other real component `create_app` already wired up -- a public
        # constructor call, not reaching into TurnRunner's private state.
        gateway_app.state.turns = TurnRunner(
            config, gateway_app.state.bots, gateway_app.state.talk, gateway_app.state.events,
            gateway_app.state.desks, model, gateway_app.state.activity_board,
        )
        gateway_server = uvicorn.Server(
            uvicorn.Config(gateway_app, host=config.host, port=config.port, log_level="warning", access_log=False)
        )
        gateway_task = asyncio.create_task(gateway_server.serve())
        cleanup_on_failure.push_async_callback(_stop_server, gateway_server, gateway_task)
        await _wait_until_listening(config.host, config.port, _SERVER_READY_TIMEOUT_S)

        client = httpx.AsyncClient(
            base_url=f"http://{config.host}:{config.port}",
            headers={"Origin": f"http://{config.host}:{config.port}"},
            # Must clear KEEPER_RETIRE_REQUEST_TIMEOUT_S with margin: the
            # gateway's own DELETE /api/bots/{id} route awaits a keeper
            # retire call that can legitimately take that long -- see its
            # docstring (roost/constants.py).
            timeout=KEEPER_RETIRE_REQUEST_TIMEOUT_S + 15.0,
        )
        cleanup_on_failure.push_async_callback(client.aclose)

        ctx = _Ctx(
            data_dir=data_dir, desks_dir=desks_dir, proxy=proxy,
            keeper_server=keeper_server, keeper_task=keeper_task,
            gateway_server=gateway_server, gateway_task=gateway_task,
            client=client, model=model,
        )
        # Everything above started cleanly -- hand ownership of tearing it
        # all down to the returned _Ctx (main()'s finally -> _teardown())
        # instead of running it here.
        cleanup_on_failure.pop_all()
        return ctx


async def _stop_server(server: uvicorn.Server, task: "asyncio.Task[None]") -> None:
    server.should_exit = True
    try:
        await asyncio.wait_for(task, timeout=_SERVER_SHUTDOWN_TIMEOUT_S)
    except asyncio.TimeoutError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _teardown(ctx: _Ctx) -> None:
    """Always runs (``main``'s ``finally``), outside whatever timeout
    bounded the steps themselves, so a step that hung never leaves a
    Brave window, a Docker container or the listening servers behind."""
    if ctx.bot_id is not None and not ctx.bot_deleted:
        # A step before the delete step failed -- best-effort retire the
        # bot's desk anyway so this run never leaks a container/process.
        with contextlib.suppress(Exception):
            await ctx.client.delete(f"/api/bots/{ctx.bot_id}")

    with contextlib.suppress(Exception):
        await ctx.client.aclose()

    await _stop_server(ctx.gateway_server, ctx.gateway_task)
    await _stop_server(ctx.keeper_server, ctx.keeper_task)

    with contextlib.suppress(Exception):
        await ctx.proxy.stop()

    shutil.rmtree(ctx.data_dir, ignore_errors=True)
    shutil.rmtree(ctx.desks_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


async def _register(ctx: _Ctx) -> None:
    r = await ctx.client.post("/api/auth/register", json={"username": _USERNAME, "password": _PASSWORD})
    if r.status_code != 201:
        raise SmokeFailure(f"POST /api/auth/register -> {r.status_code}: {r.text}")


async def _create_bot(ctx: _Ctx) -> str:
    body = {"name": "Scout", "job": "read a web page", "instructions": "", "avatar": _AVATAR}
    r = await ctx.client.post("/api/bots", json=body)
    if r.status_code != 201:
        raise SmokeFailure(f"POST /api/bots -> {r.status_code}: {r.text}")
    return r.json()["id"]


async def _start_browser(ctx: _Ctx, bot_id: str) -> None:
    r = await ctx.client.post(f"/api/bots/{bot_id}/desk/browser/start")
    if r.status_code != 200 or r.json().get("browser") != "running":
        raise SmokeFailure(f"POST .../desk/browser/start -> {r.status_code}: {r.text}")


async def _create_thread(ctx: _Ctx, bot_id: str) -> str:
    r = await ctx.client.post(f"/api/bots/{bot_id}/threads", json={})
    if r.status_code != 201:
        raise SmokeFailure(f"POST .../threads -> {r.status_code}: {r.text}")
    return r.json()["id"]


async def _send_and_await_reply(ctx: _Ctx, thread_id: str) -> None:
    r = await ctx.client.post(
        f"/api/threads/{thread_id}/messages",
        json={"text": f"Open {_SMOKE_URL} and tell me what it says."},
    )
    if r.status_code != 202:
        raise SmokeFailure(f"POST .../messages -> {r.status_code}: {r.text}")

    deadline = time.monotonic() + _TURN_TIMEOUT_S
    while time.monotonic() < deadline:
        messages = (await ctx.client.get(f"/api/threads/{thread_id}/messages")).json()
        if any(m["role"] == "bot" for m in messages):
            return
        await asyncio.sleep(0.2)
    raise SmokeFailure(f"no stored bot reply within {_TURN_TIMEOUT_S}s")


def _assert_second_request_saw_the_page(ctx: _Ctx) -> None:
    """Ruling 5: the proof is the model's SECOND request, not the reply."""
    if len(ctx.model.requests) < 2:
        raise SmokeFailure(
            f"expected >= 2 model requests (the tool call, then the follow-up "
            f"with its result), got {len(ctx.model.requests)}"
        )
    tool_turns = [t for t in ctx.model.requests[1].turns if t.role == "tool"]
    if any(_SMOKE_EXPECT in t.text for t in tool_turns):
        return
    snippet = tool_turns[-1].text[:200] if tool_turns else "(no tool-result turn at all)"
    raise SmokeFailure(
        f"the model's 2nd request did not carry {_SMOKE_EXPECT!r} from the real "
        f"page — most likely this environment has no outbound internet to "
        f"{_SMOKE_URL} (DNS/egress blocked); got instead: {snippet!r}"
    )


async def _assert_last_reply_tainted(ctx: _Ctx, thread_id: str) -> None:
    """Independent of the check above: whether the browser actually
    reached example.com's real content or just an error page, having
    called ``open_page`` at all must still mark the stored reply tainted
    (``roost/talk/turn.py``'s ``_ToolRunner._open_page`` sets this the
    moment the desk call *succeeds*, regardless of what it fetched)."""
    messages = (await ctx.client.get(f"/api/threads/{thread_id}/messages")).json()
    bot_messages = [m for m in messages if m["role"] == "bot"]
    if not bot_messages:
        raise SmokeFailure("no stored bot message to check taintedness on")
    if not bot_messages[-1]["tainted"]:
        raise SmokeFailure(f"stored bot reply has tainted=False: {bot_messages[-1]}")


async def _exec_echo_hi(ctx: _Ctx, bot_id: str) -> None:
    r = await ctx.client.post(f"/api/bots/{bot_id}/desk/workspace/exec", json={"command": "echo hi"})
    if r.status_code != 200:
        raise SmokeFailure(f"POST .../workspace/exec -> {r.status_code}: {r.text}")
    body = r.json()
    if body.get("exit_code") != 0 or body.get("stdout", "").strip() != "hi":
        raise SmokeFailure(f"expected exit_code=0, stdout='hi' -- got {body}")


async def _delete_bot(ctx: _Ctx, bot_id: str) -> None:
    r = await ctx.client.delete(f"/api/bots/{bot_id}")
    if r.status_code != 204:
        raise SmokeFailure(f"DELETE /api/bots/{{id}} -> {r.status_code}: {r.text}")
    ctx.bot_deleted = True


def _assert_desk_dir_gone(ctx: _Ctx, bot_id: str) -> None:
    desk_path = ctx.desks_dir / bot_id
    if desk_path.exists():
        raise SmokeFailure(f"{desk_path} still exists after deleting the bot")


def _assert_container_gone(bot_id: str) -> str:
    """Checks the specific container this run created (robust against an
    unrelated leftover from a previous crashed run), and also returns
    the brief's own generic ``name=roost-desk-`` listing for the report."""
    specific = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=roost-desk-{bot_id}", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=10,
    )
    if specific.returncode != 0:
        raise SmokeFailure(f"`docker ps` failed: {specific.stderr.strip()}")
    if specific.stdout.strip():
        raise SmokeFailure(f"container still present: {specific.stdout.strip()}")

    generic = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=roost-desk-", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=10,
    )
    return generic.stdout.strip()


# ---------------------------------------------------------------------------
# Step runner / report
# ---------------------------------------------------------------------------


async def _check(ctx: _Ctx, name: str, awaitable: Awaitable[T]) -> tuple[bool, T | None]:
    """Runs ``awaitable``, records one PASS/FAIL row, and returns
    ``(ok, value)`` -- ``ok`` is the one thing callers should branch on;
    several steps legitimately return ``None`` on SUCCESS too (register,
    start browser, exec, delete, ...), so ``value is None`` alone can
    never mean "this step failed"."""
    try:
        value = await awaitable
    except SmokeFailure as exc:
        ctx.results.append(_Result(name, False, str(exc)))
        return False, None
    except Exception as exc:  # the turn loop / keeper / docker calls can raise all sorts
        ctx.results.append(_Result(name, False, f"{type(exc).__name__}: {exc}"))
        return False, None
    ctx.results.append(_Result(name, True))
    return True, value


def _check_sync(ctx: _Ctx, name: str, fn: Callable[[], T]) -> tuple[bool, T | None]:
    try:
        value = fn()
    except SmokeFailure as exc:
        ctx.results.append(_Result(name, False, str(exc)))
        return False, None
    except Exception as exc:
        ctx.results.append(_Result(name, False, f"{type(exc).__name__}: {exc}"))
        return False, None
    ctx.results.append(_Result(name, True))
    return True, value


def _skip_rest(ctx: _Ctx, reason: str) -> None:
    ctx.results.append(_Result("remaining steps", False, f"skipped: {reason}"))


async def _run_steps(ctx: _Ctx) -> None:
    await _check(ctx, "register the (single) account", _register(ctx))

    ok, bot_id = await _check(ctx, "create a bot", _create_bot(ctx))
    ctx.bot_id = bot_id
    if not ok or bot_id is None:
        return _skip_rest(ctx, "bot creation failed")

    await _check(ctx, "desk: start the browser", _start_browser(ctx, bot_id))

    ok, thread_id = await _check(ctx, "talk: open a thread", _create_thread(ctx, bot_id))
    if not ok or thread_id is None:
        return _skip_rest(ctx, "no thread to talk in")

    sent_ok, _ = await _check(
        ctx, "talk: send a message and get a stored bot reply", _send_and_await_reply(ctx, thread_id)
    )

    # These two run regardless of whether the turn above fully finished in
    # time -- Ruling 4: the network-dependent check must be reported on
    # its own, never silently skipped just because it's expected to fail
    # in an offline sandbox.
    _check_sync(ctx, "turn loop: model's 2nd request carried the real page text", lambda: _assert_second_request_saw_the_page(ctx))
    if sent_ok:
        await _check(ctx, "turn loop: stored reply is tainted=True", _assert_last_reply_tainted(ctx, thread_id))
    else:
        ctx.results.append(_Result("turn loop: stored reply is tainted=True", False, "skipped: no reply arrived"))

    await _check(ctx, "desk: exec 'echo hi' via the workspace container", _exec_echo_hi(ctx, bot_id))

    deleted_ok, _ = await _check(ctx, "delete the bot (retires its desk)", _delete_bot(ctx, bot_id))
    if not deleted_ok:
        return _skip_rest(ctx, "bot delete failed")

    _check_sync(ctx, "desk directory removed from disk", lambda: _assert_desk_dir_gone(ctx, bot_id))
    _check_sync(ctx, "docker workspace container removed", lambda: _assert_container_gone(bot_id))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_table(results: list[_Result]) -> None:
    name_width = max((len(r.name) for r in results), default=4)
    print()
    print(f"{'STATUS':6}  {'STEP'.ljust(name_width)}")
    print("-" * (8 + name_width))
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL':6}  {r.name.ljust(name_width)}")
        if not r.ok and r.detail:
            print(f"        -> {r.detail}")
    print()
    passed = sum(1 for r in results if r.ok)
    print(f"{passed}/{len(results)} steps passed.")
    print()


async def main() -> int:
    try:
        ctx = await _setup()
    except SmokeFailure as exc:
        _print_table([_Result("preflight", False, str(exc))])
        return 1

    try:
        try:
            await asyncio.wait_for(_run_steps(ctx), timeout=_OVERALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            ctx.results.append(_Result("smoke run", False, f"timed out after {_OVERALL_TIMEOUT_S}s overall"))
    finally:
        # Outside the timeout above on purpose -- see _teardown's docstring.
        await _teardown(ctx)

    _print_table(ctx.results)
    return 0 if all(r.ok for r in ctx.results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
