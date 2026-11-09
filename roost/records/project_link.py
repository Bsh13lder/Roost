"""A record's link to one of the user's projects (projects hub, H11, H12).

A foreign key proves that a project exists, not whose it is. So every write
that sets a ``project_id`` (on a task, a note or a document) first runs
``require_project`` inside the SAME ``db_session`` as the write. The session
holds the pooled connection's lock, so the project can't be deleted between
the check and the write. An archived project may be linked. A deleted one,
another user's, or an unknown id may not."""

from __future__ import annotations

import aiosqlite

NO_SUCH_PROJECT_TEXT = "No such project."
_OWNED_PROJECT_SQL = "SELECT 1 FROM money_projects WHERE id = ? AND user_id = ? AND deleted_at IS NULL"


async def require_project(db: aiosqlite.Connection, user_id: str, project_id: str | None) -> None:
    """``None`` (no link, or unlinking) always passes. ``ValueError`` when
    ``project_id`` is not one of this user's live projects. The routes turn it
    into 422 and the tools into "Refused: No such project."

    ``fetchall`` drains the cursor, so the caller's commit in the same session
    never meets a statement still in progress (see ``db_session``)."""
    if project_id is None:
        return
    rows = await (await db.execute(_OWNED_PROJECT_SQL, (project_id, user_id))).fetchall()
    if not rows:
        raise ValueError(NO_SUCH_PROJECT_TEXT)


async def project_currencies(db: aiosqlite.Connection, user_id: str, project_ids: tuple[str, ...]) -> dict[str, str]:
    """The currency of each of these projects that is one of this user's live ones. An id that is not
    (another user's, deleted, unknown) is missing from the answer. Read in the caller's session."""
    marks = ",".join("?" * len(project_ids))
    rows = await (await db.execute(
        f"SELECT id, currency FROM money_projects WHERE user_id = ? AND deleted_at IS NULL AND id IN ({marks})",
        (user_id, *project_ids),
    )).fetchall()
    return {row["id"]: row["currency"] for row in rows}
