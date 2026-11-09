"""Roost runtime configuration.

Carried from LazyClaw's ``lazyclaw/config.py`` (git history preserved via
git-filter-repo) and trimmed to the Night-1 contract: one dataclass
(``RoostConfig``), one loader (``load_config``), loopback-only, no
OpenAI/MiniMax/Telegram fields — those belonged to the old multi-channel
app and have no place here.

Two secrets are written to disk on first run, 0600, and read back on every
later call so they stay stable across restarts:
  - ``server_secret``  (env ``ROOST_SERVER_SECRET``, else
    ``<database_dir>/server.secret``)
  - ``keeper_secret``  (always ``<database_dir>/keeper.secret`` — the shared
    HMAC secret between the gateway and the keeper process, see
    ``roost/desk/signing.py`` in a later task)
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from roost.constants import (
    CONTAINER_MOBILE_DIR, DEFAULT_DATA_DIR, DEFAULT_DESKS_DIR, DEFAULT_MOBILE_DIR, MODEL_CHECK_MODES, SCHEDULER_TICK_OVERRIDE_MAX_SECONDS,
    STEER_DEBOUNCE_OVERRIDE_MAX_SECONDS, VOICE_PORT,
)
from roost.voice.constants import VOICE_MODES, VOICE_SECRET_FILE

DEFAULT_MAC_BACKUPS_DIR = Path("~/Roost/mac-backups").expanduser()

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost")

# Inside the gateway container (docker/gateway/Dockerfile) the server must
# bind every interface, or Docker's port publishing can't reach it at all.
# That's only safe because docker-compose.yml publishes the port on the
# HOST's 127.0.0.1 alone (pinned by tests/test_compose.py) -- so this one
# extra host is allowed only with the exact container flag below, never
# on a bare host run.
_CONTAINER_ALL_INTERFACES_HOST = "0.0.0.0"
_IN_CONTAINER_ENV = "ROOST_IN_CONTAINER"
_IN_CONTAINER_FLAG = "1"

_DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:18800",
    "http://localhost:18800",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)

# ROOST_EXTRA_ORIGINS: comma-separated https origins added to the allowlist (e.g. the Mac's Tailscale address, which
# `tailscale serve` forwards to 127.0.0.1:18800). Never http, never a path or a wildcard.
_EXTRA_ORIGINS_ENV = "ROOST_EXTRA_ORIGINS"
_HTTPS_ORIGIN = re.compile(r"https://[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:[0-9]{1,5})?")


def _extra_origins(source: Mapping[str, str]) -> tuple[str, ...]:
    """The https origins ROOST_EXTRA_ORIGINS adds, lowercased; ValueError on anything else."""
    raw = source.get(_EXTRA_ORIGINS_ENV, "")
    origins = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    bad = [origin for origin in origins if not _HTTPS_ORIGIN.fullmatch(origin)]
    if bad or (raw.strip() and not origins):
        raise ValueError(f"{_EXTRA_ORIGINS_ENV} takes plain https origins only, like https://mac.example.ts.net.")
    return origins


_DEFAULT_BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"


@dataclass(frozen=True)
class RoostConfig:
    server_secret: str
    database_dir: Path                 # env ROOST_DATA_DIR, default ~/Roost/data
    desks_dir: Path                    # env ROOST_DESKS_DIR, default ~/Roost/desks
    keeper_secret: str                 # file <database_dir>/keeper.secret (0600), created on first load
    host: str = "127.0.0.1"
    port: int = 18800
    keeper_url: str = "http://127.0.0.1:18801"
    proxy_port: int = 18803
    model_mode: str = "claude"         # env ROOST_MODEL: "claude" | "scripted"
    model_script: Path | None = None   # env ROOST_MODEL_SCRIPT: per-bot script for ROOST_MODEL=scripted (E2E only)
    desk_mode: str = "keeper"          # env ROOST_DESK: "keeper" | "fake"
    brave_path: str = _DEFAULT_BRAVE_PATH
    allowed_origins: tuple[str, ...] = _DEFAULT_ALLOWED_ORIGINS
    tailnet_origins: tuple[str, ...] = ()   # the ROOST_EXTRA_ORIGINS part: the phone through `tailscale serve`
    log_level: str = "WARNING"
    in_container: bool = False         # env ROOST_IN_CONTAINER == "1" (set only by the gateway image)
    model_check: str = "on"            # env ROOST_MODEL_CHECK: "on" | "off" (the daily new-model check)
    model_check_file: Path | None = None   # env ROOST_MODEL_CHECK_FILE: a page file for the E2E (scripted mode only)
    mac_home: Path = field(default_factory=Path.home)   # env ROOST_MAC_HOME: the keeper's home for Mac folder grants
    mac_backups_dir: Path = field(default_factory=lambda: DEFAULT_MAC_BACKUPS_DIR)   # env ROOST_MAC_BACKUPS_DIR
    fake_mac_tree: Path | None = None  # env ROOST_FAKE_MAC_TREE: a JSON tree for FakeMacFiles (fake desk only)
    scheduler_tick_seconds: float | None = None   # env ROOST_SCHEDULER_TICK_SECONDS: a faster routine tick (scripted E2E only)
    steer_debounce_seconds: float | None = None   # env ROOST_STEER_DEBOUNCE_SECONDS: the burst debounce (scripted only)
    mobile_dir: Path = DEFAULT_MOBILE_DIR   # env ROOST_MOBILE_DIR; /mobile in the container: the published phone app
    voice_url: str = "http://127.0.0.1:18804"   # env ROOST_VOICE_URL: the voice service on the Mac (roost/voice_host/)
    voice_secret: str = ""             # file <database_dir>/voice.secret (0600): signs requests to the voice service
    voice_mode: str = "service"        # env ROOST_VOICE: "service" | "fake" (tests and the scripted E2E)


# Alias so carried modules (key_manager.py, auth.py, db/connection.py, ...)
# can keep referring to `Config` without caring that it's really RoostConfig.
Config = RoostConfig


_MIN_SECRET_LENGTH = 32


def _validate_secret_value(value: str, source: str) -> str:
    """Refuse an empty, whitespace-only, or too-short secret value.

    A short-circuited secret (empty file, truncated write, a typo'd env
    var) derives DEKs from near-nothing — encryption becomes void, or
    DEKs wrapped under today's accidental value can't be unwrapped after
    the next restart (data loss either way). Fail loudly instead.
    """
    stripped = value.strip()
    if len(stripped) < _MIN_SECRET_LENGTH:
        raise ValueError(
            f"Secret from {source} is empty or too short "
            f"({len(stripped)} chars; need at least {_MIN_SECRET_LENGTH}). "
            "Refusing to start with a weak or corrupt secret."
        )
    return stripped


def _check_secret_file_permissions(path: Path) -> None:
    """Refuse a secret file that's readable or writable by group/other."""
    mode = path.stat().st_mode
    if mode & 0o077 != 0:
        raise ValueError(
            f"Secret file {path} has loose permissions "
            f"({oct(mode & 0o777)}, expected 0600). Refusing to use it — "
            f"run `chmod 600 {path}` and restart."
        )


def _create_secret_file(path: Path, value: str) -> None:
    """Atomically create ``path`` (mode 0600) holding ``value``.

    Writes ``value`` to a temp file in the same directory, then links
    that temp file to ``path`` with ``os.link``. A hardlink can only ever
    point at a file whose content is already complete, so ``path`` is
    never observably empty or partially written to a concurrent reader —
    unlike the previous O_EXCL-then-write approach, where a second
    process could open and read the file in the window between its
    creation and its write (the realistic case: two processes, e.g.
    gateway and keeper, both starting for the first time at once under
    ``make dev``).

    Raises ``FileExistsError`` if another process already won the race —
    the caller should read ``path`` back in that case, not retry.
    """
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(value)
        os.link(tmp_path, path)
    except FileExistsError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to write secret file at {path}") from exc
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _read_or_create_secret(path: Path) -> str:
    """Read a 0600 secret file, creating it atomically on first run.

    Every value returned — freshly created, read from a pre-existing
    file, or read after losing the creation race (see
    ``_create_secret_file``) — is validated for length, and the file's
    permissions are checked.
    """
    try:
        existing = path.read_text()
    except FileNotFoundError:
        pass
    else:
        _check_secret_file_permissions(path)
        return _validate_secret_value(existing, str(path))

    value = secrets.token_urlsafe(48)
    try:
        _create_secret_file(path, value)
    except FileExistsError:
        # Another process won the race; its file is already complete.
        existing = path.read_text()
        _check_secret_file_permissions(path)
        return _validate_secret_value(existing, str(path))

    _check_secret_file_permissions(path)
    return _validate_secret_value(value, str(path))


def _resolve_host(source: Mapping[str, str], in_container: bool) -> str:
    """``ROOST_HOST``, validated: loopback always; ``0.0.0.0`` only in the
    gateway container (see ``_CONTAINER_ALL_INTERFACES_HOST``); anything
    else is refused with a ``ValueError``."""
    host = source.get("ROOST_HOST", "127.0.0.1").strip()
    if host in _LOOPBACK_HOSTS:
        return host
    if in_container and host == _CONTAINER_ALL_INTERFACES_HOST:
        return host
    raise ValueError(
        f"ROOST_HOST must be one of {_LOOPBACK_HOSTS} (got {host!r}) — "
        "Roost never binds beyond loopback (0.0.0.0 is allowed only inside "
        f"the gateway container, {_IN_CONTAINER_ENV}={_IN_CONTAINER_FLAG})."
    )


def _scripted_tick_seconds(source: Mapping[str, str], model_mode: str) -> float | None:
    """The E2E's faster scheduler tick. Read only in scripted mode, so a real install can never speed it up."""
    raw = source.get("ROOST_SCHEDULER_TICK_SECONDS")
    if not raw or model_mode != "scripted":
        return None
    try:
        seconds = float(raw)
    except ValueError:
        seconds = 0.0
    if not 0 < seconds <= SCHEDULER_TICK_OVERRIDE_MAX_SECONDS:
        raise ValueError(f"ROOST_SCHEDULER_TICK_SECONDS must be a number above 0 and up to "
                         f"{SCHEDULER_TICK_OVERRIDE_MAX_SECONDS:g} (got {raw!r}).")
    return seconds


def _scripted_debounce_seconds(source: Mapping[str, str], model_mode: str) -> float | None:
    """The steer burst debounce for tests and the E2E (0 turns it off). Read only in scripted mode."""
    raw = source.get("ROOST_STEER_DEBOUNCE_SECONDS")
    if not raw or model_mode != "scripted":
        return None
    try:
        seconds = float(raw)
    except ValueError:
        seconds = -1.0
    if not 0 <= seconds <= STEER_DEBOUNCE_OVERRIDE_MAX_SECONDS:
        raise ValueError(f"ROOST_STEER_DEBOUNCE_SECONDS must be a number from 0 to "
                         f"{STEER_DEBOUNCE_OVERRIDE_MAX_SECONDS:g} (got {raw!r}).")
    return seconds


def _mobile_dir(source: Mapping[str, str], in_container: bool) -> Path:
    """Where the published phone app lives (read only, never created here)."""
    raw = source.get("ROOST_MOBILE_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return CONTAINER_MOBILE_DIR if in_container else DEFAULT_MOBILE_DIR


def load_config(env: Mapping[str, str] | None = None) -> RoostConfig:
    """Build a ``RoostConfig`` from the given mapping (default: ``os.environ``).

    Raises ``ValueError`` if ``ROOST_HOST`` is set to anything other than a
    loopback address — Roost never binds beyond 127.0.0.1/localhost, except
    ``0.0.0.0`` inside the gateway container (``ROOST_IN_CONTAINER=1``),
    whose port compose publishes on the host's 127.0.0.1 only.
    """
    source: Mapping[str, str] = env if env is not None else os.environ

    database_dir = Path(source.get("ROOST_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()
    desks_dir = Path(source.get("ROOST_DESKS_DIR", str(DEFAULT_DESKS_DIR))).expanduser()
    database_dir.mkdir(parents=True, exist_ok=True)

    in_container = source.get(_IN_CONTAINER_ENV, "") == _IN_CONTAINER_FLAG
    host = _resolve_host(source, in_container)

    env_secret = source.get("ROOST_SERVER_SECRET")
    if env_secret:
        server_secret = _validate_secret_value(env_secret, "ROOST_SERVER_SECRET")
    else:
        server_secret = _read_or_create_secret(database_dir / "server.secret")
    keeper_secret = _read_or_create_secret(database_dir / "keeper.secret")
    voice_secret = _read_or_create_secret(database_dir / VOICE_SECRET_FILE)
    voice_mode = source.get("ROOST_VOICE", "service").strip().lower()
    if voice_mode not in VOICE_MODES:
        raise ValueError(f"ROOST_VOICE must be one of {VOICE_MODES} (got {voice_mode!r}).")

    model_check = source.get("ROOST_MODEL_CHECK", "on").strip().lower()
    if model_check not in MODEL_CHECK_MODES:
        raise ValueError(f"ROOST_MODEL_CHECK must be one of {MODEL_CHECK_MODES} (got {model_check!r}).")
    model_mode = source.get("ROOST_MODEL", "claude")
    desk_mode = source.get("ROOST_DESK", "keeper")
    fake_tree = source.get("ROOST_FAKE_MAC_TREE")
    if fake_tree and desk_mode != "fake":
        raise ValueError("ROOST_FAKE_MAC_TREE is only for the fake desk (ROOST_DESK=fake); the keeper reads the real Mac.")
    check_file = source.get("ROOST_MODEL_CHECK_FILE")

    return RoostConfig(
        scheduler_tick_seconds=_scripted_tick_seconds(source, model_mode),
        steer_debounce_seconds=_scripted_debounce_seconds(source, model_mode),
        server_secret=server_secret,
        database_dir=database_dir,
        desks_dir=desks_dir,
        keeper_secret=keeper_secret,
        host=host,
        port=int(source.get("ROOST_PORT", 18800)),
        keeper_url=source.get("ROOST_KEEPER_URL", "http://127.0.0.1:18801"),
        proxy_port=int(source.get("ROOST_PROXY_PORT", 18803)),
        model_mode=model_mode,
        model_script=Path(source["ROOST_MODEL_SCRIPT"]).expanduser() if source.get("ROOST_MODEL_SCRIPT") else None,
        desk_mode=desk_mode,
        brave_path=source.get("ROOST_BRAVE_PATH", _DEFAULT_BRAVE_PATH),
        log_level=source.get("ROOST_LOG_LEVEL", "WARNING"),
        in_container=in_container,
        model_check=model_check,
        model_check_file=Path(check_file).expanduser() if check_file and model_mode == "scripted" else None,
        mac_home=Path(source.get("ROOST_MAC_HOME") or Path.home()).expanduser(),
        mac_backups_dir=Path(source.get("ROOST_MAC_BACKUPS_DIR") or DEFAULT_MAC_BACKUPS_DIR).expanduser(),
        fake_mac_tree=Path(fake_tree).expanduser() if fake_tree else None,
        allowed_origins=_DEFAULT_ALLOWED_ORIGINS + _extra_origins(source),
        tailnet_origins=_extra_origins(source),
        mobile_dir=_mobile_dir(source, in_container),
        voice_url=source.get("ROOST_VOICE_URL", f"http://127.0.0.1:{VOICE_PORT}"),
        voice_secret=voice_secret,
        voice_mode=voice_mode,
    )
