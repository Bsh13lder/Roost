#!/usr/bin/python3
"""roost-apt <verb> <package>...: install or remove a Debian package on a bot's computer, after the owner's Yes.

The keeper runs this as root with `docker exec --user 0:0 roost-computer-<id> /usr/local/bin/roost-apt`, only from
its signed route (docs/plans/2026-10-22-roost-install-app.md). It is the last check on that path: it parses the
argv again, checks each name against Debian's rule and the deny list (its own copy of roost/apps/constants.py; a
test keeps them equal), and runs apt with its own configuration on every call: a sources file with Debian
bookworm, bookworm-updates and bookworm-security `main` only, an empty sources folder and its own lists folder,
so the Brave repository is never visible to it. Before an install it reads `apt-cache policy` and refuses unless
the candidate comes from Debian main. apt runs from argv lists with no shell; there is no way to name a file or a
URL. apt's own output is never passed on: a refusal or a failure is one fixed word on stderr.

    describe PACKAGE    print {"package", "version", "description"} as JSON
    install PACKAGE     install one package that is not on the computer yet
    remove PACKAGE      remove one package, only when nothing else would go with it
    ensure PACKAGE...   install those of the packages that are missing, in one apt call

Exit codes: 0 done, 2 bad arguments, 3 refused (denied / not_found / not_debian / already_installed /
not_installed / would_remove_others), 4 failed. Standard library only (Debian's python3).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from typing import Callable, Sequence, TextIO

# The same rule and lists as roost/apps/constants.py (tests/test_apps_names.py keeps them equal).
NAME_PATTERN = r"^[a-z0-9][a-z0-9+.-]{1,62}$"
IMAGE_PACKAGES = frozenset({
    "python3", "ca-certificates", "tigervnc-standalone-server", "jwm", "xterm", "tini", "brave-browser",
    "fonts-liberation", "procps", "pcmanfm", "lxterminal", "gpicview",
    "papirus-icon-theme", "fonts-dejavu-core", "tzdata", "xdotool",
})
DENIED_PATTERNS = (
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
ENSURE_MAX = 40                         # APPS_PER_BOT_MAX
UPDATE_TIMEOUT_S = 120                  # APP_UPDATE_TIMEOUT_S
INSTALL_TIMEOUT_S = 300                 # APP_INSTALL_TIMEOUT_S
QUERY_TIMEOUT_S = 30
LISTS_MAX_AGE_S = 3600                  # the package lists are read again when older than this
DESCRIPTION_MAX_CHARS = 200             # APP_DESCRIPTION_MAX_CHARS

APT_GET, APT_CACHE, DPKG_QUERY = "/usr/bin/apt-get", "/usr/bin/apt-cache", "/usr/bin/dpkg-query"
CONF_DIR = "/etc/roost-apt"
SOURCE_LIST = f"{CONF_DIR}/debian.list"
SOURCE_PARTS = f"{CONF_DIR}/sources.list.d"          # empty: no other repository is ever read
STATE_DIR = "/var/lib/roost-apt"
LISTS_DIR = f"{STATE_DIR}/lists"
UPDATED_STAMP = f"{STATE_DIR}/updated"
PROXY = "http://roost-egress:3128"
KEYRING = "/usr/share/keyrings/debian-archive-keyring.gpg"
DEBIAN_SOURCES = (
    f"deb [signed-by={KEYRING}] https://deb.debian.org/debian bookworm main\n"
    f"deb [signed-by={KEYRING}] https://deb.debian.org/debian bookworm-updates main\n"
    f"deb [signed-by={KEYRING}] https://deb.debian.org/debian-security bookworm-security main\n"
)
# (address, suite/component) pairs a candidate may come from.
DEBIAN_ORIGINS = frozenset({
    ("https://deb.debian.org/debian", "bookworm/main"),
    ("https://deb.debian.org/debian", "bookworm-updates/main"),
    ("https://deb.debian.org/debian-security", "bookworm-security/main"),
})
STATUS_FILE = "/var/lib/dpkg/status"
APT_OPTIONS = (
    "-o", f"Dir::Etc::SourceList={SOURCE_LIST}",
    "-o", f"Dir::Etc::SourceParts={SOURCE_PARTS}",
    "-o", f"Dir::State::Lists={LISTS_DIR}",
    "-o", f"Acquire::http::Proxy={PROXY}",
    "-o", f"Acquire::https::Proxy={PROXY}",
    "-o", "Acquire::Languages=none",
    "-o", "APT::Sandbox::User=root",
    "-o", "APT::Install-Recommends=false",
    "-o", "APT::Keep-Downloaded-Packages=false",
    "-o", "Dpkg::Options::=--force-confdef",
    "-o", "Dpkg::Options::=--force-confold",
)
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "DEBIAN_FRONTEND": "noninteractive", "LANG": "C.UTF-8",
       "HOME": "/root"}

EXIT_OK, EXIT_BAD, EXIT_REFUSED, EXIT_FAILED = 0, 2, 3, 4
BAD_ARGUMENTS, FAILED = "bad arguments", "failed"
VERBS = ("describe", "install", "remove", "ensure")

Run = Callable[[Sequence[str], float], "tuple[int, str]"]


class Refused(Exception):
    def __init__(self, word: str, code: int = EXIT_REFUSED) -> None:
        super().__init__(word)
        self.word, self.code = word, code


def valid_name(name: str) -> bool:
    return re.fullmatch(NAME_PATTERN, name) is not None


def denied(name: str) -> bool:
    return name in IMAGE_PACKAGES or any(fnmatch.fnmatchcase(name, p) for p in DENIED_PATTERNS)


def update_argv() -> list[str]:
    return [APT_GET, *APT_OPTIONS, "update", "-q"]


def policy_argv(name: str) -> list[str]:
    return [APT_CACHE, *APT_OPTIONS, "policy", "--", name]


def show_argv(name: str) -> list[str]:
    return [APT_CACHE, *APT_OPTIONS, "show", "--no-all-versions", "--", name]


def install_argv(names: Sequence[str]) -> list[str]:
    return [APT_GET, *APT_OPTIONS, "install", "-y", "--no-install-recommends", "-q", "--", *names]


def remove_sim_argv(name: str) -> list[str]:
    return [APT_GET, *APT_OPTIONS, "remove", "-s", "--no-auto-remove", "-q", "--", name]


def remove_argv(name: str) -> list[str]:
    return [APT_GET, *APT_OPTIONS, "remove", "-y", "--no-auto-remove", "-q", "--", name]


def status_argv(name: str) -> list[str]:
    return [DPKG_QUERY, "-W", "-f=${Status}", "--", name]


def _candidate(policy_text: str) -> str | None:
    match = re.search(r"^\s*Candidate:\s*(\S+)\s*$", policy_text, re.MULTILINE)
    return None if match is None or match.group(1) == "(none)" else match.group(1)


def _candidate_origins(policy_text: str, candidate: str) -> list[str]:
    """The origin lines under the candidate's own entry in the version table."""
    lines = policy_text.splitlines()
    try:
        start = lines.index("  Version table:") + 1
    except ValueError:
        return []
    origins: list[str] = []
    inside = False
    for line in lines[start:]:
        words = line.replace("***", " ").split()
        if len(line) - len(line.lstrip()) <= 5 and words:     # a version line ("     1.6-2.1 500")
            inside = words[0] == candidate
            continue
        if inside and words:
            origins.append(line.strip())
    return origins


def _is_debian_origin(line: str) -> bool:
    words = line.split()                 # "500 https://deb.debian.org/debian bookworm/main arm64 Packages"
    return len(words) >= 3 and (words[1], words[2]) in DEBIAN_ORIGINS


def candidate_is_debian(policy_text: str) -> bool:
    """True when the candidate version exists and every place it comes from is Debian main (or the installed copy)."""
    candidate = _candidate(policy_text)
    if candidate is None:
        return False
    origins = [line for line in _candidate_origins(policy_text, candidate) if not line.endswith(STATUS_FILE)]
    return bool(origins) and all(_is_debian_origin(line) for line in origins)


def description_of(show_text: str) -> tuple[str, str]:
    """(version, Debian's one-line description), each cut short."""
    fields = dict(re.findall(r"^(Version|Description(?:-en)?):\s*(.*)$", show_text, re.MULTILINE))
    text = fields.get("Description") or fields.get("Description-en") or ""
    return fields.get("Version", "")[:60], text.strip()[:DESCRIPTION_MAX_CHARS]


def removes_only(sim_text: str, name: str) -> bool:
    """True when the simulated removal takes exactly the one package."""
    removed = {line.split()[1].split(":")[0] for line in sim_text.splitlines() if line.startswith("Remv ")}
    return removed == {name}


def _run(argv: Sequence[str], timeout_s: float) -> tuple[int, str]:
    try:
        done = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout_s, env=ENV, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return (-1, "")
    return (done.returncode, done.stdout)


def _lists_stale() -> bool:
    try:
        return time.time() - os.stat(UPDATED_STAMP).st_mtime > LISTS_MAX_AGE_S
    except OSError:
        return True


def _mark_updated() -> None:
    with open(UPDATED_STAMP, "w", encoding="utf-8") as stamp:
        stamp.write(str(int(time.time())))


class Apt:
    """One roost-apt call's apt steps, through an injectable ``run``."""

    def __init__(self, run: Run, lists_stale: Callable[[], bool], mark_updated: Callable[[], None]) -> None:
        self._run, self._stale, self._mark = run, lists_stale, mark_updated

    def installed(self, name: str) -> bool:
        code, out = self._run(status_argv(name), QUERY_TIMEOUT_S)
        return code == 0 and "install ok installed" in out

    def refresh(self) -> None:
        if not self._stale():
            return
        if self._run(update_argv(), UPDATE_TIMEOUT_S)[0] != 0:
            raise Refused(FAILED, EXIT_FAILED)
        self._mark()

    def check_debian(self, name: str) -> None:
        code, out = self._run(policy_argv(name), QUERY_TIMEOUT_S)
        if code != 0:
            raise Refused(FAILED, EXIT_FAILED)
        if _candidate(out) is None:
            raise Refused("not_found")
        if not candidate_is_debian(out):
            raise Refused("not_debian")

    def must(self, argv: Sequence[str], timeout_s: float) -> str:
        code, out = self._run(argv, timeout_s)
        if code != 0:
            raise Refused(FAILED, EXIT_FAILED)
        return out


def _describe(apt: Apt, name: str, out: TextIO) -> None:
    if apt.installed(name):
        raise Refused("already_installed")
    apt.refresh()
    apt.check_debian(name)
    version, text = description_of(apt.must(show_argv(name), QUERY_TIMEOUT_S))
    out.write(json.dumps({"package": name, "version": version, "description": text}))


def _install(apt: Apt, names: Sequence[str], *, skip_installed: bool) -> None:
    missing = [n for n in names if not apt.installed(n)]
    if not skip_installed and len(missing) != len(names):
        raise Refused("already_installed")
    if not missing:
        return
    apt.refresh()
    for name in missing:
        apt.check_debian(name)
    apt.must(install_argv(missing), INSTALL_TIMEOUT_S)


def _remove(apt: Apt, name: str) -> None:
    if not apt.installed(name):
        raise Refused("not_installed")
    if not removes_only(apt.must(remove_sim_argv(name), QUERY_TIMEOUT_S), name):
        raise Refused("would_remove_others")
    apt.must(remove_argv(name), INSTALL_TIMEOUT_S)


def _parse(argv: Sequence[str]) -> tuple[str, list[str]]:
    if len(argv) < 2 or argv[0] not in VERBS:
        raise Refused(BAD_ARGUMENTS, EXIT_BAD)
    verb, names = argv[0], list(argv[1:])
    if (verb != "ensure" and len(names) != 1) or len(names) > ENSURE_MAX or len(set(names)) != len(names):
        raise Refused(BAD_ARGUMENTS, EXIT_BAD)
    if not all(valid_name(n) for n in names):
        raise Refused(BAD_ARGUMENTS, EXIT_BAD)
    if any(denied(n) for n in names):
        raise Refused("denied")
    return verb, names


def main(argv: Sequence[str], *, run: Run = _run, out: TextIO = sys.stdout, err: TextIO = sys.stderr,
         lists_stale: Callable[[], bool] = _lists_stale, mark_updated: Callable[[], None] = _mark_updated) -> int:
    apt = Apt(run, lists_stale, mark_updated)
    try:
        verb, names = _parse(argv)
        if verb == "describe":
            _describe(apt, names[0], out)
        elif verb == "remove":
            _remove(apt, names[0])
        else:
            _install(apt, names, skip_installed=verb == "ensure")
    except Refused as refused:
        err.write(refused.word + "\n")
        return refused.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
