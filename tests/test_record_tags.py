"""The tag rules for what a bot writes (obsidian track, part 1)."""

from __future__ import annotations

import pytest

from roost.constants import MAX_BOT_TOPIC_TAGS
from roost.tags.rules import (
    bot_tag, is_system_tag, keep_system_tags, obsidian_tag, project_tag, record_tags, slug, topic_tags,
)


def test_slug_folds_accents_spaces_and_symbols():
    assert slug("Nota Bené: Café!") == "nota-bene-cafe"
    assert slug("  ") == "untitled"
    assert len(slug("x" * 200)) <= 40


def test_topic_tags_drop_the_hash_fold_case_and_repeat_once():
    assert topic_tags(["#Home", "home", "garden/roses", "to_do-2"]) == ("home", "garden/roses", "to_do-2")
    assert topic_tags(["", "  "]) == ()


@pytest.mark.parametrize("bad", ["two words", "bot:me", "émoji🙂", "-lead", "x" * 33])
def test_topic_tags_refuse_what_is_not_one_word(bad):
    with pytest.raises(ValueError, match="one word"):
        topic_tags([bad])


def test_topic_tags_refuse_more_than_a_few():
    with pytest.raises(ValueError, match=str(MAX_BOT_TOPIC_TAGS)):
        topic_tags([f"t{i}" for i in range(MAX_BOT_TOPIC_TAGS + 1)])


def test_bot_and_project_tags():
    assert bot_tag("Penny Pincher", "b1234567-aaaa") == "bot:penny-pincher"
    assert bot_tag(None, "b1234567-aaaa") == "bot:b1234567"
    assert project_tag("Garden 2026") == "project:garden-2026"


def test_record_tags_put_the_bot_then_the_project_then_the_topics():
    tags = record_tags(bot_name="Ana", bot_id="b", project_name="Home", topics=("home", "chores"))
    assert tags == ("bot:ana", "project:home", "home", "chores")
    assert record_tags(bot_name="Ana", bot_id="b", project_name=None, topics=()) == ("bot:ana",)


def test_system_tags_survive_a_new_set_of_topics():
    assert is_system_tag("bot:ana") and is_system_tag("project:x") and not is_system_tag("home")
    assert keep_system_tags(("bot:ana", "old"), ("new",)) == ("bot:ana", "new")


def test_obsidian_tags_hold_no_colon():
    assert obsidian_tag("bot:ana") == "bot/ana"
    assert obsidian_tag("Two Words") == "two-words"
    assert obsidian_tag("#home") == "home"
    assert obsidian_tag("!!") is None
