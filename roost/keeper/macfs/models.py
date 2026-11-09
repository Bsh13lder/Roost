"""Bodies of the keeper's Mac routes. Every model forbids unknown fields (422), takes ids as UUID4
and caps every string, so nothing but these fields can ever reach an operation."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from roost.constants import MAC_FIND_QUERY_MAX_CHARS, MAC_READ_MAX_BYTES, MAC_STAT_MAX_PATHS
from roost.keeper.macfs.backups import BACKUP_ID_PATTERN

UUID4 = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
SHA256 = r"^[0-9a-f]{64}$"
PATH_MAX = 4096
GRANTS_MAX = 1000
NAME_MAX = 255


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GrantIn(Strict):
    grant_id: str = Field(pattern=UUID4)
    root: str = Field(min_length=1, max_length=PATH_MAX)
    access: Literal["read", "read_write"]
    bot_id: str | None = Field(default=None, pattern=UUID4)


class PutGrantsIn(Strict):
    grants: list[GrantIn] = Field(max_length=GRANTS_MAX)


class CheckFolderIn(Strict):
    path: str = Field(max_length=PATH_MAX)


class EmptyIn(Strict):
    pass


class FsIn(Strict):
    grant_id: str = Field(pattern=UUID4)
    bot_id: str = Field(pattern=UUID4)


class ListIn(FsIn):
    path: str = Field(default="", max_length=PATH_MAX)


class FindIn(FsIn):
    name: str | None = Field(default=None, min_length=1, max_length=MAC_FIND_QUERY_MAX_CHARS)
    text: str | None = Field(default=None, min_length=1, max_length=MAC_FIND_QUERY_MAX_CHARS)
    path: str = Field(default="", max_length=PATH_MAX)

    @model_validator(mode="after")
    def _one_of_name_or_text(self) -> "FindIn":
        if self.name is None and self.text is None:
            raise ValueError("name or text")
        return self


class ReadIn(FsIn):
    path: str = Field(max_length=PATH_MAX)


class StatIn(FsIn):
    paths: list[str] = Field(max_length=MAC_STAT_MAX_PATHS)


class TextBody(ReadIn):
    text: str = Field(max_length=MAC_READ_MAX_BYTES)


class CreateIn(TextBody):
    parents: bool = False   # make missing folders inside the grant (the vault export)


class WriteIn(TextBody):
    expected_sha256: str = Field(pattern=SHA256)


class RenameIn(ReadIn):
    new_path: str = Field(max_length=PATH_MAX)
    expected_sha256: str = Field(pattern=SHA256)


class TrashIn(ReadIn):
    expected_sha256: str = Field(pattern=SHA256)


class UndoContentIn(FsIn):
    kind: Literal["content"]
    path: str = Field(max_length=PATH_MAX)
    backup_id: str = Field(pattern=BACKUP_ID_PATTERN)
    expected_sha256: str = Field(pattern=SHA256)


class UndoCreateIn(FsIn):
    kind: Literal["create"]
    path: str = Field(max_length=PATH_MAX)
    expected_sha256: str = Field(pattern=SHA256)


class UndoRenameIn(FsIn):
    kind: Literal["rename"]
    path: str = Field(max_length=PATH_MAX)
    back_to: str = Field(max_length=PATH_MAX)
    expected_sha256: str = Field(pattern=SHA256)


class UndoTrashIn(FsIn):
    kind: Literal["trash"]
    trash_name: str = Field(max_length=NAME_MAX)
    back_to: str = Field(max_length=PATH_MAX)


class UndoIn(RootModel[Annotated[
    Union[UndoContentIn, UndoCreateIn, UndoRenameIn, UndoTrashIn], Field(discriminator="kind")
]]):
    """``POST /mac/fs/undo``: one of four kinds, told apart by ``kind``."""
