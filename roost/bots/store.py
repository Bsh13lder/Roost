"""``BotStore`` — encrypted CRUD over the ``bots`` table.

Encryption: ``name``/``job``/``instructions`` are encrypted with the
owning user's DEK, each under its own AAD context from the contract
(``bots:name``, ``bots:job``, ``bots:instructions`` via ``user_aad``).
Passing an AAD to ``roost.crypto.encryption.encrypt`` always produces an
``enc:v2`` token (never ``enc:v1`` — that format exists only for
AAD-less callers); this matches
``docs/specs/2026-10-12-roost-design.md`` §4.7 ("New bot tables ... use
the existing `enc:v2` format, with AAD") — see ``tests/test_bot_store.py``
for where this is pinned down.

Name uniqueness is case-insensitive per user without ever storing or
comparing a plaintext name server-side: ``name_key`` is an
HMAC-SHA256(dek, casefolded-and-stripped name), so two users with a
same-named bot get unrelated keys, and the DB's own
``UNIQUE(user_id, name_key)`` constraint (schema.sql) is the actual
enforcement point — ``create``/``update`` just translate the resulting
``IntegrityError`` into ``DuplicateBotName``, which also makes this
race-safe against a concurrent duplicate insert.

Every method takes ``user_id`` and scopes its query by it; a mismatched
or unknown ``bot_id`` is indistinguishable from "doesn't exist" — the
gateway routes turn that into a 404, never leaking whether the id
belongs to someone else.

``bot_roles`` (M1) is left in the database and read by nothing (S1 D2).
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

import aiosqlite

from roost.bots.look import avatar_dict
from roost.bots.models import Avatar, Bot, BotDraft, BotPatch, BotStatus, DuplicateBotName
from roost.bots.picture import Picture, open_picture, picture_tag, seal_picture
from roost.config import Config
from roost.approvals.models import DEFAULT_BOT_APPROVAL, BotApproval, parse_topics, topics_json
from roost.constants import DEFAULT_COMPUTER, BOT_ROLES, DEFAULT_ROBOT_SCREEN, NEW_BOT_APPROVAL_MODE, NEW_BOT_AUTO_REVIEW
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.voice.settings import VoiceSettings, voice_dump, voice_load

if TYPE_CHECKING:
    from roost.events.hub import EventHub

_NAME_AAD = "bots:name"
_JOB_AAD = "bots:job"
_INSTRUCTIONS_AAD = "bots:instructions"
_GROUP_AAD = "bots:group_label"
_PICTURE_KEY = "picture"   # in the avatar JSON: the sealed picture (roost/bots/picture.py)

_SELECT_COLUMNS = (
    "id, user_id, name, job, instructions, avatar, template_id, "
    "status, model_override, created_at, updated_at, off_duty, is_primary, notify, group_label, pinned, pinned_at, effort, "
    "approval_mode, approval_ask_topics, computer, full_limit_until, workspace_internet, auto_review, voice"
)


def normalize_bot_name(name: str) -> str:
    """The contract's case-insensitive uniqueness normalization: casefolded
    and stripped, so a trailing space (``BOT_NAME_PATTERN`` allows one, and
    some clients send one) never makes two names distinct. Shared with
    ``roost.bots.main_bot`` so a by-name Chief match agrees with this."""
    return name.casefold().strip()


def _name_key(dek: bytes, name: str) -> str:
    """HMAC-SHA256(dek, normalized name) — the contract's case-insensitive
    uniqueness key, bound to the user's own DEK so it reveals nothing about
    the name and can't be compared across users."""
    return hmac.new(dek, normalize_bot_name(name).encode("utf-8"), hashlib.sha256).hexdigest()


def _next_group(current: str | None, wanted: str | None) -> str | None:
    """None keeps the label; blank clears it; text sets it, stripped."""
    return current if wanted is None else (wanted.strip() or None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _avatar_dump(avatar: Avatar, sealed_picture: str | None = None) -> str:
    data = avatar_dict(avatar)   # the role only when it has one
    return json.dumps(data if sealed_picture is None else {**data, _PICTURE_KEY: sealed_picture})


def _avatar_load(raw: str) -> Avatar:
    """An avatar stored before the robots has no screen: it shows the default style. Badges are not
    drawn any more, so a row without one reads as "none" too."""
    data = json.loads(raw)
    sealed = data.get(_PICTURE_KEY)
    return Avatar(shape=data["shape"], color=data["color"], badge=data.get("badge", "none"),
                  screen=data.get("screen", DEFAULT_ROBOT_SCREEN), picture=picture_tag(sealed) if sealed else None,
                  role=data["role"] if data.get("role") in BOT_ROLES else None)


async def _sealed_picture(db: aiosqlite.Connection, user_id: str, bot_id: str) -> str | None:
    row = await (await db.execute("SELECT avatar FROM bots WHERE id = ? AND user_id = ?", (bot_id, user_id))).fetchone()
    return None if row is None else json.loads(row["avatar"]).get(_PICTURE_KEY)


def _row_to_bot(row: aiosqlite.Row, dek: bytes) -> Bot:
    user_id = row["user_id"]
    return Bot(
        id=row["id"],
        user_id=user_id,
        name=decrypt_field(row["name"], dek, user_aad(user_id, _NAME_AAD)),
        job=decrypt_field(row["job"], dek, user_aad(user_id, _JOB_AAD)),
        instructions=decrypt_field(row["instructions"], dek, user_aad(user_id, _INSTRUCTIONS_AAD)),
        avatar=_avatar_load(row["avatar"]),
        template_id=row["template_id"],
        status=BotStatus(row["status"]),
        model_override=row["model_override"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        off_duty=bool(row["off_duty"]),
        is_primary=bool(row["is_primary"]),
        notify=bool(row["notify"]),
        group=None if row["group_label"] is None
        else decrypt_field(row["group_label"], dek, user_aad(user_id, _GROUP_AAD)),
        pinned=bool(row["pinned"]),
        pinned_at=row["pinned_at"],
        effort=row["effort"],
        approval=BotApproval(row["approval_mode"], parse_topics(row["approval_ask_topics"]),
                             auto_review=bool(row["auto_review"])),
        computer=row["computer"],
        full_limit_until=row["full_limit_until"],
        workspace_internet=bool(row["workspace_internet"]),
        voice=voice_load(row["voice"]),
    )


class BotStore:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def create(self, user_id: str, draft: BotDraft) -> Bot:
        dek = await get_user_dek(self._config, user_id)
        bot_id = str(uuid4())
        now = _now_iso()

        async with db_session(self._config) as db:
            try:
                await db.execute(
                    "INSERT INTO bots (id, user_id, name, name_key, job, instructions, "
                    "avatar, template_id, status, model_override, created_at, updated_at, "
                    "approval_mode, approval_ask_topics, computer, auto_review) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        bot_id,
                        user_id,
                        encrypt(draft.name, dek, user_aad(user_id, _NAME_AAD)),
                        _name_key(dek, draft.name),
                        encrypt(draft.job, dek, user_aad(user_id, _JOB_AAD)),
                        encrypt(draft.instructions, dek, user_aad(user_id, _INSTRUCTIONS_AAD)),
                        _avatar_dump(draft.avatar),
                        draft.template_id,
                        BotStatus.RESTING.value,
                        None,
                        now,
                        now,
                        NEW_BOT_APPROVAL_MODE,
                        "[]",
                        DEFAULT_COMPUTER,
                        int(NEW_BOT_AUTO_REVIEW),
                    ),
                )
                await db.commit()
            except aiosqlite.IntegrityError as exc:
                raise DuplicateBotName(f"A bot named '{draft.name}' already exists.") from exc

        return Bot(
            id=bot_id,
            user_id=user_id,
            name=draft.name,
            job=draft.job,
            instructions=draft.instructions,
            avatar=draft.avatar,
            template_id=draft.template_id,
            status=BotStatus.RESTING,
            model_override=None,
            created_at=now,
            updated_at=now,
            approval=DEFAULT_BOT_APPROVAL,
        )

    async def get(self, user_id: str, bot_id: str) -> Bot | None:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"SELECT {_SELECT_COLUMNS} FROM bots WHERE id = ? AND user_id = ?",
                (bot_id, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        dek = await get_user_dek(self._config, user_id)
        return _row_to_bot(row, dek)

    async def list(self, user_id: str) -> list[Bot]:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"SELECT {_SELECT_COLUMNS} FROM bots WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            )
            rows = await cursor.fetchall()
        if not rows:
            return []
        dek = await get_user_dek(self._config, user_id)
        return [_row_to_bot(row, dek) for row in rows]

    async def update(self, user_id: str, bot_id: str, patch: BotPatch) -> Bot | None:
        current = await self.get(user_id, bot_id)
        if current is None:
            return None

        dek = await get_user_dek(self._config, user_id)
        name = patch.name if patch.name is not None else current.name
        job = patch.job if patch.job is not None else current.job
        instructions = patch.instructions if patch.instructions is not None else current.instructions
        avatar = patch.avatar if patch.avatar is not None else current.avatar
        group = _next_group(current.group, patch.group)
        computer = patch.computer if patch.computer is not None else current.computer
        now = _now_iso()

        async with db_session(self._config) as db:
            kept = await _sealed_picture(db, user_id, bot_id)   # a new look keeps the bot's picture
            try:
                cursor = await db.execute(
                    "UPDATE bots SET name = ?, name_key = ?, job = ?, instructions = ?, "
                    "avatar = ?, group_label = ?, computer = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (
                        encrypt(name, dek, user_aad(user_id, _NAME_AAD)),
                        _name_key(dek, name),
                        encrypt(job, dek, user_aad(user_id, _JOB_AAD)),
                        encrypt(instructions, dek, user_aad(user_id, _INSTRUCTIONS_AAD)),
                        _avatar_dump(avatar, kept),
                        None if group is None else encrypt(group, dek, user_aad(user_id, _GROUP_AAD)),
                        computer,
                        now,
                        bot_id,
                        user_id,
                    ),
                )
                await db.commit()
            except aiosqlite.IntegrityError as exc:
                raise DuplicateBotName(f"A bot named '{name}' already exists.") from exc

        if cursor.rowcount == 0:
            return None

        return dataclasses.replace(
            current, name=name, job=job, instructions=instructions, group=group, computer=computer, updated_at=now,
            avatar=dataclasses.replace(avatar, picture=picture_tag(kept) if kept else None),
        )

    async def set_picture(self, user_id: str, bot_id: str, picture: Picture | None) -> Bot | None:
        """Put the bot's own picture on its screen, or take it off (``None``). The look stays."""
        current = await self.get(user_id, bot_id)
        if current is None:
            return None
        sealed = None if picture is None else seal_picture(picture, await get_user_dek(self._config, user_id), user_id)
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE bots SET avatar = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (_avatar_dump(current.avatar, sealed), _now_iso(), bot_id, user_id),
            )
            await db.commit()
        return await self.get(user_id, bot_id)

    async def get_picture(self, user_id: str, bot_id: str) -> Picture | None:
        async with db_session(self._config) as db:
            sealed = await _sealed_picture(db, user_id, bot_id)
        if sealed is None:
            return None
        return open_picture(sealed, await get_user_dek(self._config, user_id), user_id)

    async def delete(self, user_id: str, bot_id: str) -> bool:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "DELETE FROM bots WHERE id = ? AND user_id = ?", (bot_id, user_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def set_status(self, user_id: str, bot_id: str, status: BotStatus) -> None:
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE bots SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (status.value, _now_iso(), bot_id, user_id),
            )
            await db.commit()

    async def set_off_duty(self, user_id: str, bot_id: str, off_duty: bool) -> Bot | None:
        """Flip the durable Off duty flag (spec §4.2). An idle bot's status
        follows at once; a bot that is ``on_it`` keeps that status until its
        run ends, when ``TurnRunner._settle_status`` picks Off duty."""
        flag = int(off_duty)
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bots SET off_duty = ?, status = CASE "
                "WHEN ? = 1 AND status != 'on_it' THEN 'off_duty' "
                "WHEN ? = 0 AND status = 'off_duty' THEN 'resting' "
                "ELSE status END, updated_at = ? WHERE id = ? AND user_id = ?",
                (flag, flag, flag, _now_iso(), bot_id, user_id),
            )
            await db.commit()
        if cursor.rowcount == 0:
            return None
        return await self.get(user_id, bot_id)

    async def set_full_limit(self, user_id: str, bot_id: str, until: datetime | None) -> Bot | None:
        """Set (or clear, with ``None``) the end of the bot's full limit. Only the full-limit route calls this."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bots SET full_limit_until = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (None if until is None else until.astimezone(timezone.utc).isoformat(), _now_iso(), bot_id, user_id),
            )
            await db.commit()
        if cursor.rowcount == 0:
            return None
        return await self.get(user_id, bot_id)

    async def set_notify(self, user_id: str, bot_id: str, notify: bool) -> Bot | None:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bots SET notify = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (int(notify), _now_iso(), bot_id, user_id),
            )
            await db.commit()
        return None if cursor.rowcount == 0 else await self.get(user_id, bot_id)

    async def set_workspace_internet(self, user_id: str, bot_id: str, on: bool) -> Bot | None:
        """A4: Internet in the workspace. ``None`` when the bot is not the user's."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bots SET workspace_internet = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (int(on), _now_iso(), bot_id, user_id),
            )
            await db.commit()
        return None if cursor.rowcount == 0 else await self.get(user_id, bot_id)

    async def set_voice(self, user_id: str, bot_id: str, voice: VoiceSettings) -> Bot | None:
        """Voice: its voice, tone, speed and Read replies aloud. ``None`` when the bot is not the user's."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bots SET voice = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (voice_dump(voice), _now_iso(), bot_id, user_id),
            )
            await db.commit()
        return None if cursor.rowcount == 0 else await self.get(user_id, bot_id)

    async def set_approval(self, user_id: str, bot_id: str, approval: BotApproval, *,
                           auto_review: bool | None = None) -> Bot | None:
        """The mode and topics; ``auto_review`` (Full auto) only when given, else the stored value stays."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bots SET approval_mode = ?, approval_ask_topics = ?, auto_review = COALESCE(?, auto_review), "
                "updated_at = ? WHERE id = ? AND user_id = ?",
                (approval.mode, topics_json(approval.ask_topics), None if auto_review is None else int(auto_review),
                 _now_iso(), bot_id, user_id),
            )
            await db.commit()
        return None if cursor.rowcount == 0 else await self.get(user_id, bot_id)

    async def set_pinned(self, user_id: str, bot_id: str, pinned: bool) -> Bot | None:
        """Pin or unpin a bot. Pinning a pinned bot keeps its place in the order."""
        now = _now_iso()
        sql = (
            "UPDATE bots SET pinned = 1, pinned_at = COALESCE(pinned_at, ?), updated_at = ? WHERE id = ? AND user_id = ?"
            if pinned else
            "UPDATE bots SET pinned = 0, pinned_at = NULL, updated_at = ? WHERE id = ? AND user_id = ?"
        )
        params = (now, now, bot_id, user_id) if pinned else (now, bot_id, user_id)
        async with db_session(self._config) as db:
            cursor = await db.execute(sql, params)
            await db.commit()
        return None if cursor.rowcount == 0 else await self.get(user_id, bot_id)

    async def set_model(self, user_id: str, bot_id: str, model: str | None, effort: str | None) -> Bot | None:
        """Store the bot's model and effort (None clears each). The caller checks the values."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bots SET model_override = ?, effort = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (model, effort, _now_iso(), bot_id, user_id),
            )
            await db.commit()
        return None if cursor.rowcount == 0 else await self.get(user_id, bot_id)

    async def get_primary(self, user_id: str) -> Bot | None:
        async with db_session(self._config) as db:
            row = await (await db.execute(
                f"SELECT {_SELECT_COLUMNS} FROM bots WHERE user_id = ? AND is_primary = 1", (user_id,),
            )).fetchone()
        if row is None:
            return None
        return _row_to_bot(row, await get_user_dek(self._config, user_id))

    async def set_primary(self, user_id: str, bot_id: str) -> tuple[Bot, ...] | None:
        """Star ``bot_id`` as the main bot, moving the star off any other
        (D-B: at most one per user — ``idx_bots_one_primary`` enforces it).
        Returns every bot whose star changed, the newly starred one first;
        ``None`` if ``bot_id`` is not this user's."""
        if await self.get(user_id, bot_id) is None:
            return None
        previous = await self.get_primary(user_id)
        now = _now_iso()
        async with db_session(self._config) as db:
            try:
                await db.execute(
                    "UPDATE bots SET is_primary = 0, updated_at = ? WHERE user_id = ? AND is_primary = 1 AND id != ?",
                    (now, user_id, bot_id),
                )
                await db.execute(
                    "UPDATE bots SET is_primary = 1, updated_at = ? WHERE id = ? AND user_id = ?", (now, bot_id, user_id),
                )
                await db.commit()
            except aiosqlite.Error:
                await db.rollback()
                raise
        changed_ids = (bot_id,) if previous is None or previous.id == bot_id else (bot_id, previous.id)
        bots = [await self.get(user_id, changed_id) for changed_id in changed_ids]
        return tuple(bot for bot in bots if bot is not None)

    async def reset_on_boot(self, events: "EventHub | None" = None) -> int:
        """Move every ``ON_IT`` bot (across every user) back to ``RESTING``.

        Called once from the gateway's lifespan on startup. A bot left
        ``ON_IT`` across a restart means the server died mid-turn — there
        is no live run left to resume into, so it goes back to idle
        rather than staying stuck in a status that implies work is still
        happening. Returns the number of bots moved.

        Final review, finding 3: this used to update the DB silently. A
        client whose WS connection survives (or reconnects) across the
        restart never learned the bot was reset, and a resumed replay
        could leave a stale ``on_it`` frame (from before the restart)
        applied on top of a fresh snapshot. When ``events`` is given, a
        real ``bot_status`` RESTING event is published for each bot this
        actually resets (never for one that was already something else,
        like ``STUCK``) — the ``UPDATE ... RETURNING`` is what the DB
        itself resets, so there's no separate SELECT to race against it.
        """
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "UPDATE bots SET status = CASE WHEN off_duty = 1 THEN 'off_duty' ELSE 'resting' END, "
                "updated_at = ? WHERE status = ? RETURNING id, user_id, status",
                (_now_iso(), BotStatus.ON_IT.value),
            )
            rows = await cursor.fetchall()
            await db.commit()

        if events is not None:
            for row in rows:
                await events.publish(row["user_id"], {
                    "type": "bot_status", "bot_id": row["id"],
                    "status": row["status"], "activity": None,
                })
        return len(rows)
