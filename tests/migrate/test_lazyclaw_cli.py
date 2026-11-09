import io
import os
import sqlite3
from pathlib import Path

import pytest

from lazyclaw_factory import OLD_USERNAME, SAMPLE_PASSWORD, TEST_SECRET, build_sample
from roost.migrate.lazyclaw.__main__ import main
from roost.migrate.lazyclaw.wipe import count_wipe


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    return build_sample(tmp_path_factory.mktemp("cli") / "lc.db")


def run(argv, *, password=SAMPLE_PASSWORD, secret=TEST_SECRET, username=OLD_USERNAME, env=None):
    out, err = io.StringIO(), io.StringIO()
    prompts = []

    def getpass_fn(prompt):
        prompts.append(prompt)
        return secret if "SERVER_SECRET" in prompt else password

    code = main(argv, getpass_fn=getpass_fn, input_fn=lambda p: username, out=out, err=err, env=env or {}, roost_ports=(), lazyclaw_ports=())
    return code, out.getvalue(), err.getvalue(), prompts


def test_password_unlock_is_default_and_report_has_no_secrets(source, tmp_path):
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    os.chmod(work, 0o700)
    code, out, err, prompts = run(["--source", str(source), "--work-dir", str(work)])
    assert code == 0, err
    assert "DRY RUN" in out and "key verified" in out.lower()
    assert SAMPLE_PASSWORD not in out + err and TEST_SECRET not in out + err
    assert "Buy kitchen tiles from the big shop" not in out
    assert any("password" in p for p in prompts)
    assert list(work.iterdir()) == []  # snapshot deleted


def test_server_secret_unlock(source):
    code, out, err, prompts = run(["--source", str(source), "--unlock", "server-secret"])
    assert code == 0, err
    assert any("SERVER_SECRET" in p for p in prompts) and TEST_SECRET not in out + err


def test_secret_from_env_var_name_not_argv(source):
    code, out, err, prompts = run(["--source", str(source), "--unlock", "server-secret",
                                   "--old-secret-env", "LC_SECRET"], env={"LC_SECRET": TEST_SECRET})
    assert code == 0, err
    assert prompts == []


def test_wrong_password_exits_1_without_echo(source):
    code, out, err, _ = run(["--source", str(source)], password="wrong-pass-123")
    assert code == 1 and "wrong-pass-123" not in out + err and "password" in err.lower()


def test_work_dir_must_be_private_temp(source, tmp_path):
    loose = tmp_path / "loose"
    loose.mkdir()
    os.chmod(loose, 0o755)
    code, _, err, _ = run(["--source", str(source), "--work-dir", str(loose)])
    assert code == 2 and "0700" in err
    home_dir = Path.home() / "Roost-nope"
    code, _, err, _ = run(["--source", str(source), "--work-dir", str(home_dir)])
    assert code == 2


def test_missing_source(tmp_path):
    code, _, err, _ = run(["--source", str(tmp_path / "none.db")])
    assert code == 1 and "not found" in err


def test_keep_snapshot_keeps_it_private(source, tmp_path):
    work = tmp_path / "w2"
    work.mkdir(mode=0o700)
    os.chmod(work, 0o700)
    code, out, _, _ = run(["--source", str(source), "--work-dir", str(work), "--keep-snapshot"])
    assert code == 0 and "snapshot kept" in out.lower()
    kept = list(work.rglob("*.db"))
    assert len(kept) == 1 and (kept[0].stat().st_mode & 0o077) == 0


def test_wipe_counts_from_a_roost_db(source, tmp_path):
    roost = tmp_path / "roost.db"
    conn = sqlite3.connect(roost)
    conn.executescript("""
        create table users (id text); insert into users values ('u1');
        create table tasks (id text, user_id text); create table task_comments (id text, user_id text);
        create table money_projects (id text, user_id text); create table money_expenses (id text, user_id text);
        create table money_topups (id text, user_id text); create table money_recurring (id text, user_id text);
        insert into tasks values ('a','u1'),('b','u1'),('c','other');
        insert into task_comments values ('a','u1');
        insert into money_projects values ('g','u1'),('p','u1'),('q','u1');
        insert into money_expenses values ('e','u1');
    """)
    conn.commit()
    conn.close()
    w = count_wipe(roost)
    assert w.available and (w.tasks, w.task_comments, w.projects, w.expenses, w.topups, w.recurring) == (2, 1, 2, 1, 0, 0)
    code, out, err, _ = run(["--source", str(source), "--roost-db", str(roost)])
    assert code == 0, err
    assert "2 tasks, 1 task comments, 1 expenses" in out
    assert not count_wipe(roost.with_name("missing.db")).available
