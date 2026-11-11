"""Shared constants — ports, directories, limits, status strings.

No magic numbers in the rest of the codebase: anything that would otherwise
be a hardcoded literal (a port, a timeout, a size cap) lives here instead.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Data directories — always outside ~/Desktop (spec: Global Constraints)
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = Path.home() / "Roost" / "data"
DEFAULT_DESKS_DIR = Path.home() / "Roost" / "desks"

# In-app update (app restructure slice 2): the published phone app lives outside the repo, mounted read-only into
# the gateway container at /mobile. `scripts/publish_mobile.sh` writes the APKs and latest.json there.
DEFAULT_MOBILE_DIR = Path.home() / "Roost" / "mobile"
CONTAINER_MOBILE_DIR = Path("/mobile")
MOBILE_LATEST_FILE = "latest.json"
MOBILE_APK_NAME_PATTERN = r"roost-[0-9.]+\+[0-9]+\.apk"
MOBILE_APK_MEDIA_TYPE = "application/vnd.android.package-archive"
MOBILE_VERSION_PATTERN = r"[0-9]+\.[0-9]+\.[0-9]+"
MOBILE_NOTES_MAX_CHARS = 200
MOBILE_LATEST_MAX_BYTES = 4096

# ---------------------------------------------------------------------------
# Ports — every listener binds 127.0.0.1 only, never 0.0.0.0
# ---------------------------------------------------------------------------

GATEWAY_PORT = 18800
KEEPER_PORT = 18801
PROXY_PORT = 18803
VOICE_PORT = 18804   # the voice service on the Mac (roost/voice_host/), docs/plans/2026-10-30-roost-voice.md

# Every listener Roost or the old LazyClaw app binds on the host — a bot's
# browser must never reach any of them, on any address. Two independent
# enforcement points share this one set: the egress proxy's resolved-
# address policy (``roost/keeper/proxy.py``) and the desk URL policy's
# pre-DNS check (``roost/desk/url_policy.py``) — see that module's
# docstring for why it still needs its own copy of this check even though
# the proxy also enforces it.
SENSITIVE_PORTS = frozenset({9222, 11434, 18789, 18790, 18791, GATEWAY_PORT, KEEPER_PORT, 18802, PROXY_PORT,
                             VOICE_PORT})

# ---------------------------------------------------------------------------
# Run limits
# ---------------------------------------------------------------------------

# Owner, 2026-11-03: longer work. A run takes up to MAX_STEPS model steps (CU_MAX_MODEL_STEPS once it used the
# screen) and MAX_RUN_SECONDS of wall time, which is the screen loop's deadline too (CU_RUN_DEADLINE_S).
MAX_STEPS = 100
MAX_RUN_SECONDS = 2700
EXEC_TIMEOUT_S = 120
PAGE_TEXT_LIMIT = 12000
OUTPUT_LIMIT = 16000

# How long `DeskBrowserPage.open_page` waits for `Page.loadEventFired`
# before giving up and reading whatever has rendered so far (contract:
# "wait Page.loadEventFired (20 s, then continue)").
PAGE_LOAD_EVENT_TIMEOUT_S = 20.0

# Final review, finding 4: `CdpClient.send` used to wait for a reply with
# no timeout at all. A hostile page whose script loops forever hangs its
# renderer, so a call like `Accessibility.getFullAXTree` (which
# `read_page` always sends) never replies -- the turn never ends, and
# every later message for that bot queues forever behind it in
# `TurnRunner._pending`. 30s is comfortably longer than any real CDP
# round-trip but short enough that a genuinely hung desk surfaces as
# `CdpClientError` (-> the existing reconnect/`DeskUnavailable` path)
# well inside `MAX_RUN_SECONDS`.
CDP_SEND_TIMEOUT_S = 30.0
# Crashed tab recovery (docs/plans/2026-10-30-roost-voice.md §4): Gela's Brave tab was OOM-killed opening WhatsApp
# Web and never answered CDP again. A command that times out has the tab probed with Runtime.evaluate("1") for this
# long (or Inspector.targetCrashed was seen on its session); a crashed tab is closed and the address opened again in
# a fresh tab, and the call runs once more. The computer's memory limit (COMPUTER_MEMORY) does not change.
CDP_CRASH_PROBE_TIMEOUT_S = 3.0
# owner, 2026-11-04: a page call after this long asks the keeper whether the Linux computer fell asleep, and wakes it
# on a fresh connection, before any CDP goes to a frozen container (which read as a crashed tab)
DESK_WAKE_CHECK_AFTER_S = 5.0
CDP_CRASH_EVENT = "Inspector.targetCrashed"
CRASHED_TAB_RECOVERED_TEXT = "The page had crashed (the computer ran low on memory), so I opened it again in a new tab."
CRASHED_TAB_KEEPS_CRASHING_TEXT = "The page keeps crashing on this computer; it may need more memory."
# A hung browser (owner, 2026-11-06: Gela's Brave, up 7½ days, timed out every command, ~90 s per page): a command
# that times out on a tab that is not merely crashed has the browser probed (Browser.getVersion within
# CDP_CRASH_PROBE_TIMEOUT_S); one that does not answer, or a page that keeps crashing, has the Linux computer stopped
# and started again (the profile stays) and the call runs once more. At most once per this long per bot.
COMPUTER_HUNG_RESTART_COOLDOWN_S = 600.0
BROWSER_RESTARTED_TEXT = "The browser had stopped answering, so I restarted the computer and tried again."
# A tab that stops answering while the browser still does (owner, 2026-11-10, docs/plans/2026-11-10-roost-self-healing.md:
# bot 1016fb46's Page.enable timed out for 30+ minutes and the probe above said the browser was fine): this many
# failed page calls within this window count as hung too, and restart the computer under the same cooldown.
DESK_UNANSWERED_STREAK: Final = 3
DESK_UNANSWERED_WINDOW_S: Final = 1200.0   # wide enough for a 5-minute watch alone (3 checks)
# The one quiet line in the bot's main chat after such a restart (kind ``computer_restart``; at most one per cooldown).
COMPUTER_RESTARTED_LINE = "My computer stopped answering, so I restarted it."

# Fix round 1, finding 4: `websockets.connect`'s own default `max_size`
# (1 MiB) is smaller than a real page's `Accessibility.getFullAXTree`
# reply routinely is -- a news front page alone commonly exceeds it. A
# reply over the limit closes the whole CDP connection (code 1009),
# wedging every later call on that bot's desk. 64 MiB covers any page
# this facade will ever read (text-only, already capped by
# PAGE_TEXT_LIMIT) with headroom to spare.
CDP_MAX_MESSAGE_BYTES = 64 * 1024 * 1024

# Fix round 1, finding 5: the keeper's own workspace/exec endpoint can
# legitimately run for up to EXEC_TIMEOUT_S (its own contractual bound)
# plus whatever it needs to notice the timeout and clean up the child
# process. The gateway's HTTP timeout for that one call must be longer
# than EXEC_TIMEOUT_S or a command that's about to finish on time looks
# exactly like a dead keeper (503) instead.
KEEPER_EXEC_CLEANUP_MARGIN_S = 15.0
KEEPER_EXEC_REQUEST_TIMEOUT_S = EXEC_TIMEOUT_S + KEEPER_EXEC_CLEANUP_MARGIN_S

# Real-desk smoke (Task 13) caught this: DELETE /desks/{bot_id} (retire)
# runs BraveLauncher.stop(), a CDP page close, and `docker rm -f`
# sequentially -- each individually bounded inside the keeper, but
# their COMBINED worst case can land close to an ordinary control-call
# timeout. The gateway's own HTTP timeout for this one call must clear
# that combined worst case with real margin, the same fix as
# KEEPER_EXEC_REQUEST_TIMEOUT_S above for a different route -- otherwise
# a retire that's about to finish on time looks exactly like a dead
# keeper and gets silently swallowed as ``DeskUnavailable``, leaving its
# desk only PARTIALLY cleaned up. Clears roost/keeper/workspaces.py's
# own _CONTAINER_REMOVE_TIMEOUT_S (60s) with margin for everything else
# around it.
KEEPER_RETIRE_REQUEST_TIMEOUT_S = 90.0

# Night 1 fix: the egress proxy's DNS resolve (`loop.getaddrinfo`) and its
# upstream TCP connect (`asyncio.open_connection`) each used to have no
# time limit at all, so a hung/blackholed target rode out the OS's own
# much longer timeout before the bot's `Page.navigate` call ever got a
# reply. Each dial-out phase gets its own short ceiling so a bad host
# surfaces as a fast 504 instead.
PROXY_RESOLVE_TIMEOUT_S = 10.0
PROXY_CONNECT_TIMEOUT_S = 10.0

# ---------------------------------------------------------------------------
# Auth — account credentials and rate limits (roost/gateway/auth.py)
# ---------------------------------------------------------------------------

MIN_USERNAME_LENGTH = 1
MAX_USERNAME_LENGTH = 64
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

SESSION_LIFETIME_HOURS = 720  # 30 days

# Per-IP login attempts.
LOGIN_RATE_LIMIT_PER_IP = 5
LOGIN_RATE_WINDOW_S = 60
# Per-username login attempts — catches a botnet spreading guesses
# across many source IPs, which the per-IP limit alone would miss.
LOGIN_RATE_LIMIT_PER_USERNAME = 10
LOGIN_USERNAME_WINDOW_S = 3600
# Per-IP registration attempts. Registration itself is also closed after
# the first account exists (see the HTTP API contract), so this mainly
# guards the single-account creation window.
REGISTER_RATE_LIMIT_PER_IP = 3
REGISTER_RATE_WINDOW_S = 3600

# ---------------------------------------------------------------------------
# Talk — threads/messages (roost/talk/store.py, roost/gateway/routes/threads.py)
# ---------------------------------------------------------------------------

# Contract: "POST /api/threads/{thread_id}/messages | {text: 1..8000}".
MIN_MESSAGE_TEXT_LENGTH = 1
MAX_MESSAGE_TEXT_LENGTH = 8000
# Not specified by the contract; a thread title is a short label, not
# message content, so it gets its own (smaller) cap.
MAX_THREAD_TITLE_LENGTH = 200
# Contract: "list_messages(self, ..., after_seq: int = 0, limit: int = 200)".
DEFAULT_MESSAGE_PAGE_LIMIT = 200

# ---------------------------------------------------------------------------
# Desk — browser/workspace facade (roost/desk/*, roost/gateway/routes/desk.py)
# ---------------------------------------------------------------------------

# Contract: "POST .../desk/workspace/exec | {command: 1..2000}".
MIN_EXEC_COMMAND_LENGTH = 1
MAX_EXEC_COMMAND_LENGTH = 2000

# ---------------------------------------------------------------------------
# Work queue (roost/work/*, roost/talk/runner.py) — spec §4.2, §11 step 5
# ---------------------------------------------------------------------------

# Items in a row for one thread become one turn; at most this many.
MAX_BATCH_ITEMS = 20
# A claimed item's lease outlives the run's own wall-time cap.
WORK_LEASE_SECONDS = MAX_RUN_SECONDS + 60
# How much of a call an "interrupted, outcome unknown" note quotes.
INFLIGHT_DESCRIPTION_CHARS = 160
# How much of a dropped message a Stop note quotes.
DROPPED_PREVIEW_CHARS = 80

# Spec A14: the per-bot daily cap (runs per local day; owner 2026-11-03: 500, and helper runs don't count).
DAILY_RUN_CAP = 500

# ---------------------------------------------------------------------------
# Handoffs (roost/talk/team_tools.py) — D-C, spec §11 step 17
# ---------------------------------------------------------------------------

HANDOFF_TIMEOUT_S = 600           # an asker waits at most 10 minutes
MAX_HANDOFF_DEPTH = 3             # Chief → Scout → Quill → Wren, and no further
MAX_HANDOFFS_PER_RUN = 6
HANDOFF_PREVIEW_CHARS = 140       # how much of a reply the "Scout → Chief: …" line shows
# M2 Task 3 fix round 1, finding 2: a hand-over's task is often "the full
# content" a bot gathered (a long task list, a month of expenses) on its way
# to ask_bot docs — a human-sized chat cap (MAX_MESSAGE_TEXT_LENGTH) refused
# it with no hint that length was the problem. Same ceiling as a doc's own
# markdown (MAX_DOC_MARKDOWN_LENGTH), since that is what it is usually bound for.
MAX_HANDOFF_TASK_LENGTH = 100_000
# @bot in a bot's chat (roost/talk/mentions.py): at most this many other bots get one of your messages.
MENTIONS_PER_MESSAGE_MAX: Final = 3
# #project in a bot's chat (2026-10-26): at most this many projects named in one message reach the run's prompt.
CHAT_PROJECTS_PER_MESSAGE_MAX: Final = 3

# ---------------------------------------------------------------------------
# Bots — field rules shared by the HTTP API and suggest_bot
# ---------------------------------------------------------------------------

BOT_NAME_PATTERN = r"^[\w][\w .\-]{0,39}$"
AVATAR_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"
MAX_SUGGESTIONS_PER_RUN = 3
MODEL_REASON_MAX_CHARS = 200   # why suggest_model proposes a model, shown on its Ask card
# The daily look at Anthropic's public models page for a new model (one fixed host, an anonymous GET).
MODEL_CHECK_URL = "https://platform.claude.com/docs/en/models/overview"
MODEL_CHECK_HOST = "platform.claude.com"
MODEL_CHECK_INTERVAL_S = 86_400
MODEL_CHECK_FIRST_DELAY_S = 600
MODEL_CHECK_TIMEOUT_S = 10
MODEL_CHECK_MAX_BYTES = 2 * 1024 * 1024
MODEL_CHECK_MODES = ("on", "off")
MAX_BOT_NAME_LENGTH = 40
MAX_BOT_JOB_LENGTH = 200
MAX_BOT_GROUP_LENGTH = 30   # a bot's sidebar label fits on one short line
MAX_BOT_INSTRUCTIONS_LENGTH = 4000
# Bot avatars (avatars v7, the Lensbots): eighteen Lensbot shapes. The ten ghosts (v5), the six Boxbot
# heads (redesign V1) and the S1.6 bird shapes stay valid and are stored as sent; the web draws each
# one as a Lensbot through one table (web/src/components/robot/look.ts LEGACY_SHAPE_TO_LENSBOT;
# tests/test_bot_look.py keeps the lists in step). "tall", "wide" and "round" are ghost names, head
# names and bird names at once, so AVATAR_SHAPES lists each once.
LENSBOT_SHAPES: tuple[str, ...] = (
    "mochi", "loaf", "gumdrop", "pebble", "bun", "acorn", "marsh", "dumpling", "muffs", "squish", "cub", "sprout",
    "cheeky", "tower", "helmet", "bell", "puck", "pod")
DEFAULT_LENSBOT_SHAPE: Final = "mochi"
GHOST_SHAPES: tuple[str, ...] = ("dome", "tall", "wide", "round", "droopy", "spire", "comet", "cape", "puff", "hooded")
ROBOT_HEADS: tuple[str, ...] = ("classic", "tall", "wide", "soft", "cube", "monitor")
LEGACY_AVATAR_SHAPES: tuple[str, ...] = ("round", "egg", "pear", "plump", "crest")
AVATAR_SHAPES: tuple[str, ...] = LENSBOT_SHAPES + GHOST_SHAPES + tuple(
    shape for shape in ROBOT_HEADS + LEGACY_AVATAR_SHAPES if shape not in GHOST_SHAPES)
# A bot's role (avatars v7 role looks): the job its body shows as a small emblem. Optional in the
# avatar JSON; an avatar without one counts as general (no emblem). web/src/components/robot/look.ts
# BOT_ROLES is the same list.
BOT_ROLES: tuple[str, ...] = ("general", "tasks", "code", "seo", "money", "social", "research", "writer")
# The screen's signal style. Still accepted and stored (an older client or template file sends it);
# a ghost has no screen, so the web no longer draws it.
ROBOT_SCREENS: tuple[str, ...] = ("glow", "pixel", "signal")
DEFAULT_ROBOT_SCREEN: Final = "glow"
# A new bot with no colour chosen takes the first of these no teammate wears
# (web/src/components/robot/palette.ts BOT_DEFAULT_COLORS is the same list).
BOT_DEFAULT_COLORS: tuple[str, ...] = (
    "#8b5cf6", "#3b82f6", "#14b8a6", "#22c55e", "#f97316", "#ec4899", "#ef4444", "#eab308", "#6366f1", "#84cc16",
)
# S1 D3 (Ruling 29): the main bot creates at most this many new bots per request.
MAX_BOTS_CREATED_PER_RUN = 3
# A bot's own picture on its robot's screen (redesign P1, the avatar editor's Upload). The web
# shrinks a picture to 256 px first, which is far under this.
AVATAR_PICTURE_MAX_BYTES = 512 * 1024

# ---------------------------------------------------------------------------
# Rooms (roost/rooms/*) — D-E, spec §11 step 17
# ---------------------------------------------------------------------------

ROOM_MIN_MEMBERS = 2
ROOM_MAX_MEMBERS = 6
MAX_ROOM_NAME_LENGTH = 40

# ---------------------------------------------------------------------------
# Gate (roost/talk/gate.py) — M1 D3/D4, spec §4.4
# ---------------------------------------------------------------------------

# Spec §4.4: a run that read outside content creates at most this many records (owner, 2026-11-03: was 3; a bot
# that does what you ask adds a whole list); past it the next one is refused.
MAX_TAINTED_CREATES_PER_RUN = 50
# The most links a run carries down a handoff chain (the user's own come first).
LINK_SCOPE_MAX_URLS = 500
# W6/W7 (owner, 2026-10-24): a run of your own new chat messages (1:1, no new outside content read yet, even when
# the chat's older history is tainted) opens any safe web address with no Open card, and its computer may browse
# the sites it opened that way. For opening sites only: the run's taint still rules everything else.
FRESH_RUN_OPENS_ANY_SITE: Final = True
# Well-known sites the user may name in plain words ("sign in to Google") in a guarded run: the word
# opens that site's own hosts and their subdomains, never anything else (link_scope.named_site_entries).
NAMED_SITES: Final = {
    "google": ("google.com",), "gmail": ("google.com",), "youtube": ("youtube.com", "google.com"),
    "github": ("github.com",), "microsoft": ("microsoft.com", "live.com", "microsoftonline.com"),
    "outlook": ("live.com", "microsoftonline.com", "office.com"), "apple": ("apple.com",),
    "icloud": ("icloud.com", "apple.com"), "amazon": ("amazon.com", "amazon.es"),
    "linkedin": ("linkedin.com",), "instagram": ("instagram.com",), "facebook": ("facebook.com",),
    "twitter": ("x.com", "twitter.com"), "upwork": ("upwork.com",), "notion": ("notion.so",),
    "slack": ("slack.com",), "reddit": ("reddit.com",), "dropbox": ("dropbox.com",),
    "paypal": ("paypal.com",), "wikipedia": ("wikipedia.org",),
    # Owner, 2026-10-23: messengers and everyday sites, plus "whatsup", the way the owner writes WhatsApp.
    "whatsapp": ("whatsapp.com",), "whatsup": ("whatsapp.com",), "telegram": ("telegram.org", "t.me"),
    "discord": ("discord.com",), "tiktok": ("tiktok.com",), "pinterest": ("pinterest.com",),
    "fiverr": ("fiverr.com",), "etsy": ("etsy.com",), "ebay": ("ebay.com", "ebay.es"),
    "spotify": ("spotify.com",), "netflix": ("netflix.com",), "canva": ("canva.com",),
    "figma": ("figma.com",), "trello": ("trello.com",), "zoom": ("zoom.us",), "airbnb": ("airbnb.com",),
    "booking": ("booking.com",), "chatgpt": ("chatgpt.com", "openai.com"), "grok": ("grok.com",),
    "wallapop": ("wallapop.com",), "idealista": ("idealista.com",),
}

# ---------------------------------------------------------------------------
# Tasks role (roost/tasks/*) — M1 D6
# ---------------------------------------------------------------------------

MAX_TASK_TITLE_LENGTH = 200
MAX_TASK_NOTES_LENGTH = 4000
MAX_TASK_CATEGORY_LENGTH = 60
MAX_TASK_STEPS = 50
MAX_TASK_TAGS = 20
MAX_TASK_TAG_LENGTH = 40       # one #tag of a task
MAX_PRE_REMINDERS = 10
MAX_DUE_TEXT_LENGTH = 100
# LazyClaw's default reminder_offsets: one advance ping, 30 minutes before.
DEFAULT_PRE_REMINDERS: tuple[str, ...] = ("-30m",)
TASK_LIST_LIMIT = 50
# Task cards in the chat (2026-10-26): at most this many tasks drawn as cards after one run; the rest are counted.
TASK_CARDS_MAX: Final = 10
# GET /api/tasks?ids=: at most this many ids in one ask (a card line never holds more than TASK_CARDS_MAX).
TASK_IDS_QUERY_MAX: Final = 50
# Task views (Task 10): the Done view's cap, the search box's length, the most dues one bulk move touches.
TASK_DONE_VIEW_LIMIT = 100
BOARD_DONE_DAYS = 7      # the Kanban's Done column holds tasks finished in the last 7 local days
TASK_SEARCH_MAX_LENGTH = 100
MOVE_OVERDUE_MAX = 200
TASK_RANGE_MAX_DAYS = 62         # the task calendar asks for at most this many days (a six-week month grid)
UPCOMING_COUNT_DAYS = 14        # the Upcoming tab's count looks this many days ahead
TASK_NO_PROJECT = "none"         # ?project_id=none on the task list and counts: only tasks in no project (the Inbox)
# Redesign P3: a task's steps and comments.
MAX_STEP_TITLE_LENGTH = 200
STEP_WRITE_ATTEMPTS = 3          # compare-and-set tries for one steps change before "try again"
MAX_COMMENT_LENGTH = 4000
COMMENT_LIST_LIMIT = 200         # the newest comments a thread shows over HTTP, oldest first
COMMENT_TOOL_LIMIT = 20          # the newest comments list_comments shows a bot
QUICK_LINE_MAX_LENGTH = 300      # the quick-add line the Board reads as you type
# Offline tasks (docs/plans/2026-11-08-roost-offline-tasks.md): a line the phone kept offline is read as of when it
# was typed; older than this, or later than now by more than the skew, the typed time is refused.
OFFLINE_TYPED_AT_MAX_AGE_DAYS = 90
OFFLINE_CLOCK_SKEW_S = 600
# The money signs the quick-add line reads as a budget slice, and the currency each one means.
QUICK_LINE_CURRENCIES: tuple[tuple[str, str], ...] = (("€", "EUR"), ("$", "USD"), ("£", "GBP"))

# ---------------------------------------------------------------------------
# Finance role (roost/money/*) — M1 D7
# ---------------------------------------------------------------------------

DEFAULT_CURRENCY = "EUR"
CURRENCY_PATTERN = r"^[A-Z]{3}$"
# Where an expense with no project goes (LazyClaw's GENERAL_PROJECT_NAME).
GENERAL_PROJECT_NAME = "General"
MAX_EXPENSE_AMOUNT = Decimal("1000000")
MAX_CATEGORY_NAME_LENGTH = 40
MAX_EXPENSE_NOTE_LENGTH = 200
MAX_EXPENSE_VENDOR_LENGTH = 80
BULK_MOVE_MAX = 100              # expenses one bulk move may carry
# Repeating expenses (Task 12): a read makes at most this many missed charges per rule (the rest on the next read).
RECURRING_CATCH_UP_MAX = 24
UPCOMING_CHARGES_DAYS = 31       # "Upcoming charges" looks this many days ahead
PINNED_EXPENSES_MAX = 8          # starred expenses the Money tab's Pinned section shows
MONEY_RANGE_MAX_DAYS = 366       # the widest span GET /api/money/range answers
RECURRING_CADENCES = ("weekly", "monthly", "yearly")
# Money reports (Task 14): the trend's months, the CSV export's row cap, the General inbox's page.
MONEY_TREND_MONTHS = 6
MONEY_TREND_MONTHS_MAX = 24
CSV_EXPORT_MAX_ROWS = 10_000
GENERAL_INBOX_PAGE = 100
EXPENSE_LIST_LIMIT = 50
# Projects hub (H2, H8, H16): a project's status, its fixed palette (the first is the
# default), the budget bars' thresholds, list and page sizes, and a top-up's source.
PROJECT_STATUSES = ("active", "archived")
PROJECT_COLORS = ("#64748b", "#ef4444", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899")
DEFAULT_PROJECT_COLOR = PROJECT_COLORS[0]
BUDGET_WARN_PERCENT = 80          # bar turns amber
BUDGET_OVER_PERCENT = 100         # bar turns red
PROJECT_LIST_LIMIT = 100
PROJECT_PAGE_ITEMS = 20           # latest expenses / notes / documents on a project page
TOPUP_SOURCE_MAX_CHARS = 120
# Task ids one query asks for at once, when a project page reads the expenses linked to its tasks (H11).
TASK_EXPENSES_QUERY_CHUNK = 500
# The most project names one "Did you mean …?" or "Say which one: …" refusal lists (ProjectService.resolve).
PROJECT_MATCHES_SHOWN = 5
# The most task titles an expense tool's "Did you mean …?" or "several tasks match" refusal lists
# (roost/money/expense_links.py).
EXPENSE_TASK_MATCHES_SHOWN = 5
# The longest record id a money or project tool takes (an expense's, a top-up's); ids are 36-character UUIDs.
MAX_RECORD_ID_LENGTH = 64

# ---------------------------------------------------------------------------
# Notes role (roost/notes/*) — M2 D1
# ---------------------------------------------------------------------------

MAX_NOTE_TITLE_LENGTH = 200
MAX_NOTE_CONTENT_LENGTH = 100_000
MAX_NOTE_TAGS = 20
MAX_NOTE_TAG_LENGTH = 40
MAX_NOTE_QUERY_LENGTH = 200
# Search decrypts up to this many of the user's newest notes and matches in Python (D1).
NOTE_SCAN_LIMIT = 2000
NOTE_LIST_LIMIT = 200
NOTE_FIND_LIMIT = 10
NOTE_SNIPPET_CHARS = 160
NOTE_READ_MAX_CHARS = 8000
NOTE_LINKS_MAX = 50

# The SPA's Content-Security-Policy (M2 Task 5): images only from the gateway,
# data: and blob: (the PDF viewer and the Univer canvas), so markdown a note
# holds can never make the browser fetch another host.
SPA_CONTENT_SECURITY_POLICY = "img-src 'self' data: blob:"

# ---------------------------------------------------------------------------
# Memory and endless chat (roost/memory/)
# ---------------------------------------------------------------------------

MEMORY_PROMPT_BUDGET_CHARS = 1500
MEMORY_ITEM_MAX_CHARS = 240
MEMORY_PINNED_MAX = 5
MEMORY_TEXT_MAX_CHARS = 500
MEMORY_CAPTURE_MIN_CHARS = 40
MEMORY_CAPTURE_MAX_ITEMS = 3
MEMORY_CAPTURE_PER_HOUR = 6
MEMORY_CAPTURE_WINDOW_S = 3600
MEMORY_FADE_DAYS = 60
MEMORY_FADE_MAX_IMPORTANCE = 2
MEMORY_IMPORTANCE_DEFAULT = 3
MEMORY_IMPORTANCE_MIN = 1
MEMORY_IMPORTANCE_MAX = 5
MEMORY_SCAN_LIMIT = 500
MEMORY_RECALL_LIMIT = 10
MEMORY_WORKER_TIMEOUT_S = 60
CHAT_SUMMARY_TRIGGER = 80
CHAT_TAINT_KEEP = 12   # a tainted reply this far back (or older) is shown to the model as a placeholder
CHAT_KEEP_RECENT = 40
CHAT_SUMMARY_MAX_CHARS = 4000
CHAT_SUMMARY_INPUT_MAX_CHARS = 24000
CHAT_SUMMARY_LINE_MAX_CHARS = 1000
CHAT_SEARCH_SCAN_LIMIT = 5000
CHAT_SEARCH_LIMIT = 8
CHAT_SEARCH_SNIPPET_CHARS = 200
CHAT_TEXT_SEARCH_RESULTS_MAX = 30     # GET /api/chats/search: hits across every chat
CHAT_TEXT_SEARCH_QUERY_MAX = 100       # its ?q= length

# ---------------------------------------------------------------------------
# Documents (roost/documents/*) — M2 D2
# ---------------------------------------------------------------------------

MAX_DOCUMENT_TITLE_LENGTH = 120          # LazyClaw's docs / sheets _NAME_MAX
MAX_DOC_MARKDOWN_LENGTH = 100_000
MAX_SHEET_ROWS_PER_CALL = 500
MAX_SHEET_COLS = 26
MAX_SHEET_CELL_TEXT = 1000
MAX_SHEET_CELLS_PER_CALL = 500
MAX_PDF_BYTES = 20 * 1024 * 1024
# A doc or sheet snapshot saved from the Board, in JSON characters.
MAX_DOCUMENT_PAYLOAD_CHARS = 8_000_000
# The store's last guard on any stored body (a 20 MB PDF is ~27M base64 characters).
MAX_DOCUMENT_BODY_CHARS = 30_000_000
# What read_document and GET /api/documents/{id}/text show (LazyClaw's preview caps).
DOCUMENT_READ_MAX_CHARS = 4000
SHEET_READ_MAX_ROWS = 30
SHEET_READ_MAX_COLS = 10
DOCUMENT_LIST_LIMIT = 50
# A sheet's far corner as 0-based indexes: 100,000 rows and columns A to ZZ
# (ZZ100000). A cell past it is refused, from a tool's A1 edit or a Board save,
# so no read is ever asked to cover millions of rows.
MAX_SHEET_ROW_INDEX = 99_999
MAX_SHEET_COL_INDEX = 701
# A PDF's text is read page by page and stops after this many pages, or sooner
# at DOCUMENT_READ_MAX_CHARS.
PDF_READ_MAX_PAGES = 50
# How long read_document or /text waits for a document's text before refusing plainly.
DOCUMENT_READ_TIMEOUT_SECONDS = 20

# ---------------------------------------------------------------------------
# Profile (S1.9) — roost/talk/links.py, roost/gateway/routes/profile.py
# ---------------------------------------------------------------------------

# The Links tab shows at most this many distinct URLs.
LINKS_LIMIT = 200
# How many of a bot's own newest messages (across its own threads, not rooms)
# are scanned for links.
LINK_SCAN_MESSAGES = 2000
# The Documents tab's "Made by <bot>" lists, per record kind.
MADE_LIST_LIMIT = 50

# ---------------------------------------------------------------------------
# Computer (S1.8) — roost/desk/control.py, roost/desk/browser.py
# ---------------------------------------------------------------------------

# How long a bot's browser call waits while the user holds control (OpenMausBot's CONTROL_WAIT_MS).
CONTROL_WAIT_SECONDS = 45.0
SCREENSHOT_JPEG_QUALITY = 60

# ---------------------------------------------------------------------------
# Home (S1.4) — roost/talk/chats.py
# ---------------------------------------------------------------------------

# A chat row's one-line preview of its newest message, in characters (… included).
CHAT_PREVIEW_CHARS = 120

# ---------------------------------------------------------------------------
# Stuck flow (Piece A) — roost/desk/stuck.py, roost/stuck/
# ---------------------------------------------------------------------------

# All markers are lowercase: the detector matches them against casefolded text.
STUCK_CHALLENGE_WAIT_SECONDS = 8.0      # rung 1: wait this long, then repeat the call once
# Owner, 2026-10-31 ("when it hits an error, just reload the page"): open_page waits each of these and loads the
# page again while it answers a server error (5xx); roost/talk/server_error.py.
SERVER_ERROR_RELOAD_WAITS_S: Final = (3.0, 8.0)
STUCK_THIN_PAGE_CHARS = 1500            # a page with at most this much text is "thin" (a wall, not content)
STUCK_REASON_MAX_CHARS = 300            # ask_for_help's reason
STUCK_REQUEST_MAX_CHARS = 2000          # the original request kept on the card
STUCK_LIST_LIMIT = 50                   # GET /api/stuck
STUCK_CHALLENGE_TITLE_MARKERS = ("just a moment", "attention required", "verify you are human", "checking your browser")
STUCK_CHALLENGE_TEXT_MARKERS = ("verify you are human", "checking if the site connection is secure",
                                "enable javascript and cookies to continue", "press and hold",
                                "complete the security check", "are you a robot")
STUCK_CHALLENGE_URL_MARKERS = ("__cf_chl",)
STUCK_LOGIN_MARKERS = ("login", "log in", "log-in", "signin", "sign in", "sign-in")
STUCK_CODE_MARKERS = ("verification code", "two-factor", "2-step verification", "two-step verification",
                      "enter the code", "one-time code", "authentication code", "security code")
STUCK_REFUSED_STATUSES = frozenset({403, 429})
STUCK_PASSWORD_SELECTOR = 'input[type="password"]'
STUCK_CAPTCHA_FRAME_SELECTOR = ('iframe[src*="hcaptcha.com"], iframe[src*="challenges.cloudflare.com"], '
                                'iframe[src*="/recaptcha/"]:not([src*="size=invisible"])')
# "Use my main Brave" (Task 6): the keeper runs this argv plus the checked URL, with no shell.
MAIN_BROWSER_OPEN_ARGV = ("/usr/bin/open", "-a", "Brave Browser")
MAIN_BROWSER_OPEN_TIMEOUT_S = 10.0
MAIN_BROWSER_URL_MAX_CHARS = 2048

# Tasks & Money polish: the quick line's grammar and the task fields.
PM_GUESS_HOURS: Final = range(1, 8)          # a bare "at 5" is the afternoon: 1-7 means 13:00-19:00
TASK_ESTIMATE_MAX_MINUTES: Final = 6000
DAY_ONLY_DUE_HOUR: Final = 9                 # a "1h before" reminder on a day-only due counts from 09:00 local time
REPEAT_DEFAULT_HOUR: Final = 9               # a repeat word with no time ("every Monday") runs at 09:00 local time

REPEAT_RULE_MAX_EVERY: Final = 365           # "every N days/weeks/months": N is 1 to this (Amendment T)
PASTE_MAX_LINES: Final = 50                  # a pasted list makes at most this many tasks (and steps) at once
PASTE_MAX_LENGTH: Final = 20_000             # characters a pasted list may hold
EXPRESSION_MAX_TERMS: Final = 6              # numbers in one money sum ("€2x31"): at most this many

# Helpers (Models & helpers, Tasks 6-7): read-only workers a bot sends out at once.
MAX_HELPERS_AT_ONCE = 3
MAX_HELPERS_PER_RUN = 6
HELPER_MAX_STEPS = 12
HELPER_MAX_SECONDS = 300
HELPER_TASK_MAX_CHARS = 4000
HELPER_REPORT_MAX_CHARS = 4000

# Day notes (Board redesign G7)
MAX_DAY_NOTE_LENGTH = 500
MAX_DAY_NOTES_PER_DAY = 20
DAY_NOTES_RANGE_MAX_DAYS = 62
DAY_NOTE_MAX_YEARS = 5
DAY_NOTES_LIST_LIMIT = 2000

# Approval modes and Your Mac (roost/approvals/, roost/mac/, roost/keeper/macfs/)
APPROVAL_MODES: Final = ("ask", "auto_edit", "plan")
NEW_BOT_APPROVAL_MODE: Final = "auto_edit"   # owner, 2026-11-03: ordinary changes go straight through
# Full auto for a new bot (owner, 2026-11-03): its own model reviews a button Roost can't read. The v36 column's
# SQLite default stays 0 (migrations are additive), so the store writes this on create.
NEW_BOT_AUTO_REVIEW: Final = True
APPROVAL_TOPICS: Final = (
    "files", "tasks", "money", "notes", "documents", "projects", "memory", "team", "routines", "posting",
)
LOCKED_TOPICS: Final = frozenset({"posting"})
APPROVAL_PLAN_MAX_STEPS: Final = 20
APPROVAL_EDIT_TEXT_MAX: Final = 4000   # the words you send back with a Proposal's Edit
APPROVAL_TITLE_MAX_CHARS: Final = 120
APPROVAL_STEPS_MAX_BYTES: Final = 4_000_000
APPROVAL_DIFF_SHOWN_LINES: Final = 400
APPROVAL_ROW_SHOWN_CHARS: Final = 300   # a card row's text is cut here; "Open full" shows all of it
APPROVAL_ROW_MAX_DEPTH: Final = 6       # lists and objects nested deeper than this cannot be shown, so no card
MAC_GRANTS_MAX: Final = 20
MAC_LABEL_MAX_CHARS: Final = 40
MAC_SESSION_MINUTES: Final = 120
MAC_PICK_ARGV: Final = ("/usr/bin/osascript", "-e", 'POSIX path of (choose folder with prompt "Choose a folder for Roost")')
MAC_PICK_TIMEOUT_S: Final = 120
MAC_PICK_REQUEST_TIMEOUT_S: Final = 130
MAC_REQUEST_TIMEOUT_S: Final = 15
MAC_LIST_MAX_ENTRIES: Final = 500
MAC_FIND_MAX_HITS: Final = 200
MAC_FIND_MAX_ENTRIES: Final = 20_000
MAC_FIND_MAX_SECONDS: Final = 5
MAC_FIND_TEXT_FILE_MAX_BYTES: Final = 1_000_000
MAC_FIND_TEXT_TOTAL_MAX_BYTES: Final = 50_000_000
MAC_FIND_SNIPPETS: Final = 3
MAC_FIND_SNIPPET_CHARS: Final = 160
MAC_FIND_QUERY_MAX_CHARS: Final = 200
MAC_NAME_MAX_CHARS: Final = 120
MAC_READ_MAX_BYTES: Final = 1_000_000
MAC_WRITE_EXTS: Final = (".md", ".txt", ".csv")
MAC_PATH_MAX_PARTS: Final = 32
MAC_STAT_MAX_PATHS: Final = 50
MAC_BACKUPS_KEEP: Final = 20
MAC_BACKUPS_MAX_DAYS: Final = 30
MAC_OPS_PER_MINUTE: Final = 60
MAC_WRITES_PER_RUN: Final = 20
MAC_WRITES_WINDOW_S: Final = 600
MAC_GRANT_PUSH_INTERVAL_S: Final = 30
MAC_DENY_ROOTS: Final = ("/System", "/Library", "/usr", "/bin", "/sbin", "/etc", "/private", "/var", "/opt",
                         "/Applications", "/Volumes")
MAC_DENY_HOME_DIRS: Final = ("Library", "Roost", "Roost-review", ".Trash")
MAC_DENY_HOME_PATHS: Final = ("Desktop/Code_Projects/lazyclaw/data",)
MAC_DENY_NAME_GLOBS: Final = ("*.env", ".env*", "*.pem", "*.key", "*.p12", "id_*", "*.keychain*", "credentials*",
                              "*.sqlite", "*.db")
MAC_TRASH_DIR: Final = ".roost-trash"
OBSIDIAN_TRASH_DIR: Final = ".trash"
MAC_TMP_INFIX: Final = ".roost-tmp-"


# Computers 2.0, C1/C2 (docs/plans/2026-10-20-roost-computers-c1-c2.md)
COMPUTER_KINDS: Final = ("linux", "mac_brave")
COMPUTER_VNC_TICKET_TTL_S: Final = 30.0     # a screen ticket opens one socket, within this long
DEFAULT_COMPUTER: Final = "linux"          # owner 2026-10-22: every new bot gets its Linux computer; Mac Brave is an option
COMPUTER_IMAGE: Final = "roost-computer:dev"
EGRESS_IMAGE: Final = "roost-egress:dev"
COMPUTER_CONTAINER_PREFIX: Final = "roost-computer-"
COMPUTER_NETWORK_PREFIX: Final = "roost-net-"
COMPUTER_PROFILE_VOLUME_PREFIX: Final = "roost-profile-"
EGRESS_CONTAINER: Final = "roost-egress"
EGRESS_OUT_NETWORK: Final = "roost-out"
EGRESS_PORT: Final = 3128                  # inside the VM only; never published
EGRESS_UID: Final = 10003
COMPUTER_UID: Final = 10002
COMPUTER_MEMORY: Final = "1500m"
COMPUTER_SHM_SIZE: Final = "512m"
COMPUTER_CPUS: Final = "1.5"
COMPUTER_PIDS_LIMIT: Final = "512"
COMPUTER_TMPFS_TMP: Final = "/tmp:rw,size=256m"
COMPUTER_SCREEN_WIDTH: Final = 1280
COMPUTER_SCREEN_HEIGHT: Final = 800
COMPUTERS_MAX_RUNNING: Final = 3
COMPUTER_PAUSE_AFTER_S: Final = 300        # idle -> docker pause (RAM kept, ~0.2 s to wake)
COMPUTER_SWEEP_EVERY_S: Final = 30
COMPUTER_START_MIN_FREE_MB: Final = 600    # the VM must have this much free to start one more
COMPUTER_ROOM_WAIT_S: Final = 60
COMPUTER_ROOM_POLL_S: Final = 5
COMPUTERS_BUSY_TEXT: Final = "All computers are busy right now. Try again in a few minutes."
COMPUTER_WAITING_LINE: Final = "Waiting for a free computer"
COMPUTER_BOOT_TIMEOUT_S: Final = 20        # until roost-pipe can reach cdp.sock
COMPUTER_DOCKER_CALL_TIMEOUT_S: Final = 15.0
LIVE_SHORT_SESSION_S: Final = 60.0       # a live screen socket that ends sooner is logged as a warning
LIVE_VIEWERS_MAX: Final = 2                # view sockets per bot (tabs); control is one more
LIVE_RELAY_CHUNK_MAX: Final = 262_144
RFB_CLIENT_VERSION: Final = b"RFB 003.008\n"
RFB_SECURITY_NONE: Final = 1
RFB_SET_ENCODINGS_MAX: Final = 64
RFB_FENCE_MAX: Final = 64
RFB_EXT_CLIPBOARD_ENCODING: Final = -1063131698   # 0xC0A1E5CE, always stripped
LIVE_PASTE_MAX_CHARS: Final = 2000
LIVE_INPUT_MAX_PER_SECOND: Final = 240
LIVE_INPUT_RATE_WINDOW_S: Final = 1.0
LIVE_LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1"})
LIVE_FORWARDED_HEADERS: Final = ("forwarded", "x-forwarded-for", "x-real-ip")
# Tailscale's own address ranges: `tailscale serve` (tailnet only) forwards the phone with one of these.
LIVE_TAILNET_NETWORKS: Final = ("100.64.0.0/10", "fd7a:115c:a1e0::/48")
LIVE_CLOSE_GIVEN_BACK: Final = 4000
LIVE_CLOSE_PROTOCOL: Final = 4400
LIVE_CLOSE_UNAUTHENTICATED: Final = 4401
LIVE_CLOSE_REFUSED: Final = 4403
LIVE_CLOSE_NOT_FOUND: Final = 4404
LIVE_CLOSE_NOT_HELD: Final = 4409
LIVE_CLOSE_ASLEEP: Final = 4410
LIVE_CLOSE_TOO_MANY: Final = 4429
LIVE_CLOSE_UNAVAILABLE: Final = 4503
SITE_LOGIN_LABEL_MAX_CHARS: Final = 100
SITE_LOGIN_LIST_LIMIT: Final = 50
SITE_LOGINS_IN_PROMPT: Final = 10
FAKE_SCREEN_WIDTH: Final = 320
FAKE_SCREEN_HEIGHT: Final = 200

# --- Routines and Plan ---
ROUTINE_MAX_TIMES: Final = 12
ROUTINE_MIN_INTERVAL_MINUTES: Final = 15
ROUTINE_CRON_CHECK_FIRES: Final = 50
ROUTINE_TICK_SECONDS: Final = 30
ROUTINE_JITTER_SECONDS: Final = 90
ROUTINE_LATE_GRACE_SECONDS: Final = 600
ROUTINE_TICK_MAX_FIRES: Final = 50
SCHEDULER_TICK_TIMEOUT_SECONDS: Final = 20
SCHEDULER_TICK_OVERRIDE_MAX_SECONDS: Final = 3600   # the scripted E2E's ROOST_SCHEDULER_TICK_SECONDS upper bound
ROUTINES_PER_BOT_MAX: Final = 20
ROUTINE_MODEL_FAILURES_MAX: Final = 2   # a routine's own model: failed runs in a row before it goes back to the bot's
ROUTINES_PER_USER_MAX: Final = 100
ROUTINE_NAME_MAX: Final = 80
ROUTINE_INSTRUCTIONS_MAX: Final = 4000
ROUTINE_PREVIEW_COUNT: Final = 5
ROUTINE_CARD_PREVIEW_COUNT: Final = 3
ROUTINE_RUNS_PAGE: Final = 50
ROUTINE_RECENT_RUNS_DEFAULT: Final = 20   # GET /api/routines/runs without ?limit=
ROUTINE_RECENT_RUNS_MAX: Final = 100
RUN_LOG_RETENTION_DAYS: Final = 90
ROUTINE_ASK_MAX_WAIT_HOURS: Final = 24
ROUTINE_PROPOSALS_OPEN_PER_BOT_MAX: Final = 5
# A routine the bot finished (owner, 2026-11-11, docs/plans/2026-11-11-roost-routine-finish.md): paused and deleted
# by the scheduler after this many days unless the user resumes it; its reason is one short sealed line.
ROUTINE_FINISHED_KEEP_DAYS: Final = 7
ROUTINE_FINISHED_REASON_MAX: Final = 200
REPORT_HEADLINE_MAX: Final = 80
REPORT_TEXT_MAX_CHARS: Final = 8000
REPORT_QUIET_SENTINEL: Final = "[nothing new]"
# A line before the sentinel that only says what the bot is checking ("Checking the Deduci chat.", "Revisando…")
# keeps the reply quiet (owner, 2026-11-07): a short line whose first word is a gerund, nothing more.
REPORT_NARRATION_LINE_MAX_CHARS: Final = 100
REPORT_NARRATION_WORD_ENDINGS: Final = ("ing", "ando", "iendo")
REPORTS_PER_BOT_PER_HOUR: Final = 6
# A task reminder card's answer, stored on its Report (2026-10-26): Done · Failed · Reschedule · Skip.
REMINDER_ANSWERS: Final = ("done", "failed", "rescheduled", "skipped")
REMINDER_DUE_PATTERN: Final = r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$"   # a Reschedule's new due: a local day, maybe a time
REMINDER_DUE_MAX: Final = 16
QUESTION_MAX_CHARS: Final = 500
QUESTION_ANSWER_MAX_CHARS: Final = 1000
QUESTIONS_PER_RUN_MAX: Final = 3
QUESTIONS_OPEN_PER_BOT_MAX: Final = 20
QUESTION_ANSWERS_IN_PROMPT: Final = 5
REMINDER_LATE_GRACE_SECONDS: Final = 21_600
REMINDER_LOOKBACK_HOURS: Final = 48
REMINDER_LOOKAHEAD_DAYS: Final = 8
REMINDERS_PER_TICK_MAX: Final = 100
USAGE_RESERVE_FRACTION: Final = 0.10
PLAN_MAX_BYTES: Final = 262_144
PLAN_MAX_ITEMS: Final = 2000
PLAN_ARCHIVE_DAYS: Final = 60
PLAN_WRITES_PER_RUN: Final = 20
PLAN_PROMPT_ITEMS: Final = 15
PLAN_ID_LENGTH: Final = 6
ROUTINE_SLOT_LOOKBACK_HOURS: Final = 48   # a tick looks back this far for missed slots, never further
REPORT_LOOKUP_MESSAGES: Final = 200       # how far back a run's history looks for the message of its Report
RECONCILE_GRACE_SECONDS: Final = 120      # a finished item's run row is left this long for its after-run pass
ROUTINE_SLOT_SCAN_MAX: Final = 500        # and counts at most this many slots (a 15-minute cron has 192 in 48 h)
ROUTINE_OCCURRENCES_MAX: Final = 400      # GET /api/routines/occurrences returns at most this many run times
ROUTINE_OCCURRENCE_SPAN_DAYS_MAX: Final = 62   # and covers at most this many days (a month grid shows 42)

# Routine watch (owner, 2026-11-04, docs/plans/2026-11-04-roost-routine-watch.md): "Only run when the page changes".
# Roost itself reads the page (no model) every few minutes and queues the routine's run only when it changed.
WATCH_EVERY_MIN_MINUTES: Final = 5            # never checked more often than this
WATCH_EVERY_MAX_MINUTES: Final = 1440
WATCH_EVERY_DEFAULT_MINUTES: Final = 5
WATCH_URL_MAX: Final = 2048
WATCH_PART_MAX: Final = 120
WATCH_TAIL_LINES: Final = 12                  # the newest lines of a message pane
WATCH_CONTEXT_LINES: Final = 3                # lines kept after a line that names the part (a row's time, preview)
WATCH_HITS_MAX: Final = 3                     # at most this many such lines
# A chat list row's stamp (its time or day), which marks where the next row starts (owner, 2026-11-10).
WATCH_DAY_WORDS: Final = frozenset({
    "yesterday", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "ayer", "hoy", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
})
WATCH_SNAPSHOT_MAX_CHARS: Final = 6000        # the stored part, cut to this
WATCH_CHANGE_MAX_CHARS: Final = 2000          # what the change run is told, cut to this
WATCH_READY_TIMEOUT_S: Final = 8.0
# A check that can't read the page (owner, 2026-11-10, docs/plans/2026-11-10-roost-self-healing.md): failures in a
# row fold into one "Couldn't check" run-log line; at this many the bot's chat says so once (a good read clears it).
WATCH_FAILS_STUCK: Final = 3
WATCH_NO_ROOM_NOTE_AFTER: Final = 2           # one skip for room stays quiet; from the second in a row it is a line
WATCH_STALE_TRIGGER_INTERVALS: Final = 2      # a waiting check older than this many intervals is dropped and queued again
# A routine's last error, a fixed word in ``routines.last_error_kind`` (plaintext, no user content; v47).
ROUTINE_ERROR_NO_ANSWER: Final = "no_answer"  # the computer didn't answer
ROUTINE_ERROR_NO_ROOM: Final = "no_room"      # no free computer
ROUTINE_ERROR_RUN: Final = "run_error"        # a run didn't finish
# Words in "what part to watch" that name no part ("the physio chat" looks for "physio").
WATCH_STOP_WORDS: Final = frozenset({
    "the", "a", "an", "my", "our", "of", "on", "in", "el", "la", "los", "las", "mi", "de", "del", "en",
    "chat", "conversation", "box", "section", "part", "page", "area",
    # what the owner asks for, never on the page (owner, 2026-11-10: "new messages from …" was never found)
    "new", "message", "messages", "from", "any", "unread", "mensaje", "mensajes", "nuevo", "nuevos", "nueva", "nuevas",
})
# A name in quotes or brackets, or a phone number, is the watched part on its own, the rest of the sentence aside
# (owner, 2026-11-10).
WATCH_QUOTED: Final = r'"([^"]+)"|“([^”]+)”|«([^»]+)»|\(([^()]+)\)|(\+?\d[\d ().-]{6,}\d)'
WATCH_PANE_ROLES: Final = frozenset({"log", "feed", "application"})   # a chat's message pane
# A part that names every chat watches the whole chat list (owner, 2026-11-11): its area by name, else the largest list.
WATCH_ALL_CHATS: Final = ("all chats", "all my chats", "all the chats", "every chat", "chat list", "all messages",
                          "all my messages", "all conversations", "todos los chats", "todos mis chats",
                          "lista de chats", "todos los mensajes")
WATCH_LIST_ROLES: Final = frozenset({"grid", "list", "listbox", "treegrid"})
# Chats in the plural with no name in the part mean every chat too ("personal one-to-one chats").
WATCH_CHATS_PLURAL: Final = frozenset({"chats", "conversations", "dms", "conversaciones"})
WATCH_PAGE_ROLES: Final = ("main", "article", "document")              # the main text, when no part is found
# Words that change on a page without anything new (a chat's "online", "typing…"), dropped before comparing.
WATCH_NOISE_WORDS: Final = ("online", "typing…", "typing...", "escribiendo…", "escribiendo...", "en línea",
                            "last seen", "últ. vez", "now", "ahora", "today", "hoy", "yesterday", "ayer")

# Chat feel (v1): the words On it shows before anything has loaded.
FIRST_LINE_ACTIVITY: Final = "reading your message"
# Run notes (owner, 2026-11-04): the bot's words between steps join the activity pill's steps, one line this long.
RUN_NOTE_MAX_CHARS: Final = 200

# Chat feel: options cards and decisions
CHOICE_OPTIONS_MIN = 2
CHOICE_OPTIONS_MAX = 4
CHOICE_QUESTION_MAX_CHARS = 300
CHOICE_OPTION_MAX_CHARS = 120
CHOICE_WHY_MAX_CHARS = 300
CHOICE_OWN_ANSWER_MAX_CHARS = 1000
DECISIONS_LIST_MAX = 200
DECISION_REUSE_MAX_DAYS = 30
# A question with one of these words is always asked again, never answered from an earlier decision.
DECISION_DANGEROUS_WORDS = ("delete", "send", "pay", "buy", "submit", "accept", "remove", "publish")
# Tapbacks: the fixed keys a reaction may carry (chat-feel Task 8).
REACTION_KEYS: Final = ("thumbs_up", "heart", "laugh", "check", "question")

# ---------------------------------------------------------------------------
# Computer use (C3) (docs/plans/2026-10-22-roost-computers-c3.md)
# ---------------------------------------------------------------------------
CU_TOOLS: Final = ("look", "wait_ready", "scroll", "click", "type", "press_key", "open_app",
                   "list_tabs", "switch_tab", "close_tab",      # these three: B1, 2026-10-23
                   "read_text", "read_pdf",                     # fast pages, 2026-10-26
                   "use_saved_login",                           # owner, 2026-11-05: the browser's saved login
                   "use_vault_password",                        # owner, 2026-11-08: Vault: passwords, on your Yes
                   "send_screenshot")                           # owner, 2026-11-05: your chat gets the screen
CU_ACT_TOOLS: Final = frozenset({"click", "type", "press_key"})
CU_VIEW_MAX_W: Final = 1280
CU_VIEW_MAX_H: Final = 800
CU_JPEG_QUALITY: Final = 60
CU_IMAGE_MAX_BYTES: Final = 350_000
CU_CROP_PAD_PX: Final = 24
CU_CROP_MAX_W: Final = 480
CU_CROP_MAX_H: Final = 200
CU_CROP_MAX_BYTES: Final = 60_000
CU_MASK_FILL: Final = (128, 128, 128)            # the grey painted over field boxes
CU_LOOK_TARGETS_MAX: Final = 60
CU_LOOK_TEXT_CHARS: Final = 3000
CU_GLANCE_TEXT_CHARS: Final = 800               # fast pages: the page text an act's glance carries (read_text reads more)
CU_GLANCE_TARGETS_MAX: Final = 30               # the controls an act's glance lists (a look lists CU_LOOK_TARGETS_MAX; tokens, 2026-11-07)
CU_AREAS_MAX: Final = 8                          # fast pages: readable areas a look lists for read_text
CU_AREA_MIN_CHARS: Final = 40                    # an area with less text than this is not listed
CU_READ_TEXT_CHARS: Final = 8000                 # read_text: characters per call (start= reads on)
CU_READ_FIND_MAX: Final = 80                     # read_text: the longest find words
CU_READ_FIND_HITS_MAX: Final = 20                # read_text: matches shown for find
CU_READ_FIND_CONTEXT: Final = 2                  # read_text: lines shown before and after each match
CU_PDF_MAX_BYTES: Final = 15_000_000             # read_pdf: the largest PDF the bot's browser fetches into memory
CU_PDF_PAGES_MAX: Final = 50                     # read_pdf: pages read from one PDF
CU_PDF_PARSE_TIMEOUT_S: Final = 20.0             # read_pdf: how long reading one PDF may take
CU_FETCH_CHUNK_BYTES: Final = 1_000_000          # read_pdf: bytes per IO.read from the browser's stream
CU_BLOB_B64_CHUNK: Final = 0x8000                # read_pdf: bytes per String.fromCharCode run when a blob: PDF is base64'd in the page
# Owner, 2026-11-03: longer work on the screen (was 60 looks, 40 acts, 90 steps, 1200 s, 2 tries).
CU_MAX_LOOKS_PER_RUN: Final = 200
CU_MAX_ACTS_PER_RUN: Final = 120
CU_MAX_MODEL_STEPS: Final = 250                  # replaces MAX_STEPS once a run has used a screen tool
CU_RUN_DEADLINE_S: Final = MAX_RUN_SECONDS       # the run's own wall time (the turn's timeout) bounds the loop
CU_TRIES_PER_TARGET: Final = 4                   # each try after a miss looks again first (session.after_miss)
CU_READY_TIMEOUT_S: Final = 10.0
CU_READY_STABLE_MS: Final = 500
CU_READY_PROBE_W: Final = 160
CU_READY_PROBE_H: Final = 100
CU_READY_DIFF_MAX: Final = 0.01                  # share of probe pixels that may differ
CU_READY_POLL_MS: Final = 100
CU_BOX_TOLERANCE_PX: Final = 8
CU_TYPE_MAX_CHARS: Final = 5000                # owner, 2026-11-01: Upwork's cover letter limit
# Owner, 2026-11-01: ``type`` pastes the whole text at once (roost/desk/box_text.py ``paste_text``), so a line break
# or a tab is text, never a key; every other control character is refused.
CU_TYPE_TEXT_CONTROLS: Final = frozenset({"\n", "\t"})
# Owner, 2026-10-27: typing replaces what a box holds, and the box is read back afterwards (roost/desk/box_text.py).
CU_BOX_TEXT_MAX_CHARS: Final = 2 * CU_TYPE_MAX_CHARS   # the longest box text read back (a draft on a Send card too)
# The Send card (owner, 2026-11-03): every box a run typed into shows as a row named by the box's label.
CU_DRAFT_BOXES_MAX: Final = 8                  # the newest boxes a run typed into that a Send card shows
CU_DRAFT_LABEL_MAX_CHARS: Final = 60           # a box's label as its row's name
CU_TYPE_TRIES: Final = 2                               # typing again once when the box doesn't hold the text
CU_SEARCH_TEXT_MAX: Final = 100
CU_TYPE_APPROVED_MIN_CHARS: Final = 3          # shorter typed text must be a whole message or line of yours
CU_EXPECT_MAX_CHARS: Final = 120
CU_TARGET_TEXT_MAX: Final = 120
# A checkbox or radio this small (an sr-only 1x1 input, owner 2026-11-04) is aimed at through its label's box.
CU_HIDDEN_CONTROL_PX: Final = 2
CU_LABEL_SHOWN_CHARS: Final = 80
# The computer card (docs/plans/2026-10-23-roost-computer-card.md): a computer_step frame's line is cut to this,
# and the snapshot keeps each bot's current run's newest steps (in memory only).
COMPUTER_STEP_LINE_MAX: Final = 120
COMPUTER_STEPS_KEPT: Final = 40
# A finished run's steps stay too (one per chat, the newest), so a restarted phone still shows the kept card.
COMPUTER_KEPT_RUNS_PER_BOT: Final = 5
RUN_STEPS_KEPT: Final = 60          # the activity pill: a bot's current run's newest steps in the live snapshot
# Keeping the cache warm (docs/plans/2026-11-09-roost-tool-groups.md §4, 2026-11-10): the prompt cache's prefix is
# tools → system → messages, so the tool list never shrinks mid-run, a thread's recent groups start loaded, and old
# tool results fold to a stub in batches (one cache break per batch, not one per step).
RECENT_GROUP_RUNS: Final = 3                    # a thread's last runs whose used tool groups its next run starts with
RECENT_GROUP_THREADS: Final = 500               # threads the runner keeps recent groups for (in memory, oldest dropped)
COMPACT_AFTER_STEPS: Final = 12                 # a tool result with this many results after it may fold to a stub
COMPACT_BATCH_STEPS: Final = 10                 # the fold moves in batches of this many results
COMPACT_KEEP_RESULTS: Final = 3                 # the newest results always stay whole
COMPACT_MIN_CHARS: Final = 400                  # a shorter result (an error, an id, "Done") never folds
CU_SCROLL_MAX_NOTCHES: Final = 25               # fast pages: one scroll call (sent in pieces, below)
CU_SCROLL_NOTCHES_PER_INPUT: Final = 10         # one scroll input: the keeper and roost-input's MAX_NOTCHES
CU_SCROLL_DEFAULT_NOTCHES: Final = 5
CU_MOVE_STEPS: Final = 8
CU_MOVE_STEP_MS: Final = 12
CU_TYPE_DELAY_MS: Final = 35
CU_INPUT_TIMEOUT_S: Final = 10.0                 # roost-input's budget for one input, plus typing time below
CU_TYPE_TIMEOUT_FACTOR: Final = 2.0              # typing gets this many times CU_TYPE_DELAY_MS per character
CU_INPUT_TIMEOUT_GRACE_S: Final = 5.0            # the keeper waits this much longer than roost-input, the desk longer still
CU_WINDOW_MATCH_PX: Final = 24                   # how far xdotool's view of the bot's window may differ from CDP's
CU_INPUT_MAX_PER_SECOND: Final = 10
CU_KEYS: Final = {                               # model's name -> xdotool keysym; nothing else is accepted
    "Enter": "Return", "Tab": "Tab", "Shift+Tab": "ISO_Left_Tab", "Escape": "Escape", "Backspace": "BackSpace",
    "Delete": "Delete", "ArrowUp": "Up", "ArrowDown": "Down", "ArrowLeft": "Left", "ArrowRight": "Right",
    "PageUp": "Page_Up", "PageDown": "Page_Down", "Home": "Home", "End": "End", "Space": "space",
    "Back": "XF86Back",                           # the browser's Back (2026-10-25): a keysym, no modifier
}
# Owner, 2026-11-05: a key that only closes a pop-up runs with no fresh look (still through the gate as usual).
CU_LOOK_FREE_KEYS: Final = frozenset({"Escape"})
CU_CLOSERS_SHOWN_MAX: Final = 3                # a covered click names at most this many of the dialog's close buttons
CU_BLIND_SCROLLS_MAX: Final = 3                # scrolls in a row without a look; the next one asks for a look (2026-10-25)
CU_TARGET_KINDS: Final = ("button", "link", "tab", "checkbox", "radio", "option", "menuitem", "row", "field", "any")
# Amendment 2026-10-21 (user): Browsing actions do NOT ask by default; "browsing" is an ordinary opt-in topic,
# so no topic asks by default and there is no opt-out word.
DEFAULT_ASK_TOPICS: Final = frozenset[str]()
CU_APPROVED_MESSAGES_MAX: Final = 500            # your newest messages in the chat that typed text may quote
CU_APPROVED_CARDS_MAX: Final = 50                # answered cards in the chat whose approved text may be typed again
# Owner, 2026-11-05: a site a routine names joins its fence once its bot opened that site from your own chat lately.
ROUTINE_CHAT_SITE_DAYS: Final = 30               # how far back such an open counts
ROUTINE_CHAT_SITE_ROWS: Final = 500              # the newest such opens read per run
ROUTINE_CHAT_SITE_REASONS: Final = ("fresh_open", "owner_site")   # gate reasons that mean your own chat opened it
# --- Tabs and sign-in (docs/plans/2026-10-23-roost-tabs-signin-flow.md) ---
# A new tab on one of these hosts (or a subdomain) stays open while the guards are armed: a sign-in popup.
SECRET_FIELD_KINDS: Final = ("password", "code")   # B3: what ask_secret_field may ask the owner to type
SECRET_VALUE_MAX_CHARS: Final = 256               # B3: the masked field's longest value
# Vault: passwords (docs/plans/2026-11-08-roost-vault-passwords.md): the longest site, user name and password
VAULT_HOST_MAX_CHARS: Final = 253
VAULT_USERNAME_MAX_CHARS: Final = 254
VAULT_PASSWORD_MAX_CHARS: Final = SECRET_VALUE_MAX_CHARS
CU_TABS_MAX: Final = 30                          # list_tabs shows at most this many; a tab number is 1..this
CU_RUN_TABS_MAX: Final = 4                       # D5: past this many tabs, a run closes the oldest one it opened
CU_FIRST_TAB_WAIT_S: Final = 3.0                 # D5: a Brave just started gets this long to show its first tab
CU_FIRST_TAB_POLL_S: Final = 0.25
SIGN_IN_POPUP_HOSTS: Final = (
    "accounts.google.com", "appleid.apple.com", "login.microsoftonline.com", "login.live.com",
)
# --- Full computer, Step 1 (docs/plans/2026-10-23-roost-full-computer.md): the whole screen, any window ---
SAVED_LOGIN_POPUP_WAIT_S: Final = 0.4           # use_saved_login: the browser's saved-login list opens after focus
CU_FREE_ACT_TOOLS: Final = frozenset({"open_app", "switch_tab", "close_tab", "use_saved_login", "use_vault_password"})   # acts with no page to resolve: free inside the computer (D1)
CU_OPEN_APPS: Final = ("browser", "files", "terminal", "images")    # open_app's fixed apps (roost-input mirrors)
CU_APP_NAME_RE: Final = r"[a-z0-9][a-z0-9+.-]{1,62}"               # an installed package's name, as open_app takes it
CU_OPEN_APP_WHY_MAX: Final = 200                 # open_app's optional reason
CU_APP_LABELS: Final = {"browser": "the browser", "files": "Files", "terminal": "Terminal", "images": "Images"}
CU_BROWSER_WINDOWS_MAX: Final = 16               # Brave windows roost-input's `browsers` lists (each blacked out)
CU_DESKTOP_SETTLE_S: Final = 1.0                 # wait_ready on the desktop: one short pause, no page to watch
CU_RERUN_SETTLE_S: Final = 1.0                   # an approved re-run that had to bring Brave up waits this first
CU_SCREEN_GRAB_TIMEOUT_S: Final = 8.0            # one whole-screen grab through the VNC relay, handshake included
CU_SCREEN_NAME_MAX: Final = 256                  # the longest desktop name a grab accepts from the server
CU_SCREEN_RECTS_MAX: Final = 4096                # rectangles in one framebuffer update
CU_SCREEN_CUT_TEXT_MAX: Final = 1_000_000        # a server cut text the grab skips; anything longer fails it
# --- Skills (docs/plans/2026-10-21-roost-skills.md, schema v26) ---
SKILL_NAME_MAX: Final = 80
SKILL_USE_WHEN_MAX: Final = 200
SKILL_BODY_MAX: Final = 8000
SKILLS_PER_USER_MAX: Final = 100
SKILLS_PROMPT_BUDGET_CHARS: Final = 2000
SKILL_READS_PER_RUN_MAX: Final = 20            # owner, 2026-11-03 (was 5)
# Skill search (owner, 2026-10-31, "like LazyClaw"): search_skills answers with the best few, and the index puts the
# skills a request names first. Scores: a word in the name counts most, then Use when, then the steps.
SKILL_SEARCH_RESULTS_MAX: Final = 5
SKILL_SEARCH_QUERY_MAX: Final = 200
SKILL_SEARCH_WEIGHTS: Final = (3, 2, 1)          # name, Use when, steps
SKILL_PROPOSALS_OPEN_PER_BOT_MAX: Final = 5
TEMPLATE_SKILLS_MAX: Final = 20
# --- Steer (docs/plans/2026-10-22-roost-steer.md): a busy bot reads your new message mid-work ---
STEER_DEBOUNCE_SECONDS: Final = 1.5              # a NEW run on your messages waits until the newest is this old
STEER_DEBOUNCE_MAX_SECONDS: Final = 6.0          # ...but never longer than this in all
STEER_DEBOUNCE_OVERRIDE_MAX_SECONDS: Final = 10.0  # ROOST_STEER_DEBOUNCE_SECONDS upper bound (scripted mode only)
STEER_MAX_RESTARTS: Final = 2                    # restarts per run while nothing happened; after that it steers
STEER_TURN_PREFIX: Final = "(New message from the user while you were working.) "
# "read" for the gate, but each leaves something behind (queued work, a card): a restart would repeat it.
STEER_SIDE_EFFECT_TOOLS: Final = frozenset({"ask_bot", "suggest_bot", "suggest_model"})
STOP_GRACE_SECONDS: Final = 20.0                 # Stop waits this long for the next boundary, then cancels the run
STOP_SKIPPED_TEXT: Final = "Not run: the user pressed Stop."
STOP_DONE_LINES_MAX: Final = 8                   # the Stopped line names at most this many things done
# --- Sign-in card (docs/plans/2026-10-22-roost-signin.md, schema v27) ---
SITE_CLEAR_STORAGE_TYPES: Final = "all"          # Storage.clearDataForOrigin: cookies, local storage, IndexedDB, caches
SITE_CLEAR_SCHEMES: Final = ("https", "http")
SITE_HOST_MAX_CHARS: Final = 253
# Two-label public suffixes a site never is: clearing one would sign the bot out of every site under it.
SITE_CLEAR_REFUSED_SUFFIXES: Final = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "com.au", "net.au", "org.au", "co.nz", "co.jp", "ne.jp",
    "com.br", "com.mx", "com.ar", "com.tr", "com.cn", "com.hk", "com.sg", "co.in", "co.za", "co.kr", "com.es",
    "github.io", "herokuapp.com", "vercel.app", "netlify.app", "pages.dev", "web.app", "firebaseapp.com",
})
SIGN_IN_WHY_MAX_CHARS: Final = 300               # request_sign_in's why
# --- Teach a task (docs/plans/2026-10-22-roost-teach.md, schema v28) ---
TEACH_STEPS_MAX: Final = 60                      # steps one teach session records; later ones are dropped
TEACH_CAPTURE_TIMEOUT_S: Final = 0.5             # how long one capture may hold a press before it is forwarded
TEACH_DESCRIPTION_MAX: Final = 200               # your optional one-line "what this is"
TEACH_LABEL_MAX: Final = 80                      # a control's label kept in a step
TEACH_TITLE_MAX: Final = 120                     # a page title kept in a step
TEACH_PATH_MAX: Final = 120                      # a URL path kept in a step (never its query or fragment)
TEACH_WORKER_AGENT: Final = "teach-skill"
# --- Replies (docs/plans/2026-10-22-roost-replies.md) ---
REPLY_QUOTE_CHARS: Final = 120                   # a reply's server-made quote of the message it answers (… included)
MESSAGE_ID_MAX: Final = 64                       # a message id a client sends (a uuid is 36)
INSTRUCTION_PROPOSALS_OPEN_PER_BOT_MAX: Final = 1
INSTRUCTION_WHY_MAX: Final = 500                 # the one-line reason on an "Update my instructions?" card
# A bot's instructions, in Markdown sections in this order (roost/bots/instruction_sections.py).
INSTRUCTION_SECTIONS: Final = ("Who you are and context", "What you do", "Rules", "Tone", "Team")
# --- Obsidian track (docs/plans/2026-10-22-roost-obsidian.md, schema v30) ---
MAX_BOT_TOPIC_TAGS: Final = 5                    # topic tags a bot may give one record
TOPIC_TAG_MAX_CHARS: Final = 32
TAG_SLUG_MAX_CHARS: Final = 30                  # "project:" + 30 fits a 40-character note tag
BOT_TAG_PREFIX: Final = "bot"                    # bot:<slug> on everything a bot writes
PROJECT_TAG_PREFIX: Final = "project"            # project:<slug> when the record is linked to a project
JOURNAL_ENTRY_MAX_CHARS: Final = 500
JOURNAL_DAY_MAX_CHARS: Final = 20_000            # one day's Markdown; a full day refuses more entries
JOURNAL_RECENT_DAYS: Final = 30                  # days the Info fold lists
JOURNAL_SEARCH_LIMIT: Final = 20
JOURNAL_SCAN_DAYS: Final = 400                   # days a search decrypts, newest first
JOURNAL_WRITE_RETRIES: Final = 3                 # a lost compare-and-swap is tried again this many times
JOURNAL_RUN_LINE_MAX_STEPS: Final = 6            # distinct steps one run's line names
VAULT_EXPORT_ROOT: Final = "Roost"               # the folder inside the grant everything goes under
VAULT_EXPORT_DEBOUNCE_S: Final = 30.0
VAULT_EXPORT_RETRY_S: Final = 70.0               # after the keeper's per-minute limit
VAULT_EXPORT_ACTOR_ID: Final = "6f1d2c3b-7a4e-4b5c-9d8e-0a1b2c3d4e5f"   # the keeper's id for export steps
VAULT_EXPORT_NAME_MAX_CHARS: Final = 80
VAULT_EXPORT_MANIFEST_MAX: Final = 5000
VAULT_EXPORT_JOURNAL_DAYS: Final = 366
VAULT_EXPORT_TRIGGERS: Final = frozenset({"tasks_changed", "notes_changed", "money_changed", "journal_changed"})
# --- Programs: a bot's own workspace (docs/plans/2026-10-22-roost-programs.md) ---
WORKSPACE_DIR: Final = "/workspace"              # the bind mount inside roost-desk-<bot_id> (roost/keeper/workspaces.py)
PROGRAM_TIMEOUT_DEFAULT_S: Final = 60
PROGRAM_TIMEOUT_MAX_S: Final = EXEC_TIMEOUT_S    # the keeper refuses more (roost/keeper/app.py)
PROGRAM_COMMAND_MAX_CHARS: Final = MAX_EXEC_COMMAND_LENGTH
PROGRAM_PATH_MAX_CHARS: Final = 512
PROGRAM_FILE_MAX_CHARS: Final = 60_000           # base64 of it stays well under Linux's 128 KiB per argument
PROGRAM_READ_MAX_CHARS: Final = 12_000           # under the keeper's 16 000-character output cut
PROGRAM_LIST_MAX_ENTRIES: Final = 200
PROGRAM_LIST_MAX_CHARS: Final = 12_000
PROGRAM_OUTPUT_TO_MODEL_CHARS: Final = 6_000     # each of stdout and stderr, first and last halves kept
PROGRAM_LINE_OUTPUT_CHARS: Final = 4_000         # the output kept in the chat's "Ran:" line
PROGRAM_CALLS_PER_RUN: Final = 30                # unapproved run_program + write_file calls in one run
PROGRAM_RUNS_REMEMBERED: Final = 500             # run ids whose counts are kept in memory
PROGRAM_FILE_OP_TIMEOUT_S: Final = 30            # write_file, read_file and list_files
# Wipe workspace: the container's tmpfs folders are emptied with /workspace, so nothing from a marked run is left.
WORKSPACE_SCRATCH_DIRS: Final = ("/tmp", "/home/desk")
PROGRAM_WIPE_TIMEOUT_S: Final = 60
WORKSPACE_WIPE_ACTION: Final = "workspace_wipe"  # the audit row a finished wipe leaves (roost/programs/marks.py)
WORKSPACE_MARK_ACTION: Final = "workspace_mark"  # the audit row a tainted write leaves as it runs
# --- Connectors (docs/plans/2026-10-22-roost-connectors.md, schema v31) ---
CONNECTORS_PER_USER_MAX: Final = 30
CONNECTOR_NAME_MAX: Final = 40
CONNECTOR_PURPOSE_MAX: Final = 300
CONNECTOR_URL_MAX: Final = 300
CONNECTOR_SECRET_MAX: Final = 4096
CONNECTOR_HINT_MIN_SECRET: Final = 12       # a shorter key shows no last characters at all
CONNECTOR_HINT_CHARS: Final = 4
CONNECTOR_PREFIXES_MAX: Final = 10
CONNECTOR_PATH_MAX: Final = 1000
CONNECTOR_QUERY_KEYS_MAX: Final = 30
CONNECTOR_TIMEOUT_S: Final = 20.0
CONNECTOR_BODY_MAX_BYTES: Final = 64_000
CONNECTOR_RESPONSE_MAX_BYTES: Final = 200_000
CONNECTOR_CALLS_PER_RUN: Final = 20
CONNECTOR_RUNS_TRACKED: Final = 500         # the per-run counter forgets the oldest runs past this
CONNECTOR_AUTH_STYLES: Final = ("bearer", "header", "query")
CONNECTOR_READ_METHODS: Final = frozenset({"GET", "HEAD"})
CONNECTOR_WRITE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CONNECTOR_DEFAULT_BEARER_HEADER: Final = "Authorization"
CONNECTOR_BLOCKED_SUFFIXES: Final = (".localhost", ".local", ".internal", ".home.arpa", ".lan", ".localdomain")
CONNECTOR_REDACTED: Final = "[key hidden]"
CONNECTOR_WHY_MAX: Final = 300
CONNECTOR_REQUESTS_OPEN_PER_BOT_MAX: Final = 3

# Research (A3, 2026-10-23): web_search reads one fixed search host, DuckDuckGo's plain HTML results page, through
# the bot's own browser. Each result's host joins the run's link scope.
WEB_SEARCH_URL: Final = "https://html.duckduckgo.com/html/"
WEB_SEARCH_HOST: Final = "html.duckduckgo.com"
WEB_SEARCH_ENGINE_HOSTS: Final = frozenset({"duckduckgo.com", "html.duckduckgo.com"})   # never a result
WEB_SEARCH_MAX_RESULTS: Final = 10
WEB_SEARCH_QUERY_MAX: Final = 300
WEB_SEARCH_TITLE_MAX: Final = 200
WEB_SEARCH_SNIPPET_MAX: Final = 400
WEB_SEARCH_HTML_MAX_CHARS: Final = 2_000_000

# Token usage (docs/plans/2026-11-04-roost-token-usage.md): what each model call cost, summed per user, bot,
# local day, kind and model (schema v39 ``token_usage``). Counts are metadata, never user content.
USAGE_KIND_CHAT: Final = "chat"
USAGE_KIND_ROUTINE: Final = "routine"
USAGE_KIND_HANDOFF: Final = "handoff"
USAGE_KIND_ROOM: Final = "room"
USAGE_KIND_HELPER: Final = "helper"
USAGE_KIND_BACKGROUND: Final = "background"
USAGE_KINDS: Final = (USAGE_KIND_CHAT, USAGE_KIND_ROUTINE, USAGE_KIND_HANDOFF, USAGE_KIND_ROOM, USAGE_KIND_HELPER,
                      USAGE_KIND_BACKGROUND)
USAGE_DAYS_DEFAULT: Final = 7
USAGE_DAYS_MAX: Final = 90
USAGE_COUNT_MAX: Final = 100_000_000      # one call's count above this is not believed (read as 0)
USAGE_MODEL_MAX: Final = 100              # a model id longer than this is stored cut
USAGE_RETIRED_BOT_NAME: Final = "Retired bot"
# The scripted models' fake usage per call, so tests (and the scripted E2E) can see numbers.
SCRIPTED_USAGE_INPUT: Final = 120
SCRIPTED_USAGE_OUTPUT: Final = 30
SCRIPTED_USAGE_CACHE_READ: Final = 40
SCRIPTED_USAGE_CACHE_WRITE: Final = 10

# ---------------------------------------------------------------------------
# Chat pictures (owner, 2026-11-05; docs/plans/2026-11-05-roost-chat-pictures.md)
# ---------------------------------------------------------------------------
CHAT_MEDIA_MAX_BYTES: Final = 15 * 1024 * 1024    # one uploaded file
CHAT_MEDIA_LONG_SIDE: Final = 1568                # px: the long side after re-encoding (the model's own size)
CHAT_MEDIA_JPEG_QUALITY: Final = 85
CHAT_MEDIA_MAX_PIXELS: Final = 60_000_000         # a bigger image is refused before it is decoded
CHAT_MEDIA_PER_MESSAGE: Final = 8                 # media_ids on one message
CHAT_MEDIA_MODEL_MAX: Final = 8                   # your pictures one run shows the model (the newest)
CHAT_MEDIA_UPLOADS_PER_WINDOW: Final = 12         # loose uploads per thread ...
CHAT_MEDIA_UPLOAD_WINDOW_S: Final = 600           # ... in this many seconds
CHAT_MEDIA_CACHE: Final = "private, max-age=86400"
CHAT_MEDIA_VIDEO: Final = "video"                 # group_label of a video's frames
SCREENSHOT_CAPTION_MAX: Final = 300
SCREENSHOT_DEFAULT_CAPTION: Final = "Here's my screen."

# The install's time zone (owner, 2026-11-09, docs/plans/2026-11-09-roost-time-zone.md): the account's own
# (users.timezone, schema v45), else ROOST_TIMEZONE, else UTC.
TIMEZONE_ENV: Final = "ROOST_TIMEZONE"
TIMEZONE_FALLBACK: Final = "UTC"
TIMEZONE_NAME_MAX: Final = 64
TIMEZONE_LEGACY: Final = "Europe/Madrid"          # what an install from before v45 keeps
