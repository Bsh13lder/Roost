"""Programs: the fixed file script that runs inside the container, run here against a temp folder."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

from roost.constants import PROGRAM_READ_MAX_CHARS, WORKSPACE_DIR
from roost.programs.file_ops import file_ops_argv, file_ops_command, parse_listing, parse_read


def _run(root: Path, op: str, path: str, text: str | None = None) -> subprocess.CompletedProcess:
    argv = file_ops_argv(op, path, text, root=str(root))
    return subprocess.run([sys.executable, *argv[1:]], capture_output=True, text=True, timeout=30)


def _error(done: subprocess.CompletedProcess) -> str:
    assert done.returncode == 3, done
    return json.loads(done.stderr)["error"]


def test_the_command_is_one_quoted_python_call_with_a_fixed_root():
    command = file_ops_command("write", "src/a.py", "print('hi')\n")
    argv = shlex.split(command)
    assert argv[:3] == ["python3", "-I", "-c"] and argv[4:6] == ["write", "src/a.py"]
    assert f'ROOT = "{WORKSPACE_DIR}"' in argv[3]
    assert file_ops_argv("read", "a; rm -rf /")[-1] == "a; rm -rf /"           # a plain argument, never shell text
    assert shlex.split(file_ops_command("read", "a; rm -rf /"))[-1] == "a; rm -rf /"


def test_write_then_read_round_trips_and_makes_folders(tmp_path):
    assert _run(tmp_path, "write", "src/deep/a.py", "print('hé')\n").returncode == 0
    assert (tmp_path / "src/deep/a.py").read_text() == "print('hé')\n"
    done = _run(tmp_path, "read", "src/deep/a.py")
    assert done.returncode == 0
    read = parse_read(done.stdout, done.stderr)
    assert read.text == "print('hé')\n" and not read.cut and read.size == len("print('hé')\n".encode())


def test_write_replaces_an_existing_file(tmp_path):
    (tmp_path / "a.txt").write_text("old")
    assert _run(tmp_path, "write", "a.txt", "new").returncode == 0
    assert (tmp_path / "a.txt").read_text() == "new"


def test_a_symlinked_file_is_never_followed(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("the user's secret")
    root = tmp_path / "ws"
    root.mkdir()
    (root / "link.txt").symlink_to(outside)
    assert _error(_run(root, "read", "link.txt")) == "link"
    assert _error(_run(root, "write", "link.txt", "pwned")) == "link"
    assert outside.read_text() == "the user's secret"


def test_a_symlinked_folder_is_never_walked(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f.txt").write_text("x")
    root = tmp_path / "ws"
    root.mkdir()
    (root / "dir").symlink_to(outside, target_is_directory=True)
    assert _error(_run(root, "read", "dir/f.txt")) == "link"
    assert _error(_run(root, "write", "dir/g.txt", "y")) == "link"
    assert _error(_run(root, "list", "dir")) == "link"
    assert not (outside / "g.txt").exists()


def test_missing_folder_and_binary_files_say_so(tmp_path):
    assert _error(_run(tmp_path, "read", "nope.txt")) == "not_found"
    (tmp_path / "d").mkdir()
    assert _error(_run(tmp_path, "read", "d")) == "not_file"
    (tmp_path / "b.bin").write_bytes(b"\x00\x01\x02")
    assert _error(_run(tmp_path, "read", "b.bin")) == "binary"
    (tmp_path / "f.txt").write_text("x")
    assert _error(_run(tmp_path, "list", "f.txt")) == "not_dir"
    assert _error(_run(tmp_path, "write", "f.txt/a", "x")) == "not_dir"


def test_a_long_file_is_cut(tmp_path):
    (tmp_path / "big.txt").write_text("a" * (PROGRAM_READ_MAX_CHARS + 50))
    done = _run(tmp_path, "read", "big.txt")
    read = parse_read(done.stdout, done.stderr)
    assert read.cut and len(read.text) == PROGRAM_READ_MAX_CHARS


def test_list_names_kinds_and_sizes_and_shows_links_as_links(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "a.txt").write_text("abc")
    (tmp_path / "l").symlink_to("/etc/hosts")
    done = _run(tmp_path, "list", "")
    listing = parse_listing(done.stdout)
    assert [(e.name, e.kind, e.size) for e in listing.entries] == [
        ("a.txt", "file", 3), ("l", "link", None), ("src", "dir", None)]
    assert not listing.more


def test_parsers_fail_soft_on_garbage():
    assert parse_listing("not json").entries == ()
    assert parse_read("text", "not json").text == "text"
