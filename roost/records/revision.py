"""A compare-and-swap miss on a revisioned record (M2 D1/D2): the revision a
writer read is no longer the stored one. ``current`` is the stored record, so
the Board can offer "Load the latest" or "Keep mine" and a tool can say
"read it again" — a stale write never silently overwrites a newer one."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class RevisionConflict(Exception, Generic[T]):
    def __init__(self, current: T) -> None:
        super().__init__("The record changed since it was read.")
        self.current = current
