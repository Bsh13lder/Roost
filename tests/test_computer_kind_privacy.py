"""The computer kind is a setting, not part of a bot's prompt, roster or shared Template."""

from __future__ import annotations


from roost.bots.models import Avatar, Bot, BotStatus
from roost.bots.template_file import template_file_for
from roost.talk.instructions import Teammate, build_instructions

_AVATAR = Avatar("round", "#22c55e", "none")


def _bot(computer: str, *, primary: bool = False) -> Bot:
    return Bot(
        id="id-1", user_id="u", name="Scout", job="read the news", instructions="be brief", avatar=_AVATAR,
        template_id=None, status=BotStatus.RESTING, model_override=None,
        created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:00+00:00",
        computer=computer, is_primary=primary,
    )


def test_the_computer_kind_never_reaches_a_prompt_or_template():
    mates = (Teammate(name="Mia", job="keeps the books", off_duty=False),)
    for kind in ("linux", "mac_brave"):
        bot = _bot(kind, primary=True)
        prompt = build_instructions(bot, teammates=mates, can_create=True)
        assert "mac_brave" not in prompt and "linux" not in prompt.lower()
        shared = template_file_for(bot).model_dump_json()
        assert "mac_brave" not in shared and "linux" not in shared and "computer" not in shared
