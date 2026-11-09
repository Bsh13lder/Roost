"""The one model registry: bot models, the Haiku worker, and resolution."""

from __future__ import annotations

from roost.llm.registry import (
    BOT_MODELS,
    DEFAULT_BOT_MODEL,
    FABLE,
    HAIKU,
    OPUS,
    SONNET,
    WORKER,
    resolve_bot_model,
)


def test_bots_choose_fable_sonnet_opus_or_haiku_and_default_to_sonnet():
    assert BOT_MODELS == (FABLE, SONNET, OPUS, HAIKU)
    assert DEFAULT_BOT_MODEL == SONNET.id


def test_haiku_is_the_worker_and_also_a_bot_model():
    assert WORKER == HAIKU.id
    assert HAIKU in BOT_MODELS


def test_resolve_falls_back_to_the_default_for_unknown_and_takes_haiku():
    assert resolve_bot_model(None) == DEFAULT_BOT_MODEL
    assert resolve_bot_model("claude-nope-9") == DEFAULT_BOT_MODEL
    assert resolve_bot_model(HAIKU.id) == HAIKU.id
    assert resolve_bot_model(OPUS.id) == OPUS.id


def test_resolve_accepts_a_seen_model():
    seen = "claude-opus-6-0"
    assert resolve_bot_model(seen) == DEFAULT_BOT_MODEL
    assert resolve_bot_model(seen, frozenset({seen})) == seen
