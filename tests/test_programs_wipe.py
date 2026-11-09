"""Programs: Wipe workspace empties a bot's workspace (and its scratch folders) and clears its workspace mark."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.constants import WORKSPACE_DIR, WORKSPACE_SCRATCH_DIRS
from roost.db.connection import db_session, init_db
from roost.desk import DeskUnavailable, ExecResult
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.programs.file_ops import file_ops_argv, file_ops_command, parse_wipe
from roost.programs.marks import WorkspaceMarks

ORIGIN = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


# --- the fixed script ---------------------------------------------------------------------------------------


def _wipe(root: Path, scratch: tuple[str, ...]) -> subprocess.CompletedProcess:
    argv = file_ops_argv("wipe", "", root=str(root), scratch=scratch)
    return subprocess.run([sys.executable, *argv[1:]], capture_output=True, text=True, timeout=30)


def test_the_wipe_command_is_fixed_and_names_the_scratch_folders():
    argv = shlex.split(file_ops_command("wipe", ""))
    assert argv[:3] == ["python3", "-I", "-c"] and argv[4:6] == ["wipe", ""] and len(argv) == 6
    assert f'ROOT = "{WORKSPACE_DIR}"' in argv[3]
    assert f"SCRATCH = {json.dumps(list(WORKSPACE_SCRATCH_DIRS))}" in argv[3]


def test_wipe_empties_the_workspace_and_scratch_but_keeps_the_folders(tmp_path):
    root, tmp, home = tmp_path / "ws", tmp_path / "tmp", tmp_path / "home"
    for folder in (root, tmp, home):
        folder.mkdir()
    (root / "src" / "deep").mkdir(parents=True)
    (root / "src" / "deep" / "a.py").write_text("print(1)")
    (root / ".hidden").write_text("x")
    (tmp / "scratch.txt").write_text("y")
    (home / ".bash_history").write_text("z")
    done = _wipe(root, (str(tmp), str(home)))
    assert done.returncode == 0, done
    assert parse_wipe(done.stderr) == 4
    assert root.is_dir() and list(root.iterdir()) == []
    assert list(tmp.iterdir()) == [] and list(home.iterdir()) == []


def test_wipe_never_follows_a_link_out(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("the user's file")
    root = tmp_path / "ws"
    root.mkdir()
    (root / "dirlink").symlink_to(outside)
    (root / "filelink").symlink_to(outside / "keep.txt")
    done = _wipe(root, ())
    assert done.returncode == 0, done
    assert list(root.iterdir()) == []
    assert (outside / "keep.txt").read_text() == "the user's file"


def test_wipe_of_an_empty_workspace_and_a_missing_scratch_folder(tmp_path):
    done = _wipe(tmp_path, (str(tmp_path / "nope"),))
    assert done.returncode == 0 and parse_wipe(done.stderr) == 0


def test_wipe_refuses_a_path(tmp_path):
    argv = file_ops_argv("wipe", "src", root=str(tmp_path))
    done = subprocess.run([sys.executable, *argv[1:]], capture_output=True, text=True, timeout=30)
    assert done.returncode == 3 and json.loads(done.stderr)["error"] == "bad_path"


def test_parse_wipe_tolerates_junk():
    assert parse_wipe("not json") == 0
    assert parse_wipe(json.dumps({"removed": "many"})) == 0


# --- the mark -----------------------------------------------------------------------------------------------


async def _audit(cfg, user_id: str, bot_id: str, action: str, tainted: int, decision: str = "do") -> None:
    async with db_session(cfg) as db:
        await db.execute(
            "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at, reason, tainted) "
            "VALUES (?,?,?,?,NULL,'2026-10-22T10:00:00+00:00','x',?)",
            (user_id, bot_id, action, decision, tainted),
        )
        await db.commit()


async def test_a_wipe_clears_the_mark_until_the_next_tainted_write():
    cfg = load_config()
    await init_db(cfg)
    marks = WorkspaceMarks(cfg)
    await _audit(cfg, "u1", "b1", "run_program", 1)
    await _audit(cfg, "u1", "b2", "write_file", 1)
    assert await marks.marked("u1", "b1")
    await marks.clear("u1", "b1")
    assert not await marks.marked("u1", "b1")
    assert await marks.marked("u1", "b2")          # another bot's mark stays
    await _audit(cfg, "u1", "b1", "run_program", 0)
    assert not await marks.marked("u1", "b1")      # a clean run does not mark
    await _audit(cfg, "u1", "b1", "write_file", 1)
    assert await marks.marked("u1", "b1")          # a new tainted write marks again


async def test_another_users_wipe_does_not_clear_my_mark():
    cfg = load_config()
    await init_db(cfg)
    marks = WorkspaceMarks(cfg)
    await _audit(cfg, "u1", "b1", "run_program", 1)
    await marks.clear("u2", "b1")
    assert await marks.marked("u1", "b1")


# --- the route ----------------------------------------------------------------------------------------------


def _client() -> tuple[object, TestClient, str]:
    app = create_app()
    c = TestClient(app)
    c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=ORIGIN)
    r = c.post("/api/bots", json={"name": "Coder", "job": "codes", "instructions": "", "avatar": AVATAR},
               headers=ORIGIN)
    assert r.status_code == 201
    return app, c, r.json()["id"]


def _desk_for(app, c: TestClient, bot_id: str):
    kind = next(b for b in c.get("/api/bots").json() if b["id"] == bot_id).get("computer", "mac_brave")
    return app.state.desks.for_bot(bot_id, kind)


def _user_id(_c: TestClient) -> str:
    import asyncio

    async def read() -> str:
        async with db_session(load_config()) as db:
            row = await (await db.execute("SELECT id FROM users WHERE username = 'alice'")).fetchone()
            return row[0]

    return asyncio.run(read())


def test_wipe_runs_the_fixed_script_and_clears_the_mark():
    import asyncio

    app, c, bot_id = _client()
    cfg = load_config()
    user_id = _user_id(c)
    asyncio.run(_audit(cfg, user_id, bot_id, "run_program", 1))
    assert asyncio.run(WorkspaceMarks(cfg).marked(user_id, bot_id))
    desk = _desk_for(app, c, bot_id)
    desk.exec_replies = (ExecResult(0, "", json.dumps({"removed": 3}), False, False),)
    r = c.post(f"/api/bots/{bot_id}/workspace/wipe", headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"removed": 3}
    inner = shlex.split(desk.exec_calls[0][0][2])
    assert inner[4:] == ["wipe", ""]
    assert not asyncio.run(WorkspaceMarks(cfg).marked(user_id, bot_id))


def test_wipe_needs_the_origin():
    _, c, bot_id = _client()
    assert c.post(f"/api/bots/{bot_id}/workspace/wipe").status_code == 403


def test_a_failed_wipe_keeps_the_mark_and_says_so():
    import asyncio

    app, c, bot_id = _client()
    cfg = load_config()
    user_id = _user_id(c)
    asyncio.run(_audit(cfg, user_id, bot_id, "write_file", 1))
    desk = _desk_for(app, c, bot_id)
    desk.exec_replies = (ExecResult(3, "", json.dumps({"error": "denied"}), False, False),)
    r = c.post(f"/api/bots/{bot_id}/workspace/wipe", headers=ORIGIN)
    assert r.status_code == 503 and "wipe" in r.json()["detail"].lower()
    desk.exec_replies = (ExecResult(0, "", "", True, False),)
    assert c.post(f"/api/bots/{bot_id}/workspace/wipe", headers=ORIGIN).status_code == 503
    assert asyncio.run(WorkspaceMarks(cfg).marked(user_id, bot_id))

    async def down(command, timeout_s=60):
        raise DeskUnavailable("keeper down")

    desk.exec = down
    assert c.post(f"/api/bots/{bot_id}/workspace/wipe", headers=ORIGIN).status_code == 503
    assert asyncio.run(WorkspaceMarks(cfg).marked(user_id, bot_id))


async def test_another_users_bot_is_404():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=ORIGIN)
    r = await alice.post("/api/bots", json={"name": "Coder", "job": "codes", "instructions": "", "avatar": AVATAR},
                         headers=ORIGIN)
    bot_id = r.json()["id"]
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, "bob", "pw-123456")
    bob = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=ORIGIN)
    assert (await bob.post(f"/api/bots/{bot_id}/workspace/wipe", headers=ORIGIN)).status_code == 404
    assert (await bob.post("/api/bots/nope/workspace/wipe", headers=ORIGIN)).status_code == 404
    await alice.aclose()
    await bob.aclose()


# --- the service and the lock it shares with the program tools ----------------------------------------------


async def test_wipe_waits_for_a_running_program_and_clears_under_the_lock():
    import asyncio

    from roost.desk import DeskFactory
    from roost.programs.tools import ProgramLimits
    from roost.programs.wipe import wipe_workspace

    cfg = load_config()
    await init_db(cfg)
    marks = WorkspaceMarks(cfg)
    await _audit(cfg, "u1", "b1", "run_program", 1)
    desk = DeskFactory(cfg).for_bot("b1")
    desk.exec_replies = (ExecResult(0, "", json.dumps({"removed": 1}), False, False),)
    lock = ProgramLimits().lock("b1")
    await lock.acquire()
    task = asyncio.create_task(wipe_workspace(desk, marks, lock, "u1", "b1"))
    await asyncio.sleep(0.05)
    assert desk.exec_calls == []                    # a program holds the workspace: the wipe waits
    lock.release()
    outcome = await task
    assert outcome.ok and outcome.removed == 1 and outcome.text == ""
    assert not await marks.marked("u1", "b1")


async def test_a_tainted_write_notes_the_mark_when_it_runs():
    from roost.desk import DeskFactory
    from roost.programs.tools import ProgramTools
    from roost.talk.domain_tools import RecordContext

    cfg = load_config()
    await init_db(cfg)
    marks = WorkspaceMarks(cfg)
    await _audit(cfg, "u1", "b1", "run_program", 1)
    await marks.clear("u1", "b1")                   # the gate's row came before this wipe ...
    tools = ProgramTools(DeskFactory(cfg).for_bot, marks, None, None)
    ctx = RecordContext(user_id="u1", bot_id="b1", tainted=True, thread_id=None, run_id="r1")
    await tools.execute("write_file", {"path": "a.txt", "text": "from the web"}, ctx)
    assert await marks.marked("u1", "b1")          # ... but the write itself, after it, marks again
    clean = RecordContext(user_id="u1", bot_id="b2", tainted=False, thread_id=None, run_id="r2")
    await tools.execute("run_program", {"command": "ls"}, clean)
    assert not await marks.marked("u1", "b2")
