"""``TalkStore`` — encrypted CRUD over the ``threads``/``messages`` tables,
plus the ``thread_out``/``message_out`` serializers (see the contract's
"Talk" section).

Encryption mirrors ``roost/bots/store.py``: ``threads.title`` and
``messages.body`` are encrypted with the owning user's DEK under their
own AAD contexts (``threads:title``, ``messages:body`` via
``user_aad``). Passing an AAD to ``roost.crypto.encryption.encrypt``
always produces an ``enc:v2`` token (never ``enc:v1`` — see
``roost/bots/store.py``'s module docstring for why; same reasoning
applies here).

Every method takes ``user_id`` and scopes its query by it, so a
mismatched or unknown ``thread_id``/``bot_id`` is indistinguishable from
"doesn't exist" — the gateway routes (``roost/gateway/routes/
threads.py``) turn that into a 404, never leaking whether the id
belongs to someone else.

``seq`` (per-thread message ordering) is assigned by
``INSERT ... SELECT COALESCE(MAX(seq), 0) + 1 ... WHERE thread_id = ?``
rather than read-then-write: one atomic statement against the single
shared connection (``roost/db/connection.py``), so two messages landing
in the same thread can never be assigned the same ``seq`` by a races-
with-itself read/write gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence
from uuid import uuid4

import aiosqlite

from roost.config import Config
from roost.constants import DEFAULT_MESSAGE_PAGE_LIMIT
from roost.crypto.encryption import decrypt_field, encrypt, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session

_TITLE_AAD = "threads:title"
_BODY_AAD = "messages:body"
_QUOTE_AAD = "messages:reply_quote"

_THREAD_COLUMNS = "id, user_id, bot_id, title, kind, peer_bot_id, created_at, updated_at"
_MESSAGE_COLUMNS = ("id, user_id, thread_id, role, body, tainted, seq, created_at, kind, author_bot_id, "
                    "reply_to, reply_quote, reply_tainted")
_JOINED_MESSAGE_COLUMNS = ", ".join(f"m.{column}" for column in _MESSAGE_COLUMNS.split(", "))

MessageRole = Literal["user", "bot", "activity", "system"]
MessageKind = Literal[
    "text", "handoff", "suggestion", "notice", "dropped", "interrupted", "daily_limit", "bot_created",
    "stuck",         # Stuck flow: a bot's Stuck card; body = stuck_message_body(card), JSON
    "card_answer",   # Stuck flow R6: your continue line after clearing a card (role "user")
    "memory_note",   # Memory: a bot's quiet "Remembered" line; body = JSON {memory_id, kind, text}; never replayed
    "memory_offer",  # Memory: "Not remembered: … · Remember it" (tainted); body = JSON {text, kind, importance, memory_id}
    "approval",         # Ask cards: a bot's card; body = JSON {card_id, kind, steps: [titles]}
    "approval_result",  # Ask cards: the outcome of a step you approved (role "system"); the model reads it
    "mac_activity",     # Your Mac: "Edited Tasks.md · MySpace (+2 −1) · Undo" (role "activity"); never replayed
    "routine",          # Routines: a routine's instructions + slot line in its run-log thread (role "user"); the model reads it
    "report",           # Routines: a bot's Report in its main chat; body = ReportBody JSON; the model reads it as text
    "routine_note",     # Routines: "Created routine · {name}" (role "activity"); never replayed
    "routine_finished", # Routines: "Finished routine · {name}: {reason}" with Resume · Delete now (role "activity");
                        # body = JSON {routine_id, name, reason, delete_at, text}; never replayed
    "routine_proposal", # Routines: a routine proposal card; body = JSON {proposal_id}; never replayed
    "question_note",    # Routines: "Picked: ..." in the question book (role "activity"); never replayed
    "skill_proposal",   # Skills: a skill proposal card; body = JSON {proposal_id, name}; never replayed
    "connector_request",  # Connectors: the Add a key card; body = JSON {request_id, service, host}; never replayed
    "reaction",         # Tapbacks: body = JSON {target_id, key}; never replayed, never a chat-list preview
    "instructions_proposal",  # Replies: an "Update my instructions?" card; body = JSON {proposal_id}; never replayed
    "program_activity", # Programs: "Ran: python3 a.py · exit 0" / "Wrote a.py" (role "activity"); never replayed
    "fresh_start",      # Fresh start: hides earlier web replies from the next runs (role "system"); never replayed
    "instruction_change",  # A2: "Updated my instructions: Tone · Undo" (role "activity"); body = JSON
                           # {section, before, after, why, undone}; never replayed
    "task_cards",       # Task cards: the tasks a run added or listed (role "activity"); body = JSON
                        # {task_ids, verb, more}; never replayed
    "english_fix",      # Correct my English: a spoken message's corrected copy (role "activity"); body = JSON
                        # {message_id, said, corrected, fixes}; never replayed, never a chat-list preview
    "computer_restart", # Self-healing: "My computer stopped answering, so I restarted it." (role "system"); plain words
]

# Kinds that never lead a chat's row in the chat list (a tapback, a correction of your own words).
PREVIEW_SKIPPED_KINDS: tuple[str, ...] = ("reaction", "english_fix")
_PREVIEW_SKIP_SQL = "(" + ", ".join(f"'{kind}'" for kind in PREVIEW_SKIPPED_KINDS) + ")"


@dataclass(frozen=True)
class Thread:
    id: str
    user_id: str
    bot_id: str
    title: str | None
    kind: str
    created_at: str
    updated_at: str
    peer_bot_id: str | None = None


@dataclass(frozen=True)
class Message:
    id: str
    user_id: str
    thread_id: str
    role: MessageRole
    body: str
    tainted: bool
    seq: int
    created_at: str
    kind: MessageKind = "text"
    author_bot_id: str | None = None
    reply_to: str | None = None        # the message this one answers (same thread); None: not a reply
    reply_quote: str | None = None     # the server-made quote of it (sealed under messages:reply_quote)
    reply_tainted: bool = False        # the quoted message came from web content


@dataclass(frozen=True)
class ReplyQuote:
    """What a reply keeps of the message it answers: its id, a short quote (roost/talk/replies.py) and its taint."""
    message_id: str
    text: str
    tainted: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_thread(row: aiosqlite.Row, dek: bytes) -> Thread:
    user_id = row["user_id"]
    return Thread(
        id=row["id"],
        user_id=user_id,
        bot_id=row["bot_id"],
        title=decrypt_field(row["title"], dek, user_aad(user_id, _TITLE_AAD)),
        kind=row["kind"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        peer_bot_id=row["peer_bot_id"],
    )


def _row_to_message(row: aiosqlite.Row, dek: bytes) -> Message:
    user_id = row["user_id"]
    return Message(
        id=row["id"],
        user_id=user_id,
        thread_id=row["thread_id"],
        role=row["role"],
        body=decrypt_field(row["body"], dek, user_aad(user_id, _BODY_AAD)),
        tainted=bool(row["tainted"]),
        seq=row["seq"],
        created_at=row["created_at"],
        kind=row["kind"],
        author_bot_id=row["author_bot_id"],
        reply_to=row["reply_to"],
        reply_quote=decrypt_field(row["reply_quote"], dek, user_aad(user_id, _QUOTE_AAD)),
        reply_tainted=bool(row["reply_tainted"]),
    )


def _later_than(after_created_at: str | None) -> tuple[str, tuple[str, ...]]:
    """The SQL for "newer than the summary boundary", and its argument."""
    if after_created_at is None:
        return "", ()
    return " AND created_at > ?", (after_created_at,)


class TalkStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create_thread(
        self, user_id: str, bot_id: str, title: str | None = None,
        *, kind: str = "chat", peer_bot_id: str | None = None,
    ) -> Thread:
        """Create a thread under ``bot_id``.

        Does not itself verify that ``bot_id`` belongs to ``user_id`` —
        the foreign-key constraint would reject an unknown bot id
        outright, but a *foreign* (someone else's) bot id is otherwise
        indistinguishable here. The gateway route looks the bot up via
        ``BotStore.get(user_id, bot_id)`` first and 404s before ever
        calling this, which is also the only place that can give a
        user-friendly "bot not found" rather than a raw FK error.
        """
        dek = await get_user_dek(self._config, user_id)
        thread_id = str(uuid4())
        now = _now_iso()

        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO threads (id, user_id, bot_id, title, kind, peer_bot_id, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    thread_id,
                    user_id,
                    bot_id,
                    encrypt_field(title, dek, user_aad(user_id, _TITLE_AAD)),
                    kind,
                    peer_bot_id,
                    now,
                    now,
                ),
            )
            await db.commit()

        return Thread(
            id=thread_id, user_id=user_id, bot_id=bot_id, title=title,
            kind=kind, created_at=now, updated_at=now, peer_bot_id=peer_bot_id,
        )

    async def find_or_create_peer_thread(self, user_id: str, bot_id: str, peer_bot_id: str, title: str) -> Thread:
        """``bot_id``'s dedicated thread for work handed over by
        ``peer_bot_id`` (D-C: "a dedicated thread of the target named
        'From <asker>'"), created on first use."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_THREAD_COLUMNS} FROM threads WHERE user_id = ? AND bot_id = ? AND peer_bot_id = ? "
                "AND kind = 'handoff' ORDER BY created_at LIMIT 1",
                (user_id, bot_id, peer_bot_id),
            )).fetchone()
        if row is not None:
            return _row_to_thread(row, await get_user_dek(self._config, user_id))
        return await self.create_thread(user_id, bot_id, title=title, kind="handoff", peer_bot_id=peer_bot_id)

    async def list_threads(self, user_id: str, bot_id: str) -> list[Thread]:
        """A room thread is listed under Rooms, not under its coordinator's
        own thread list, and a routine's run-log thread has its own page (``kind NOT IN ('room', 'routine')``)."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"SELECT {_THREAD_COLUMNS} FROM threads WHERE user_id = ? AND bot_id = ? AND kind NOT IN ('room', 'routine') "
                "ORDER BY created_at",
                (user_id, bot_id),
            )
            rows = await cursor.fetchall()
        if not rows:
            return []
        dek = await get_user_dek(self._config, user_id)
        return [_row_to_thread(row, dek) for row in rows]

    async def main_thread(self, user_id: str, bot_id: str) -> Thread | None:
        """The bot's one chat: its ``kind='chat'`` thread with the newest activity (a thread with no message
        counts its creation), ties broken by creation then id. Handoff and room threads are never it."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_THREAD_COLUMNS} FROM threads t WHERE t.user_id = ? AND t.bot_id = ? AND t.kind = 'chat' "
                "ORDER BY COALESCE((SELECT MAX(m.created_at) FROM messages m "
                "WHERE m.thread_id = t.id AND m.user_id = t.user_id), t.created_at) DESC, "
                "t.created_at DESC, t.id DESC LIMIT 1",
                (user_id, bot_id),
            )).fetchone()
        if row is None:
            return None
        return _row_to_thread(row, await get_user_dek(self._config, user_id))

    async def ensure_main_thread(self, user_id: str, bot_id: str) -> tuple[Thread, bool]:
        """The bot's main chat, made when it has none (``True`` when made). The caller has checked the bot."""
        found = await self.main_thread(user_id, bot_id)
        if found is not None:
            return found, False
        return await self.create_thread(user_id, bot_id), True

    async def get_thread(self, user_id: str, thread_id: str) -> Thread | None:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"SELECT {_THREAD_COLUMNS} FROM threads WHERE id = ? AND user_id = ?",
                (thread_id, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        dek = await get_user_dek(self._config, user_id)
        return _row_to_thread(row, dek)

    async def add_message(
        self, user_id: str, thread_id: str, role: str, body: str, tainted: bool = False,
        *, message_id: str | None = None, kind: MessageKind = "text", author_bot_id: str | None = None,
        reply: ReplyQuote | None = None,
    ) -> Message:
        """Append a message to ``thread_id`` with the next per-thread ``seq``
        (one atomic ``INSERT ... SELECT``). ``message_id`` lets a turn persist
        its reply under the id its placeholder frame announced (Ruling 15);
        ``kind``/``author_bot_id`` mark handoff lines, notices, suggestion
        cards and which bot wrote a message in a room. ``reply`` is the quote
        of the message this one answers, already checked by the caller
        (``roost/talk/replies.py`` ``resolve_reply``)."""
        dek = await get_user_dek(self._config, user_id)
        message_id = message_id or str(uuid4())
        now = _now_iso()
        encrypted_body = encrypt(body, dek, user_aad(user_id, _BODY_AAD))
        quote = encrypt(reply.text, dek, user_aad(user_id, _QUOTE_AAD)) if reply is not None else None

        async with db_session(self._config) as db:
            await db.execute(
                "INSERT INTO messages (id, user_id, thread_id, role, body, tainted, seq, created_at, kind, author_bot_id, "
                "reply_to, reply_quote, reply_tainted) "
                "SELECT ?, ?, ?, ?, ?, ?, COALESCE(MAX(seq), 0) + 1, ?, ?, ?, ?, ?, ? "
                "FROM messages WHERE thread_id = ?",
                (message_id, user_id, thread_id, role, encrypted_body, int(tainted), now, kind, author_bot_id,
                 reply.message_id if reply else None, quote, int(bool(reply and reply.tainted)), thread_id),
            )
            await db.commit()
            cursor = await db.execute("SELECT seq FROM messages WHERE id = ?", (message_id,))
            seq_row = await cursor.fetchone()

        return Message(
            id=message_id, user_id=user_id, thread_id=thread_id, role=role, body=body, tainted=tainted,
            seq=seq_row["seq"], created_at=now, kind=kind, author_bot_id=author_bot_id,
            reply_to=reply.message_id if reply else None, reply_quote=reply.text if reply else None,
            reply_tainted=bool(reply and reply.tainted),
        )

    async def get_message(self, user_id: str, message_id: str) -> Message | None:
        """One message, only when it is the user's (another user's id reads as no such message)."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE id = ? AND user_id = ?", (message_id, user_id))
            ).fetchone()
        if row is None:
            return None
        return _row_to_message(row, await get_user_dek(self._config, user_id))

    async def replace_body(self, user_id: str, message_id: str, body: str) -> bool:
        """Replace one message's body (a Mac activity line loses its Undo once it was used). False when it is not the user's."""
        dek = await get_user_dek(self._config, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE messages SET body = ? WHERE id = ? AND user_id = ?",
                (encrypt(body, dek, user_aad(user_id, _BODY_AAD)), message_id, user_id))
            await db.commit()
        return cursor.rowcount > 0

    async def list_messages(
        self, user_id: str, thread_id: str, after_seq: int = 0, limit: int = DEFAULT_MESSAGE_PAGE_LIMIT,
    ) -> list[Message]:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM messages "
                "WHERE user_id = ? AND thread_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                (user_id, thread_id, after_seq, limit),
            )
            rows = await cursor.fetchall()
        if not rows:
            return []
        dek = await get_user_dek(self._config, user_id)
        return [_row_to_message(row, dek) for row in rows]

    async def list_latest_messages(
        self, user_id: str, thread_id: str, limit: int | None = None, *, after_created_at: str | None = None,
    ) -> list[Message]:
        """The newest ``limit`` messages in ``thread_id``, still in
        chronological (ascending ``seq``) order (Final review, finding
        8). ``list_messages``'s default is ``ORDER BY seq ASC LIMIT``
        -- the OLDEST page -- so once a thread passes the limit, the
        turn's own model context (``roost/talk/turn.py``'s
        ``run_turn``) and a fresh page load of Talk (``GET
        /api/threads/{id}/messages`` with no ``after``) both need this
        instead, or the model answers stale context and the UI never
        shows anything posted past the thread's first page.

        ``limit`` defaults to ``DEFAULT_MESSAGE_PAGE_LIMIT`` looked up
        dynamically (not baked into this method's own default argument
        at import time), so a test can turn it down via
        ``monkeypatch.setattr(store_module, "DEFAULT_MESSAGE_PAGE_LIMIT", ...)``
        without inserting hundreds of rows -- the same pattern
        ``roost/talk/turn.py``/``roost/talk/runner.py`` already use for
        ``MAX_RUN_SECONDS``.
        """
        if limit is None:
            limit = DEFAULT_MESSAGE_PAGE_LIMIT

        later, later_args = _later_than(after_created_at)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM messages "
                f"WHERE user_id = ? AND thread_id = ?{later} ORDER BY seq DESC LIMIT ?",
                (user_id, thread_id, *later_args, limit),
            )
            rows = await cursor.fetchall()
        if not rows:
            return []
        dek = await get_user_dek(self._config, user_id)
        return [_row_to_message(row, dek) for row in reversed(rows)]

    async def count_messages(self, user_id: str, thread_id: str, *, after_created_at: str | None = None) -> int:
        """How many messages ``thread_id`` holds (after ``after_created_at`` when given)."""
        later, later_args = _later_than(after_created_at)
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT COUNT(*) AS n FROM messages WHERE user_id = ? AND thread_id = ?{later}",
                (user_id, thread_id, *later_args),
            )).fetchone()
        return int(row["n"])

    async def list_messages_since(
        self, user_id: str, thread_id: str, *, after_created_at: str | None, limit: int,
    ) -> list[Message]:
        """The oldest ``limit`` messages after ``after_created_at`` (all when ``None``), oldest first."""
        later, later_args = _later_than(after_created_at)
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM messages "
                f"WHERE user_id = ? AND thread_id = ?{later} ORDER BY seq LIMIT ?",
                (user_id, thread_id, *later_args, limit),
            )).fetchall()
        if not rows:
            return []
        dek = await get_user_dek(self._config, user_id)
        return [_row_to_message(row, dek) for row in rows]

    async def scan_messages(
        self, user_id: str, thread_id: str, *, upto_created_at: str | None, limit: int,
    ) -> tuple[Message, ...]:
        """Text-like messages (text, card answers, handoff lines) up to ``upto_created_at`` (all when ``None``),
        newest first, at most ``limit``: what ``search_chat`` reads."""
        bound, bound_args = ("", ()) if upto_created_at is None else (" AND created_at <= ?", (upto_created_at,))
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE user_id = ? AND thread_id = ? "
                f"AND kind IN ('text', 'card_answer', 'handoff'){bound} ORDER BY seq DESC LIMIT ?",
                (user_id, thread_id, *bound_args, limit),
            )).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_message(row, dek) for row in rows)

    async def scan_all_chats(self, user_id: str, *, limit: int) -> tuple[tuple[Message, str], ...]:
        """Text-like messages across the user's chats and rooms (not routine run logs), newest first, at most
        ``limit``, each with its thread's ``bot_id``: what ``GET /api/chats/search`` reads."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_JOINED_MESSAGE_COLUMNS}, t.bot_id AS thread_bot_id FROM messages m JOIN threads t "
                "ON t.id = m.thread_id AND t.user_id = m.user_id "
                "WHERE m.user_id = ? AND t.kind != 'routine' AND m.kind IN ('text', 'card_answer', 'handoff') "
                "ORDER BY m.created_at DESC, m.seq DESC LIMIT ?",
                (user_id, limit),
            )).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple((_row_to_message(row, dek), row["thread_bot_id"]) for row in rows)

    async def list_bot_messages(self, user_id: str, bot_id: str, limit: int) -> tuple[Message, ...]:
        """The newest ``limit`` messages across ``bot_id``'s own threads (not rooms), newest first."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_JOINED_MESSAGE_COLUMNS} FROM messages m JOIN threads t "
                "ON t.id = m.thread_id AND t.user_id = m.user_id "
                "WHERE m.user_id = ? AND t.bot_id = ? AND t.kind NOT IN ('room', 'routine') "
                f"AND m.kind NOT IN {_PREVIEW_SKIP_SQL} "
                "ORDER BY m.created_at DESC, m.seq DESC LIMIT ?",
                (user_id, bot_id, limit),
            )).fetchall()
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_message(row, dek) for row in rows)

    async def latest_for_bot(self, user_id: str, bot_id: str) -> Message | None:
        """The newest message across ``bot_id``'s own threads (not rooms): Home's chat row."""
        found = await self.list_bot_messages(user_id, bot_id, 1)
        return found[0] if found else None

    async def latest_in_thread(self, user_id: str, thread_id: str) -> Message | None:
        """The newest message in ``thread_id`` (a room's chat row), or ``None`` when it has none."""
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE user_id = ? AND thread_id = ? "
                f"AND kind NOT IN {_PREVIEW_SKIP_SQL} ORDER BY seq DESC LIMIT 1",
                (user_id, thread_id),
            )).fetchone()
        if row is None:
            return None
        return _row_to_message(row, await get_user_dek(self._config, user_id))


def thread_out(thread: Thread) -> dict[str, Any]:
    """Build the ``ThreadOut`` wire shape for ``thread`` (contract's HTTP
    API table) — deliberately omits ``user_id``, which the client never
    needs and the server never leaks."""
    return {
        "id": thread.id,
        "bot_id": thread.bot_id,
        "title": thread.title,
        "kind": thread.kind,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }


def message_out(message: Message, media: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Build the ``MessageOut`` wire shape for ``message`` (contract's
    HTTP API table and ``events/hub.py``'s ``message``/``message_done``
    frame payloads). ``media`` is its pictures (chat pictures, owner
    2026-11-05; ``roost/media/store.py``), an empty list when none."""
    return {
        "id": message.id,
        "thread_id": message.thread_id,
        "role": message.role,
        "body": message.body,
        "tainted": message.tainted,
        "seq": message.seq,
        "created_at": message.created_at,
        "kind": message.kind,
        "author_bot_id": message.author_bot_id,
        "reply_to": message.reply_to,
        "reply_quote": message.reply_quote,
        "reply_tainted": message.reply_tainted,
        "media": [dict(item) for item in media],
    }
