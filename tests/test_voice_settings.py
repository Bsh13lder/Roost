"""Voice tuning (docs/plans/2026-11-06-roost-voice-tuning.md D2, D3): a bot's voice language (Auto-detect or one of
the hearing model's 30) and Correct what I say (``correct_speech``), stored in the same ``bots.voice`` JSON with no
schema bump; ``correct_english`` stays an alias both ways so an older row, client or phone build keeps working."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from roost.voice.constants import (
    DEFAULT_VOICE, VOICE_LANGUAGE_AUTO, VOICE_LANGUAGE_IDS, VOICE_LANGUAGES, VoiceSettings,
)
from roost.voice.settings import (
    BAD_LANGUAGE_TEXT, VoiceIn, VoicePatch, apply_patch, check_language, voice_dict, voice_dump, voice_load,
)

# What mlx-community/Qwen3-ASR-0.6B-8bit lists in its config.support_languages (measured 2026-11-06).
MODEL_LANGUAGES = {
    "Chinese", "English", "Cantonese", "Arabic", "German", "French", "Spanish", "Portuguese", "Indonesian", "Italian",
    "Korean", "Russian", "Thai", "Vietnamese", "Japanese", "Turkish", "Hindi", "Malay", "Dutch", "Swedish", "Danish",
    "Finnish", "Polish", "Czech", "Filipino", "Persian", "Greek", "Romanian", "Hungarian", "Macedonian",
}


def test_the_language_list_is_exactly_what_the_hearing_model_supports():
    assert {lang.asr for lang in VOICE_LANGUAGES} == MODEL_LANGUAGES
    assert len({lang.id for lang in VOICE_LANGUAGES}) == len(VOICE_LANGUAGES) == 30
    assert "ka" not in VOICE_LANGUAGE_IDS and "Georgian" not in {lang.name for lang in VOICE_LANGUAGES}
    assert VOICE_LANGUAGE_AUTO not in VOICE_LANGUAGE_IDS            # auto is a choice, not a language
    assert [lang.id for lang in VOICE_LANGUAGES[:2]] == ["en", "es"]   # the owner's languages first


def test_the_defaults_are_auto_detect_and_no_correction():
    assert DEFAULT_VOICE.language == VOICE_LANGUAGE_AUTO
    assert DEFAULT_VOICE.correct_speech is False and DEFAULT_VOICE.correct_english is False


def test_an_old_row_reads_its_english_switch_as_the_general_one():
    old = json.dumps({"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False, "correct_english": True})
    loaded = voice_load(old)
    assert loaded.correct_speech is True and loaded.correct_english is True
    assert loaded.language == VOICE_LANGUAGE_AUTO
    new = json.dumps({"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False,
                      "correct_speech": True, "language": "es"})
    assert voice_load(new) == VoiceSettings("aiden", "natural", 1.0, False, True, "es")


def test_the_new_key_wins_over_the_alias_when_both_are_stored():
    both = json.dumps({"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False,
                       "correct_speech": False, "correct_english": True})
    assert voice_load(both).correct_speech is False


def test_a_language_off_the_list_reads_as_the_defaults():
    bad = json.dumps({"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False, "language": "ka"})
    assert voice_load(bad) == DEFAULT_VOICE


def test_the_dump_writes_both_keys_so_an_older_client_still_reads_the_switch():
    settings = VoiceSettings("ryan", "calm", 1.0, True, True, "es")
    data = voice_dict(settings)
    assert data == {"speaker": "ryan", "tone": "calm", "speed": 1.0, "read_aloud": True, "correct_speech": True,
                    "correct_english": True, "language": "es"}
    assert voice_load(voice_dump(settings)) == settings


def test_check_language_takes_auto_or_a_listed_id():
    assert check_language("auto") == "auto" and check_language("es") == "es"
    with pytest.raises(ValueError, match=BAD_LANGUAGE_TEXT):
        check_language("Georgian")


def test_voice_in_takes_either_name_for_the_switch_and_the_language():
    base = {"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False}
    assert VoiceIn(**base).patch() == VoicePatch(speaker="aiden", tone="natural", speed=1.0, read_aloud=False)
    assert VoiceIn(**base, correct_english=True).patch().correct_speech is True
    assert VoiceIn(**base, correct_speech=True).patch().correct_speech is True
    assert VoiceIn(**base, correct_speech=False, correct_english=True).patch().correct_speech is False
    assert VoiceIn(**base, language="fr").patch().language == "fr"
    with pytest.raises(ValidationError):
        VoiceIn(**base, language="ka")
    with pytest.raises(ValidationError):
        VoiceIn(**base, correct_speech="yes")


def test_a_patch_changes_only_the_fields_it_names():
    patched = apply_patch(DEFAULT_VOICE, VoicePatch(language="es"))
    assert patched.language == "es" and patched.correct_speech is False and patched.speaker == "aiden"
    assert apply_patch(patched, VoicePatch(correct_speech=True)).language == "es"
    assert VoicePatch(correct_speech=True, language="en").fields() == {"correct_speech": True, "language": "en"}
