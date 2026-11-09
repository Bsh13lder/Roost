"""@mentions are matched to member bots and bound to their ids (D-E)."""

from __future__ import annotations

from roost.bots.models import Avatar, Bot, BotStatus
from roost.rooms.mentions import MentionResult, parse_mentions, route_targets

_AVATAR = Avatar("round", "#22c55e", "none")


def _bot(bot_id: str, name: str) -> Bot:
    return Bot(id=bot_id, user_id="u", name=name, job="j", instructions="", avatar=_AVATAR, template_id=None,
               status=BotStatus.RESTING, model_override=None, created_at="t", updated_at="t")


SCOUT, SCOUT_TWO, QUILL = _bot("s", "Scout"), _bot("s2", "Scout Two"), _bot("q", "Quill")
MEMBERS = (SCOUT, SCOUT_TWO, QUILL)


def test_a_mention_is_case_insensitive_and_bound_to_the_id():
    assert parse_mentions("hey @scout, prices?", MEMBERS) == MentionResult(everyone=False, bot_ids=("s",))


def test_the_longest_matching_name_wins():
    assert parse_mentions("@Scout Two please", MEMBERS).bot_ids == ("s2",)
    assert set(parse_mentions("@Scout and @Scout Two", MEMBERS).bot_ids) == {"s", "s2"}


def test_emails_longer_words_and_non_members_are_not_mentions():
    assert parse_mentions("mail me@scout.com", MEMBERS).bot_ids == ()
    assert parse_mentions("@Scouting ahead", MEMBERS).bot_ids == ()
    assert parse_mentions("@Wren?", MEMBERS).bot_ids == ()


def test_a_mention_may_end_a_sentence():
    assert parse_mentions("ask @Quill.", MEMBERS).bot_ids == ("q",)


def test_everyone():
    assert parse_mentions("@everyone what do you think?", MEMBERS).everyone is True


def test_routing():
    assert route_targets(MentionResult(True, ()), MEMBERS, "q") == ("s", "s2", "q")
    assert route_targets(MentionResult(False, ("q",)), MEMBERS, "s") == ("q",)
    assert route_targets(MentionResult(False, ()), MEMBERS, "q") == ("q",)
    assert route_targets(MentionResult(False, ()), MEMBERS, None) == ("s",)
