"""``WorkQueue`` — encrypted, durable per-bot work items (spec §4.2).

``origin``, ``body``, ``inflight`` and ``result`` are user content and are
encrypted under ``work_items:<column>`` AADs; ids, kind, state, taint,
depth and times stay plaintext for queryability. Every per-user method
scopes by ``user_id``. ``recover_on_boot`` and ``bots_with_queued`` run
once at gateway start, across users, like ``BotStore.reset_on_boot``.

Claiming: your messages first, then other work, then routine items; the oldest queued items of a bot that share the first one's
thread ("items in a row for the same thread become one turn") move to
``claimed`` with a run id and a lease. The ``UPDATE ... RETURNING`` keeps
only what it really claimed, so a Stop racing a claim never runs a
dropped item.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import MAX_BATCH_ITEMS, WORK_LEASE_SECONDS
from roost.crypto.encryption import decrypt, decrypt_field, encrypt, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.work.models import (
    DropReport, RecoveryReport, WorkDraft, WorkItem, WorkKind, WorkState, _first_per_run,
)

_ORIGIN_AAD = "work_items:origin"
_BODY_AAD = "work_items:body"
_INFLIGHT_AAD = "work_items:inflight"
_RESULT_AAD = "work_items:result"
_LINK_SCOPE_AAD = "work_items:link_scope"

_COLUMNS = (
    "id, user_id, bot_id, thread_id, kind, origin, body, tainted, depth, parent_item_id, "
    "message_id, state, run_id, inflight, result, result_tainted, created_at, updated_at, link_scope"
)
_OPEN = "('queued','claimed')"
_CLAIM_ORDER = "CASE kind WHEN 'message' THEN 0 WHEN 'card_answer' THEN 0 WHEN 'routine' THEN 2 ELSE 1 END"


def _encode_scope(scope: tuple[str, ...], dek: bytes, user_id: str) -> str | None:
    return encrypt(json.dumps(list(scope)), dek, user_aad(user_id, _LINK_SCOPE_AAD)) if scope else None


def _decode_scope(raw: str | None, dek: bytes, user_id: str) -> tuple[str, ...]:
    """A scope that can't be read is empty: fewer links allowed, never more."""
    text = decrypt_field(raw, dek, user_aad(user_id, _LINK_SCOPE_AAD))
    if not text:
        return ()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return ()
    return tuple(str(url) for url in parsed) if isinstance(parsed, list) else ()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _marks(values: Sequence[str]) -> str:
    return ",".join("?" * len(values))


def _row_to_item(row: aiosqlite.Row, dek: bytes) -> WorkItem:
    user_id = row["user_id"]
    return WorkItem(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"], thread_id=row["thread_id"],
        kind=WorkKind(row["kind"]),
        origin=decrypt(row["origin"], dek, user_aad(user_id, _ORIGIN_AAD)),
        body=decrypt(row["body"], dek, user_aad(user_id, _BODY_AAD)),
        tainted=bool(row["tainted"]), depth=row["depth"], parent_item_id=row["parent_item_id"],
        message_id=row["message_id"], state=WorkState(row["state"]), run_id=row["run_id"],
        inflight=decrypt_field(row["inflight"], dek, user_aad(user_id, _INFLIGHT_AAD)),
        result=decrypt_field(row["result"], dek, user_aad(user_id, _RESULT_AAD)),
        result_tainted=bool(row["result_tainted"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
        link_scope=_decode_scope(row["link_scope"], dek, user_id),
    )


def _leading_same_thread(rows: Sequence[aiosqlite.Row]) -> tuple[aiosqlite.Row, ...]:
    """The first item and the items in a row for its thread. A page watch's check (a ``trigger``) is always a
    batch of its own: it runs no model, so nothing may join it and it joins nothing."""
    if not rows:
        return ()
    if rows[0]["kind"] == WorkKind.TRIGGER.value:
        return (rows[0],)
    thread_id = rows[0]["thread_id"]
    batch: tuple[aiosqlite.Row, ...] = ()
    for row in rows:
        if row["thread_id"] != thread_id or row["kind"] == WorkKind.TRIGGER.value:
            break
        batch = (*batch, row)
    return batch


class WorkQueue:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def enqueue(self, user_id: str, draft: WorkDraft, *, item_id: str | None = None) -> WorkItem:
        """Store ``draft`` as a queued item. ``item_id`` lets a caller (a
        handoff) register a waiter for the id BEFORE the item exists."""
        dek = await get_user_dek(self._config, user_id)
        new_id = item_id or str(uuid4())
        now = _now_iso()
        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO work_items (id, user_id, bot_id, thread_id, kind, origin, body, tainted, depth, "
                "parent_item_id, message_id, state, created_at, updated_at, link_scope) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id, user_id, draft.bot_id, draft.thread_id, draft.kind.value,
                 encrypt(draft.origin, dek, user_aad(user_id, _ORIGIN_AAD)),
                 encrypt(draft.body, dek, user_aad(user_id, _BODY_AAD)),
                 int(draft.tainted), draft.depth, draft.parent_item_id, draft.message_id,
                 WorkState.QUEUED.value, now, now, _encode_scope(draft.link_scope, dek, user_id)),
            )
            await db.commit()
        return WorkItem(
            id=new_id, user_id=user_id, bot_id=draft.bot_id, thread_id=draft.thread_id, kind=draft.kind,
            origin=draft.origin, body=draft.body, tainted=draft.tainted, depth=draft.depth,
            parent_item_id=draft.parent_item_id, message_id=draft.message_id, state=WorkState.QUEUED,
            run_id=None, inflight=None, result=None, result_tainted=False, created_at=now, updated_at=now,
            link_scope=draft.link_scope,
        )

    async def get(self, user_id: str, item_id: str) -> WorkItem | None:
        rows = await self._select("WHERE id = ? AND user_id = ?", (item_id, user_id))
        return (await self._decrypt(user_id, rows))[0] if rows else None

    async def claim_batch(
        self, user_id: str, bot_id: str, run_id: str, *, exclude_kinds: frozenset[WorkKind] = frozenset(),
    ) -> tuple[WorkItem, ...]:
        """Claim the next turn's items. Your messages and card answers go first, then other work, then routine
        items; each group keeps its queue order. ``exclude_kinds`` are never claimed (the usage reserve)."""
        skip = f" AND kind NOT IN ({_marks(tuple(exclude_kinds))})" if exclude_kinds else ""
        rows = _leading_same_thread(await self._select(
            f"WHERE user_id = ? AND bot_id = ? AND state = 'queued'{skip} ORDER BY {_CLAIM_ORDER}, rowid LIMIT ?",
            (user_id, bot_id, *sorted(k.value for k in exclude_kinds), MAX_BATCH_ITEMS),
        ))
        if not rows:
            return ()
        ids = tuple(row["id"] for row in rows)
        now = datetime.now(timezone.utc)
        lease = (now + timedelta(seconds=WORK_LEASE_SECONDS)).isoformat()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE work_items SET state = 'claimed', run_id = ?, lease_until = ?, inflight = NULL, "
                f"updated_at = ? WHERE user_id = ? AND state = 'queued' AND id IN ({_marks(ids)}) RETURNING id",
                (run_id, lease, now.isoformat(), user_id, *ids),
            )
            claimed = {row["id"] for row in await cursor.fetchall()}
            await db.commit()
        items = await self._decrypt(user_id, [row for row in rows if row["id"] in claimed])
        return tuple(replace(item, state=WorkState.CLAIMED, run_id=run_id) for item in items)

    async def claim_thread_messages(
        self, user_id: str, bot_id: str, thread_id: str, run_id: str,
    ) -> tuple[WorkItem, ...]:
        """Steer: your waiting messages in ``thread_id`` join the running run ``run_id`` (claimed under its id,
        so ``complete`` closes them with it and nobody answers them twice). Only ``message`` items: a routine,
        a handoff or a room post never joins a run it was not claimed for."""
        rows = await self._select(
            "WHERE user_id = ? AND bot_id = ? AND thread_id = ? AND kind = 'message' AND state = 'queued' "
            "ORDER BY rowid LIMIT ?", (user_id, bot_id, thread_id, MAX_BATCH_ITEMS),
        )
        if not rows:
            return ()
        ids = tuple(row["id"] for row in rows)
        now = datetime.now(timezone.utc)
        lease = (now + timedelta(seconds=WORK_LEASE_SECONDS)).isoformat()
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE work_items SET state = 'claimed', run_id = ?, lease_until = ?, updated_at = ? "
                f"WHERE user_id = ? AND state = 'queued' AND id IN ({_marks(ids)}) RETURNING id",
                (run_id, lease, now.isoformat(), user_id, *ids),
            )
            claimed = {row["id"] for row in await cursor.fetchall()}
            await db.commit()
        items = await self._decrypt(user_id, [row for row in rows if row["id"] in claimed])
        return tuple(replace(item, state=WorkState.CLAIMED, run_id=run_id) for item in items)

    async def has_open(self, user_id: str, bot_id: str, thread_id: str, kind: WorkKind) -> bool:
        """Whether an item of ``kind`` waits or runs in ``thread_id`` (a routine's watch queues one check at most)."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT 1 FROM work_items WHERE user_id = ? AND bot_id = ? AND thread_id = ? AND kind = ? "
                f"AND state IN {_OPEN} LIMIT 1", (user_id, bot_id, thread_id, kind.value))).fetchone()
        return row is not None

    async def oldest_open(self, user_id: str, bot_id: str, thread_id: str, kind: WorkKind) -> WorkItem | None:
        """The oldest item of ``kind`` that waits or runs in ``thread_id`` (the page watch asks how old it is)."""
        rows = await self._select(
            f"WHERE user_id = ? AND bot_id = ? AND thread_id = ? AND kind = ? AND state IN {_OPEN} "
            "ORDER BY rowid LIMIT 1", (user_id, bot_id, thread_id, kind.value))
        return (await self._decrypt(user_id, rows))[0] if rows else None

    async def newest_queued_message_at(self, user_id: str, bot_id: str) -> str | None:
        """When your newest waiting message to ``bot_id`` was queued (UTC ISO), for the burst debounce."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                "SELECT MAX(created_at) AS newest FROM work_items "
                "WHERE user_id = ? AND bot_id = ? AND kind = 'message' AND state = 'queued'", (user_id, bot_id),
            )).fetchone()
        return row["newest"] if row is not None else None

    async def claimed_for_bot(self, user_id: str, bot_id: str) -> tuple[WorkItem, ...]:
        """The items the bot's run holds right now (Stop stops the work they handed out first)."""
        rows = await self._select(
            "WHERE user_id = ? AND bot_id = ? AND state = 'claimed' ORDER BY rowid", (user_id, bot_id),
        )
        return await self._decrypt(user_id, rows)

    async def drop_waiting_for_bot(self, user_id: str, bot_id: str) -> DropReport:
        """Stop: drop only what waits; the running run ends at its own boundary."""
        return await self._drop(user_id, "bot_id = ? AND state = 'queued'", (bot_id,))

    async def drop_claimed_for_bot(self, user_id: str, bot_id: str) -> DropReport:
        """After Stop: drop only what the stopped run still holds (a cancelled run's items). A message queued
        while it was stopping stays queued and runs next."""
        return await self._drop(user_id, "bot_id = ? AND state = 'claimed'", (bot_id,))

    async def complete(self, user_id: str, run_id: str, result: str, result_tainted: bool) -> tuple[str, ...]:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE work_items SET state = 'done', result = ?, result_tainted = ?, lease_until = NULL, "
                "inflight = NULL, updated_at = ? WHERE user_id = ? AND run_id = ? AND state = 'claimed' RETURNING id",
                (encrypt(result, dek, user_aad(user_id, _RESULT_AAD)), int(result_tainted),
                 _now_iso(), user_id, run_id),
            )
            ids = tuple(row["id"] for row in await cursor.fetchall())
            await db.commit()
        return ids

    async def set_link_scope(self, user_id: str, item_ids: Sequence[str], scope: tuple[str, ...]) -> None:
        """Replace these items' stored link scope (the sites a run that stopped on a card may still open)."""
        if not item_ids:
            return
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await db.execute(
                f"UPDATE work_items SET link_scope = ?, updated_at = ? WHERE user_id = ? AND id IN ({_marks(item_ids)})",
                (_encode_scope(scope, dek, user_id), _now_iso(), user_id, *item_ids),
            )
            await db.commit()

    async def set_inflight(self, user_id: str, run_id: str, description: str | None) -> None:
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE work_items SET inflight = ?, updated_at = ? "
                "WHERE user_id = ? AND run_id = ? AND state = 'claimed'",
                (encrypt_field(description, dek, user_aad(user_id, _INFLIGHT_AAD)), _now_iso(), user_id, run_id),
            )
            await db.commit()

    async def drop_for_bot(self, user_id: str, bot_id: str) -> DropReport:
        return await self._drop(user_id, "bot_id = ?", (bot_id,))

    async def drop_items(self, user_id: str, item_ids: Sequence[str]) -> DropReport:
        if not item_ids:
            return DropReport()
        return await self._drop(user_id, f"id IN ({_marks(item_ids)})", tuple(item_ids))

    async def children_of(self, user_id: str, parent_ids: Sequence[str]) -> tuple[WorkItem, ...]:
        if not parent_ids:
            return ()
        rows = await self._select(
            f"WHERE user_id = ? AND state IN {_OPEN} AND parent_item_id IN ({_marks(parent_ids)}) ORDER BY rowid",
            (user_id, *parent_ids),
        )
        return await self._decrypt(user_id, rows)

    async def requeue_claimed(self, user_id: str, bot_id: str) -> int:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE work_items SET state = 'queued', run_id = NULL, lease_until = NULL, updated_at = ? "
                "WHERE user_id = ? AND bot_id = ? AND state = 'claimed'",
                (_now_iso(), user_id, bot_id),
            )
            await db.commit()
        return cursor.rowcount

    async def first_queued(self, user_id: str, bot_id: str) -> WorkItem | None:
        rows = await self._select(
            "WHERE user_id = ? AND bot_id = ? AND state = 'queued' ORDER BY rowid LIMIT 1", (user_id, bot_id),
        )
        return (await self._decrypt(user_id, rows))[0] if rows else None

    async def bots_with_queued(self) -> tuple[tuple[str, str], ...]:
        """Boot only, across users: every (user_id, bot_id) with queued work."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT user_id, bot_id FROM work_items WHERE state = 'queued' "
                "GROUP BY user_id, bot_id ORDER BY MIN(rowid)",
            )).fetchall()
        return tuple((row["user_id"], row["bot_id"]) for row in rows)

    async def recover_on_boot(self) -> RecoveryReport:
        """Boot only, across users. One gateway process: nothing can still be
        working on a claimed item. Open handoffs are dropped (their asker's
        run died with the process and asks again when it re-runs); every
        other claimed item goes back to queued, keeping its in-flight note."""
        async with db_session(self._config) as db:
            handoffs = await (await db.execute(
                f"SELECT {_COLUMNS} FROM work_items WHERE kind = 'handoff' AND state IN {_OPEN} ORDER BY rowid",
            )).fetchall()
            claimed = await (await db.execute(
                f"SELECT {_COLUMNS} FROM work_items WHERE kind != 'handoff' AND state = 'claimed' ORDER BY rowid",
            )).fetchall()
            now = _now_iso()
            await db.execute(
                f"UPDATE work_items SET state = 'dropped', lease_until = NULL, updated_at = ? "
                f"WHERE kind = 'handoff' AND state IN {_OPEN}", (now,),
            )
            await db.execute(
                "UPDATE work_items SET state = 'queued', run_id = NULL, lease_until = NULL, updated_at = ? "
                "WHERE state = 'claimed'", (now,),
            )
            await db.commit()
        requeued = await self._decrypt_any(claimed)
        return RecoveryReport(
            dropped_handoffs=await self._decrypt_any(handoffs),
            interrupted=_first_per_run(tuple(item for item in requeued if item.inflight)),
        )

    async def _drop(self, user_id: str, condition: str, params: tuple) -> DropReport:
        rows = await self._select(
            f"WHERE user_id = ? AND state IN {_OPEN} AND {condition} ORDER BY rowid", (user_id, *params),
        )
        if not rows:
            return DropReport()
        ids = tuple(row["id"] for row in rows)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE work_items SET state = 'dropped', lease_until = NULL, updated_at = ? "
                f"WHERE user_id = ? AND state IN {_OPEN} AND id IN ({_marks(ids)}) RETURNING id",
                (_now_iso(), user_id, *ids),
            )
            dropped = {row["id"] for row in await cursor.fetchall()}
            await db.commit()
        return DropReport(dropped=await self._decrypt(user_id, [r for r in rows if r["id"] in dropped]))

    async def _select(self, where: str, params: tuple) -> list[aiosqlite.Row]:
        async with db_session(self._config) as db:
            cursor = await db.execute(f"SELECT {_COLUMNS} FROM work_items {where}", params)
            return list(await cursor.fetchall())

    async def _decrypt(self, user_id: str, rows: Sequence[aiosqlite.Row]) -> tuple[WorkItem, ...]:
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_item(row, dek) for row in rows)

    async def _decrypt_any(self, rows: Sequence[aiosqlite.Row]) -> tuple[WorkItem, ...]:
        """Rows that may belong to several users (boot recovery only)."""
        items: tuple[WorkItem, ...] = ()
        for user_id in dict.fromkeys(row["user_id"] for row in rows):
            items = (*items, *await self._decrypt(user_id, [r for r in rows if r["user_id"] == user_id]))
        return items
