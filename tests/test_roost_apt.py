"""roost-apt (docs/plans/2026-10-22-roost-install-app.md §3): apt inside the computer, Debian bookworm main only.

Pure tests with a fake ``run``: nothing here starts apt or Docker. They pin the argv of every apt call (its own
Debian-only sources, no shell, no files, no URLs) and the origin check on ``apt-cache policy``."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[1] / "docker" / "computer"


def _load():
    spec = importlib.util.spec_from_file_location("roost_apt", _DIR / "roost_apt.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["roost_apt"] = module
    spec.loader.exec_module(module)
    return module


ra = _load()

DEBIAN_POLICY = """jq:
  Installed: (none)
  Candidate: 1.6-2.1+deb12u1
  Version table:
     1.6-2.1+deb12u1 500
        500 https://deb.debian.org/debian bookworm/main arm64 Packages
        500 https://deb.debian.org/debian-security bookworm-security/main arm64 Packages
     1.6-2.1 400
        400 https://example.org/other stable/main arm64 Packages
"""
BRAVE_POLICY = """brave-keyring:
  Installed: (none)
  Candidate: 1.15
  Version table:
     1.15 500
        500 https://brave-browser-apt-release.s3.brave.com stable/main arm64 Packages
"""
CONTRIB_POLICY = """unrar:
  Installed: (none)
  Candidate: 1:6.2.6-1
  Version table:
     1:6.2.6-1 500
        500 https://deb.debian.org/debian bookworm/non-free arm64 Packages
"""
MIXED_POLICY = """jq:
  Installed: (none)
  Candidate: 1.7
  Version table:
     1.7 500
        500 https://deb.debian.org/debian bookworm/main arm64 Packages
        500 https://evil.example stable/main arm64 Packages
"""
NONE_POLICY = """nothere:
  Installed: (none)
  Candidate: (none)
  Version table:
"""
SHOW = "Package: jq\nVersion: 1.6-2.1+deb12u1\nDescription: lightweight and flexible command-line JSON processor\n"


class FakeApt:
    """Answers each apt argv by its verb; records every call."""

    def __init__(self, *, installed=(), policy=DEBIAN_POLICY, sim="Remv jq [1.6]\n", fail=None) -> None:
        self.calls: list[list[str]] = []
        self.installed = set(installed)
        self.policy, self.sim, self.fail = policy, sim, fail

    def __call__(self, argv, timeout_s):
        self.calls.append(list(argv))
        if argv[0] == ra.DPKG_QUERY:
            name = argv[-1]
            return (0, "install ok installed") if name in self.installed else (1, "")
        verb = next(word for word in argv[1:] if not word.startswith("-") and "=" not in word and word != "-o")
        if verb == self.fail:
            return (100, "E: boom")
        if verb == "policy":
            return (0, self.policy)
        if verb == "show":
            return (0, SHOW)
        if verb == "remove" and "-s" in argv:
            return (0, self.sim)
        return (0, "")


def _main(args, apt, *, stale=True):
    out, err = io.StringIO(), io.StringIO()
    code = ra.main(args, run=apt, out=out, err=err, lists_stale=lambda: stale, mark_updated=lambda: None)
    return code, out.getvalue(), err.getvalue().strip()


def _apt_calls(apt):
    return [c for c in apt.calls if c[0] in (ra.APT_GET, ra.APT_CACHE)]


def test_every_apt_call_uses_only_debian_sources_and_never_a_shell():
    apt = FakeApt()
    assert _main(["install", "jq"], apt)[0] == 0
    for argv in _apt_calls(apt):
        joined = " ".join(argv)
        assert f"Dir::Etc::SourceList={ra.SOURCE_LIST}" in joined
        assert f"Dir::Etc::SourceParts={ra.SOURCE_PARTS}" in joined
        assert f"Dir::State::Lists={ra.LISTS_DIR}" in joined
        assert "Acquire::https::Proxy=http://roost-egress:3128" in joined
        assert "sh" not in (argv[0], "-c") and ".deb" not in joined and "dpkg -i" not in joined
    install = [c for c in apt.calls if "install" in c]
    assert install == [[ra.APT_GET, *ra.APT_OPTIONS, "install", "-y", "--no-install-recommends", "-q", "--", "jq"]]


def test_the_sources_file_is_debian_bookworm_main_only():
    lines = [line for line in ra.DEBIAN_SOURCES.splitlines() if line.strip()]
    assert lines and all(line.startswith("deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] "
                                         "https://deb.debian.org/") for line in lines)
    assert all(line.split()[-1] == "main" for line in lines)
    assert {line.split()[-2] for line in lines} == {"bookworm", "bookworm-updates", "bookworm-security"}
    assert "brave" not in ra.DEBIAN_SOURCES


def test_the_image_ships_the_same_sources_and_installs_roost_apt():
    assert (_DIR / "config" / "roost-apt-debian.list").read_text() == ra.DEBIAN_SOURCES
    dockerfile = (_DIR / "Dockerfile").read_text()
    assert "COPY --chmod=0755 roost_apt.py /usr/local/bin/roost-apt" in dockerfile
    assert f"COPY config/roost-apt-debian.list {ra.SOURCE_LIST}" in dockerfile
    assert f"mkdir -p {ra.SOURCE_PARTS} {ra.LISTS_DIR}/partial" in dockerfile


@pytest.mark.parametrize("policy,ok", [
    (DEBIAN_POLICY, True), (BRAVE_POLICY, False), (CONTRIB_POLICY, False), (MIXED_POLICY, False),
    (NONE_POLICY, False), ("", False),
])
def test_only_a_debian_main_candidate_passes(policy, ok):
    assert ra.candidate_is_debian(policy) is ok


def test_a_non_debian_candidate_is_refused_before_any_install():
    apt = FakeApt(policy=BRAVE_POLICY)
    code, _, err = _main(["install", "some-tool"], apt)
    assert (code, err) == (ra.EXIT_REFUSED, "not_debian")
    assert not any("install" in c for c in apt.calls)


def test_an_unknown_package_is_not_found():
    code, _, err = _main(["install", "nothere"], FakeApt(policy=NONE_POLICY))
    assert (code, err) == (ra.EXIT_REFUSED, "not_found")


@pytest.mark.parametrize("args,word", [
    (["install", "sudo"], "denied"), (["install", "firefox-esr"], "denied"), (["install", "Bad;name"], "bad arguments"),
    (["install"], "bad arguments"), (["install", "jq", "gimp"], "bad arguments"), (["frobnicate", "jq"], "bad arguments"),
    (["install", "https://x.org/a.deb"], "bad arguments"), (["ensure", "jq", "tor"], "denied"),
])
def test_bad_or_denied_names_never_reach_apt(args, word):
    apt = FakeApt()
    code, _, err = _main(args, apt)
    assert err == word and code in (ra.EXIT_BAD, ra.EXIT_REFUSED)
    assert _apt_calls(apt) == []


def test_an_installed_package_is_refused():
    apt = FakeApt(installed={"jq"})
    assert _main(["install", "jq"], apt)[2] == "already_installed"
    assert not any("install" in c for c in _apt_calls(apt))


def test_fresh_lists_skip_the_update():
    apt = FakeApt()
    _main(["install", "jq"], apt, stale=False)
    assert not any("update" in c for c in apt.calls)
    apt = FakeApt()
    _main(["install", "jq"], apt, stale=True)
    assert [c for c in apt.calls if "update" in c] == [[ra.APT_GET, *ra.APT_OPTIONS, "update", "-q"]]


def test_describe_prints_debians_one_line():
    code, out, _ = _main(["describe", "jq"], FakeApt())
    assert code == 0
    assert json.loads(out) == {"package": "jq", "version": "1.6-2.1+deb12u1",
                               "description": "lightweight and flexible command-line JSON processor"}


def test_remove_is_refused_when_it_would_take_more():
    apt = FakeApt(installed={"jq"}, sim="Remv libjq1:arm64 [1.6]\nRemv jq [1.6]\n")
    assert _main(["remove", "jq"], apt)[2] == "would_remove_others"
    assert not any("-y" in c and "remove" in c for c in apt.calls)


def test_remove_runs_one_fixed_argv():
    apt = FakeApt(installed={"jq"})
    assert _main(["remove", "jq"], apt)[0] == 0
    assert apt.calls[-1] == [ra.APT_GET, *ra.APT_OPTIONS, "remove", "-y", "--no-auto-remove", "-q", "--", "jq"]
    assert _main(["remove", "gimp"], FakeApt())[2] == "not_installed"


def test_ensure_installs_only_the_missing_in_one_call():
    apt = FakeApt(installed={"jq"})
    assert _main(["ensure", "jq", "gimp", "vlc"], apt)[0] == 0
    installs = [c for c in apt.calls if "install" in c]
    assert installs == [[ra.APT_GET, *ra.APT_OPTIONS, "install", "-y", "--no-install-recommends", "-q", "--",
                         "gimp", "vlc"]]
    apt = FakeApt(installed={"jq"})
    assert _main(["ensure", "jq"], apt)[0] == 0 and _apt_calls(apt) == []


def test_an_apt_failure_is_one_word_and_never_apts_output():
    code, out, err = _main(["install", "jq"], FakeApt(fail="install"))
    assert (code, err, out) == (ra.EXIT_FAILED, "failed", "")
