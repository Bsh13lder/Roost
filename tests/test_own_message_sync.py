"""Your own message is published as a ``message`` frame (owner, 2026-10-25: a message sent from the Mac didn't show
on the phone and the other way round), so every open web page and phone shows it at once."""

from __future__ import annotations

import httpx

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from team_helpers import GatedModel, frames_so_far, wait_idle
from test_reactions import BOT, _user_ids
from test_threads_api import O


async def test_your_message_is_published_to_your_other_screens():
    await init_db(load_config())
    app = create_app()
    app.state.turns._model = GatedModel(["hello"], hold=())
    mac = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await mac.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await mac.post("/api/bots", json=BOT, headers=O)).json()["id"]
    thread_id = (await mac.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
    phone = app.state.events.subscribe(next(iter(await _user_ids())))

    sent = (await mac.post(f"/api/threads/{thread_id}/messages", json={"text": "from the Mac"}, headers=O)).json()
    await wait_idle(app.state.turns)

    mine = [f for f in await frames_so_far(phone)
            if f["type"] == "message" and f["message"]["id"] == sent["message_id"]]
    assert len(mine) == 1
    frame = mine[0]
    assert frame["thread_id"] == thread_id
    assert (frame["message"]["role"], frame["message"]["body"]) == ("user", "from the Mac")
    await mac.aclose()
