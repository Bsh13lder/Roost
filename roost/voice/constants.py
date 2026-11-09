"""Voice's fixed values (docs/plans/2026-10-30-roost-voice.md): the voices, tones and speeds a bot can have, the size
caps, the pinned models and the words the routes show. Imported by the gateway and the voice service alike, so it
imports nothing but the standard library."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Speaker:
    id: str          # the speaking model's own speaker name
    name: str        # what the Info tab shows
    best_in: str     # the language it was made for; every voice speaks the others too


@dataclass(frozen=True)
class Tone:
    name: str
    instruct: str | None   # the words the speaking model gets; None: its own natural way


@dataclass(frozen=True)
class Language:
    id: str      # the short code stored and sent (BCP 47's language part)
    name: str    # what the picker shows
    asr: str     # the hearing model's own name for it (``config.support_languages``)


@dataclass(frozen=True)
class VoiceSettings:
    speaker: str
    tone: str
    speed: float
    read_aloud: bool   # a reply that arrives while its chat is open plays by itself
    # Correct what I say (voice tuning D3; §4's Correct my English before it): a spoken message gets a corrected
    # copy with the mistakes marked, in whatever language was spoken. Stored as ``correct_speech``; an old row's
    # ``correct_english`` reads into it, and both keys are written so an older client still sees the switch.
    correct_speech: bool = False
    # Voice tuning D2: the language the hearing model is told, or ``VOICE_LANGUAGE_AUTO`` to let it listen.
    language: str = "auto"

    @property
    def correct_english(self) -> bool:
        """The switch under its old name (§4's clients and tools)."""
        return self.correct_speech


SPEAKERS: Final = (
    Speaker("aiden", "Aiden", "English"),
    Speaker("ryan", "Ryan", "English"),
    Speaker("serena", "Serena", "Chinese"),
    Speaker("vivian", "Vivian", "Chinese"),
    Speaker("uncle_fu", "Uncle Fu", "Chinese"),
    Speaker("dylan", "Dylan", "Chinese (Beijing)"),
    Speaker("eric", "Eric", "Chinese (Sichuan)"),
    Speaker("ono_anna", "Ono Anna", "Japanese"),
    Speaker("sohee", "Sohee", "Korean"),
)
SPEAKER_IDS: Final = frozenset(s.id for s in SPEAKERS)

TONES: Final = {
    "natural": Tone("Natural", None),
    "calm": Tone("Calm", "Calm, relaxed and steady."),
    "warm": Tone("Warm", "Warm and friendly."),
    "cheerful": Tone("Cheerful", "Cheerful and bright."),
    "energetic": Tone("Energetic", "Energetic and lively."),
    "serious": Tone("Serious", "Serious and clear."),
    "gentle": Tone("Gentle", "Soft and gentle."),
    "excited": Tone("Excited", "Very happy and excited."),
}

SPEEDS: Final = (0.75, 0.9, 1.0, 1.15, 1.25, 1.5, 1.75, 2.0)   # the player's rate; it keeps the pitch

# Voice tuning D2: exactly the languages the pinned hearing model lists (measured 2026-11-06; Georgian is not one
# of them), the owner's two first and the rest by name. "auto" lets the model read the language itself.
VOICE_LANGUAGE_AUTO: Final = "auto"
VOICE_LANGUAGES: Final = (
    Language("en", "English", "English"),
    Language("es", "Spanish", "Spanish"),
    Language("ar", "Arabic", "Arabic"),
    Language("yue", "Cantonese", "Cantonese"),
    Language("zh", "Chinese", "Chinese"),
    Language("cs", "Czech", "Czech"),
    Language("da", "Danish", "Danish"),
    Language("nl", "Dutch", "Dutch"),
    Language("fil", "Filipino", "Filipino"),
    Language("fi", "Finnish", "Finnish"),
    Language("fr", "French", "French"),
    Language("de", "German", "German"),
    Language("el", "Greek", "Greek"),
    Language("hi", "Hindi", "Hindi"),
    Language("hu", "Hungarian", "Hungarian"),
    Language("id", "Indonesian", "Indonesian"),
    Language("it", "Italian", "Italian"),
    Language("ja", "Japanese", "Japanese"),
    Language("ko", "Korean", "Korean"),
    Language("mk", "Macedonian", "Macedonian"),
    Language("ms", "Malay", "Malay"),
    Language("fa", "Persian", "Persian"),
    Language("pl", "Polish", "Polish"),
    Language("pt", "Portuguese", "Portuguese"),
    Language("ro", "Romanian", "Romanian"),
    Language("ru", "Russian", "Russian"),
    Language("sv", "Swedish", "Swedish"),
    Language("th", "Thai", "Thai"),
    Language("tr", "Turkish", "Turkish"),
    Language("vi", "Vietnamese", "Vietnamese"),
)
VOICE_LANGUAGE_IDS: Final = frozenset(lang.id for lang in VOICE_LANGUAGES)
VOICE_LANGUAGE_BY_ID: Final = {lang.id: lang for lang in VOICE_LANGUAGES}
VOICE_LANGUAGE_AUTO_NAME: Final = "Auto-detect"

DEFAULT_VOICE: Final = VoiceSettings(speaker="aiden", tone="natural", speed=1.0, read_aloud=False)

# What you say: a WAV of PCM 16-bit mono, at most this long. 48 kHz for two minutes is the largest body.
VOICE_MAX_SECONDS: Final = 120
VOICE_RATE_MIN: Final = 8000
VOICE_RATE_MAX: Final = 48000
VOICE_WAV_BYTES_MAX: Final = VOICE_RATE_MAX * 2 * VOICE_MAX_SECONDS + 1024

# What a bot says: a reply's words, capped, spoken in parts of at most this many characters, one request per part.
VOICE_TEXT_CHARS_MAX: Final = 4000
VOICE_PART_CHARS_MAX: Final = 300
VOICE_CODE_WORDS: Final = "(code)"
VOICE_SAMPLE_TEXT: Final = "Hi! This is how I sound. Pick the voice you like best."

# The voice service (roost/voice_host/): its models, fetched once at these revisions into ~/Roost/voice-models.
VOICE_HEAR_MODEL: Final = "mlx-community/Qwen3-ASR-0.6B-8bit"
VOICE_HEAR_REVISION: Final = "89e96d92ba34aca20b3e29fb10cc284097d1219f"
VOICE_SPEAK_MODEL: Final = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
VOICE_SPEAK_REVISION: Final = "049ef77fe8816b536193c0c25f9a214d17921282"
VOICE_IDLE_UNLOAD_S: Final = 1800.0     # a model not used for this long leaves memory
VOICE_SERVICE_TIMEOUT_S: Final = 180.0  # the gateway's wait; a first use loads a model
VOICE_HEAR_TIMEOUT_S: Final = 30.0      # the gateway's wait for a transcript once the service is warm
VOICE_HEALTH_TIMEOUT_S: Final = 3.0
VOICE_HEALTH_CACHE_S: Final = 30.0
VOICE_CACHE_PARTS: Final = 48           # spoken parts and fixed lines the gateway keeps in memory for a replay
VOICE_SECRET_FILE: Final = "voice.secret"
VOICE_MODES: Final = ("service", "fake")   # ROOST_VOICE: the Mac's voice service, or FakeVoice (tests, E2E)

VOICE_OFF_TEXT: Final = "Voice isn't running on your Mac yet."
VOICE_FAILED_TEXT: Final = "Voice couldn't do that just now. Try again."
VOICE_BUSY_TEXT: Final = "Still working on your last recording."
VOICE_BAD_AUDIO_TEXT: Final = "That recording couldn't be read."
VOICE_NOT_SPOKEN_TEXT: Final = "This message has nothing to read aloud."

# Call mode (§3): a client beats the thread's call every VOICE_CALL_HEARTBEAT_S; a call with no beat for
# VOICE_CALL_EXPIRES_S is over. The models are kept resident by a warm at most once per VOICE_WARM_KEEP_S.
VOICE_CALL_HEARTBEAT_S: Final = 20.0
VOICE_CALL_EXPIRES_S: Final = 60.0
VOICE_WARM_KEEP_S: Final = 240.0
VOICE_TRACK_KEEP_S: Final = 600.0       # a reply's speak-ahead track is dropped this long after it opened
# Speak-ahead: the first part is cut at a clause past this many characters, so the first sound comes in a second or two.
VOICE_FIRST_PART_CHARS_MAX: Final = 120
VOICE_FIRST_PART_CUTS: Final = ",;:"
VOICE_LIVE_TYPE: Final = "speech_ready"
# The fixed spoken lines a call plays in the bot's voice (never user words), by key.
VOICE_LINES: Final = {
    "greeting": "Hi, I'm listening.",
    "bye": "Bye for now.",
    "not_caught": "Sorry, I didn't catch that.",
    "still_on_it": "Still on it.",
    "asking": "I need a yes or no from you.",
    "say_again": "Say that again?",
}
VOICE_LINE_CACHE_KEY: Final = "line"

# §4 Correct my English (owner, 2026-10-31: "I want my words transcribed, corrected, and shown where I made
# mistakes"): a spoken message's correction by the worker model, in the background, as one ``english_fix`` line.
VOICE_CORRECT_TIMEOUT_S: Final = 30.0    # background only; Haiku once took 9.9 s (owner, 2026-11-03)
VOICE_CORRECT_AGENT: Final = "english-correct"
VOICE_CORRECT_FIXES_MAX: Final = 12
VOICE_CORRECT_FIX_CHARS_MAX: Final = 60
VOICE_CORRECT_TEXT_CHARS_MAX: Final = 4000      # a spoken message longer than this is not corrected
ENGLISH_FIX_KIND: Final = "english_fix"          # the stored kind stays (rows and clients read it)
ENGLISH_FIX_PREVIEW: Final = "Corrected what you said"
VOICE_CORRECT_UNCHANGED_TEXT: Final = "Nothing to correct."

# Voice tuning D1 (docs/plans/2026-11-06-roost-voice-tuning.md): the context the hearing model reads before it
# writes — names and site names, bounded and sanitised (roost/voice/envelope.py) — and how it is built
# (roost/voice/context.py) and carried (the /hear envelope).
HEAR_CONTEXT_LEAD: Final = "Names and words that may be said:"
VOICE_CONTEXT_TERMS_MAX: Final = 80
VOICE_CONTEXT_TERM_CHARS_MIN: Final = 2
VOICE_CONTEXT_TERM_CHARS_MAX: Final = 40
VOICE_CONTEXT_CHARS_MAX: Final = 900
VOICE_HEAR_HINT_BYTES_MAX: Final = 8192          # the hint's JSON in the envelope, at most
VOICE_CONTEXT_RECENT_MESSAGES: Final = 40        # your own newest messages in the bot's chat the names are read from
VOICE_CONTEXT_MEMORY_TERMS_MAX: Final = 30       # proper nouns taken from your memories, at most
VOICE_CONTEXT_CACHE_S: Final = 60.0              # a bot's hint is remembered this long (the live partials reuse it)
VOICE_HEAR_FALLBACK_S: Final = 300.0             # an old voice service with no /hear: /transcribe for this long
# Voice tuning D4: live words while recording — the whole buffer so far, every VOICE_PARTIAL_EVERY_MS, while it is
# at most VOICE_PARTIAL_MAX_S long (both clients mirror these).
VOICE_PARTIAL_EVERY_MS: Final = 1000
VOICE_PARTIAL_MAX_S: Final = 30
VOICE_PARTIAL_WAV_BYTES_MAX: Final = VOICE_RATE_MAX * 2 * VOICE_PARTIAL_MAX_S + 1024
# The fixed site names every hint carries (the owner's sites and the common ones), and the city.
COMMON_SITE_NAMES: Final = (
    "Google", "Gmail", "WhatsApp", "YouTube", "Upwork", "ALSA", "Renfe", "Amazon", "LinkedIn", "Instagram",
    "Facebook", "Telegram", "Slack", "Notion", "GitHub", "Booking", "Airbnb", "Idealista", "Wallapop", "Bizum",
    "Revolut", "PayPal", "Stripe", "Fiverr", "Zoom", "Google Meet", "Google Drive", "Dropbox", "Netflix", "Spotify",
    "TikTok", "Obsidian", "Roost", "Madrid",
)

# §4 set_my_voice: the bot changes only its own voice settings when the user asks.
SET_MY_VOICE_TOOL: Final = "set_my_voice"
VOICE_CHANGED_LINE: Final = "Changed my voice"
VOICE_CHANGE_TITLE: Final = "Change my voice"
VOICE_CHANGING_ACTIVITY: Final = "changing my voice"
