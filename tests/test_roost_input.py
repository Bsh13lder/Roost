"""C3 Task 3: roost-input clicks and types in the computer's browser window with xdotool, text on stdin only.

Pure tests with a fake ``run``: nothing here starts xdotool or Docker."""

from __future__ import annotations

import importlib.util
import io
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from roost.constants import CU_KEYS, CU_MOVE_STEPS, CU_TYPE_MAX_CHARS, CU_WINDOW_MATCH_PX

_DIR = Path(__file__).resolve().parents[1] / "docker" / "computer"


def _load():
    spec = importlib.util.spec_from_file_location("roost_input", _DIR / "roost_input.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["roost_input"] = module          # a dataclass looks its module up while it is built
    spec.loader.exec_module(module)
    return module


ri = _load()
CHROMIUM_ID, XTERM_ID = "4194307", "6291462"
GEOMETRY = "WINDOW={id}\nX=0\nY=40\nWIDTH=1280\nHEIGHT=760\nSCREEN=0\n"


WINDOW = ["--window", "0", "40", "1280", "760"]       # the bot's window as the desk read it (CDP)
OTHER_GEOMETRY = "WINDOW={id}\nX=200\nY=100\nWIDTH=800\nHEIGHT=600\nSCREEN=0\n"


def _p(argv: list[str]):
    return ri.parse_argv([*argv, *WINDOW])


class FakeX:
    """A pretend X server: answers xdotool's read commands and records every call."""

    def __init__(self, active: str = CHROMIUM_ID, chromium: tuple[str, ...] = (CHROMIUM_ID,),
                 activates: bool = True, fail_on: str = "", geometries: dict[str, str] | None = None) -> None:
        self.active, self.chromium, self.activates, self.fail_on = active, chromium, activates, fail_on
        self.geometries = geometries or {}
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append((list(argv), kwargs))
        verb = argv[1]
        if self.fail_on and self.fail_on == verb:
            raise subprocess.CalledProcessError(1, argv)
        out = {"getactivewindow": f"{self.active}\n", "search": "".join(f"{i}\n" for i in self.chromium),
               "getwindowgeometry": self.geometries.get(argv[-1], GEOMETRY).format(id=argv[-1]),
               "getmouselocation": "X=10\nY=20\nSCREEN=0\nWINDOW=1\n"}.get(verb, "")
        if verb == "windowactivate" and self.activates:
            self.active = argv[-1]
        return subprocess.CompletedProcess(argv, 0, stdout=out.encode(), stderr=b"")

    def acts(self) -> list[list[str]]:
        reads = {"getactivewindow", "search", "getwindowgeometry", "getmouselocation", "windowactivate"}
        return [argv for argv, _ in self.calls if argv[1] not in reads]


def _main(argv: list[str], x: FakeX, stdin: bytes = b"", capsys=None) -> int:
    full = argv if "--window" in argv else [*argv, *WINDOW]
    return ri.main(full, io.BytesIO(stdin), x, sleep=lambda _s: None)


def test_only_the_five_verbs_parse() -> None:
    assert ri.VERBS == ("click", "move", "key", "type", "scroll")
    assert _p(["click", "10", "20"]).verb == "click"
    assert _p(["click", "10", "20", "2"]).count == 2
    assert _p(["move", "1", "2"]).verb == "move"
    assert _p(["key", "Return"]).keysym == "Return"
    assert _p(["type"]).verb == "type"
    assert _p(["scroll", "5", "6", "-3"]).notches == -3
    for bad in ([], ["drag", "1", "2"], ["exec", "sh"], ["click", "1"], ["click", "1", "2", "3"],
                ["type", "hello"], ["scroll", "1", "2", "0"], ["scroll", "1", "2", "11"], ["move", "1", "2", "3"],
                ["click", "a", "b"], ["click", "+1", "2"], ["click", "1", "2", " 1"]):
        with pytest.raises(ri.BadArguments):
            _p(bad)


def test_coordinates_outside_the_screen_are_refused() -> None:
    assert _p(["click", "1279", "799"]).x == 1279
    for bad in (["click", "1280", "10"], ["click", "10", "800"], ["click", "-1", "10"], ["move", "99999", "1"]):
        with pytest.raises(ri.BadArguments):
            _p(bad)


def test_type_reads_text_from_stdin_never_argv(capsys) -> None:
    secret_text = "Dear client, I can start Monday"
    x = FakeX()
    assert _main(["type"], x, secret_text.encode()) == 0
    assert all(secret_text not in " ".join(argv) for argv, _ in x.calls)
    typed = [(argv, kw) for argv, kw in x.calls if argv[1] == "type"]
    assert typed == [([ri.XDOTOOL, "type", "--clearmodifiers", "--delay", "35", "--file", "-"],
                      typed[0][1])]
    assert typed[0][1]["input"] == secret_text.encode()
    assert secret_text not in capsys.readouterr().err


def test_type_refuses_empty_long_broken_or_control_text() -> None:
    for text in (b"", ("a" * (CU_TYPE_MAX_CHARS + 1)).encode(), b"\xff\xfe", b"line one\nline two", b"tab\there"):
        x = FakeX()
        assert _main(["type"], x, text) == 2
        assert x.acts() == []
    assert _main(["type"], FakeX(), "señor €".encode()) == 0


def test_keys_outside_the_list_are_refused() -> None:
    assert ri.KEYSYMS == frozenset(CU_KEYS.values())
    for key in ("ctrl+l", "super", "F12", "alt+F4", "Return+x", "ctrl"):
        with pytest.raises(ri.BadArguments):
            _p(["key", key])
    x = FakeX()
    assert _main(["key", "Return"], x) == 0
    assert x.acts() == [[ri.XDOTOOL, "key", "--clearmodifiers", "Return"]]


def test_a_non_chromium_window_is_refused(capsys) -> None:
    assert not ri.window_ok("XTerm", {"X": 0, "Y": 0, "WIDTH": 1280, "HEIGHT": 800}, (5, 5))
    assert not ri.window_ok("jwm", {"X": 0, "Y": 0, "WIDTH": 1280, "HEIGHT": 800}, None)
    assert ri.window_ok("Brave-browser", {"X": 0, "Y": 0, "WIDTH": 1280, "HEIGHT": 800}, (5, 5))
    assert ri.window_ok("brave-browser", {"X": 0, "Y": 0, "WIDTH": 1280, "HEIGHT": 800}, None)
    # The browser is Brave now: Debian's Chromium class and Brave's hidden leader window ("Brave") are not it.
    for other in ("Chromium", "Brave"):
        assert not ri.window_ok(other, {"X": 0, "Y": 0, "WIDTH": 1280, "HEIGHT": 800}, None)
    assert ri.CHROMIUM_SEARCH == "^brave-browser$"
    for argv in (["click", "100", "100"], ["key", "Return"], ["type"]):
        x = FakeX(active=XTERM_ID, chromium=())
        assert _main(argv, x, b"hello") == 3
        assert x.acts() == []
    assert capsys.readouterr().err.strip().splitlines() == ["not_chromium"] * 3


def test_a_minimized_chromium_window_is_raised_first() -> None:
    x = FakeX(active=XTERM_ID, chromium=("111", CHROMIUM_ID), geometries={"111": OTHER_GEOMETRY})
    assert _main(["click", "100", "100"], x) == 0
    activated = [argv for argv, _ in x.calls if argv[1] == "windowactivate"]
    assert activated == [[ri.XDOTOOL, "windowactivate", "--sync", CHROMIUM_ID]]
    assert x.acts()[-1] == [ri.XDOTOOL, "click", "--repeat", "1", "1"]


def test_a_window_that_will_not_come_up_is_refused() -> None:
    x = FakeX(active=XTERM_ID, chromium=(CHROMIUM_ID,), activates=False)
    assert _main(["click", "100", "100"], x) == 3
    assert x.acts() == []


def test_a_point_outside_the_window_is_refused(capsys) -> None:
    geometry = {"X": 0, "Y": 40, "WIDTH": 1280, "HEIGHT": 760}
    assert not ri.window_ok("Brave-browser", geometry, (100, 39))
    assert ri.window_ok("Brave-browser", geometry, (100, 40))
    assert not ri.window_ok("Brave-browser", geometry, (1280, 100))
    x = FakeX()
    assert _main(["click", "100", "10"], x) == 3
    assert _main(["scroll", "100", "10", "2"], x) == 3
    assert x.acts() == []
    assert capsys.readouterr().err.strip().splitlines() == ["outside", "outside"]


def test_move_path_ends_on_the_target_in_eight_steps() -> None:
    path = ri.move_path((0, 0), (80, 160), CU_MOVE_STEPS)
    assert len(path) == 8
    assert path[-1] == (80, 160)
    assert path[0] != (0, 0)
    assert list(path) == sorted(path)
    x = FakeX()
    assert _main(["click", "330", "420", "2"], x) == 0
    moves = [argv for argv in x.acts() if argv[1] == "mousemove"]
    assert len(moves) == 8 and moves[-1] == [ri.XDOTOOL, "mousemove", "--sync", "330", "420"]
    assert x.acts()[-1] == [ri.XDOTOOL, "click", "--repeat", "2", "1"]


def test_a_move_never_asks_xdotool_to_sync_on_a_point_the_pointer_is_already_on() -> None:
    # `mousemove --sync` to where the pointer already is waits for a motion that never comes (found on the real
    # computer: a second click on the same spot was "input failed" after the 10 s timeout).
    class PointerAt300(FakeX):
        def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            done = super().__call__(argv, **kwargs)
            if argv[1] == "getmouselocation":
                return subprocess.CompletedProcess(argv, 0, stdout=b"X=300\nY=300\nSCREEN=0\nWINDOW=1\n", stderr=b"")
            return done

    x = PointerAt300()
    assert _main(["click", "300", "300"], x) == 0
    assert x.acts() == [[ri.XDOTOOL, "click", "--repeat", "1", "1"]]
    x = PointerAt300()
    assert _main(["click", "302", "301"], x) == 0               # a short hop: eight steps, many rounded alike
    points = [tuple(argv[-2:]) for argv in x.acts() if argv[1] == "mousemove"]
    assert points[-1] == ("302", "301") and len(points) == len(set(points)) and ("300", "300") not in points


def test_scroll_moves_then_turns_the_wheel() -> None:
    x = FakeX()
    assert _main(["scroll", "300", "300", "3"], x) == 0
    assert x.acts()[-1] == [ri.XDOTOOL, "click", "--repeat", "3", "5"]
    x = FakeX()
    assert _main(["scroll", "300", "300", "-2"], x) == 0
    assert x.acts()[-1] == [ri.XDOTOOL, "click", "--repeat", "2", "4"]


def test_no_call_uses_a_shell() -> None:
    x = FakeX(active=XTERM_ID, chromium=(CHROMIUM_ID,))
    for argv, stdin in ((["click", "100", "100"], b""), (["type"], b"hi"), (["key", "Tab"], b""),
                        (["scroll", "100", "100", "1"], b""), (["move", "100", "100"], b"")):
        assert _main(argv, x, stdin) == 0
    assert x.calls
    for argv, kwargs in x.calls:
        assert isinstance(argv, list) and argv[0] == ri.XDOTOOL
        assert kwargs.get("shell", False) is False
        assert kwargs["timeout"] > 0 and kwargs["check"] is True
        assert kwargs["env"]["DISPLAY"] == ":1"
    source = (_DIR / "roost_input.py").read_text()
    assert "shell=True" not in source and "os.system" not in source and "Popen" not in source


def test_errors_print_only_a_fixed_word(capsys) -> None:
    assert _main(["click", "1", "2", "3", "; rm -rf /"], FakeX()) == 2
    assert _main(["click", "100", "100"], FakeX(fail_on="click")) == 4
    assert _main(["type"], FakeX(fail_on="type"), b"my secret words") == 4
    assert _main(["key", "Return"], FakeX(fail_on="getactivewindow")) == 4
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.strip().splitlines() == ["bad arguments", "input failed", "input failed", "input failed"]
    # in_browser and no_window are the full computer's (tests/test_roost_input_screen.py).
    assert {"bad arguments", "not_chromium", "outside", "input failed"} <= set(ri.ERROR_WORDS)


def test_a_timeout_is_input_failed(capsys) -> None:
    def slow(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
    assert ri.main(["key", "Tab", *WINDOW], io.BytesIO(b""), slow, sleep=lambda _s: None) == 4
    assert capsys.readouterr().err.strip() == "input failed"


def test_dockerfile_installs_xdotool_and_roost_input() -> None:
    dockerfile = (_DIR / "Dockerfile").read_text()
    installs = re.sub(r"\\\n", " ", dockerfile)
    apt = [line for line in installs.splitlines() if "apt-get install" in line]
    assert len(apt) == 1 and re.search(r"\bxdotool\b", apt[0])
    assert "COPY --chmod=0755 roost_input.py /usr/local/bin/roost-input" in dockerfile
    for package in ("pcmanfm", "lxterminal", "gpicview", "brave-browser", "tini"):
        assert package in apt[0]
    licences = (_DIR / "licences.sh").read_text()
    assert "xdotool" in licences and "libxdo3" in licences and "BSD" in licences
    notices = (_DIR.parents[1] / "THIRD_PARTY_NOTICES.md").read_text()
    assert re.search(r"xdotool.*BSD-3", notices)
    assert (_DIR / "roost_input.py").read_text().startswith("#!/usr/bin/python3")


# -- security review (b) after Task 10 ------------------------------------------------------------------------


def test_the_window_the_desk_read_is_required_and_checked() -> None:
    assert ri.WINDOW_MATCH_PX == CU_WINDOW_MATCH_PX
    assert _p(["click", "10", "20"]).window == (0, 40, 1280, 760)
    assert ri.parse_argv(["click", "10", "20", "--window", "-300", "0", "800", "600"]).window == (-300, 0, 800, 600)
    for bad in (["click", "10", "20"], ["click", "10", "20", "--window", "0", "40", "1280"],
                ["click", "10", "20", "--window", "0", "40", "0", "760"],
                ["click", "10", "20", "--window", "0", "40", "99999", "760"],
                ["click", "10", "20", "--win", "0", "40", "1280", "760"]):
        with pytest.raises(ri.BadArguments):
            ri.parse_argv(bad)


def test_another_chromium_window_in_front_is_not_clicked() -> None:
    # The user opened a second Chromium window under Take control and left it in front.
    x = FakeX(active="777", chromium=(CHROMIUM_ID, "777"), geometries={"777": OTHER_GEOMETRY})
    assert _main(["click", "300", "300"], x) == 0
    activated = [argv for argv, _ in x.calls if argv[1] == "windowactivate"]
    assert activated == [[ri.XDOTOOL, "windowactivate", "--sync", CHROMIUM_ID]]
    assert x.acts()[-1] == [ri.XDOTOOL, "click", "--repeat", "1", "1"]


def test_no_window_or_two_windows_like_the_bot_s_are_refused(capsys) -> None:
    lookalike = FakeX(active=CHROMIUM_ID, chromium=(CHROMIUM_ID, "777"))           # same place, same size
    assert _main(["click", "300", "300"], lookalike) == 3
    assert lookalike.acts() == []
    elsewhere = FakeX(active="777", chromium=("777",), geometries={"777": OTHER_GEOMETRY})
    assert _main(["type"], elsewhere, b"hello") == 3
    assert elsewhere.acts() == []
    assert capsys.readouterr().err.strip().splitlines() == ["not_chromium", "not_chromium"]


def test_typing_gets_time_for_its_length_and_stops_itself_first() -> None:
    from roost.computer_use.timing import input_budget_s, keeper_input_timeout_s

    assert ri.budget_s(0) == input_budget_s(0)
    assert ri.budget_s(CU_TYPE_MAX_CHARS) == input_budget_s(CU_TYPE_MAX_CHARS)
    assert ri.budget_s(2000) > 2000 * 0.035                      # the whole text fits
    assert keeper_input_timeout_s(2000) > ri.budget_s(2000)       # roost-input gives up before the keeper kills it
    x = FakeX()
    assert _main(["type"], x, b"a" * 1000) == 0
    typed = next(kw for argv, kw in x.calls if argv[1] == "type")
    assert typed["timeout"] > 1000 * 0.035


def test_the_whole_input_keeps_to_one_deadline(capsys) -> None:
    now = [0.0]

    def clock() -> float:
        now[0] += 4.0                                             # every xdotool call seems to take 4 s
        return now[0]

    x = FakeX()
    code = ri.main(["click", "100", "100", *WINDOW], io.BytesIO(b""), x, sleep=lambda _s: None, clock=clock)
    assert code == 4 and capsys.readouterr().err.strip() == "input failed"
    assert all(kw["timeout"] <= ri.TIMEOUT_S for _argv, kw in x.calls)


def test_a_framed_window_is_matched_at_its_true_place_not_xdotools_doubled_one(monkeypatch) -> None:
    """xdotool's getwindowgeometry adds a window manager frame's offset twice: JWM's 3px border and 30px title put
    Brave's page area at (3, 30), which CDP reports, while xdotool says (6, 60). The true place is read from X."""
    framed = "WINDOW={id}\nX=6\nY=60\nWIDTH=1274\nHEIGHT=708\nSCREEN=0\n"
    monkeypatch.setattr(ri, "_x11_origin", lambda window: (3, 30))
    x = FakeX(geometries={CHROMIUM_ID: framed})
    argv = ["click", "100", "100", "--window", "3", "30", "1274", "708"]
    assert ri.main(argv, io.BytesIO(b""), x, sleep=lambda _s: None) == ri.EXIT_OK
    assert any(a[1] == "click" for a in x.acts())


def test_without_an_x_answer_xdotools_place_is_kept(monkeypatch) -> None:
    framed = "WINDOW={id}\nX=6\nY=60\nWIDTH=1274\nHEIGHT=708\nSCREEN=0\n"
    monkeypatch.setattr(ri, "_x11_origin", lambda window: None)
    x = FakeX(geometries={CHROMIUM_ID: framed})
    argv = ["click", "100", "100", "--window", "3", "30", "1274", "708"]
    assert ri.main(argv, io.BytesIO(b""), x, sleep=lambda _s: None) == ri.EXIT_REFUSED


def test_the_x11_origin_is_none_where_no_display_answers() -> None:
    assert ri._x11_origin("not-a-number") is None
