"""``python -m roost.llm.claude_status`` — is the bundled ``claude`` CLI
logged in? Run by ``make claude-status`` inside the gateway container.

The gateway image sets ``CLAUDE_CONFIG_DIR=/home/roost/.claude`` (the
``roost_claude`` named volume), where ``make claude-login`` leaves the
CLI's OAuth credentials as ``.credentials.json``. This prints exactly one
line — ``logged in until <date>``, ``expired`` or ``not logged in`` — and
never any part of a token. It checks the token's EXPIRY, not just that
the file exists: a stale file is how a "logged in" container ends up
failing every real turn with a 401.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

NOT_LOGGED_IN = "not logged in"
EXPIRED = "expired"

_CREDENTIALS_FILENAME = ".credentials.json"
_OAUTH_KEY = "claudeAiOauth"
_MS_PER_S = 1000
_DATE_FORMAT = "%Y-%m-%d %H:%M UTC"


def credentials_path(env: Mapping[str, str] | None = None) -> Path:
    """``$CLAUDE_CONFIG_DIR/.credentials.json``, else ``~/.claude/...``."""
    source = env if env is not None else os.environ
    config_dir = source.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / _CREDENTIALS_FILENAME
    return Path(source.get("HOME", str(Path.home()))) / ".claude" / _CREDENTIALS_FILENAME


def _read_oauth(path: Path) -> dict | None:
    """The ``claudeAiOauth`` block, or ``None`` if there isn't a usable one.

    A file that exists but can't be read or parsed is reported on stderr
    (never silently) and treated as not logged in.
    """
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        print(f"claude_status: could not read {path}: {exc.__class__.__name__}", file=sys.stderr)
        return None
    oauth = payload.get(_OAUTH_KEY) if isinstance(payload, dict) else None
    if not isinstance(oauth, dict) or not oauth.get("accessToken"):
        return None
    return oauth


def describe_login(path: Path, now_ms: int) -> str:
    """One status line for the credentials at ``path`` as of ``now_ms``."""
    oauth = _read_oauth(path)
    if oauth is None:
        return NOT_LOGGED_IN
    expires_at = oauth.get("expiresAt")
    # bool is an int subclass; a True/False "expiry" is malformed, not epoch 1.
    if not isinstance(expires_at, int) or isinstance(expires_at, bool) or expires_at <= now_ms:
        return EXPIRED
    when = datetime.fromtimestamp(expires_at / _MS_PER_S, tz=timezone.utc)
    return f"logged in until {when.strftime(_DATE_FORMAT)}"


def main() -> int:
    print(describe_login(credentials_path(), int(time.time() * _MS_PER_S)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
