"""The accept rules for a bot's live screen (Computers 2.0, C1, Task 9; live control's Task 6, D1 and D6).

``WS /api/bots/{id}/live`` accepts first and then closes with a specific code, so the browser always gets a real
close frame with a reason it can show. ``live_refusal`` checks, in this order: Roost's own Origin (4403), this
Mac (4403), a signed-in user (4401), a bot of that user's (4404), a known mode (4400), and, for ``control``, a
held lock for this bot (4409).

Nothing here reads, logs or keeps what a user types or sees.
"""

from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass
from typing import Literal

from fastapi import WebSocket

from roost.bots.models import Bot
from roost.config import RoostConfig
from roost.constants import (
    LIVE_CLOSE_NOT_FOUND,
    LIVE_CLOSE_NOT_HELD,
    LIVE_CLOSE_PROTOCOL,
    LIVE_CLOSE_REFUSED,
    LIVE_CLOSE_UNAUTHENTICATED,
    LIVE_FORWARDED_HEADERS,
    LIVE_LOOPBACK_HOSTS,
    LIVE_TAILNET_NETWORKS,
    LIVE_VIEWERS_MAX,
)
from roost.db.connection import ensure_initialized
from roost.gateway.auth import SESSION_COOKIE_NAME, get_session_user

NOT_THIS_MAC_REASON = "Live control works only on this Mac for now."
ORIGIN_REASON = "Origin not allowed."
SIGN_IN_REASON = "Sign in first."
NOT_FOUND_REASON = "Bot not found"
NOT_HELD_REASON = "Take control first."
GIVEN_BACK_REASON = "Given back."
ASLEEP_REASON = "asleep"
TOO_MANY_REASON = "The screen is open in too many tabs."
PROTOCOL_REASON = "The screen sent something Roost doesn't understand."
UNAVAILABLE_REASON = "The bot's computer stopped answering."

LiveMode = Literal["view", "control"]
_MODES: tuple[LiveMode, ...] = ("view", "control")


@dataclass(frozen=True)
class Refusal:
    code: int
    reason: str


_TAILNET_NETWORKS = tuple(ipaddress.ip_network(net) for net in LIVE_TAILNET_NETWORKS)


def _is_tailnet_address(text: str) -> bool:
    try:
        address = ipaddress.ip_address(text.strip())
    except ValueError:
        return False
    return any(address in net for net in _TAILNET_NETWORKS)


def forwarded_from_tailnet(websocket: WebSocket, config: RoostConfig) -> bool:
    """True for the owner's phone through `tailscale serve`: only X-Forwarded-For, every hop a Tailscale address,
    and the Origin one of the tailnet origins (ROOST_EXTRA_ORIGINS). Funnel or any other proxy stays refused."""
    headers = websocket.headers
    if "forwarded" in headers or "x-real-ip" in headers:
        return False
    hops = headers.get("x-forwarded-for", "").split(",")
    return (headers.get("origin") in config.tailnet_origins
            and all(_is_tailnet_address(hop) for hop in hops))


def peer_is_this_mac(websocket: WebSocket, config: RoostConfig) -> bool:
    """True for a loopback peer, or any peer in the gateway container (compose publishes its port on the
    Mac's 127.0.0.1 alone). A forwarded request is this Mac only when it comes from the owner's tailnet."""
    if any(header in websocket.headers for header in LIVE_FORWARDED_HEADERS):
        if not forwarded_from_tailnet(websocket, config):
            return False
    if config.in_container:
        return True
    client = websocket.client
    return client is not None and client.host in LIVE_LOOPBACK_HOSTS


async def live_refusal(
    websocket: WebSocket, bot_id: str, mode_text: str,
) -> tuple[Bot, LiveMode] | Refusal:
    """The bot and mode when the socket may go on, else the ``Refusal`` to close with."""
    config: RoostConfig = websocket.app.state.config
    if websocket.headers.get("origin") not in config.allowed_origins:
        return Refusal(LIVE_CLOSE_REFUSED, ORIGIN_REASON)
    if not peer_is_this_mac(websocket, config):
        return Refusal(LIVE_CLOSE_REFUSED, NOT_THIS_MAC_REASON)
    await ensure_initialized(config)
    session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    user = await get_session_user(config, session_id) if session_id else None
    if user is None:
        return Refusal(LIVE_CLOSE_UNAUTHENTICATED, SIGN_IN_REASON)
    bot = await websocket.app.state.bots.get(user.id, bot_id)
    if bot is None:
        return Refusal(LIVE_CLOSE_NOT_FOUND, NOT_FOUND_REASON)
    if mode_text not in _MODES:
        return Refusal(LIVE_CLOSE_PROTOCOL, PROTOCOL_REASON)
    mode: LiveMode = "control" if mode_text == "control" else "view"
    if mode == "control" and websocket.app.state.control.held(bot.id) is None:
        return Refusal(LIVE_CLOSE_NOT_HELD, NOT_HELD_REASON)
    return bot, mode


class LiveViewers:
    """How many live sockets a bot has open: ``LIVE_VIEWERS_MAX`` view sockets and one control socket."""

    def __init__(self) -> None:
        self._open: dict[tuple[str, LiveMode], int] = {}
        self._kicks: dict[str, asyncio.Event] = {}

    def enter(self, bot_id: str, mode: LiveMode) -> bool:
        key = (bot_id, mode)
        count = self._open.get(key, 0)
        if count >= (LIVE_VIEWERS_MAX if mode == "view" else 1):
            return False
        self._open = {**self._open, key: count + 1}
        return True

    def claim_control(self, bot_id: str) -> asyncio.Event:
        """A new control socket replaces the old one: the old one's event is set, so it closes 4000."""
        previous = self._kicks.get(bot_id)
        if previous is not None:
            previous.set()
        mine = asyncio.Event()
        self._kicks = {**self._kicks, bot_id: mine}
        return mine

    def release_control(self, bot_id: str, mine: asyncio.Event) -> None:
        if self._kicks.get(bot_id) is mine:
            self._kicks = {k: v for k, v in self._kicks.items() if k != bot_id}

    def leave(self, bot_id: str, mode: LiveMode) -> None:
        key = (bot_id, mode)
        count = self._open.get(key, 0)
        if count <= 1:
            self._open = {k: v for k, v in self._open.items() if k != key}
        else:
            self._open = {**self._open, key: count - 1}
