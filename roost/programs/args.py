"""The program tools' arguments, checked at the boundary (pydantic) before anything reaches the workspace.

A path is relative to ``/workspace``: a leading ``/workspace/`` is dropped, and an absolute path elsewhere,
``..``, ``.``, an empty part, a control character or a backslash is refused. The container's own file script
walks it again with ``O_NOFOLLOW`` (``roost/programs/file_ops.py``)."""

from __future__ import annotations

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator

from roost.constants import (
    PROGRAM_COMMAND_MAX_CHARS, PROGRAM_FILE_MAX_CHARS, PROGRAM_PATH_MAX_CHARS, PROGRAM_TIMEOUT_DEFAULT_S,
    PROGRAM_TIMEOUT_MAX_S, WORKSPACE_DIR,
)

BAD_PATH_TEXT = (
    "a path inside your workspace, such as src/main.py: no absolute paths outside /workspace, no '..', "
    "no empty parts"
)
_PREFIX = WORKSPACE_DIR + "/"


def _plain(text: str) -> bool:
    return "\\" not in text and all(unicodedata.category(ch)[0] != "C" for ch in text)


def _relative(raw: str) -> str:
    """``raw`` without a leading ``/workspace/`` and trailing slashes; still absolute when it pointed elsewhere."""
    text = raw[len(_PREFIX):] if raw.startswith(_PREFIX) else raw
    return text.rstrip("/") if text != "/" else text


def workspace_path(raw: str, *, allow_root: bool = False) -> str:
    """The checked relative path, or ``ValueError``. ``allow_root``: ``""``, ``.`` and ``/workspace`` mean the
    workspace itself (``""``), for a folder to list."""
    if len(raw) > PROGRAM_PATH_MAX_CHARS or not _plain(raw):
        raise ValueError(BAD_PATH_TEXT)
    if allow_root and raw in ("", ".", WORKSPACE_DIR, _PREFIX):
        return ""
    text = _relative(raw)
    parts = text.split("/")
    if not text or text.startswith(("/", "~")) or any(part in ("", ".", "..") for part in parts):
        raise ValueError(BAD_PATH_TEXT)
    return text


class RunArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    command: str = Field(min_length=1, max_length=PROGRAM_COMMAND_MAX_CHARS)
    timeout_s: int = Field(default=PROGRAM_TIMEOUT_DEFAULT_S, ge=1, le=PROGRAM_TIMEOUT_MAX_S)

    @field_validator("command")
    @classmethod
    def _command(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("a command to run")
        return value


class _PathArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return workspace_path(value)


class WriteArgs(_PathArgs):
    text: str = Field(max_length=PROGRAM_FILE_MAX_CHARS)


class ReadArgs(_PathArgs):
    pass


class ListArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str = ""

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return workspace_path(value, allow_root=True)
