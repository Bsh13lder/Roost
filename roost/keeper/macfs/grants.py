"""Grants held in the keeper's memory only. The gateway pushes the whole set (``PUT /mac/grants``);
nothing is ever written to disk, so a keeper restart forgets them (``grants_unset``) until the
gateway pushes again. A revoke is one reference swap: the next lookup refuses the old id."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from roost.keeper.macfs.errors import MacFsError
from roost.keeper.macfs.paths import check_resolved, map_oserror

Access = Literal["read", "read_write"]
_ROOT_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


@dataclass(frozen=True)
class KeeperGrant:
    grant_id: str
    root: str            # resolved, absolute, already past check_grant_root
    access: Access
    bot_id: str | None   # None: every bot
    dev: int
    ino: int


class GrantRegistry:
    def __init__(self, home: str | None = None) -> None:
        self._home = home
        self._grants: dict[str, KeeperGrant] | None = None
        self.generation = 0   # walks compare it to stop after a push

    def replace(self, grants: tuple[KeeperGrant, ...]) -> None:
        """Swap the whole set in one reference assignment."""
        self._grants = {g.grant_id: g for g in grants}
        self.generation += 1

    def lookup(self, grant_id: str, bot_id: str | None) -> KeeperGrant:
        current = self._grants
        if current is None:
            raise MacFsError("grants_unset")
        grant = current.get(grant_id)
        if grant is None or (grant.bot_id is not None and grant.bot_id != bot_id):
            raise MacFsError("no_grant")
        return grant

    def open_root(self, grant: KeeperGrant) -> int:
        """Open the grant's folder and refuse it when it is no longer the folder that was granted."""
        try:
            fd = os.open(grant.root, _ROOT_FLAGS)
        except OSError as exc:
            raise map_oserror(exc) from None
        try:
            st = os.fstat(fd)
            if (st.st_dev, st.st_ino) != (grant.dev, grant.ino):
                raise MacFsError("no_grant")
            check_resolved(fd, self._home, grant.root)
        except BaseException:
            os.close(fd)
            raise
        return fd
