# Replies: reply quotes, structured instructions and "Update my instructions?"

Track "replies" (2026-10-22). Functionality first; the web gets only what the owner needs to use it.

## What

1. **Reply quotes.** You can reply to one message in a bot's chat. Your message keeps a link to it and a short
   quote made by the server (the first `REPLY_QUOTE_CHARS` = 120 characters of the quoted message, as words: a
   Report quotes its headline, never its JSON). The bot reads your message as
   `(replying to: <quote>)` + your words, the quote escaped as data. A quote of a message from web content keeps
   that mark: your message then counts as tainted for the run that reads it (`_starts_tainted`), and once it ages
   out of the chat (Amendment A1, `CHAT_TAINT_KEEP`) the quote is replaced by the placeholder line.
2. **Structured instructions.** `roost/bots/instruction_sections.py` turns free text into five Markdown sections
   in a fixed order: *Who you are and context · What you do · Rules · Tone · Team*. Headings it knows (and
   `Label: text` lines) are sorted into place, other text goes under *What you do*, lines that start with
   Never / Always / Don't / Do not go under *Rules*, and an empty section gets one short default line. It is
   idempotent and never passes `MAX_BOT_INSTRUCTIONS_LENGTH` (defaults go first, then the plain text is kept as
   it was). `create_bot` and `POST /api/bots` (the New bot form) store the structured text; `PATCH` (your own
   edit) stores what you typed.
3. **"Update my instructions?" card.** `propose_instructions_update(new_text, why)` is every bot's tool for its
   own instructions only. It writes nothing: it stores a sealed proposal (before, after, why) and posts an
   `instructions_proposal` card in the bot's chat with a line diff. Only your Accept (optionally with your edited
   text) writes the instructions through `BotStore.update` and publishes `bot_updated`; Decline closes it. A run
   that read web content may still propose, but the card is marked *from web content* (and *from a routine* for a
   routine's run). Accept is a compare-and-swap on the instructions the card was made from (422 when they
   changed). One open proposal per bot.

## Schema (one migration, the next version)

- `messages.reply_to` (TEXT, a message id in the same thread and user), `messages.reply_quote` (enc:v2,
  `messages:reply_quote`), `messages.reply_tainted` (INTEGER 0/1).
- `instruction_proposals`: id, user_id, bot_id, payload (enc:v2 `instruction_proposals:payload`, JSON
  `{before, after, why}`), tainted, from_routine, state (`open | accepted | declined`), thread_id, message_id,
  created_at, decided_at. Index on (user_id, state, created_at).

## Routes and tools

- `POST /api/threads/{id}/messages` takes `reply_to` (optional). An id that is not a quotable message of this
  thread and user is a 404. `message_out` gains `reply_to`, `reply_quote`, `reply_tainted`.
- `GET /api/instruction-proposals?state=open`, `GET /api/instruction-proposals/{id}`,
  `POST /api/instruction-proposals/{id}/accept` (body `{text?}`), `POST /api/instruction-proposals/{id}/decline`.
  Another user's proposal is a 404; a decided one is a 409. Event `instruction_proposals_changed`.
- Tool `propose_instructions_update` (kind `write_change`, `allowed_when_tainted`, `no_ask`; not for helpers).

## Web (minimum)

A Reply action on a message (hover), a quote chip over the composer with ×, the quote above the sent message, and
the card as a lazy chunk (Before/After diff, the why, Accept · Edit · Decline).

## Risks

- A quote carries web text into your own message: kept marked and aged out like the message it quotes.
- A bot steering its own instructions from a page: only your Accept writes, the card shows the full diff and the
  mark, and the tool never names another bot.
