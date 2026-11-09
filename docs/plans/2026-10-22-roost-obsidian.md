# Roost track: obsidian (tags on bot writes, the Bot Journal, Obsidian export)

Functionality first; the web gets only the minimum to use it. One migration (v30 after the merge).

## 1. Tags on everything a bot writes

- A bot's new task, note, expense, document, memory and Plan item carries `bot:<slug>` (the bot's name,
  slugged), `project:<slug>` when it is linked to a project, and up to `MAX_BOT_TOPIC_TAGS` (5) topic tags
  the bot gives in `tags` (one word each: `a-z 0-9 _ - /`, a leading `#` is dropped; anything else is
  refused with a plain sentence). `roost/tags/` holds the rules (`record_tags`, `topic_tags`, `slug`).
- The bot's name comes from `RecordContext.bot_name`, which `DomainTools` fills from the bot store on
  every run and every approved call. The user's own writes get no system tags.
- Existing tag fields are reused (tasks, notes, documents). New sealed columns: `money_expenses.tags`
  (`money_expenses:tags`) and `memories.tags` (`memories:tags`), JSON lists, `enc:v2`.
- Plan items are Obsidian Tasks lines, whose tags cannot hold `:`, so there they are `#bot/<slug>`.
  The Obsidian export writes every `a:b` tag as `a/b` for the same reason.

## 2. Bot Journal

- `bot_journals` (v30): one row per bot per Madrid day, `content` sealed under `bot_journals:content`
  (Obsidian Markdown: front matter with tags, a heading, one `- HH:MM text` line per entry), `tainted`
  (sticky: an entry written in a tainted run), `revision` compare-and-swap.
- `roost/journal/`: store, service (append with retry on a lost swap, a per-day size cap, read, recent
  days, search), tools `journal_append(text)` (`write_create`) and `journal_read(day)` (`read`; a
  tainted day taints the run), and `JournalRuns`, which collects the run's write steps (the
  `DomainTools` dispatch reports each successful write) and, after the run, appends one line built from
  their activity words ("Added a task, saved a note ×2"). No model call.
- Search: `find_notes` also lists the bot's journal days that match; `GET /api/journal/search?q=`.
- Routes: `GET /api/bots/{id}/journal` (recent days), `GET /api/bots/{id}/journal/{day}` (the day's
  Markdown). Web: an Info fold "Journal" listing recent days; a day opens read-only as Markdown.

## 3. Obsidian export (one-way)

- `money_projects.vault_export` (v30, default 0): the per-project "Export to my vault" switch,
  `PUT /api/projects/{id}/vault-export {on}`.
- `vault_exports` (v30, one row per user): the chosen grant (`grant_id`), "Export journals"
  (`journals`), the manifest of written paths and hashes (sealed `vault_exports:manifest`), and the last
  result (code, counts, time). `GET/PUT /api/vault-export`, `POST /api/vault-export/run` (Export now).
- `roost/vault_export/`: `render.py` (pure: a project, its tasks, notes and money, and journal days as
  Markdown files with front matter tags and `[[wikilinks]]`, under `Roost/Projects/<Project>/…` and
  `Roost/Journals/<Bot>/<day>.md`; the money table is `<Project> · Money.md`, so a project named
  Money never shares a path with it), `defang.py` (pure: text from a web page, in a tainted journal
  day, note, task or expense, is written with every web address as inline code and `\`, backticks,
  `~ [ ] ! < >` escaped, so no remote image, embed, HTML or code fence reaches the vault live; titles
  stay on one line inside their wikilink or heading), `plan.py` (pure: what to do with each file given the manifest and
  the disk's hash), `exporter.py` (runs it through `MacFiles`: `stat` in chunks, `create` with
  `parents`, `write` with the expected hash), `scheduler.py` (debounced per user, poked by the
  `tasks_changed` / `notes_changed` / `money_changed` / `journal_changed` frames through an `EventHub`
  listener; started and stopped by the gateway's lifespan).
- Rules: only a live `read_write` grant; never outside it (the keeper's `openat` walk); never deletes;
  only overwrites a file whose disk hash is the one Roost last wrote. A file changed on disk, or one
  Roost never wrote, gets a `<name>.conflict.md` copy instead. A rate limit or an away keeper stops the
  pass (partial) and the scheduler tries again.
- Keeper: `POST /mac/fs/create` takes `parents: true` to make missing folders inside the grant, one
  `mkdir` + `openat` per part, with the same name rules (no dot parts, no denied names).

## Risks

- A big first export meets the keeper's 60 steps a minute: the pass stops as partial and resumes.
- Tags change what a bot-written note's tags look like (tests updated).
- Wikilinks are path links (`[[Roost/Projects/X/Tasks/Y|Y]]`), so renaming in Obsidian breaks them
  until the next export writes them again (then a conflict copy if the file was edited).
