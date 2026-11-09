"""``GET /api/usage?days=N`` and ``GET /api/bots/{id}/usage?days=N``: per bot and per day token totals, a grand
total, the busiest bot; another user's bot is a 404; ``days`` is 1 to 90."""

from __future__ import annotations

from roost.constants import USAGE_RETIRED_BOT_NAME
from roost.llm.types import Usage
from roost.usage.report import user_report, window
from roost.usage.store import UsageRow
from roost.usage.counts import UsageTotals
from money_http import O, two_users
from test_threads_api import VALID_AVATAR

BOT = {"name": "Scout", "job": "looks around", "instructions": "", "avatar": VALID_AVATAR}


async def _me(client) -> str:
    return (await client.get("/api/auth/me")).json()["id"]


def test_window_is_oldest_first_and_ends_today():
    assert window("2026-11-04", 3) == ("2026-11-02", "2026-11-03", "2026-11-04")


def test_user_report_names_a_retired_bot_and_picks_the_busiest():
    rows = (UsageRow("2026-11-04", "gone", "chat", "m", UsageTotals(input=50, calls=1)),
            UsageRow("2026-11-03", "b1", "chat", "m", UsageTotals(input=10, output=5, calls=1)),
            UsageRow("2026-11-04", None, "background", "m", UsageTotals(input=7, calls=1)),
            UsageRow("2026-10-01", "b1", "chat", "m", UsageTotals(input=999, calls=1)))   # outside the window
    out = user_report(rows, today="2026-11-04", days=7, names={"b1": "Scout"})
    assert out["total"]["tokens"] == 72 and out["today_total"]["tokens"] == 57
    assert [b["name"] for b in out["bots"]] == [USAGE_RETIRED_BOT_NAME, "Scout"]
    assert out["busiest"] == {"bot_id": "gone", "name": USAGE_RETIRED_BOT_NAME, "tokens": 50}
    assert out["background"]["total"]["tokens"] == 7
    assert len(out["per_day"]) == 7 and out["per_day"][-1]["day"] == "2026-11-04"


def test_user_report_with_nothing_has_no_busiest():
    out = user_report((), today="2026-11-04", days=7, names={})
    assert out["busiest"] is None and out["bots"] == [] and out["total"]["tokens"] == 0


async def test_the_routes_sum_per_bot_and_day_and_keep_users_apart():
    async with two_users() as (alice, bob, app):
        bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
        me = await _me(alice)
        store = app.state.token_usage
        await store.add(me, bot_id, "chat", "claude-sonnet-5-5", Usage(input=100, output=20, cache_read=5))
        await store.add(me, bot_id, "helper", "claude-haiku-5-5", Usage(input=10, output=2))
        await store.add(me, None, "background", "claude-haiku-5-5", Usage(input=3))
        out = (await alice.get("/api/usage")).json()
        assert out["readable"] is False and out["days"] == 7 and len(out["per_day"]) == 7
        assert out["total"] == {"input": 113, "output": 22, "cache_read": 5, "cache_write": 0, "calls": 3,
                                "tokens_in": 118, "tokens_out": 22, "tokens": 140}
        assert out["today_total"]["tokens"] == 140
        assert out["bots"][0]["bot_id"] == bot_id and out["bots"][0]["name"] == "Scout"
        assert out["bots"][0]["total"]["tokens"] == 137 and out["background"]["total"]["tokens"] == 3
        assert out["busiest"] == {"bot_id": bot_id, "name": "Scout", "tokens": 137}
        one = (await alice.get(f"/api/bots/{bot_id}/usage?days=3")).json()
        assert one["bot_id"] == bot_id and one["days"] == 3 and len(one["per_day"]) == 3
        assert one["total"]["tokens"] == 137 and one["per_day"][-1]["tokens"] == 137
        # bob sees none of it, and alice's bot is a 404 for him
        theirs = (await bob.get("/api/usage")).json()
        assert theirs["total"]["tokens"] == 0 and theirs["bots"] == [] and theirs["busiest"] is None
        assert (await bob.get(f"/api/bots/{bot_id}/usage")).status_code == 404


async def test_days_must_be_between_1_and_90():
    async with two_users() as (alice, _bob, _app):
        bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
        assert (await alice.get("/api/usage?days=90")).status_code == 200
        for bad in ("0", "91", "x"):
            assert (await alice.get(f"/api/usage?days={bad}")).status_code == 422
            assert (await alice.get(f"/api/bots/{bot_id}/usage?days={bad}")).status_code == 422


async def test_the_routes_need_a_session():
    async with two_users() as (alice, _bob, app):
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as anon:
            assert (await anon.get("/api/usage")).status_code == 401
            assert (await anon.get("/api/bots/x/usage")).status_code == 401


async def test_a_chat_message_shows_up_in_the_usage():
    """End to end on the scripted gateway: your message runs, and its tokens count for the bot as chat."""
    import asyncio

    async with two_users() as (alice, _bob, app):
        bot_id = (await alice.post("/api/bots", json=BOT, headers=O)).json()["id"]
        thread_id = (await alice.post(f"/api/bots/{bot_id}/threads", json={}, headers=O)).json()["id"]
        await alice.post(f"/api/threads/{thread_id}/messages", json={"text": "hello"}, headers=O)
        for _ in range(100):
            one = (await alice.get(f"/api/bots/{bot_id}/usage")).json()
            if one["total"]["calls"] >= 1:
                break
            await asyncio.sleep(0.05)
        assert one["total"]["tokens"] > 0
