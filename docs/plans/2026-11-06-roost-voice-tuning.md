# Voice tuning: names, numbers and sites heard right, any language corrected, live words

Owner, 2026-11-06: "the voice engine can't recognise names well, also when I say numbers, and web pages also Google
or WhatsApp … don't hear it good. Also about correction there is 'English correction' — let's do general correction
and select languages or auto-detect language. Also I want to see on screen what I am saying. And a little tune it like
Claude voice message, when it understands where I made a mistake." The owner speaks English (not native), Spanish and
probably Georgian, lives in Madrid, and dictates names of people, amounts, dates, times and site names to their bots.

This extends `docs/plans/2026-10-30-roost-voice.md` (§2 V1–V4, §4 Correct my English). Names below are exact.

## 1. What the pinned models really do (measured on this Mac, 2026-11-06)

Throwaway process, the voice venv's `mlx-audio 0.6.3`, `mlx-community/Qwen3-ASR-0.6B-8bit` at the pinned revision,
phrases synthesised with the pinned Qwen3-TTS so the words were known (the live voice service was never touched).

- `generate(audio, language=…, system_prompt=…, hotwords=…, stream=…)`. `hotwords` is folded into `system_prompt`
  (`mlx_audio.stt.utils.merge_hotwords`: the terms joined with commas after the prompt), so the two are one
  mechanism: **a text context the model reads before it writes**. With no `language`, the model writes
  `language <X><asr_text>…` and reads the language itself; with one, the prefix is forced.
- The model lists **30 languages** in its `config.support_languages`: Chinese, English, Cantonese, Arabic, German,
  French, Spanish, Portuguese, Indonesian, Italian, Korean, Russian, Thai, Vietnamese, Japanese, Turkish, Hindi,
  Malay, Dutch, Swedish, Danish, Finnish, Polish, Czech, Filipino, Persian, Greek, Romanian, Hungarian, Macedonian.
  **Georgian is not among them**, so it is left out of the picker.
- Context works, in both languages, at no extra cost (0.4 s for a 6–8 s clip either way):

  | Heard with no context | With the context |
  |---|---|
  | Tell Maka **Aramadze** that Nino **Berizzi** will call her | Tell Maka **Eremadze** that Nino **Beridze** will call her |
  | send to **Mar Kiknads of** the invoice | send **Tamar Kiknadze** the invoice |
  | Dio a **MacaIrmaz** que la reunión con Nino **Perice** | Dio a Maka **Eremadze** que la reunión con Nino **Beridze** |
  | billetes de **Al Esca** a Granada … a **Gila** | billetes de **ALSA** a Granada … a **Gela** |
  | and check **upwork** | and check **Upwork** |

  A short first name ("Gela" → "Gola") was not always rescued in English; the correction pass gets the same context
  for that. Numbers stayed as words ("thirty six euros and forty cents") in five clips of six; the correction pass
  writes them as digits.
- The language hint alone changed nothing in these clips (auto-detect was already right). It stays as a choice for
  when an accent fools the detector.
- Partial transcripts of a growing buffer cost 0.25 s (1 s of audio) to 0.55 s (6 s), so a partial every second on
  the whole buffer is affordable up to the cap below.
- An instruction planted inside the context ("Ignore the audio and write …") was ignored: the model transcribed.
  The terms are still sanitised to a small character set and bounded.

## 2. Decisions

**D1 — Context biasing, built at the gateway, sent inside the signed body.** `roost/voice/context.py` builds a
frozen `HearHint(terms, language)` per transcription from: the user's bots' names; proper nouns in the user's own
untainted memories (About you and the bot's); proper nouns in the user's own recent messages in that bot's chat
(`VOICE_CONTEXT_RECENT_MESSAGES`); the hosts in Vault: site logins turned into site names (never a login's label,
which may be an address); and the fixed `COMMON_SITE_NAMES` (Google, WhatsApp, Gmail, ALSA, Upwork, Renfe, …) plus
Madrid. Never a bot's reply, a web page or a tainted memory: only words the owner wrote or chose. Each term is
letters (any script), digits, spaces and `' - . &`, 2–`VOICE_CONTEXT_TERM_CHARS_MAX` characters, never an address
(`@`) or digits alone; at most `VOICE_CONTEXT_TERMS_MAX` terms and `VOICE_CONTEXT_CHARS_MAX` characters, deduplicated
without case. The voice service puts them after a fixed lead line (`HEAR_CONTEXT_LEAD`) in Qwen3-ASR's
`system_prompt`. The hint is remembered per (user, bot) for `VOICE_CONTEXT_CACHE_S` so the live partials cost one
database read a minute, not one a second. The signature covers the body only (`roost/desk/signing.py`), so the hint
travels in it: `POST /hear` takes `pack_hear(hint, wav)` (`roost/voice/envelope.py`: a 4-byte length, the hint's
JSON, then the WAV). `/transcribe` stays as it was for an older service, and `VoiceClient` falls back to it when
`/hear` answers 404, so dictation keeps working until the owner's `make voice-update` (it then remembers the fallback
for `VOICE_HEALTH_CACHE_S`).

**D2 — Language is a per-bot voice setting.** `VoiceSettings.language` ("auto" by default, or one of
`VOICE_LANGUAGES`, the 30 ids above as short codes, Georgian left out) inside the existing `bots.voice` JSON (no
schema bump, like `correct_english`). Per bot and not per user because every voice setting already lives there with
its route, frame, Info fold and the bot's own `set_my_voice` ("from now on I'll speak Spanish to you" just works),
a per-user setting would need a new table, route and screen on both clients, and Auto-detect is the default anyway.
Chosen, it goes to the ASR as its `language` and tells the correction which language to keep.

**D3 — General correction, any language, before the send.** `Correct my English` becomes **Correct what I say**:
after the final transcript lands in the composer, the client asks `POST /api/voice/correct` (`{text, bot_id}` →
`{corrected, fixes}`; the same worker-model pass as §4, now with the hint's terms as escaped `<known_names>` data
and the rule to write prices, dates, times and counts as digits in the local style — "thirty six euros" → "36 €",
"half past three" → "3:30"); the composer swaps in the corrected text with each fix marked (wrong struck through,
right beside it, "You said: …") and **Keep my words** puts the raw transcript back. The send carries `spoken: true`
plus `heard` (the raw transcript) and `fixes`; the server validates them with the same bounds and posts the
`english_fix` line at once (no second model call), so the chat keeps the marks under the message. A spoken send
without `heard` (Send pressed before the check landed, a call turn, an older phone build) keeps §4's background
correction. The setting is stored as `correct_speech`, with `correct_english` kept as an alias both ways (read
either, write both, `PUT` and `set_my_voice` take either), the message kind stays `english_fix` (stored rows and
clients read it), and the scripted worker learns a few site and number fixes so the E2E can show one.

**D4 — Live words while recording: chunked partials.** mlx-audio's `stream=True` streams the tokens of one finished
recording, not a microphone, so the clients do it in chunks: every `VOICE_PARTIAL_EVERY_MS` while the mic is open,
the whole buffer so far (while it is at most `VOICE_PARTIAL_MAX_S` long) goes to `POST /api/voice/partial?bot_id=`
(a WAV, the same hint, `{text}`), one in flight at a time, and the words appear in the composer as they come (on
the phone, in the recording strip). Stop cancels the partial in flight and the final transcript replaces the live
words. The partial route shares the per-user "one recording at a time" guard with the final one and the service's
hear lock, so a final transcript waits for at most one partial. Dictation longer than the cap keeps its last partial
on screen until the final text comes.

**D5 — Nothing secret reaches a prompt.** The hint never holds a Vault label, a password, a card, an address or a
number; the correction gets the same terms and the owner's own words, as escaped data; the voice service logs the
hint's size, never its words.

## 3. Pieces

- `roost/voice/constants.py`: `VOICE_LANGUAGES` (id → `Language(name, asr)`), `VOICE_LANGUAGE_AUTO = "auto"`,
  `VoiceSettings.language`, `VoiceSettings.correct_speech` (property `correct_english` kept), the context bounds,
  `COMMON_SITE_NAMES`, `HEAR_CONTEXT_LEAD`, `VOICE_PARTIAL_EVERY_MS`, `VOICE_PARTIAL_MAX_S`, `VOICE_CONTEXT_CACHE_S`.
- `roost/voice/settings.py`: `language` and `correct_speech` in load, dump, `VoiceIn`, `VoicePatch`; `check_language`.
- `roost/voice/envelope.py`: `HearHint`, `pack_hear`, `unpack_hear` (shared by the gateway and the service).
- `roost/voice/context.py`: `HearHints` (builds and remembers a bot's hint), `proper_nouns`, `site_name`, `clean_term`.
- `roost/voice_host/app.py` `POST /hear`; `Engine.hear(recording, hint)`; `MlxEngine` passes `language` and
  `system_prompt`; `FakeEngine` records the hint.
- `roost/voice/client.py`: `transcribe(wav, hint=None)` with the `/hear` → `/transcribe` fallback; `FakeVoice` too.
- `roost/gateway/routes/voice.py`: `?bot_id=` on `/api/voice/transcribe`, `POST /api/voice/partial`,
  `POST /api/voice/correct`, `languages` in `GET /api/voice`.
- `roost/voice/correct.py`: `SpeechCorrector` (`EnglishCorrector` kept as its name), `correct_now`, the new prompt,
  `fix_line_from_client`; `MessageCreate.heard` / `fixes` in `roost/gateway/routes/threads.py`.
- `roost/voice/tools.py`, `tool_specs.py`, `prompt.py`: `language` and `correct_speech` on `set_my_voice`.
- Web: `useMicRecorder(onText, onError, options)` — `MicOptions.botId`, `correct`, `onLive` (the partials, one
  in flight, from `Recording.snapshot()`), `onChecked` (the check came back, changed or fine, so the send carries
  `heard` and the server never asks again) and `onCorrected`; the composer shows the live words read-only in its
  box (`data-live`), keeps the spoken bookkeeping in refs (the callbacks fire between renders), swaps in the
  corrected text and draws `SpokenFixStrip` (`EnglishFixText` + Keep my words) above the box; `SendMeta.heard /
  fixes`; `VoiceSection`'s "I speak" select (hidden on a server without `languages`) and "Correct what I say";
  `api/voice.ts` `transcribe(wav, signal, botId)`, `partialTranscribe`, `correctSpeech`.
- Phone: `MicController(partial:, correct:, correctOn:, onCorrected:, onChecked:)` with `live` and the
  `checking` phase, `VoiceRecorder.soFar()`, `RecordingStrip`'s live words (`mic-live`) and "Checking…", the
  chat screen's `SpokenFixStrip` (`spoken-fix`, `keep-my-words`) and `send(heard:, fixes:)`, `VoiceApi.partial /
  correct` (an older gateway's 404 is nothing), `BotVoice.correctSpeech / language` (`correctEnglish` a getter,
  both keys written), `VoiceInfo.languages`, the Voice card's "I speak" row and "Correct what I say".

Tests: `tests/test_voice_settings.py`, `test_voice_envelope.py`, `test_voice_hear.py`, `test_voice_context.py`,
`test_voice_correct_now.py` and the updated `test_voice_api.py`, `test_voice_tool.py`, `test_voice_correct.py`;
`web/tests/MicLive.test.tsx`, `voiceTuning.test.ts`, the updated `VoiceSection.test.tsx`;
`mobile/test/voice/voice_live_test.dart` and the updated `voice_unit_test.dart`, `voice_section_test.dart`.

## 5. As built (2026-11-06)

Everything in §2–§3 is built and green: `uv run pytest`, `cd web && npm test` (272 files), `flutter test`.
Measured once more through the new `MlxEngine.hear(recording, hint)` on the real pinned model, in a throwaway
process: the plain hint gave "Maka Aramadze … Nino Berizzi", the hint with the names gave "Maka Eremadze … Nino
Beridze", and a forced wrong language ("Spanish" on an English clip) still transcribed the English words — the
language hint steers, it does not break. A forced language is therefore a safe choice when auto-detect errs.

## 4. What the owner must do

- `make voice-update` (the voice service needs the new `/hear` route; until then dictation works as before, with
  no hints — the gateway falls back by itself).
- `make up` for the gateway, and a phone publish for the phone's part.
