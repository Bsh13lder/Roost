"""The voice service's launchd agent, ``app.roost.voice``: ``make voice-install`` puts Roost and mlx-audio into
``~/Roost/voice-venv`` and runs ``python -m roost.voice_host.launchd write ~/Library/LaunchAgents/app.roost.voice.plist``.
Same two macOS rules as the keeper's agent (``roost/keeper/launchd.py``): nothing under ``Desktop`` (TCC) and every
path absolute (launchd never expands ``~``). The models live in ``~/Roost/voice-models`` (``HF_HOME``)."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

from roost.keeper.launchd import LAUNCHD_PATH

LAUNCHD_LABEL = "app.roost.voice"
_USAGE = "Usage: python -m roost.voice_host.launchd write <plist-path>"
_TCC_BLOCKED_DIRNAME = "Desktop"
_PLIST_MODE = 0o644


def build_plist(home: Path) -> dict[str, object]:
    if not home.is_absolute():
        raise ValueError(f"home must be an absolute path (got {str(home)!r}) — launchd never expands it.")
    root = home / "Roost"
    paths = {"python": root / "voice-venv" / "bin" / "python", "data": root / "data",
             "models": root / "voice-models", "log": root / "logs" / "voice.log"}
    for path in paths.values():
        if _TCC_BLOCKED_DIRNAME in path.parts:
            raise ValueError(f"{path} is under a {_TCC_BLOCKED_DIRNAME} directory — macOS TCC blocks launchd jobs there.")
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [str(paths["python"]), "-m", "roost.voice_host"],
        "EnvironmentVariables": {"ROOST_DATA_DIR": str(paths["data"]), "HF_HOME": str(paths["models"]),
                                 "HF_HUB_DISABLE_TELEMETRY": "1", "PATH": LAUNCHD_PATH},
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(paths["log"]),
        "StandardErrorPath": str(paths["log"]),
    }


def write_plist(target: Path, home: Path) -> None:
    content = plistlib.dumps(build_plist(home))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    try:
        tmp.write_bytes(content)
        tmp.chmod(_PLIST_MODE)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "write":
        print(_USAGE, file=sys.stderr)
        return 2
    try:
        write_plist(Path(args[1]).expanduser(), Path.home())
    except (ValueError, OSError) as exc:
        print(f"Could not write the voice service's launchd plist: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
