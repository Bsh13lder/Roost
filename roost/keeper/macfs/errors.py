"""The one error type of the Mac file API. ``code`` is one of the Shared Contract's keeper codes."""

from __future__ import annotations


class MacFsError(Exception):
    """A refused or failed Mac file operation. The message is the code only: never a path or a name."""

    def __init__(self, code: str, *, current_sha256: str | None = None, grant_id: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.current_sha256 = current_sha256
        self.grant_id = grant_id   # set for ``bad_grant``: the pushed grant whose folder the keeper refused
