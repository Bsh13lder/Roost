# Roost "Your Mac: folders" (and the Obsidian bridge): Design

**Status:** DRAFT (2026-10-21). Nothing is built or approved yet. §7 holds the open decisions.

**Sources:** `roost/keeper/` (`app.py`, `auth.py`, `audit.py`, `main_browser.py` + its tests), `roost/talk/gate.py`,
`tool_catalog.py`; spec §4.4, §4.5 (parked runs, Ask cards), A13, §5.2, §5.4; the routines design (Plan
grammar §4.1, user decision D4: two-way Obsidian); computers-2 (bots live in their own Linux computers).

**Asked for:** bots find, read and edit files in Mac folders the user grants; the main case is an Obsidian
vault with the Tasks plugin. Loved elsewhere: a tasks note made with checkboxes, dates and a tag; a rename
on request; a weekday routine pointed at it; "Rename Tasks.md?" as a card; "with your OK each time".

## 1. Shape in one paragraph

The user **grants** a folder (one bot or all; read-only or read-write), stored sealed and pushed to the
**keeper**, the only process that touches the Mac's disk. The keeper gains a small signed **file API** on
`127.0.0.1:18801` (no new port, no shell, no exec) that checks every path against the grant and a fixed
deny list itself. Bots get five gated tools with an **approval policy per grant** (default: an Ask card
every time). Mac text is outside content and taints the run, unless the bot wrote the file and it is
unchanged. On top sits the **Obsidian bridge**: vault detection, a two-way Plan (later Board tasks) sync
in the Tasks emoji format, and a keeper watcher for ticks made in Obsidian.

## 2. Granting

**Where:** Settings → **Your Mac: folders** (all grants) and Profile → Info → "Folders it may use" (this
bot's, plus all-bots ones locked): label, path, scope, access, approval policy, **Revoke**.

**Adding:** type a path, or **Choose folder…** → signed `POST /mac/pick-folder`, which runs one **fixed
argv** in the `main_browser.py` pattern: `/usr/bin/osascript -e 'POSIX path of (choose folder with prompt
"Choose a folder for Roost")'` — a constant, no user text, no shell, `MAC_PICK_TIMEOUT_S` (120 s), an
injectable runner for tests. Cancel grants nothing; a picked path takes the same checks. Only the user
grants, from these screens; no bot tool can grant, widen or approve a folder.

**Checks on a new grant (keeper and gateway both, fail closed):**
- Resolved by `realpath`; an existing directory **under `~`**, never `~` itself; stored resolved.
- **Never allowed**, as root or anywhere below (list in `roost/constants.py`, enforced by the keeper on
  every operation): system folders (`/System`, `/Library`, `/usr`, `/bin`, `/sbin`, `/etc`, `/private`,
  `/var`, `/opt`, `/Applications`, `/Volumes`); `~/Library` (keychains, Mail, browser profiles);
  `~/.ssh`, `~/.gnupg`, `~/.config`, `~/.aws`, `~/.docker`, `~/.netrc` and every top-level dot-folder;
  `~/Roost` and `~/.Trash`; the Roost and LazyClaw repos' `data/` folders and `.env*` files;
  and by name, anywhere: `*.env`, `.env*`, `*.pem`, `*.key`, `*.p12`, `id_*`, `*.keychain*`,
  `credentials*`, `*.sqlite`, `*.db`.
  Denied entries are hidden from `list`/`find`; touching one gives "That file is off limits", no reason.
- A grant that **contains** a denied folder is allowed (e.g. `~/Desktop/Code_Projects`); the denied
  part stays invisible inside it, and the grant form says so.

**Storage (schema: next free version at build time):** `mac_grants`: `id`, `user_id`,
`bot_id` (NULL means all bots; cascade on Retire this bot), `path` and `label` (`enc:v2`, AAD
`mac_grants:<column>`), `access` (`read` | `read_write`), `approval_read`, `approval_create`,
`approval_change` (§4.2), `is_vault`, `created_at`, `revoked_at`. Every query has `user_id` in its
`WHERE`, and another user's grant id gives 404.

**Revoke is instant.** The gateway sets `revoked_at` and pushes the grant set (`PUT /mac/grants`, signed).
The keeper holds grants **in memory only** (never a plaintext file), swaps the set atomically and refuses
the old id from then on; a running walk stops at its current file. After a keeper restart it has no
grants until the gateway's health check pushes them, so a lost push fails closed. Revoke also ends that
grant's session OKs (§4.2).

## 3. The keeper file API

**Routes** (all `POST`, all `require_signed_body`, strict pydantic bodies with `extra="forbid"`, 422 on
an unknown field): `/mac/grants` (PUT), `/mac/pick-folder`, `/mac/fs/list`, `/mac/fs/find`,
`/mac/fs/read`, `/mac/fs/write`, `/mac/fs/create`, `/mac/fs/rename`, `/mac/fs/trash`, `/mac/fs/stat`,
`/mac/watch`. Each body carries `grant_id`, `bot_id` (UUID4), and **paths relative to the grant root**.
The keeper never accepts an absolute path from the gateway. Code lives in `roost/keeper/macfs/`
(`grants.py`, `paths.py`, `deny.py`, `ops.py`, `find.py`, `picker.py`, `watch.py`), each file under 400
lines.

| Op | Does | Caps (constants) |
|---|---|---|
| `list` | One folder's entries: name, kind, size, mtime | 500 entries |
| `find` | By name (glob or words) and/or by text (plain substring, case-folded, no regex), walking the grant | 200 hits; a walk stops at 20,000 entries or 5 s; text search skips files over 1 MB and stops after 50 MB scanned; 3 snippets of up to 160 chars per hit |
| `read` | One text file: UTF-8 (BOM stripped), with no NUL bytes; returns the text, `sha256`, `mtime` and size | `MAC_READ_MAX_BYTES` 1 MB; a binary file is refused ("not a text file") |
| `create` | A new file. It refuses a name that already exists | 1 MB; the extension must be on `MAC_WRITE_EXTS` (`.md`, `.txt`, `.csv`) |
| `write` | Replaces a file's content **only if** its current `sha256` equals `expected_sha256` (409 + the current hash otherwise) | 1 MB, same extensions |
| `rename` | Renames or moves a file inside the same grant. It refuses an existing target, and never moves anything out of the grant | — |
| `trash` | Moves a file to the folder's trash: Obsidian's own `<vault>/.trash/` in a vault, otherwise `<grant>/.roost-trash/`. **Nothing is ever deleted** | — |
| `stat` | Batched `sha256`/`mtime`/size for the files being synced | 50 paths |

**Path rules** (§5.4's rules, applied to the Mac):
- A relative path is NFC-normalised. The keeper refuses NUL bytes, empty or `.`/`..` parts, a
  leading `/` or `~`, and more than 32 parts.
- The keeper walks the path from the grant root **one part at a time** with `openat` and
  `O_NOFOLLOW | O_DIRECTORY` (`os.open(..., dir_fd=…)`). A symlink anywhere in the path is refused,
  so a link can never lead outside the grant. It then checks the final, resolved path against the
  deny list again.
- A regular file with `st_nlink > 1` is refused, so a hard link to a key file can't be read through a
  vault. Devices, FIFOs and sockets are refused too.
- **Writes are atomic.** The keeper writes `.<name>.roost-tmp-<random>` in the same folder (`O_EXCL`,
  mode 0600, then chmod to match the old file), fsyncs it, checks the `sha256` again, and calls
  `rename` over the old file. Before any change it saves a **backup copy** to
  `~/Roost/mac-backups/<grant_id>/<path-hmac>/<utc-time>` (folder 0700, files 0600, outside the
  grant so neither Obsidian nor iCloud syncs it). It keeps the last 20 copies per file and deletes
  copies after 30 days. "Undo" on an activity line restores one of them (as a normal write that
  asks).
- Writes into `.obsidian/`, `.git/`, `.trash/` or any dot-folder are refused. A file in
  `.obsidian/plugins/` is code that Obsidian runs, so a bot that could write there could run code on
  the Mac.
- **Rate caps:** `MAC_OPS_PER_MINUTE` (60) per bot, and `MAC_WRITES_PER_RUN` (20) per run, enforced
  in the gateway (so a parked run can't reset the count) and checked again in the keeper per minute.

**No shell, no exec.** File ops are plain Python file calls; the only process started is the fixed
`osascript` picker, and nothing the gateway sends can choose a program or its arguments.

**Why the keeper, not a bind mount into the gateway container.** The gateway container holds
`SERVER_SECRET`, the DB, OAuth credentials and the keeper secret. A bind mount would expose the **whole
folder, all the time**, to every process there with no per-operation check; it can't enforce the deny
list (a denied subfolder is still mounted), the hard-link rule or the Mac's symlinks; granting or
revoking would need a container restart and Docker Desktop file sharing widened to `~`.

The keeper already runs as the user, takes only signed requests and has the single-door pattern
(`main-browser/open`). Bots' Linux computers (computers-2) **never** see the Mac's folders.

## 4. Bot tools, approval and taint

### 4.1 Tools (`roost/mac/tool_specs.py`, catalog entries with gate kinds)

| Tool | Gate kind | Notes |
|---|---|---|
| `mac_find(query?, text?, folder?)` | `read` | Hits across the bot's grants: label, relative path, size, date, and snippets for a text search. |
| `mac_read(folder, path)` | `read` | Text, wrapped as quoted data with a header line naming the file. |
| `mac_write_new(folder, path, text)` | `write_create` | Needs a `read_write` grant. Refuses an existing name. |
| `mac_edit(folder, path, base_hash, edits \| text)` | `write_change` | `edits` = exact old → new pairs (each must match once), or a full new `text`. `base_hash` comes from the bot's last read; a 409 says "the file changed since you read it". |
| `mac_rename(folder, path, new_path)` | `write_change` | Same grant only. |

`folder` is the grant's label. Each run's instructions list the bot's grants (label, access, policy)
and one true line: "You reach these Mac folders with the user's OK each time unless they set otherwise." 

### 4.2 Approval policy per grant

| Kind | Choices (default first) |
|---|---|
| read (`mac_find`, `mac_read`) | **Ask every time** · Ask once per session |
| write_create (`mac_write_new`) | **Ask every time** · Ask once per session · Just do it |
| write_change (`mac_edit`, `mac_rename`) | **Ask every time** · Ask once per session |

- **The gate gains an `ask` verdict** for these tools. Asking parks the run and posts an Approve Ask
  card (spec §4.5). If generic Ask cards are not built when P0 starts, P0 builds the minimal one
  needed here (park, card, `card_answer` work item), following the stuck card's shape.
- **"Session"**: one OK covers that bot, grant and kind for `MAC_SESSION_MINUTES` (120); it ends early on
  Revoke, Off duty, Retire this bot, a gateway restart, or taint. In memory only.
- **Card buttons:** Yes, once · Yes for this session · No. A rename card is a Question card with
  chips: **"Rename Tasks.md?"** → `grtasks.md` (the bot's proposal) · Keep the name · Other name….
- **Edit cards show a diff:** a unified, line-based diff of the exact bytes to be written (the keeper
  hash on the card is checked again just before the write, spec S12), with the file's label and path
  and "+12 −3 lines". A create card shows the whole new file. Over 400 diff lines, the card shows the
  first 400 and "Open full diff".
- **Hard floor (cannot be relaxed):** writes in dot-folders, any trash, more than
  `MAC_WRITES_PER_RUN` writes, and every Mac write in a tainted run always ask, whatever the policy.

### 4.3 Taint

- `mac_read` and `mac_find` with text snippets **taint the run** (spec §8.2), like `read_page`. A
  vault is full of pasted and clipped web text. `mac_find` by name only (names, sizes and dates,
  each name quoted and capped at 120 chars with control characters stripped) counts as
  metadata and does not taint.
- **The exception for the bot's own files:** `mac_file_marks` (`user_id`, `grant_id`, `path_key` = a
  keyed HMAC of the path, never the path itself, `sha256`, `bot_id`, `written_tainted`). After every
  Roost write it stores the hash. A later read whose hash equals a mark written by a **clean** run
  does not taint.
- **Tick-only changes stay clean:** if a file differs from its mark **only** in Tasks status
  characters (`[ ]`/`[x]`/`[/]`/`[-]`) and added or removed `✅`/`❌ YYYY-MM-DD` on lines that carry a
  Roost `🆔`, the read stays clean and the mark moves to the new hash. That's how the morning routine
  can read the note the user ticked in Obsidian.
- The gate rule holds: a tainted run may create at most `MAX_TAINTED_CREATES_PER_RUN` Mac files (each
  asks, and gets a mark with `written_tainted=1`) and **never** edits or renames (but see §7 D1).

## 5. The Obsidian bridge

**Detection:** a folder holding `.obsidian/` is a **vault**. The keeper reports `is_vault`, `has_tasks`
(the Tasks plugin's `manifest.json` exists and its id is in `community-plugins.json`) and Tasks'
`globalFilter` (≤ 40 chars, e.g. `#task`, added to new lines). These are its only `.obsidian/` reads, and
they return fields, never files. The grant card shows "Obsidian vault · Tasks plugin on".

**What syncs (two-way, user decision D4):**
- **The bot's Plan** ↔ `<vault>/Roost/<bot name>.md`. The Profile switch "Share Plan to my Obsidian
  vault" (off by default) now picks a vault grant (`read_write`). The sync is a system action the
  user switched on, so it doesn't ask per write and doesn't use the bot's tools or count against
  `MAC_WRITES_PER_RUN`.
- **Board tasks** (P2b, opt-in per project, §7 D3) ↔ `<vault>/Roost/Tasks - <project>.md`. Field
  mapping: due `📅`, scheduled `⏳`, start `🛫`, priority `⏫ 🔼 🔽`, repeat `🔁`, tags `#tag`, done
  `✅`, dropped `❌`, the id `🆔`.

**Format:** the routines design's grammar (§4.1 there): lenient reading, canonical writing
(`desc ⏰ HH:MM #tags 📅 date … ✅ date 🆔 id`), Tasks' global filter added to new lines when set.
Every item has a `🆔` (6 chars, Tasks' own id field). The sync maps Roost ids to `🆔` in a table, so
the user moving lines around in Obsidian never retargets a write. **Lines Roost can't parse, and every
non-task line, are kept byte for byte** in place (anchored to the previous parsed line).

**Sync state:** `vault_syncs`: `user_id`, `grant_id`, `scope` (`plan:<bot_id>` | `project:<id>`),
`rel_path` (`enc:v2`), `base_text` (`enc:v2`, the last merged text, the common ancestor), `base_sha256`,
`base_revision`.

**The merge** (pure, `roost/obsidian/merge.py`, 3-way by `🆔`: base = `base_text`, ours = the Roost
copy at its `revision`, theirs = the vault file at its `sha256`):
- Changed on one side only: that side wins. New lines on either side are added; a new vault line
  without a `🆔` gets one on the next write.
- **Conflict rule (same item changed on both sides), per field:** a done (`[x]`, `✅`) beats not-done,
  because losing a tick is worse than a stale one. Otherwise **the vault wins**, because the user's
  hands were on it. The losing value goes into an activity line ("Kept your Obsidian edit of 'Call
  bank'; Roost had 'Call bank Fri'") and the backup.
- Deleted in the vault: the item leaves the Plan (backup kept). Deleted in Roost but edited in the
  vault: the vault copy is kept.
- **Writes are double compare-and-swap:** the DB save checks `revision` (409 + current copy, as
  notes), and the keeper `write` checks `expected_sha256`. On either miss, the gateway re-reads,
  re-merges and tries again, at most 3 times, and then posts "Couldn't sync <file>; I'll try again".
- **Taint:** per D4, Plan lines read back from the vault count as **user-edited** (they clear
  `item_taint`). Any other note the bot reads stays outside content (§4.3).

**Catching ticks made in Obsidian:** the keeper watches only the synced files with **FSEvents** (the
`watchdog` package, Apache-2.0, a new dependency). `POST /mac/watch` is a gateway long poll (≤ 25 s)
returning changed sync files; events debounce 2 s, and a hash equal to Roost's own last write is
ignored. **Fallback:** if FSEvents can't start, the gateway polls `/mac/fs/stat` every 20 s.

## 6. Activity lines, audit, phases

**In the chat**, one line per action: "Read grtasks.md · MySpace", "Edited grtasks.md · MySpace (+2 −1)
· Undo", "Renamed Tasks.md → grtasks.md · MySpace · Undo", "Synced Plan · MySpace · 2 ticks from Obsidian".

**Audit, no contents:** the gate's encrypted `audit.detail` for `mac_*` tools stores **redacted
arguments**: grant id, `path_key`, sizes, hashes and line counts, never `text` or `edits`. The keeper's
plaintext `keeper-audit.log` gets `action`, `bot_id`, `result`, plus `grant_id` and a byte count (no
path, no name, no content), keeping `AuditLog.record`'s narrow-parameters idea. Python logs never
carry a path or a body. A test greps the DB, the logs and the audit for a canary string written to and
read from a temp vault.

**Phases:**
- **P0: read and find.** Grants (Settings + Profile, typed path and the picker), deny list, keeper
  `list`/`find`/`read`/`stat`, `mac_find`/`mac_read`, the `ask` verdict with ask every time only,
  taint, activity lines, audit.
- **P1: edits with diffs.** `create`/`write`/`rename`/`trash` in the keeper, backups and Undo,
  `mac_write_new`/`mac_edit`/`mac_rename`, diff cards, the three approval policies, `mac_file_marks`.
- **P2: the Obsidian sync.** Detection, the Plan ↔ vault two-way sync, the merge, the watcher. P2b:
  Board tasks per project.
- **P3: routines that use it.** A routine may name granted files. Its Ask card (routines §3) lists
  them, and approving the routine approves those reads (and the listed edits) for that routine's runs
  (§7 D4). Unattended cards follow routines D2 (they wait until the next slot).
- **P4: Roost Link** (§8), only when Roost runs off the Mac.

Tests: path and deny cases on a temp tree (mid-path symlink, `..`, NFC look-alikes, hard links, FIFO,
`.env` in a grant), revoke mid-walk, 409 on a changed hash, a crash mid-write, merge fixtures, a fake
picker. No test touches the real home folder (tripwire) or calls a real model.

## 7. OPEN DECISIONS for the user

- **D1. Editing notes the bot had to read first.** Reads taint and tainted runs never change, so "fix
  the typo in my Ideas note" is always refused. (a) Keep it strict. (b) A per-grant "these are my own
  notes" switch that stops reads tainting. (c) For `mac_edit` only, a tainted run **asks** with the full
  diff and a red "based on outside content" line, never via Just do it or a session OK.
  **Recommend (c):** the diff is the human check and taint stays honest; (b) would trust clipped pages.
- **D2. iCloud vaults** live in `~/Library/Mobile Documents/iCloud~md~obsidian/`, inside denied `~/Library`.
  (a) Never; the user moves the vault. (b) A narrow exception for that container (and
  `com~apple~CloudDocs`) only. **Recommend (b)**, with §8's iCloud rules.
- **D3. Board tasks in the vault.** (a) Plan only. (b) Plan, then opt-in per project (P2b).
  **Recommend (b):** the user's real tasks live on the Board; per project keeps files small.
- **D4. Routines and "ask every time".** A 7:00 routine would wait for a tap every morning. (a) Keep
  asking. (b) Approving the routine approves the files it names, for its runs only, until it changes.
  **Recommend (b)**; edits still show a diff on the first run, and a tainted routine run still asks.

## 8. Risks

- **Prompt injection from notes** (clipped pages, shared notes, a crafted file name). Handled by
  taint (§4.3), quoted data framing, no tainted edits (D1), the hard floor, and egress rules S9 for
  anything that would send data out. Notes can also hold the user's own secrets. The read card names
  the file, and reads go through the same secret scrub as `read_page`.
- **Accidental mass edits.** Handled by `MAC_WRITES_PER_RUN` (the hard floor above it), one Ask card
  per change by default, backups with Undo, trash instead of delete, and **Pause all Mac access**
  in Settings (an instant revoke of every grant that can be undone).
- **iCloud-synced vaults.** Files may be "dataless" (still in the cloud): the keeper refuses to read
  them ("Open it on the Mac once so iCloud downloads it") and never forces a download. iCloud can
  make conflict copies ("Tasks 2.md"), so sync only follows its own `rel_path` and reports a sibling
  conflict copy as a line. Atomic rename-writes are iCloud-safe. Backups stay out of iCloud.
- **macOS privacy (TCC):** the launchd keeper's first `~/Documents` access triggers a macOS prompt; a
  denial shows "macOS said no; allow it in System Settings → Privacy & Security → Files and Folders".
- **Roost on a server later (no Mac).** Then the keeper isn't on the Mac. **Roost Link** would be a
  tiny MIT helper app on the Mac (a menu-bar item) holding only `macfs/` and the picker. It is paired
  once with a code shown in Settings and keeps a pinned key. It dials **out** to the server over TLS
  (no listening port on the Mac) and serves the same signed file API. The Mac enforces grants and the
  deny list again, and the menu shows the last actions plus Pause. When the Mac is asleep, tools
  answer "Your Mac is away", and the vault sync catches up when it's back.

## User decisions (2026-10-21)

- **D1. Approval modes, like a coding agent.** Each bot has a mode, plus per-topic switches in its panel (Files, Tasks, Money, Notes, Posting/sending, …). It's the LazyClaw idea, made stricter.
  - **Ask every time.** Every change raises an Ask card. Edits to Mac files show the full diff.
  - **Auto-edit.** Ordinary changes go straight through, including editing a note the bot read first. Each change shows as an activity line with Undo, and a backup copy is made first. It does not disturb you unless something is risky.
  - **Plan mode.** The bot first posts a Plan card: the steps, the files it will touch, and the diffs. Accept runs the whole plan without asking again; Edit or Decline stops it.

  Rules for all three modes:
  - The hard floor always asks, whatever the mode: money moves, deleting (beyond the trash), posting or sending outside, new grants, and secrets.
  - The default mode for a new bot is Ask every time.
  - The tainted-write rule is relaxed only for Mac-file edits, and only in Auto-edit or an accepted Plan. Diffs, backups and Undo are always kept.
- **D2.** The vault is local, so ~/Library stays blocked, with no iCloud exception.
- **D3.** Bot Plans sync with the vault first. Board tasks come later, as an opt-in per project.
- **D4.** Approving a routine also approves the files it names.
