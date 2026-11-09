"""The Plan slice of a bot's instructions (design 4.3): today and tomorrow, clean items only."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from test_plan_store import bot, cfg, service, user_id  # noqa: F401  (fixtures)

from roost.constants import PLAN_PROMPT_ITEMS
from roost.plan.prompt import plan_section

NOW = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)   # Madrid: 2026-10-22 10:00


async def test_the_prompt_shows_today_and_tomorrow_clean_items_only(user_id, bot, service):
    body = ("- [ ] today thing ⏰ 11:00 📅 2026-10-22 🆔 aaaaaa\n- [ ] tomorrow thing 📅 2026-10-23 🆔 bbbbbb\n"
            "- [ ] later 📅 2026-10-30 🆔 cccccc\n- [x] finished ✅ 2026-10-22 📅 2026-10-22 🆔 dddddd\n"
            "- [ ] <b>evil</b> & co 📅 2026-10-22 🆔 eeeeee\n- [ ] undated 🆔 ffffff\n")
    plan = await service.put_text(user_id, bot.id, body, base_revision=1)
    await service.bot_add(user_id, bot.id, text="web said do x", date="2026-10-22", run_key="r", tainted=True)
    shown = await service.items_for_prompt(user_id, bot.id)
    assert [i.id for i in shown.items] == ["aaaaaa", "eeeeee", "bbbbbb"]
    assert shown.hidden == 1
    text = plan_section(shown)
    assert text.startswith("Your Plan for today and tomorrow")
    assert "today thing" in text and "tomorrow thing" in text and "later" not in text and "finished" not in text
    assert "&lt;b&gt;evil&lt;/b&gt; &amp; co" in text and "<b>" not in text
    assert "1 more from outside content; use plan_read" in text
    assert "web said do x" not in text
    assert plan.revision == 2


async def test_the_prompt_is_capped_and_empty_plans_say_nothing(user_id, bot, service):
    assert plan_section(await service.items_for_prompt(user_id, bot.id)) is None
    many = "".join(f"- [ ] t{i} 📅 2026-10-22\n" for i in range(PLAN_PROMPT_ITEMS + 5))
    await service.put_text(user_id, bot.id, many, base_revision=1)
    shown = await service.items_for_prompt(user_id, bot.id)
    assert len(shown.items) == PLAN_PROMPT_ITEMS
