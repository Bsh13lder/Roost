"""The roost-computer image's files, checked without Docker."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "docker" / "computer"
DOCKERFILE = (DIR / "Dockerfile").read_text()
SPIKE = ROOT / "spikes" / "computers-c0"
FIVE = {"clone", "clone3", "unshare", "setns", "chroot"}


def _instructions() -> list[str]:
    text = re.sub(r"\\\n", " ", DOCKERFILE)
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def test_the_base_is_pinned_by_digest():
    froms = [ln for ln in _instructions() if ln.startswith("FROM ")]
    assert len(froms) == 1 and re.search(r"debian:bookworm-slim@sha256:[0-9a-f]{64}", froms[0])


def test_it_runs_as_the_computer_user_with_no_port_and_tini_first():
    lines = _instructions()
    assert "USER 10002" in lines
    assert not [ln for ln in lines if ln.startswith("EXPOSE")]
    assert 'ENTRYPOINT ["/usr/bin/tini", "--", "/start.sh"]' in lines
    assert "useradd" in DOCKERFILE and "10002" in DOCKERFILE


def test_no_extra_vnc_or_web_bridges_are_installed():
    everything = "\n".join(p.read_text() for p in DIR.iterdir() if p.is_file()).lower()
    for banned in ("websockify", "x11vnc", "xpra", "kasmvnc", "--no-sandbox"):
        assert banned not in everything


def test_it_installs_the_proven_packages_without_recommends():
    for package in ("tigervnc-standalone-server", "jwm", "xterm", "tini", "brave-browser", "fonts-liberation",
                    "python3", "ca-certificates"):
        assert package in DOCKERFILE
    assert "--no-install-recommends" in DOCKERFILE and "rm -rf /var/lib/apt/lists" in DOCKERFILE


def test_brave_comes_from_its_own_repo_with_a_pinned_key_and_its_extras_off():
    # Owner decision 2026-10-22: Brave, not Debian's chromium (Google refuses sign-in there).
    install = re.sub(r"\\\n", " ", DOCKERFILE)
    assert not re.search(r"\bchromium\b", install.split("apt-get install", 2)[2].split("&&")[0])
    assert re.search(r"BRAVE_KEY_SHA256=[0-9a-f]{64}", DOCKERFILE) and "sha256sum -c" in DOCKERFILE
    assert "BRAVE_REPO=https://brave-browser-apt-release.s3.brave.com" in DOCKERFILE
    assert "deb [signed-by=$BRAVE_KEYRING]" in DOCKERFILE
    assert "COPY brave-policies.json /etc/brave/policies/managed/" in DOCKERFILE
    policies = json.loads((DIR / "brave-policies.json").read_text())
    for name in ("BraveRewardsDisabled", "BraveWalletDisabled", "BraveVPNDisabled", "TorDisabled"):
        assert policies[name] is True
    for name in ("BraveAIChatEnabled", "BraveP3AEnabled", "BraveStatsPingEnabled", "MetricsReportingEnabled",
                 "BackgroundModeEnabled"):
        assert policies[name] is False


def test_the_licence_scan_runs_as_the_last_run_of_the_build():
    runs = [ln for ln in _instructions() if ln.startswith("RUN ")]
    assert "licences.sh" in runs[-1]
    script = (DIR / "licences.sh").read_text()
    assert "AGPL" in script and "SSPL" in script and "exit 1" in script


def test_start_sh_clears_stale_files_then_hands_over_to_the_supervisor():
    script = (DIR / "start.sh").read_text()
    assert script.startswith("#!/bin/sh")
    assert "exec roost-computerd" in script
    assert "rm -f" in script


def test_the_scripts_are_installed_and_the_jwm_menu_has_no_exit():
    assert "roost-computerd" in DOCKERFILE and "roost-pipe" in DOCKERFILE and "system.jwmrc" in DOCKERFILE
    rc = (DIR / "system.jwmrc").read_text()
    assert "Terminal" in rc
    # The Browser button only asks the running Chromium for a new window: a second Chromium would skip the proxy.
    assert "exec:roost-browser" in rc and "exec:chromium" not in rc and "exec:brave" not in rc
    assert "Exit" not in rc and "Restart" not in rc


def test_the_desktop_has_window_buttons_a_task_list_and_show_desktop():
    rc = (DIR / "system.jwmrc").read_text()
    assert "<TaskList" in rc                     # a minimized window comes back from the bar
    assert "showdesktop" in rc                   # one press clears the screen
    assert "<Background" in rc                   # a desktop behind the windows, not black
    assert "tiled" not in rc                     # windows can be moved, resized and minimized
    assert "<ButtonMin" in rc or "minimize" in rc.lower()


def test_the_desktop_is_calm_with_a_centred_dock_and_no_desktop_icons():
    for package in ("pcmanfm", "lxterminal", "gpicview", "papirus-icon-theme", "tzdata"):
        assert package in DOCKERFILE
    rc = (DIR / "system.jwmrc").read_text()
    for command in ("roost-browser", "pcmanfm", "lxterminal"):
        assert f"exec:{command}" in rc
    for gone in ("mousepad", "galculator"):          # the owner's call: a bot installs an editor when it needs one
        assert gone not in DOCKERFILE and f"exec:{gone}" not in rc
    assert 'halign="center"' in rc                 # a small dock in the middle, not a full-width bar
    assert 'labeled="false"' in rc                 # open windows show as icons only
    assert "pcmanfm --desktop" not in rc and "<Clock" not in rc
    assert "Desktop/" not in DOCKERFILE and not (DIR / "desktop").exists()
    assert 'cp -R /usr/share/roost/home/. "$HOME"/' in (DIR / "start.sh").read_text()

def test_roost_browser_never_starts_its_own_chromium():
    script = (DIR / "roost-browser").read_text()
    assert "SingletonSocket" in script                  # only when the supervised Chromium is up
    assert "--user-data-dir=/home/comp/profile" in script
    assert "--proxy-server=http://roost-egress:3128" in script
    # D5: with no Brave up it asks roost-computerd for the supervised one, never runs brave-browser bare.
    assert "roost-pipe want" in script
    before_check = script.split("SingletonSocket")[0]
    assert "brave-browser" not in before_check


def test_the_wallpaper_is_made_at_build_time_with_the_standard_library():
    assert "make_wallpaper.py" in DOCKERFILE
    source = (DIR / "make_wallpaper.py").read_text()
    assert "import zlib" in source and "PIL" not in source


def test_make_computer_image_runs_the_disk_guard_before_docker_build():
    makefile = (ROOT / "Makefile").read_text()
    target = makefile.split("\ncomputer-image:")[1].split("\n\n")[0]
    assert target.index("df -g /System/Volumes/Data") < target.index("docker build -t roost-computer:dev docker/computer")
    deploy = makefile.split("\ndeploy:")[1].split("\n\n")[0]
    assert "roost-computer:dev" in deploy and "computer-image" in deploy


def _profile() -> dict:
    path = ROOT / "roost" / "keeper" / "seccomp" / "chromium.json"
    return json.loads(path.read_text())


def test_the_seccomp_profile_is_dockers_default_plus_exactly_five_syscalls():
    default = json.loads((SPIKE / "default-seccomp.json").read_text())
    ours = _profile()
    assert ours["defaultAction"] != "SCMP_ACT_ALLOW"
    assert ours["defaultAction"] == default["defaultAction"]
    extra = [rule for rule in ours["syscalls"] if rule not in default["syscalls"]]
    assert len(extra) == 1
    assert extra[0]["action"] == "SCMP_ACT_ALLOW" and set(extra[0]["names"]) == FIVE
    assert not extra[0].get("args") and not extra[0].get("includes") and not extra[0].get("excludes")
    assert [r for r in default["syscalls"] if r in ours["syscalls"]] == default["syscalls"]
    rest = {k: v for k, v in ours.items() if k != "syscalls"}
    assert rest == {k: v for k, v in default.items() if k != "syscalls"}


def test_the_seccomp_profile_is_packaged_and_licensed():
    folder = ROOT / "roost" / "keeper" / "seccomp"
    assert (folder / "__init__.py").exists()
    assert "SPDX-License-Identifier: Apache-2.0" in (folder / "chromium.json.license").read_text()
    names = subprocess.run(["uv", "run", "python", "-c",
                            "import importlib.resources as r; print(r.files('roost.keeper.seccomp').joinpath('chromium.json').is_file())"],
                           cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert names == "True"
