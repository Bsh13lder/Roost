"""Types shared by the schema migrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


class MigrationError(RuntimeError):
    """A migration failed and was rolled back; the schema version is unchanged."""


@dataclass(frozen=True)
class AddColumn:
    table: str
    column: str
    definition: str


Step = Union[str, AddColumn]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    steps: tuple[Step, ...]
