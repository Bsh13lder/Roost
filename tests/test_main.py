"""Tests for ``python -m roost`` (``roost/__main__.py``).

``create-user`` is exercised end-to-end against a temp dir (the brief's
Step 5). ``main()`` with no subcommand is exercised by stubbing
``uvicorn.run`` — this module must never actually start a server during
``pytest``.
"""

from __future__ import annotations

import pytest

from roost import __main__ as main_module
from roost.config import load_config
from roost.db.connection import close_pool, db_session, init_db


async def test_create_user_creates_a_row(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOST_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "pw-123456")

    await main_module._create_user("alice")

    cfg = load_config()
    try:
        async with db_session(cfg) as db:
            row = await (await db.execute("SELECT username FROM users WHERE username = ?", ("alice",))).fetchone()
        assert row is not None and row[0] == "alice"
    finally:
        await close_pool()


async def test_create_user_rejects_duplicate_username(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ROOST_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "pw-123456")

    await main_module._create_user("alice")
    with pytest.raises(SystemExit):
        await main_module._create_user("alice")
    assert "already taken" in capsys.readouterr().err


def test_main_with_no_args_serves(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module.uvicorn, "run", lambda *a, **kw: calls.append((a, kw)))
    main_module.main([])
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 18800


def test_serve_strips_a_leaked_anthropic_api_key_from_the_process_env(monkeypatch):
    """Final review, finding 7: ``build_options`` (``roost/llm/
    claude_sdk.py``) removes the key from ITS OWN ``options.env`` copy,
    but the installed SDK builds the CLI's subprocess environment as
    ``{**os.environ, ..., **options.env}`` (claude_agent_sdk's own
    ``_internal/transport/subprocess_cli.py``) -- a key still sitting in
    the GATEWAY PROCESS's ``os.environ`` survives that merge untouched,
    since omitting a key from the right-hand dict never removes it from
    the left. The only fix that actually works is removing it from the
    process's own env, once, at startup -- before anything (uvicorn,
    then any request's SDK call) can read it."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-reach-the-sdk")
    monkeypatch.setattr(main_module.uvicorn, "run", lambda *a, **kw: None)

    main_module._serve()

    assert "ANTHROPIC_API_KEY" not in main_module.os.environ

    # Apply the SDK's own merge directly, so this fails the same way a
    # change to the SDK's merge order (or a reintroduced `env.pop`
    # instead of an `os.environ.pop`) would actually be caught.
    from roost.llm.claude_sdk import build_options

    options = build_options("sys", (), "claude-sonnet-5")
    merged = {**main_module.os.environ, **(options.env or {})}
    assert "ANTHROPIC_API_KEY" not in merged


def test_serve_with_no_leaked_key_is_a_safe_no_op(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(main_module.uvicorn, "run", lambda *a, **kw: None)

    main_module._serve()  # must not raise

    assert "ANTHROPIC_API_KEY" not in main_module.os.environ


def test_main_create_user_without_username_exits(capsys):
    with pytest.raises(SystemExit):
        main_module.main(["create-user"])
    assert "Usage" in capsys.readouterr().err


def test_main_unknown_command_exits(capsys):
    with pytest.raises(SystemExit):
        main_module.main(["bogus"])
    assert "Unknown command" in capsys.readouterr().err


def test_main_create_user_dispatches(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOST_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "pw-123456")
    main_module.main(["create-user", "bob"])

    cfg = load_config()

    async def _check():
        async with db_session(cfg) as db:
            row = await (await db.execute("SELECT username FROM users WHERE username = ?", ("bob",))).fetchone()
        assert row is not None
        await close_pool()

    import asyncio

    asyncio.run(_check())


def test_main_inside_the_container_serves_on_all_interfaces(monkeypatch):
    """docker/gateway/Dockerfile sets ROOST_IN_CONTAINER=1 + ROOST_HOST=0.0.0.0;
    ``_serve`` must hand that host to uvicorn unchanged, or Docker's port
    publishing (127.0.0.1:18800 on the host) has nothing to reach."""
    monkeypatch.setenv("ROOST_IN_CONTAINER", "1")
    monkeypatch.setenv("ROOST_HOST", "0.0.0.0")
    calls = []
    monkeypatch.setattr(main_module.uvicorn, "run", lambda *a, **kw: calls.append((a, kw)))
    main_module.main([])
    assert calls[0][1]["host"] == "0.0.0.0"
    assert calls[0][1]["port"] == 18800
