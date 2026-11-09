"""Full computer, Step 1: roost-input's `front`, `browsers` and `open` verbs and its `--screen` mode.

Pure tests with a fake ``run``: nothing here starts xdotool, dpkg or Docker."""

from __future__ import annotations

import io
import subprocess
from typing import Any

import pytest

from test_roost_input import CHROMIUM_ID, GEOMETRY, OTHER_GEOMETRY, XTERM_ID, ri

BRAVE_RECT = (0, 40, 1280, 760)          # GEOMETRY's window


class FakeHost:
    """A pretend X server, dpkg and file system: answers the read commands and records every call."""

    def __init__(self, active: str | None = XTERM_ID, chromium: tuple[str, ...] = (CHROMIUM_ID,),
                 visible: tuple[str, ...] | None = None, geometries: dict[str, str] | None = None,
                 dpkg: str = "", files: dict[str, str] | None = None, activates: bool = True) -> None:
        self.active, self.chromium = active, chromium
        self.visible = chromium if visible is None else visible
        self.geometries = geometries or {}
        self.dpkg, self.files, self.activates = dpkg, files or {}, activates
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout=self._answer(argv).encode(), stderr=b"")

    def _answer(self, argv: list[str]) -> str:
        if argv[0] == ri.DPKG:
            return self.dpkg
        verb = argv[1] if len(argv) > 1 else ""
        if verb == "getactivewindow":
            if self.active is None:
                raise subprocess.CalledProcessError(1, argv)
            return f"{self.active}\n"
        if verb == "search":
            found = self.visible if "--onlyvisible" in argv else self.chromium
            if not found:
                raise subprocess.CalledProcessError(1, argv)
            return "".join(f"{i}\n" for i in found)
        if verb == "getwindowgeometry":
            return self.geometries.get(argv[-1], GEOMETRY).format(id=argv[-1])
        if verb == "getmouselocation":
            return "X=10\nY=20\nSCREEN=0\nWINDOW=1\n"
        if verb == "windowactivate" and self.activates:
            self.active = argv[-1]
        return ""

    def read(self, path: str) -> str | None:
        return self.files.get(path)

    def which(self, name: str) -> str | None:
        return name if name.startswith("/") else f"/usr/bin/{name}"

    def acts(self) -> list[list[str]]:
        reads = {"getactivewindow", "search", "getwindowgeometry", "getmouselocation", "windowactivate"}
        return [argv for argv, _ in self.calls if argv[0] == ri.XDOTOOL and argv[1] not in reads]

    def launched(self) -> list[list[str]]:
        return [argv for argv, _ in self.calls if argv[0] == ri.SETSID]


def _main(argv: list[str], host: FakeHost, stdin: bytes = b"") -> int:
    return ri.main(argv, io.BytesIO(stdin), host, sleep=lambda _s: None, read=host.read, which=host.which)


# -- parsing ---------------------------------------------------------------------------------------------------


def test_the_new_shapes_parse_and_nothing_else() -> None:
    assert ri.parse_argv(["front"]).verb == "front"
    assert ri.parse_argv(["browsers"]).verb == "browsers"
    assert ri.parse_argv(["open", "files"]).app == "files"
    assert ri.parse_argv(["open", "geany"]).app == "geany"
    assert ri.parse_argv(["open", "libreoffice-calc"]).app == "libreoffice-calc"
    screen = ri.parse_argv(["click", "10", "20", "--screen"])
    assert screen.screen and screen.verb == "click" and screen.window == (0, 0, 0, 0)
    assert ri.parse_argv(["type", "--screen"]).screen
    for bad in (["front", "x"], ["browsers", "1"], ["open"], ["open", "a", "b"], ["open", "Geany"],
                ["open", "../bin/sh"], ["open", "-rf"], ["open", "a"], ["open", "x" * 70], ["open", "files;sh"],
                ["click", "10", "20", "--screen", "--window", "0", "40", "1280", "760"], ["--screen"],
                ["click", "1280", "20", "--screen"], ["key", "ctrl+l", "--screen"], ["type", "hi", "--screen"]):
        with pytest.raises(ri.BadArguments):
            ri.parse_argv(bad)


# -- front, browsers -------------------------------------------------------------------------------------------


def test_front_says_brave_and_its_rect_or_other_and_nothing_else(capsys) -> None:
    assert _main(["front"], FakeHost(active=CHROMIUM_ID)) == 0
    assert capsys.readouterr().out == "brave 0 40 1280 760\n"
    assert _main(["front"], FakeHost(active=XTERM_ID)) == 0
    assert capsys.readouterr().out == "other\n"
    assert _main(["front"], FakeHost(active=None, chromium=())) == 0       # an empty desktop has no active window
    out = capsys.readouterr()
    assert out.out == "other\n" and out.err == ""


def test_browsers_prints_only_the_visible_brave_rects(capsys) -> None:
    host = FakeHost(chromium=(CHROMIUM_ID, "777", "888"), visible=(CHROMIUM_ID, "777"),
                    geometries={"777": OTHER_GEOMETRY})
    assert _main(["browsers"], host) == 0
    assert capsys.readouterr().out == "0 40 1280 760\n200 100 800 600\n"
    assert _main(["browsers"], FakeHost(chromium=(), visible=())) == 0
    assert capsys.readouterr().out == ""
    assert host.acts() == [] and host.launched() == []


def test_browsers_lists_at_most_the_cap(capsys) -> None:
    many = tuple(str(1000 + i) for i in range(ri.MAX_BROWSER_WINDOWS + 5))
    assert _main(["browsers"], FakeHost(chromium=many)) == 0
    assert len(capsys.readouterr().out.splitlines()) == ri.MAX_BROWSER_WINDOWS


# -- --screen acts ---------------------------------------------------------------------------------------------


def test_a_screen_click_outside_every_brave_window_runs() -> None:
    host = FakeHost(active=XTERM_ID, visible=("777",), geometries={"777": OTHER_GEOMETRY})
    assert _main(["click", "100", "50", "--screen"], host) == 0
    assert host.acts()[-1] == [ri.XDOTOOL, "click", "--repeat", "1", "1"]
    assert not [argv for argv, _ in host.calls if argv[1:2] == ["windowactivate"]]   # nothing is raised


def test_a_screen_point_inside_a_visible_brave_window_is_refused(capsys) -> None:
    host = FakeHost(active=XTERM_ID, visible=(CHROMIUM_ID,))
    assert _main(["click", "100", "100", "--screen"], host) == 3
    assert _main(["scroll", "100", "100", "2", "--screen"], host) == 3
    assert host.acts() == []
    assert capsys.readouterr().err.strip().splitlines() == ["in_browser", "in_browser"]


def test_a_minimized_brave_window_does_not_fence_the_screen() -> None:
    host = FakeHost(active=XTERM_ID, chromium=(CHROMIUM_ID,), visible=())
    assert _main(["click", "100", "100", "--screen"], host) == 0


def test_screen_acts_are_refused_while_brave_is_in_front(capsys) -> None:
    for argv, stdin in ((["key", "Return", "--screen"], b""), (["type", "--screen"], b"hello"),
                        (["click", "5", "5", "--screen"], b"")):
        host = FakeHost(active=CHROMIUM_ID, visible=())
        assert _main(argv, host, stdin) == 3
        assert host.acts() == []
    assert capsys.readouterr().err.strip().splitlines() == ["in_browser"] * 3


def test_screen_typing_reads_stdin_only_and_keys_stay_on_the_list(capsys) -> None:
    secret = "my words for the terminal"
    host = FakeHost(active=XTERM_ID)
    assert _main(["type", "--screen"], host, secret.encode()) == 0
    typed = [(argv, kw) for argv, kw in host.calls if argv[1:2] == ["type"]]
    assert typed[0][0] == [ri.XDOTOOL, "type", "--clearmodifiers", "--delay", "35", "--file", "-"]
    assert typed[0][1]["input"] == secret.encode()
    assert all(secret not in " ".join(argv) for argv, _ in host.calls)
    assert secret not in capsys.readouterr().err
    assert _main(["key", "Escape", "--screen"], FakeHost(active=XTERM_ID)) == 0
    # With no active window xdotool can't say where a key would go, so typing and keys are refused; a click at a
    # point outside Brave still lands (it picks its own window).
    for argv, stdin in ((["key", "Escape", "--screen"], b""), (["type", "--screen"], b"hi")):
        assert _main(argv, FakeHost(active=None), stdin) == 3
    assert _main(["click", "700", "500", "--screen"], FakeHost(active=None, visible=())) == 0


# -- open ------------------------------------------------------------------------------------------------------


def test_open_runs_a_fixed_app_detached_with_no_shell() -> None:
    host = FakeHost()
    assert _main(["open", "files"], host) == 0
    assert _main(["open", "terminal"], host) == 0
    assert _main(["open", "images"], host) == 0
    assert host.launched() == [[ri.SETSID, "-f", "/usr/bin/pcmanfm", "/home/comp"],
                               [ri.SETSID, "-f", "/usr/bin/lxterminal"], [ri.SETSID, "-f", "/usr/bin/gpicview"]]
    for argv, kwargs in host.calls:
        if argv[0] == ri.SETSID:
            assert kwargs.get("shell", False) is False and kwargs["stdout"] == subprocess.DEVNULL
            assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["stderr"] == subprocess.DEVNULL
            assert kwargs["env"]["DISPLAY"] == ":1" and kwargs["timeout"] > 0


def test_open_browser_raises_an_existing_window_else_starts_one() -> None:
    host = FakeHost(active=XTERM_ID, chromium=(CHROMIUM_ID,))
    assert _main(["open", "browser"], host) == 0
    assert host.active == CHROMIUM_ID and host.launched() == []
    empty = FakeHost(active=XTERM_ID, chromium=())
    assert _main(["open", "browser"], empty) == 0
    assert empty.launched() == [[ri.SETSID, "-f", "/usr/local/bin/roost-browser"]]


_GEANY = "[Desktop Entry]\nName=Geany\nExec=geany %F --new-instance\nType=Application\n"


def test_open_a_package_runs_its_first_desktop_entry_with_field_codes_removed() -> None:
    host = FakeHost(dpkg="/usr/bin/geany\n/usr/share/doc/geany\n/usr/share/applications/geany.desktop\n",
                    files={"/usr/share/applications/geany.desktop": _GEANY})
    assert _main(["open", "geany"], host) == 0
    assert [argv for argv, _ in host.calls if argv[0] == ri.DPKG] == [[ri.DPKG, "-L", "geany"]]
    assert host.launched() == [[ri.SETSID, "-f", "/usr/bin/geany", "--new-instance"]]


def test_open_parses_quotes_and_skips_terminal_and_other_groups() -> None:
    files = {
        "/usr/share/applications/a.desktop": "[Desktop Entry]\nExec=vim %f\nTerminal=true\n",
        "/usr/share/applications/b.desktop": "[Desktop Action New]\nExec=evil\n[Desktop Entry]\n"
                                             "Exec=\"/opt/my app/run\" --title \"two words\" %U %%\n",
    }
    host = FakeHost(dpkg="/usr/share/applications/a.desktop\n/usr/share/applications/b.desktop\n", files=files)
    assert _main(["open", "myapp"], host) == 0
    assert host.launched() == [[ri.SETSID, "-f", "/opt/my app/run", "--title", "two words", "%"]]


def test_a_package_with_no_window_is_refused(capsys) -> None:
    for dpkg, files in (("/usr/bin/tool\n", {}),
                        ("/usr/share/applications/x.desktop\n", {"/usr/share/applications/x.desktop": "[Desktop Entry]\nName=X\n"}),
                        ("/usr/share/applications/x.desktop\n", {}),
                        ("/etc/xdg/autostart/x.desktop\n", {"/etc/xdg/autostart/x.desktop": _GEANY})):
        host = FakeHost(dpkg=dpkg, files=files)
        assert _main(["open", "tool"], host) == 3
        assert host.launched() == []
    assert capsys.readouterr().err.strip().splitlines() == ["no_window"] * 4


def test_a_package_dpkg_does_not_know_is_no_window(capsys) -> None:
    class Unknown(FakeHost):
        def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if argv[0] == ri.DPKG:
                raise subprocess.CalledProcessError(1, argv)
            return super().__call__(argv, **kwargs)

    assert _main(["open", "nothere"], Unknown()) == 3
    assert capsys.readouterr().err.strip() == "no_window"


def test_open_refuses_a_program_that_is_not_there(capsys) -> None:
    host = FakeHost(dpkg="/usr/share/applications/geany.desktop\n",
                    files={"/usr/share/applications/geany.desktop": _GEANY})
    code = ri.main(["open", "geany"], io.BytesIO(b""), host, sleep=lambda _s: None, read=host.read,
                   which=lambda _name: None)
    assert code == 3 and host.launched() == []
    assert capsys.readouterr().err.strip() == "no_window"


def test_the_error_words_are_fixed() -> None:
    assert set(ri.ERROR_WORDS) == {"bad arguments", "not_chromium", "outside", "input failed", "in_browser",
                                   "no_window"}


def test_roost_input_mirrors_the_constants() -> None:
    from roost.constants import CU_APP_NAME_RE, CU_BROWSER_WINDOWS_MAX, CU_OPEN_APPS

    assert ri.MAX_BROWSER_WINDOWS == CU_BROWSER_WINDOWS_MAX
    assert ri.APP_NAME.pattern == CU_APP_NAME_RE
    assert (ri.BROWSER_APP, *ri.FIXED_APPS) == CU_OPEN_APPS
