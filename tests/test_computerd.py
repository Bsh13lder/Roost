"""The computer's supervisor and pipe, loaded by path (they are stdlib scripts that ship in the image)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[1] / "docker" / "computer"
_PROXY = "http://roost-egress:3128"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, _DIR / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def computerd():
    return _load("roost_computerd", "roost_computerd.py")


@pytest.fixture(scope="module")
def pipe():
    return _load("roost_pipe", "roost_pipe.py")


def test_xvnc_listens_on_a_unix_socket_only_with_clipboard_out_off(computerd):
    argv = computerd.xvnc_argv(1280, 800, "/run/screen/vnc.sock")
    assert argv[:2] == ["Xvnc", ":1"]
    assert argv[argv.index("-geometry") + 1] == "1280x800"
    assert argv[argv.index("-rfbport") + 1] == "-1"
    assert argv[argv.index("-rfbunixpath") + 1] == "/run/screen/vnc.sock"
    assert argv[argv.index("-rfbunixmode") + 1] == "0600"
    assert argv[argv.index("-SecurityTypes") + 1] == "None"
    assert "-nolisten" in argv and argv[argv.index("-nolisten") + 1] == "tcp"
    for flag in ("-SendCutText=0", "-SendPrimary=0", "-AcceptSetDesktopSize=0", "-AlwaysShared"):
        assert flag in argv


def test_xvnc_never_blanks_the_screen(computerd):
    # Owner, 2026-10-29: watching showed a black screen. X blanks after 10 idle minutes unless -s 0, and a
    # viewer sends no input.
    argv = computerd.xvnc_argv(1280, 800, "/run/screen/vnc.sock")
    assert argv[argv.index("-s") + 1] == "0"


def test_chromium_keeps_its_sandbox_and_uses_the_proxy(computerd):
    argv = computerd.chromium_argv("/home/comp/profile", _PROXY)
    assert argv[0] == "brave-browser"
    assert not any("no-sandbox" in a for a in argv)
    # Nothing that tells a page it is automated (navigator.webdriver, the infobar) or headless.
    assert not any(f in a for a in argv for f in ("enable-automation", "headless"))
    assert "--disable-blink-features=AutomationControlled" in argv     # the pipe alone sets navigator.webdriver
    assert "--remote-debugging-pipe" in argv
    assert "--user-data-dir=/home/comp/profile" in argv
    assert f"--proxy-server={_PROXY}" in argv
    assert "--proxy-bypass-list=<-loopback>" in argv
    assert "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE roost-egress" in argv
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in argv
    assert "--hide-crash-restore-bubble" in argv     # a fresh start after a crash shows no "Restore pages?" bubble
    assert "--window-size=1280,800" in argv and "--start-maximized" in argv
    assert "--disk-cache-dir=/tmp/browser-cache" in argv
    for flag in ("--no-first-run", "--no-default-browser-check", "--disable-background-timer-throttling",
                 "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"):
        assert flag in argv


def test_stale_files_cover_the_x_lock_the_sockets_and_singleton(computerd, tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "SingletonLock").write_text("x")
    (profile / "SingletonSocket").write_text("x")
    (profile / "Preferences").write_text("{}")
    stale = computerd.stale_files(str(tmp_path), 1)
    assert "/tmp/.X1-lock" in stale and "/tmp/.X11-unix/X1" in stale
    assert "/run/screen/vnc.sock" in stale and "/run/screen/cdp.sock" in stale
    assert str(profile / "SingletonLock") in stale and str(profile / "SingletonSocket") in stale
    assert str(profile / "Preferences") not in stale


def test_restart_budget_stops_a_crash_loop(computerd):
    now = [0.0]
    budget = computerd.RestartBudget(5, 60.0, lambda: now[0])
    assert [budget.allow() for _ in range(5)] == [True] * 5
    assert budget.allow() is False
    now[0] = 61.0
    assert budget.allow() is True


def test_roost_pipe_knows_only_cdp_and_vnc(pipe):
    assert pipe.socket_for("cdp") == "/run/screen/cdp.sock"
    assert pipe.socket_for("vnc") == "/run/screen/vnc.sock"
    for bad in ("", "x", "../etc/passwd", "CDP", "cdp.sock"):
        with pytest.raises(ValueError):
            pipe.socket_for(bad)
    assert pipe.main(["bogus"]) == 2
    assert pipe.main([]) == 2
    assert pipe.main(["cdp", "extra"]) == 2


def test_the_pipe_copies_bytes_both_ways_until_a_side_closes(pipe):
    import os
    import socket
    import tempfile
    import threading
    path = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s.sock")   # short: AF_UNIX paths are limited
    server = socket.socket(socket.AF_UNIX)
    server.bind(path)
    server.listen(1)

    def echo_upper():
        conn, _ = server.accept()
        data = conn.recv(100)
        conn.sendall(data.upper())
        conn.close()

    t = threading.Thread(target=echo_upper)
    t.start()
    r_in, w_in = os.pipe()
    r_out, w_out = os.pipe()
    os.write(w_in, b"hello")
    os.close(w_in)
    assert pipe.relay(path, r_in, w_out) == 0
    os.close(w_out)
    assert os.read(r_out, 100) == b"HELLO"
    t.join()
    server.close()


def test_a_missing_socket_fails_with_a_plain_exit_code(pipe, tmp_path):
    assert pipe.relay(str(tmp_path / "none.sock"), 0, 1) == 1


def test_the_devtools_pipe_reaches_the_child_as_fds_3_and_4(computerd):
    """Regression: pass_fds closed fds 3 and 4 again after the dup2, so Chromium saw no DevTools pipe."""
    import fcntl
    import os
    import sys

    in_r, in_w = os.pipe()
    out_r, out_w = os.pipe()
    child_in, child_out = fcntl.fcntl(in_r, fcntl.F_DUPFD, 10), fcntl.fcntl(out_w, fcntl.F_DUPFD, 10)
    code = "import os; os.write(4, os.read(3, 5).upper())"
    proc = computerd.popen_with_fds_3_and_4([sys.executable, "-I", "-c", code], child_in, child_out)
    for fd in (in_r, out_w, child_in, child_out):
        os.close(fd)
    os.write(in_w, b"hello")
    assert os.read(out_r, 5) == b"HELLO"
    assert proc.wait(timeout=10) == 0
    os.close(in_w)
    os.close(out_r)


def test_chromium_uses_the_desktop_title_bar_so_minimize_and_maximize_work(computerd, tmp_path):
    computerd.use_system_title_bar(str(tmp_path))
    prefs = json.loads((tmp_path / "Default" / "Preferences").read_text())
    assert prefs["browser"]["custom_chrome_frame"] is False


def test_the_title_bar_setting_keeps_every_other_preference(computerd, tmp_path):
    (tmp_path / "Default").mkdir()
    (tmp_path / "Default" / "Preferences").write_text(json.dumps({"browser": {"x": 1}, "profile": {"name": "a"}}))
    computerd.use_system_title_bar(str(tmp_path))
    prefs = json.loads((tmp_path / "Default" / "Preferences").read_text())
    assert prefs == {"browser": {"x": 1, "custom_chrome_frame": False}, "profile": {"name": "a"}}


def test_a_broken_preferences_file_is_left_alone(computerd, tmp_path):
    (tmp_path / "Default").mkdir()
    (tmp_path / "Default" / "Preferences").write_text("{not json")
    computerd.use_system_title_bar(str(tmp_path))
    assert (tmp_path / "Default" / "Preferences").read_text() == "{not json"


# -- D5: Brave on demand, one fresh window (owner decision 2026-10-23) -------------------------------------


class _FakeProc:
    def __init__(self) -> None:
        self.code = None

    def poll(self):
        return self.code


class _FakeBridge:
    def __init__(self) -> None:
        self.detached = 0
        self.dropped = 0

    def detach(self) -> None:
        self.detached += 1

    def drop_client(self) -> None:
        self.dropped += 1


def _browser(computerd, limit=5):
    started = []

    def start(bridge):
        proc = _FakeProc()
        started.append(proc)
        return proc

    bridge = _FakeBridge()
    browser = computerd.BrowserProcess(bridge, start, computerd.RestartBudget(limit, 60.0, lambda: 0.0))
    return browser, bridge, started


def test_the_computer_starts_without_a_browser_and_a_want_starts_one(computerd):
    browser, _, started = _browser(computerd)
    assert started == [] and browser.running() == []
    assert browser.want() is True
    assert browser.want() is True                     # still running: no second Brave
    assert len(started) == 1 and browser.running() == started


def test_a_closed_browser_is_not_started_again_until_wanted(computerd):
    browser, bridge, started = _browser(computerd)
    browser.want()
    started[0].code = 0                               # the last window closed
    browser.reap()
    assert browser.running() == [] and len(started) == 1
    assert bridge.detached == 1 and bridge.dropped == 1   # the gateway's old connection is closed, not left dead
    browser.reap()
    assert len(started) == 1
    assert browser.want() is True and len(started) == 2


def test_a_crash_loop_stops_being_fed(computerd):
    browser, _, started = _browser(computerd, limit=2)
    for _ in range(2):
        assert browser.want() is True
        started[-1].code = 1
        browser.reap()
    assert browser.want() is False and len(started) == 2


def test_a_start_that_fails_is_a_no(computerd):
    def start(bridge):
        raise OSError("no brave")

    browser = computerd.BrowserProcess(_FakeBridge(), start, computerd.RestartBudget(5, 60.0, lambda: 0.0))
    assert browser.want() is False and browser.running() == []


def test_a_fresh_start_drops_the_last_session_but_keeps_logins(computerd, tmp_path):
    default = tmp_path / "Default"
    (default / "Sessions").mkdir(parents=True)
    (default / "Sessions" / "Session_1").write_text("x")
    (default / "Sessions" / "Tabs_1").write_text("x")
    for name in ("Current Session", "Last Session", "Current Tabs", "Last Tabs", "Cookies", "Login Data"):
        (default / name).write_text("x")
    computerd.drop_last_session(str(tmp_path))
    assert list((default / "Sessions").iterdir()) == []
    assert sorted(p.name for p in default.iterdir() if p.is_file()) == ["Cookies", "Login Data"]


def test_a_fresh_start_marks_a_clean_exit_and_keeps_other_preferences(computerd, tmp_path):
    (tmp_path / "Default").mkdir()
    prefs_file = tmp_path / "Default" / "Preferences"
    prefs_file.write_text(json.dumps({"profile": {"exit_type": "Crashed", "name": "a"}, "x": 1}))
    computerd.mark_clean_exit(str(tmp_path))
    prefs = json.loads(prefs_file.read_text())
    assert prefs == {"profile": {"exit_type": "Normal", "exited_cleanly": True, "name": "a"}, "x": 1}


def test_a_missing_profile_is_fine_for_a_fresh_start(computerd, tmp_path):
    computerd.drop_last_session(str(tmp_path / "none"))
    computerd.mark_clean_exit(str(tmp_path))
    assert json.loads((tmp_path / "Default" / "Preferences").read_text())["profile"]["exit_type"] == "Normal"


def test_stale_files_cover_the_want_socket(computerd, tmp_path):
    assert "/run/screen/want.sock" in computerd.stale_files(str(tmp_path), 1)


def _short_dir():
    import tempfile
    return tempfile.mkdtemp(dir="/tmp")             # AF_UNIX paths are limited


def test_the_bridge_wants_the_browser_only_when_a_client_speaks(computerd):
    """The keeper's boot probe connects and says nothing: that must not start Brave. A DevTools command does."""
    import os
    import socket
    import time

    wants = []
    r_chrome, w_chrome = os.pipe()     # what the bridge writes "to Chrome"
    r_back, _w_back = os.pipe()        # what Chrome would answer
    holder = {}

    def want():
        wants.append(1)
        holder["bridge"].attach(w_chrome, r_back)
        return True

    path = os.path.join(_short_dir(), "c.sock")
    holder["bridge"] = computerd.CdpBridge(path, want=want)
    holder["bridge"].serve()
    probe = socket.socket(socket.AF_UNIX)
    probe.connect(path)
    probe.close()
    time.sleep(0.2)
    assert wants == []
    client = socket.socket(socket.AF_UNIX)
    client.connect(path)
    client.sendall(b'{"id":1}\0')
    assert os.read(r_chrome, 100) == b'{"id":1}\0'
    assert wants == [1]
    client.close()


def test_the_bridge_closes_a_client_when_no_browser_can_start(computerd):
    import os
    import socket

    path = os.path.join(_short_dir(), "c.sock")
    computerd.CdpBridge(path, want=lambda: False).serve()
    client = socket.socket(socket.AF_UNIX)
    client.settimeout(5)
    client.connect(path)
    client.sendall(b'{"id":1}\0')
    assert client.recv(10) == b""
    client.close()


def test_the_want_socket_starts_the_browser_and_says_so(computerd):
    import os
    import socket

    wants = []
    path = os.path.join(_short_dir(), "w.sock")
    computerd.serve_want(path, lambda: wants.append(1) or True)
    client = socket.socket(socket.AF_UNIX)
    client.settimeout(5)
    client.connect(path)
    assert client.recv(10) == b"ok\n"
    assert wants == [1]
    client.close()


def test_roost_pipe_can_ask_for_the_browser(pipe):
    assert pipe.socket_for("want") == "/run/screen/want.sock"
