"""The published phone app: ``latest.json`` and the versioned APKs beside it.

``scripts/publish_mobile.sh`` writes both into the mobile dir (``RoostConfig.mobile_dir``). The gateway only reads
them: ``read_latest`` validates the JSON (a bad or missing file reads as "nothing published"), and ``apk_path``
answers only a plain file whose name matches ``MOBILE_APK_NAME_PATTERN`` directly inside that dir."""

from __future__ import annotations

import json
import logging
import re
import stat
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, model_validator

from roost.constants import (
    MOBILE_APK_NAME_PATTERN, MOBILE_LATEST_FILE, MOBILE_LATEST_MAX_BYTES, MOBILE_NOTES_MAX_CHARS,
    MOBILE_VERSION_PATTERN,
)

log = logging.getLogger(__name__)

_APK_NAME = re.compile(MOBILE_APK_NAME_PATTERN)
_SHA256_HEX = r"[0-9a-f]{64}"


class LatestRelease(BaseModel):
    """One published build, exactly as ``latest.json`` holds it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: StrictStr = Field(pattern=f"^{MOBILE_VERSION_PATTERN}$")
    build: StrictInt = Field(ge=1)
    file: StrictStr = Field(pattern=f"^{MOBILE_APK_NAME_PATTERN}$")
    sha256: StrictStr = Field(pattern=f"^{_SHA256_HEX}$")
    notes: StrictStr = Field(default="", max_length=MOBILE_NOTES_MAX_CHARS)

    @model_validator(mode="after")
    def _file_names_this_build(self) -> "LatestRelease":
        if self.file != f"roost-{self.version}+{self.build}.apk":
            raise ValueError("file must be roost-<version>+<build>.apk")
        return self


def _read_text(path: Path) -> str | None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MOBILE_LATEST_MAX_BYTES:
            log.warning("mobile update: %s is not a small plain file", path)
            return None
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("mobile update: could not read %s: %s", path, exc)
        return None


def read_latest(folder: Path) -> LatestRelease | None:
    """The published release, or None when nothing (valid) is published."""
    text = _read_text(folder / MOBILE_LATEST_FILE)
    if text is None:
        return None
    try:
        return LatestRelease.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        log.warning("mobile update: %s is not a valid release file: %s", MOBILE_LATEST_FILE, exc)
        return None


def apk_path(folder: Path, name: str) -> Path | None:
    """The APK called ``name`` directly in ``folder``, or None (bad name, missing, a symlink or not a file)."""
    if not _APK_NAME.fullmatch(name):
        return None
    path = folder / name
    try:
        info = path.lstat()
    except OSError:
        return None
    return path if stat.S_ISREG(info.st_mode) else None
