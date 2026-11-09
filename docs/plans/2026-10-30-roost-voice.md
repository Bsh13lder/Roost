# Roost voice: speak to a bot, hear it answer

Owner, 2026-10-30: "speak agent or send voice … whisper or something new small amazing … give me several voices and
tones and speed change". The owner accepted the plan of a small ear and a small voice on this Mac with Claude as the
brain in between, and lifted the v1 freeze for voice. A Roost keyboard was declined for now (an Android keyboard sees
every password typed anywhere); a "Talk to Chief" tile and Talk mode come after this plan.

## 1. What was tried on this Mac (Apple M2, 16 GB, 2026-10-30)

| Job | Model (Hugging Face, pinned revision) | Licence | Result |
|---|---|---|---|
| Hearing | `mlx-community/Qwen3-ASR-0.6B-8bit` @ `89e96d92ba34aca20b3e29fb10cc284097d1219f` | Apache-2.0 | 4.6 s of English in 2.0 s, 8 s of Spanish in 0.6 s, both word-perfect |
| Speaking | `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit` @ `049ef77fe8816b536193c0c25f9a214d17921282` | Apache-2.0 | about 1.7× faster than real time; peak memory about 5 GB while speaking |

Both run through `mlx-audio==0.6.3` (MIT; its 40 packages are MIT, BSD, Apache, ISC, MPL, PSF, CNRI, Zlib, CC0, MIT-0;
nothing GPL). Ruled out: Kokoro (needs espeak-ng, GPL-3 — breaks the licence rule), Parakeet and Canary (CC-BY-4.0),
Voxtral TTS (CC-BY-NC), Supertonic (OpenRAIL-M), Moonshine Spanish (revenue-limited licence), Fish Speech and F5-TTS
(non-commercial), Moshi and Qwen3-Omni (7B/30B, and they would replace Claude as the brain).

The speaking model has nine built-in voices (`serena`, `vivian`, `uncle_fu`, `ryan`, `aiden`, `ono_anna`, `sohee`,
`eric`, `dylan`), takes a tone as words (`instruct`, e.g. "Calm and warm."), and reads the language itself
(`language="auto"`). Speed is the player's: the web's `playbackRate` and the phone's `setSpeed` keep the pitch.

## 2. Pieces

**V1 — the voice service** (`roost/voice_host/`, a host process like the keeper; MLX can't use the Apple GPU from
Docker). FastAPI on **127.0.0.1:18804** only, every request HMAC-signed with `<data>/voice.secret` (its own secret, not
the keeper's: the voice service never holds power over computers). Routes:

- `GET /health` → `{"ok": true, "loaded": [...]}` (signed too).
- `POST /transcribe`, body a WAV (PCM 16-bit mono, 8–48 kHz, at most `VOICE_MAX_SECONDS` = 120 s) → `{"text"}`.
- `POST /speak`, JSON `{text, speaker, tone}` (text at most `VOICE_PART_CHARS_MAX`, speaker and tone from the fixed
  lists; the tone's words come from the fixed table, never from the request) → `audio/wav`.

Each model is loaded on first use, one job at a time (a lock; the work runs in a thread), and unloaded after
`VOICE_IDLE_UNLOAD_S` (10 min) idle. Models live in `~/Roost/voice-models` (`HF_HOME`), fetched once at the pinned
revisions. Audio and text are never written to disk or logged; the log keeps sizes and times. Tests use a fake
engine; the real one is imported only inside the service. Installed by `make voice-install` into its own
`~/Roost/voice-venv` (Roost's wheel with `--no-deps`, plus pinned `mlx-audio`, `fastapi`, `uvicorn`, `pydantic`) as the
launchd agent `app.roost.voice`.

**V2 — the gateway** (`roost/voice/`):

- `VoiceClient` signs and calls the service (`ROOST_VOICE_URL`, default `http://127.0.0.1:18804`;
  `host.docker.internal:18804` in compose). A service that can't be reached is "Voice isn't running on your Mac yet."
- `speech_parts(text)`: a message's words for speaking (markdown → plain, links as their words, a code block as "(code)",
  at most `VOICE_TEXT_CHARS_MAX`), split on sentence ends into parts of at most `VOICE_PART_CHARS_MAX`.
- Schema **v37** `bots.voice`: JSON `{"speaker","tone","speed","read_aloud"}` (fixed ids and a number, no user words,
  like the avatar JSON); NULL means the defaults (`aiden`, `natural`, 1.0, off).
- Routes:
  - `GET /api/voice` → `{available, speakers:[{id,name,best_in}], tones:[{id,name}], speeds:[...]}`.
  - `PUT /api/bots/{id}/voice` → the bot (owner only, validated).
  - `POST /api/voice/transcribe` (Origin checked, raw `audio/wav`, size and header checked at the gateway too,
    one at a time per user) → `{text}`.
  - `GET /api/threads/{thread_id}/messages/{message_id}/speech` → `{parts, speed}`; `…/speech/{part}` → `audio/wav`
    in the bot's voice. Only the owner's thread, only a bot's text message (a 404 otherwise). A small in-memory cache
    keeps the last few parts made.
  - `GET /api/bots/{id}/voice/sample?speaker=&tone=` → a fixed sample line, for trying a voice.
- What you say becomes text in the composer, and Send sends it as your own message — your own words, so it is trusted
  like typing.

**V3 — web**: a mic in the composer (tap to start, tap to stop; WAV made in the browser, 16 kHz mono), a speaker button
on each bot reply (plays its parts in order at the bot's speed; tap again stops), and a Voice fold on the Info tab:
Voice, Tone, Speed, Try it, and "Read replies aloud" (a reply that arrives while that chat is open plays by itself).

**V4 — phone**: the same — mic in the composer (`record`, WAV), speaker on replies (`just_audio` with `setSpeed`), the
Voice section on Info, and Read replies aloud.

**Later**: Talk mode (speak, hear, speak again), a "Talk to Chief" quick tile, cloned voices (the Base model).

## 3. Call mode (owner, 2026-10-30: "call doesn't work, it's a little late … make the voice things perfect")

The call is the flow warm → listen → transcribe → send as your own message → the bot's reply spoken → listen
again. What made it late: nothing was spoken until the whole reply was stored and a 300-character part synthesised,
the "On it: …" lead was spoken too, every turn waited the 1.5 s steer debounce, and each request to the voice
service opened a new connection. This section is the shared contract the server, the web and the phone follow;
names are exact. The gateway and the voice service go live only after the owner's `make up` and
`make voice-update`.

### A. Call registry (server, in memory, no schema change) — `roost/voice/calls.py`

- `CallRegistry` on `app.state.calls`: frozen `CallSession(thread_id, bot_id, user_id, started_at, beat_at,
  interrupted: str | None)`; `active(thread_id)` (a beat within `VOICE_CALL_EXPIRES_S`), `get`, `beat(user_id,
  thread_id, bot_id)`, `end(thread_id)`, `interrupt(thread_id, message_id)`.
- `POST /api/threads/{thread_id}/call` (Origin-checked, owner only; 404 for another user's or an unknown thread;
  409 for a room): body `{}`, nothing, or `{"interrupted": "<message_id>"}` → `{"ok": true, "expires_in": 60}`.
  Starts the call or beats it. Clients call it when the call screen opens, then every `VOICE_CALL_HEARTBEAT_S` =
  20 s, and with `interrupted` when the user cuts the bot off (the speak-ahead stops that reply). The route also
  keeps the voice models resident: it kicks `voice.warm()` as a tracked background task at most once per
  `VOICE_WARM_KEEP_S` = 240 s.
- `DELETE /api/threads/{thread_id}/call` → `{"ok": true}` (idempotent; the thread's speak-ahead tracks go).
- `POST /api/threads/{thread_id}/messages` takes `"call": true` (optional, default false; `MessageCreate.call`):
  it beats the registry before the message is queued. The response shape is unchanged. Clients send every call
  turn with `call: true`.
- Effects of an active call on the thread's runs (server only): no steer debounce before a new run on your
  messages (`StopFlow.debounce`); `RunInputs.call = True`; in a run of your own message outside a room the prompt
  swaps the chat rules for the voice section and the model is `resolve_call_model(...)`; the memory capture after
  the run is a tracked background task (`TurnRunner._background`), not awaited by the drain loop.

### B. Speak-ahead (server) — `roost/voice/sentences.py`, `roost/voice/speak_ahead.py`

- While a call is active on a thread, `SpeakAhead` (an `EventHub` listener) splits the reply's streamed text
  (`text_delta` frames) into sentence parts and synthesises each finished sentence at once into
  `app.state.voice_cache` under the same key shape as `/speech`: `(message_id, part, speaker, tone)`. Part 0 is
  cut at `, ; :` when its sentence passes `VOICE_FIRST_PART_CHARS_MAX` = 120 (even while the sentence is still
  open), so the first sound comes in a second or two; later parts are one sentence each, at most
  `VOICE_PART_CHARS_MAX` = 300 (a long one cut at words). A sentence is closed by its terminator (`.!?…。！？`)
  followed by whitespace; the open tail is spoken only at `message_done`. The split is prefix-stable: parts
  already numbered never change when more text arrives. The "On it: …" lead is never spoken (the split waits for
  the lead's line end), and `speech_words` drops emoji and a table's rule rows.
- `message_id` is the placeholder id clients receive in the `message` frame (role `bot`, `seq` 0) right after
  their send; the same id carries `text_delta` and `message_done`.
- Frame after each part is cached: `{"type": "speech_ready", "thread_id", "message_id", "part": <int>, "done":
  false}`; once more after the last part with `"done": true` (`part` is then the last index, -1 when no part was
  made). It is live only (not stored, not replayed). Clients ignore `speech_ready` for any message that is not the
  reply of their current call turn.
- `GET /api/threads/{thread_id}/live-speech/{message_id}` → `{"parts": <ready count>, "done": <bool>, "speed":
  <float>}`; 404 when the id is not a reply made in a call on this thread of yours. Polling fallback: at most
  every 400 ms.
- `GET /api/threads/{thread_id}/live-speech/{message_id}/{part}` → `audio/wav`, `Cache-Control: no-store`; 404
  until that part is ready (clients retry on the next `speech_ready` or poll).
- A reply spoken through live-speech is never also fetched through `/speech` by the call; `/speech` stays for
  Read aloud and the speaker button, and strips the "On it: …" lead (`shown_reply`) and emoji too.
- The spoken text in a call is exactly what the live-speech parts contain; captions use the client's own
  `shownReply(streaming text)` and need no server field.

### C. Fixed spoken lines (server) — `roost/voice/constants.py`

- `VOICE_LINES = {"greeting": "Hi, I'm listening.", "bye": "Bye for now.", "not_caught": "Sorry, I didn't catch
  that.", "still_on_it": "Still on it.", "asking": "I need a yes or no from you.", "say_again": "Say that
  again?"}` (fixed text only, never user words).
- `GET /api/bots/{bot_id}/voice/line/{key}` → `audio/wav` in the bot's voice (speaker and tone from
  `bots.voice`), 404 for an unknown key or another user's bot; cached in memory under `("line", key, speaker,
  tone)` (`VOICE_CACHE_PARTS` is 48 so lines are not evicted by parts).
- `POST /api/voice/warm` accepts an optional body `{"bot_id": "<id>"}` (an empty body or `{}` still works) →
  `{"ok": true}`; with `bot_id` it also pre-makes the six lines for that bot's voice after the models load
  (a tracked background task, never delaying the response).
- Clients: greeting plays once when warm resolves (not before the mic opens); `not_caught` when a transcript is
  empty; `asking` when the bot parks on a card; `say_again` on a transcribe failure; `still_on_it` when thinking
  passes `CALL_STILL_ON_IT_AFTER_S` = 15 s with no `text_delta` yet (then every 30 s, at most 3 times); `bye`
  before ending on a goodbye word. Service-off and mic-denied stay text only.

### D. Goodbye words (both clients, pure, identical sets) — `web/src/lib/callWords.ts`, `mobile/lib/call/call_words.dart`

`isGoodbye(text)`: true only when the whole utterance, lower-cased, trimmed, punctuation stripped, is one of
`bye`, `goodbye`, `bye bye`, `hang up`, `end call`, `end the call`, `that's all`, `that is all`, `adiós`,
`adios`, `hasta luego`, `cuelga`, `chao`. Never a substring match. A goodbye is not sent as a message.

### E. Endpointer constants, mirrored on both clients (web `ENDPOINT_DEFAULTS` in `web/src/lib/endpointer.ts`; phone the `endpointer*` consts in `mobile/lib/call/endpointer.dart`)

| Value | Setting |
|---|---|
| frame | 20 ms |
| `endSilenceMs` | 700 |
| `startMs` | 120 (300 while guarded) |
| `minSpeechMs` | 350 |
| `maxMs` | 30000 |
| `prerollMs` | 300 |
| start threshold | the running floor + 10 dB, never below -50 dBFS (web: never below 0.01 RMS) |
| end threshold | lower than start (hysteresis) |
| floor | frozen while guarded |
| `SPEAKER_TAIL_MS` | 300: the wait before re-arming after the bot's speech |
| `CALL_HEARING_TIMEOUT_S` | 20 |
| `CALL_THINKING_TIMEOUT_S` | 120 |

### F. Models and prompt (server only) — `roost/llm/registry.py`, `roost/voice/prompt.py`

- `CALL_MODEL = HAIKU.id`; `resolve_call_model(override, extra_ids)` returns the bot's pickable override when set,
  else `CALL_MODEL`. Used only when `RunInputs.call` is true and the run was started by the user's own message
  outside a room.
- `voice_section()` replaces `chat_feel_section()` in `build_instructions(..., spoken=True)`: "You are on a voice
  call: the user hears you and does not read. Answer in one to three short spoken sentences in plain words; no
  lists, headings, links, code or markdown; name a site instead of pasting an address; say numbers, dates and
  times the way you would aloud, in Madrid time; when you must look something up, first say in one short sentence
  what you are doing, then do it." `DONE_RULE` and `TIME_RULE` stay; `FIRST_LINE_RULE`, `LENGTH_RULE`,
  `LINK_RULE` and the typed answer style ("… link it") are left out.

### G. Other server constants (`roost/voice/constants.py`)

`VOICE_CALL_HEARTBEAT_S = 20.0`, `VOICE_CALL_EXPIRES_S = 60.0`, `VOICE_FIRST_PART_CHARS_MAX = 120`,
`VOICE_HEAR_TIMEOUT_S = 30.0` (a transcript's wait once the service has been seen warm, else the long
`VOICE_SERVICE_TIMEOUT_S`), `VOICE_IDLE_UNLOAD_S = 1800.0`, `VOICE_WARM_KEEP_S = 240.0`, `VOICE_TRACK_KEEP_S =
600.0` (a reply's speak-ahead track is dropped after this, or on call end).

### Server details

- `VoiceClient` keeps one `httpx.AsyncClient` for the whole process (closed by `aclose()` in the app's
  lifespan); its health check reads `loaded` and `warm`.
- The voice service hears and speaks at the same time (`hear_job` and `speak_job` locks; warm takes both),
  `/health` answers without any lock and adds `"warm"`, and the `roost.voice.timing` logger keeps heard/spoke/warm
  durations and sizes at INFO whatever the log level (never a word of what was heard or said).
- The system prompt's time line is rounded to the minute, so the prompt's prefix is the same across a run's steps.
- Deferred: streaming TTS inside the service (the parts already give the first sound in a second or two), cloned
  voices, Talk to Chief.

## 4. Correct my English, a bot's own voice settings, and the crashed tab (owner, 2026-10-31)

> Since 2026-11-06 this is **Correct what I say** (any language, the hearing context's names, numbers as digits,
> checked before the send): `docs/plans/2026-11-06-roost-voice-tuning.md` D3. The setting is stored as
> `correct_speech`, `correct_english` stays its alias, and the `english_fix` line keeps its kind and body.

The owner's English is not perfect: "I want my words transcribed, corrected, and shown where I made mistakes in the
sentence", and "let the bot control bot settings too". Separately, Gela's Linux computer OOM-killed its Brave tab
while opening WhatsApp Web; the tab never answered CDP again and `open_page` said the browser "did not answer".
Server parts below; the web and phone parts follow the same contract.

### A. The setting — `roost/voice/constants.py`, `roost/voice/settings.py`

`VoiceSettings.correct_english: bool = False`, stored inside the existing `bots.voice` JSON (schema v37, no bump; an
old row without the key reads False). `GET /api/bots/{id}` carries it under `"voice"`. `PUT /api/bots/{id}/voice`
takes it as optional (`VoiceIn.correct_english`, the stored switch stays when absent). Every change goes through
`VoicePatch` → `apply_patch` and the one `VoiceSettingsService.save` (`roost/voice/service.py`), which stores and
publishes `bot_updated`; the route and the bot's own tool share it, so the lists are checked in one place
(`check_speaker` / `check_tone` / `check_speed`). The Info tab's switch reads "Correct my English" with the hint
"Shows a corrected copy of what you say, with your mistakes marked."

### B. Spoken messages — `POST /api/threads/{thread_id}/messages`

`MessageCreate.spoken: bool = False`: the text came from the voice service (every call turn, along with `call`, and
a dictation sent unedited). The response shape is unchanged; the bot's run always gets the user's ORIGINAL words.

### C. The correction — `roost/voice/correct.py`

With `spoken` and the bot's `correct_english` on, `EnglishCorrector.spawn` runs a background job on
`app.state.voice_tasks` after the message is stored and published (never delaying the response or the run). It asks
the worker model (Haiku, `make_worker_model`; agent `VOICE_CORRECT_AGENT = "english-correct"`) with the words as
escaped data inside `<said>` and no tools, for strict JSON `{"corrected", "fixes": [{"wrong", "right"}]}`: grammar,
word choice and spelling only, same meaning and language, no rephrasing for style, at most
`VOICE_CORRECT_FIXES_MAX = 12` fixes of at most `VOICE_CORRECT_FIX_CHARS_MAX = 60` characters, `"fixes": []` when the
sentence is fine. `parse_correction` validates it with pydantic; any failure, a timeout
(`VOICE_CORRECT_TIMEOUT_S = 8.0`) or no change (the same words back) posts nothing. A real change stores ONE
`english_fix` activity line in the same thread (role `activity`, body sealed JSON
`{"message_id", "said", "corrected", "fixes"}`, `author_bot_id` the bot) and publishes it as a normal `message`
frame. The line is not a model kind (never replayed), is skipped by the chat-list queries (`PREVIEW_SKIPPED_KINDS`;
its preview words are "Corrected your English" if ever asked), is never read aloud (not a bot reply) and never
tainted. Scripted mode: `ScriptedWorker` corrects a few fixed mistakes ("I has goed" → "I went", "dont", "teh", …),
so the E2E and `make e2e`'s gateway can show the line.

### D. `set_my_voice` — `roost/voice/tool_specs.py`, `roost/voice/tools.py`

Every bot has it (`VOICE_TOOL_DEFS`, kind `write_change`, topic `team`, `ToolDef.own_settings=True`; never a
helper's). Optional fields `speaker` (one of `SPEAKER_IDS`), `tone` (one of `TONES`), `speed` (one of `SPEEDS`),
`read_aloud`, `correct_english`; at least one. It changes ONLY the calling bot's settings through
`VoiceSettingsService`, so open clients refresh the bot from the same `bot_updated` frame and a call in progress
speaks its next part in the new voice (`SpeakAhead._on_bot_updated`; each ready part remembers the voice it was made
in, `ReplyTrack.part_voices`, so earlier parts still play). The gate (`_own_settings_verdict`): no card in a run the
owner's own message started in their 1:1 chat that has read no outside content (`owner_chat` and clean, or
`site_fresh`), whatever the mode; anywhere else (tainted, a routine, a handoff, a room) an ordinary Ask card
(`hard_floor`), or `needs_your_ok` where none can open — on a rig with no approval state too: only your own 1:1
chat ever changes a bot's settings with no card.
Words: plain step "Changed my voice", card title "Change my voice", activity "changing my voice", result
"Changed my voice: speed 1.5, tone Warm.". The prompt gains one line in the call's `voice_section()` and in every
run's instructions (`VOICE_SETTINGS_TEXT`): the user can ask you to speak slower or faster, change your voice or
tone, turn reading replies aloud on or off, or turn English correction on or off; use `set_my_voice` and confirm in
one short sentence.

### E. Crashed tab recovery — `roost/desk/crash.py`, `roost/desk/browser.py`, `roost/desk/page_keeping.py`

`CrashWatch` tells a crashed tab from a slow one: `Inspector.targetCrashed` seen on the bot's session (the page
sends `Inspector.enable` on attach and keeps a standing listener), or a `Runtime.evaluate("1")` probe that fails or
gets no answer within `CDP_CRASH_PROBE_TIMEOUT_S = 3.0`. When a page command fails (`CdpReplyError`, not a gone
session) and the tab crashed, `PageKeeping._healing` has the page close that target (`Target.closeTarget`), open a
fresh tab (`Target.createTarget`, attached and guarded the normal way) at the same address (read from the browser's
`Target.getTargetInfo`) and runs the call once more; a `PageText` from that read carries `notice =
CRASHED_TAB_RECOVERED_TEXT` and the tool result starts with it: "The page had crashed (the computer ran low on
memory), so I opened it again in a new tab." If the fresh tab fails too, `PageKeepsCrashing` (a `DeskUnavailable`)
says "The page keeps crashing on this computer; it may need more memory." instead of "unavailable". While you hold
the computer (Take control) no tab is closed or opened again under you: the command's failure stays what it was.
The worker's reply is read back through `html.unescape`, since the words went in escaped. Constants in
`roost/constants.py`; `COMPUTER_MEMORY` is unchanged.

Tests: `tests/test_voice_correct.py`, `tests/test_voice_tool.py`, `tests/test_desk_crash.py`, and the updated
`tests/test_voice_api.py`.
