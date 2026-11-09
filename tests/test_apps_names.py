"""Install an app (docs/plans/2026-10-22-roost-install-app.md §2): Debian's name rule and the hard deny list.

The image's own packages are on the deny list (read from its Dockerfile), and roost-apt inside the computer holds
the same lists as the gateway."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from roost.apps.constants import APP_DENIED_PATTERNS, APP_IMAGE_PACKAGES, APP_NAME_PATTERN
from roost.apps.names import is_denied, package_refusal

_DIR = Path(__file__).resolve().parents[1] / "docker" / "computer"


def _load_roost_apt():
    spec = importlib.util.spec_from_file_location("roost_apt", _DIR / "roost_apt.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["roost_apt"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["gimp", "jq", "libreoffice-calc", "g++", "python3-pandas", "inkscape", "x2"])
def test_good_names_pass(name):
    assert package_refusal(name) is None


@pytest.mark.parametrize("name", [
    "", "a", "Gimp", "-gimp", ".jq", "jq;rm -rf /", "jq rm", "../jq", "jq/", "https://x.org/a.deb", "a.deb ",
    "x" * 64, "jq\n", "jq=1.6", "jq:amd64", "ji*", "./local.deb",
])
def test_bad_names_are_refused(name):
    assert package_refusal(name) is not None
    assert re.fullmatch(APP_NAME_PATTERN, name) is None


@pytest.mark.parametrize("name", [
    "chromium", "chromium-driver", "brave-browser", "firefox-esr", "google-chrome-stable", "epiphany-browser",
    "sudo", "sudo-ldap", "doas", "openssh-server", "tor", "torsocks", "proxychains4", "docker.io",
    "docker-compose", "openvpn", "network-manager-openvpn", "wireguard-tools", "xserver-xorg",
    "tigervnc-standalone-server", "jwm", "python3", "xdotool", "apt", "dpkg", "pcmanfm", "tini", "podman",
])
def test_denied_names(name):
    assert is_denied(name)
    assert package_refusal(name) is not None


def test_ordinary_apps_are_not_denied():
    assert not any(is_denied(n) for n in ("gimp", "jq", "libreoffice-writer", "vlc", "python3-numpy", "curl"))


def _dockerfile_packages() -> set[str]:
    text = (_DIR / "Dockerfile").read_text().replace("\\\n", " ")
    found: set[str] = set()
    for match in re.finditer(r"apt-get install -y --no-install-recommends([^&]*)", text):
        found |= {word for word in match.group(1).split() if not word.startswith("-")}
    return found


def test_every_package_the_image_installs_is_denied():
    packages = _dockerfile_packages()
    assert {"brave-browser", "xdotool", "jwm", "python3"} <= packages
    assert packages <= APP_IMAGE_PACKAGES
    assert all(is_denied(name) for name in packages)


def test_roost_apt_holds_the_same_rules():
    ra = _load_roost_apt()
    assert ra.NAME_PATTERN == APP_NAME_PATTERN
    assert frozenset(ra.DENIED_PATTERNS) == frozenset(APP_DENIED_PATTERNS)
    assert frozenset(ra.IMAGE_PACKAGES) == APP_IMAGE_PACKAGES


def test_a_package_the_computer_comes_with_says_so_instead_of_a_refusal():
    assert package_refusal("pcmanfm") == "pcmanfm comes with the computer already, so there is nothing to install."
    assert package_refusal("sudo") == "sudo can't be installed on a bot's computer."
