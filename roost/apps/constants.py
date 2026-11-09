"""The constants of installing apps (docs/plans/2026-10-22-roost-install-app.md).

Kept apart from ``roost/constants.py`` (already past its size), with no Roost imports, so the keeper and the gateway
share one copy. ``docker/computer/roost_apt.py`` holds its own copy of the name rule and the deny lists, because the
computer image carries no Roost code; ``tests/test_apps_names.py`` keeps the two equal."""

from __future__ import annotations

from typing import Final

# Debian's package name rule (Debian Policy §5.6.1), anchored.
APP_NAME_PATTERN: Final = r"^[a-z0-9][a-z0-9+.-]{1,62}$"

# Every package the computer image's Dockerfile installs: never installed or removed through install_app.
APP_IMAGE_PACKAGES: Final = frozenset({
    "python3", "ca-certificates", "tigervnc-standalone-server", "jwm", "xterm", "tini", "brave-browser",
    "fonts-liberation", "procps", "pcmanfm", "lxterminal", "gpicview",
    "papirus-icon-theme", "fonts-dejavu-core", "tzdata", "xdotool",
})

# Shell-style patterns (fnmatch, case-sensitive) a package may never match: browsers, ways to root, remote shells,
# anonymity and tunnel tools, containers, the screen stack, the system Python, the input tool, and apt itself.
APP_DENIED_PATTERNS: Final = (
    "chromium*", "brave*", "firefox*", "google-chrome*", "epiphany*", "falkon*", "konqueror*", "midori*",
    "qutebrowser*", "luakit*", "netsurf*", "surf", "dillo*", "torbrowser*", "webext-*",
    "sudo*", "doas*", "su-exec", "super", "calife", "policykit*", "polkit*", "pkexec", "pkexec-*",
    "openssh-server*", "dropbear*", "tinysshd", "telnetd*", "*-telnetd",
    "tor", "tor-*", "torsocks", "obfs4proxy", "proxychains*", "redsocks", "sshuttle", "*vpn*", "wireguard*",
    "docker*", "podman*", "containerd*", "runc", "lxc*", "lxd*", "buildah", "crun",
    "xserver*", "*vnc*", "jwm*", "xdotool*", "libxdo*",
    "python3", "python3-minimal", "python3.*", "libpython3*",
    "apt", "apt-*", "dpkg", "dpkg-*", "debian-archive-keyring", "*-archive-keyring",
)

APP_WHY_MAX_CHARS: Final = 300
APP_DESCRIPTION_MAX_CHARS: Final = 200
APPS_PER_BOT_MAX: Final = 40

# roost-apt's own deadlines (it holds the same numbers), and how much longer the keeper waits.
APP_UPDATE_TIMEOUT_S: Final = 120
APP_INSTALL_TIMEOUT_S: Final = 300
APP_KEEPER_GRACE_S: Final = 30
APP_OUTPUT_MAX_BYTES: Final = 4096
APP_REQUEST_GRACE_S: Final = 15          # the gateway's HTTP wait past the keeper's own

APP_VERBS: Final = ("describe", "install", "remove", "ensure")
APP_REFUSAL_WORDS: Final = frozenset({
    "denied", "not_found", "not_debian", "already_installed", "not_installed", "would_remove_others",
})
APT_BIN: Final = "/usr/local/bin/roost-apt"

# What apt needs as root inside the computer, added to the bounding set only (the computer's own uid-10002
# processes run with no-new-privileges and so hold none of them).
COMPUTER_APT_CAPS: Final = ("CHOWN", "DAC_OVERRIDE", "FOWNER")
COMPUTER_TMPFS_VAR_TMP: Final = "/var/tmp:rw,size=64m"


def keeper_timeout_s(verb: str) -> float:
    """How long the keeper waits for one roost-apt call: its own deadline plus the grace."""
    work = 0 if verb == "describe" else APP_INSTALL_TIMEOUT_S
    return float(APP_UPDATE_TIMEOUT_S + work + APP_KEEPER_GRACE_S)
