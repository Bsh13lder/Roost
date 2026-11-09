"""Which rows an import made: the "from LazyClaw" mark (``import_links``, schema v18).

One indexed read per list, scoped by the user, never a join into the row queries."""

from __future__ import annotations

from typing import Sequence

import aiosqlite

IMPORTED_FROM_LAZYCLAW = "lazyclaw"
IMPORT_QUERY_CHUNK = 400      # ids per lookup, well under SQLite's variable limit


async def imported_ids(db: aiosqlite.Connection, user_id: str, kind: str, ids: Sequence[str]) -> frozenset[str]:
    """The ids (of ``kind``: ``task``, ``expense``, ...) that came from LazyClaw."""
    found: set[str] = set()
    for start in range(0, len(ids), IMPORT_QUERY_CHUNK):
        chunk = tuple(ids[start:start + IMPORT_QUERY_CHUNK])
        marks = ",".join("?" * len(chunk))
        rows = await (await db.execute(
            f"SELECT new_id FROM import_links WHERE user_id = ? AND source = ? AND kind = ? AND new_id IN ({marks})",
            (user_id, IMPORTED_FROM_LAZYCLAW, kind, *chunk))).fetchall()
        found.update(row[0] for row in rows)
    return frozenset(found)
