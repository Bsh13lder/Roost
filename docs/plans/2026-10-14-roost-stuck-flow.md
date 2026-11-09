# Roost Stuck Flow (Piece A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A bot that hits a "prove you're human" check, a sign-in page or a code check stops cleanly and posts a Stuck card in its chat. You clear the block in the bot's own window (Take control, or Try again), give it back, and the bot carries on. "Use my main Brave" opens the page in your own Brave for you to do by hand. A task that stays blocked is reported loudly, never finished with an empty result.

**Architecture:**
- **A pure detector** (`roost/desk/stuck.py`) reads each page the bot opens or reads: the HTTP status, the title and text, a password field, and a visible captcha frame. The bot's browser starts reporting those signals (`PageText` gains three defaulted fields).
- **`ToolRunner`** handles a block:
  - It waits and repeats the call once (rung 1).
  - A block that stays sets `ToolRunner.block`, and `run_turn` stops after that step.
  - The new tool `ask_for_help` sets a block too.
  - Cards open only in your own 1:1 chat runs. In every other run the block comes back as a loud tool result.
- **`TurnRunner`** turns a block into a **Stuck card**: a row in the new `stuck_cards` table (schema v12) plus a `kind="stuck"` bot message. It then settles the bot's status to **Stuck**. When a continue run is blocked again on the same host, the card becomes **blocked** and the bot says so (rung 4).
- **`StuckService`** owns the card's buttons, behind `/api/stuck` routes:
  - **clear** queues a `card_answer` work item with a user line;
  - **give up** ends the task;
  - **open in main browser** sends a signed keeper request that runs `/usr/bin/open -a "Brave Browser" <url>`, with no automation.
- **The web** renders the card in the chat and lists open cards under **My turn** on Home. A notification fires when a bot becomes Stuck.

**Tech Stack:** The S1 stack, with no new dependency:
- Python 3.12 (uv), FastAPI, aiosqlite, pydantic 2, `cryptography` (`enc:v2` + AAD).
- Vite, React 19 and TypeScript, tested with vitest + Testing Library and Playwright.

**Spec:** `docs/plans/2026-10-14-roost-stuck-flow-design.md`, **including §6 "Refinements after reading the code" (R1–R11), which overrides the earlier sections where they differ**. Background: `docs/specs/2026-10-12-roost-design.md` §5.6 (the stuck ladder) and §7.4 (vocabulary).

## Global Constraints

- **Path guard, first in every task:**
  - `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` must print `/Users/blckit/Desktop/Code_Projects/roost`.
  - `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` must print `night-1`.
  - If either check fails, stop.
- **Where you may edit:**
  - Edit only under `/Users/blckit/Desktop/Code_Projects/roost`.
  - `/Users/blckit/Desktop/Code_Projects/lazyclaw` is never touched. That includes `lazyclaw/data`, its containers and its `make` targets.
- **Clean room (spec §10.3):**
  - Never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`.
  - Do not use browser MCP tools.
  - Only MIT, Apache-2.0, BSD, ISC or MPL-2.0 dependencies. This plan adds none.
- **Ports and the main Brave:**
  - Every listener binds `127.0.0.1` only (gateway 18800, keeper 18801, egress proxy 18803).
  - Never use port 9222.
  - **No code in this plan attaches to, drives or reads the user's main Brave.** The only main-Brave action is the keeper running the argv `("/usr/bin/open", "-a", "Brave Browser", <checked url>)`, with no shell, when the user presses the button (design D-A3/D-A4). Tests never run it: they inject a fake runner.
- **Tests:**
  - Tests first: red, then green.
  - At least 80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`).
  - Tests never call a real LLM (`ROOST_MODEL=scripted`) and never launch a real browser (`ROOST_DESK=fake`; `tests/conftest.py` forces both).
- **Code rules:**
  - Files at most 800 lines (typically 200–400); functions under 50 lines.
  - Frozen dataclasses; no mutation of shared state (reassign tuples and dicts instead).
  - Pydantic validation at every boundary.
  - Explicit error handling with user-friendly messages.
  - No magic values: they go in `roost/constants.py`, in the new section.
- **Encryption:** every user-content column is `enc:v2` with AAD `user_aad(user_id, "stuck_cards:<column>")` (`url`, `note`, `request`). Ids, timestamps, `reason`, `state` and flags are plaintext.
- **Queries:** every query on user data has `user_id` in its `WHERE`. Another user's card id gives **404**, never the card.
- **Vocabulary (§7.4):** Stuck, Take control / Give it back, Ask cards, Computer, bot. Never "Take the wheel", ">Desk<" or " in Talk" (`tests/test_vocabulary.py` scans `web/src`).
- **Git:**
  - Commit after each task's green tests. Stage files **by name**, never `git add -A`, `-a` or `.`.
  - Messages are conventional (`feat:`, `fix:`, `test:`, `docs:`), with **no Co-Authored-By or any AI attribution line**.
- **Disk guard:** before `npm install` or `make e2e`, run `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`. If it shows fewer than 8 GB free, stop and report.
- **Commands:**
  - `uv run pytest tests/<file>.py -q` runs one file.
  - `uv run pytest -q` runs the full suite.
  - `cd web && npx vitest run tests/<file>` runs one web test; `cd web && npm test` runs them all.
  - `make e2e` runs the Playwright E2E.

## Review Focus

These are the input classes the spec implies but no task's main tests exercise. The test for each one is added to the task named.

1. **A normal page that only has a sign-in box in its header, or an invisible reCAPTCHA, must not make the bot Stuck.**
   - Expected: no block, and the page is returned as usual.
   - Tests: Task 1, `test_a_long_page_with_a_password_box_is_not_a_login_wall` and `test_a_long_article_that_mentions_verify_you_are_human_is_not_a_challenge`. Task 2, `test_an_invisible_recaptcha_frame_is_not_a_captcha_frame`.
2. **The user presses Take control during the rung-1 wait.**
   - Expected: the repeat call is not performed and the card opens straight away. The bot must not navigate under the user's hands.
   - Test: Task 4, `test_taking_control_during_the_wait_skips_the_repeat`.
3. **Give it back is pressed twice (double click, or two tabs).**
   - Expected: exactly one continue item is queued; the second press answers 409.
   - Test: Task 7, `test_clearing_twice_queues_one_continue_item`.
4. **The bot is retired while its card is open.**
   - Expected: the card disappears with it (`ON DELETE CASCADE`), `GET /api/stuck` no longer lists it, and nothing crashes.
   - Test: Task 3, `test_retiring_a_bot_removes_its_cards`.
5. **The gateway restarts while a card is open.**
   - Expected: after boot the bot shows Stuck again, the card is still listed, and Give it back still works even though the in-memory control hold is gone.
   - Tests: Task 5, `test_boot_puts_a_bot_with_an_open_card_back_to_stuck`. Task 7, `test_clear_works_with_no_control_hold`.

---

## Shared Contract (every task uses these exact names)

### Schema version (`roost/db/migrations.py`, `PRAGMA user_version`)

**v12 "stuck cards"** (Task 3):

```sql
CREATE TABLE IF NOT EXISTS stuck_cards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    work_item_id TEXT,
    reason TEXT NOT NULL CHECK (reason IN ('challenge','login','code','refused','asked')),
    url TEXT NOT NULL,                 -- enc:v2, AAD stuck_cards:url
    note TEXT,                         -- enc:v2, AAD stuck_cards:note (nullable)
    request TEXT NOT NULL,             -- enc:v2, AAD stuck_cards:request
    suggest_main_browser INTEGER NOT NULL DEFAULT 0,
    tainted INTEGER NOT NULL DEFAULT 0,
    main_opened INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','cleared','given_up','blocked')),
    answer_item_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
)
```

The table also gets two indexes:
- a partial unique index `idx_stuck_cards_one_open ON stuck_cards(user_id, bot_id) WHERE state = 'open'`;
- `idx_stuck_cards_user ON stuck_cards(user_id, state, created_at)`.

Task 3 checks the real `threads` table name and whether `thread_id` can carry `REFERENCES threads(id) ON DELETE CASCADE`. If it can, Task 3 adds that.

### Constants (`roost/constants.py`, new section "Stuck flow (Piece A) — roost/desk/stuck.py, roost/stuck/")

```python
STUCK_CHALLENGE_WAIT_SECONDS = 8.0      # rung 1: wait this long, then repeat the call once
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
MAIN_BROWSER_OPEN_ARGV = ("/usr/bin/open", "-a", "Brave Browser")
MAIN_BROWSER_OPEN_TIMEOUT_S = 10.0
MAIN_BROWSER_URL_MAX_CHARS = 2048
```

All markers are matched against lowercased text (`casefold()`).

### Python names

**`roost/desk/__init__.py`** (Task 1): `PageText` gains three trailing defaulted fields, so every existing constructor keeps working.

```python
@dataclass(frozen=True)
class PageText:
    url: str
    title: str
    text: str
    truncated: bool
    status: int | None = None       # main document HTTP status; None when unknown (read_page)
    password_field: bool = False    # an <input type="password"> is on the page
    captcha_frame: bool = False     # a visible hCaptcha / reCAPTCHA / Turnstile frame is on the page
```

**`roost/desk/stuck.py`** (Task 1):

```python
BlockReason = Literal["challenge", "login", "code", "refused", "asked"]

@dataclass(frozen=True)
class Block:
    reason: BlockReason
    url: str
    host: str
    note: str = ""
    suggest_main_browser: bool = False

def host_of_url(url: str) -> str: ...            # urlsplit(url).hostname or url ("" for "")
def is_thin(page: PageText) -> bool: ...          # len(page.text) <= STUCK_THIN_PAGE_CHARS
def detect_block(page: PageText) -> Block | None: ...   # design R3; never returns reason "asked"
```

**`roost/desk/cdp.py`** (Task 2): `wait_event(self, method, session_id=None, timeout=20.0, predicate: Callable[[dict[str, Any]], bool] | None = None)`. A waiter whose predicate returns False is skipped.

**`roost/desk/browser.py`** (Task 2):
- `_ensure_session` also sends `Network.enable` and `Page.getFrameTree`, and stores `self._main_frame_id`.
- `open_page` returns the page with `status` set from the main document's `Network.responseReceived`.
- `read_page` fills `password_field` / `captcha_frame` through `DOM.getDocument` + `DOM.querySelectorAll`, and never sends `Runtime.evaluate`.

**`roost/desk/fake.py`** (Task 2):
- `FakeDesk(bot_id, *, force_unavailable=False, pages: Mapping[str, Sequence[PageText]] | None = None)`. When `pages` is None it defaults to `FAKE_PAGES`.
- `serve(url: str, *pages: PageText) -> None`.
- **Semantics:**
  - Every `open_page(url)` or `read_page()` of a served URL returns that URL's next page, and the last page repeats.
  - `open_page` keeps the served `status`; `read_page` returns `status=None`.
  - Unserved URLs behave exactly as today ("Fake Page").

**`roost/desk/fake_pages.py`** (Task 2): `FAKE_PAGES: Mapping[str, tuple[PageText, ...]]` with:
- `"https://login.example/"` → `(LOGIN_WALL, SIGNED_IN)`
- `"https://challenge.example/"` → `(CHALLENGE, CHALLENGE, CLEARED)`

**`roost/stuck/models.py`** (Task 3):

```python
class CardState(str, Enum):
    OPEN = "open"; CLEARED = "cleared"; GIVEN_UP = "given_up"; BLOCKED = "blocked"

@dataclass(frozen=True)
class CardDraft:
    bot_id: str
    thread_id: str
    work_item_id: str | None
    block: Block
    request: str
    tainted: bool

@dataclass(frozen=True)
class StuckCard:
    id: str
    user_id: str
    bot_id: str
    thread_id: str
    work_item_id: str | None
    reason: BlockReason
    url: str
    note: str
    request: str
    suggest_main_browser: bool
    tainted: bool
    main_opened: bool
    state: CardState
    answer_item_id: str | None
    created_at: str
    closed_at: str | None

    @property
    def host(self) -> str: ...        # host_of_url(self.url)

class StuckCardOut(BaseModel):       # wire shape; no user_id, no request
    id: str; bot_id: str; thread_id: str; reason: BlockReason; host: str; url: str; note: str
    suggest_main_browser: bool; tainted: bool; main_opened: bool; state: CardState
    created_at: str; closed_at: str | None

def stuck_card_out(card: StuckCard) -> StuckCardOut: ...

class CardClosed(Exception): ...      # the card is no longer open → 409
class NoAddress(Exception): ...       # the card has no web address → 400
```

**`roost/stuck/store.py`** (Task 3):

```python
class StuckStore:
    def __init__(self, config: RoostConfig) -> None: ...
    async def open(self, user_id: str, draft: CardDraft) -> StuckCard: ...
        # one open card per bot: returns the existing open card instead of a second
    async def get(self, user_id: str, card_id: str) -> StuckCard | None: ...
    async def list_open(self, user_id: str) -> tuple[StuckCard, ...]: ...          # newest first, STUCK_LIST_LIMIT
    async def open_for_bot(self, user_id: str, bot_id: str) -> StuckCard | None: ...
    async def close(self, user_id: str, card_id: str, state: CardState, *,
                    answer_item_id: str | None = None) -> StuckCard | None: ...
        # only from state open; None when not yours or not open
    async def mark_blocked(self, user_id: str, card_id: str) -> StuckCard | None: ...  # only from cleared
    async def mark_main_opened(self, user_id: str, card_id: str) -> StuckCard | None: ...  # only while open
    async def card_for_answer(self, user_id: str, item_id: str) -> StuckCard | None: ...
    async def open_bots(self) -> tuple[tuple[str, str], ...]: ...                  # (user_id, bot_id), across users, for boot
```

**`roost/stuck/texts.py`** (Task 3). These are user-facing and chat-facing words, kept in one place.

```python
REASON_WORDS: Mapping[str, str] = {
    "challenge": "a check that I'm human", "login": "a sign-in page", "code": "a code check",
    "refused": "the site refusing me", "asked": "something only you can do",
}
GIVE_UP_LINE = "OK, I stopped that task."
def stuck_line(card: StuckCard) -> str: ...
    # asked:  "I need your help on {host}: {note}." / "I need your help: {note}." when no url
    # others: "I'm stuck on {host}: {REASON_WORDS[reason]}."
    # then always " Take control to clear it, then give it back."
    # and, when suggest_main_browser: " I think this needs your main Brave."
def blocked_line(host: str, request: str) -> str: ...
    # "Blocked: {host} keeps stopping me. I didn't finish: {request}"
def continue_text(card: StuckCard) -> str: ...
    # main_opened False: "I cleared the block on {host}. Read the page again and carry on with: {request}"
    # main_opened True:  "I did this step in my own browser on {host}. Read your page again and carry on with: {request}"
    # no host: "I helped with: {note}. Carry on with: {request}"
def stuck_message_body(card: StuckCard) -> str: ...
    # json.dumps({"card_id", "bot_id", "reason", "host", "url", "note", "suggest_main_browser", "line": stuck_line(card)})
```

**`roost/stuck/announce.py`** (Task 3):

```python
async def publish_card(events: EventHub, user_id: str, card: StuckCard) -> None: ...
    # {"type": "stuck_card", "card": stuck_card_out(card).model_dump(mode="json")}
async def post_bot_line(talk: TalkStore, events: EventHub, user_id: str, card: StuckCard, body: str, *,
                        kind: MessageKind) -> Message: ...
    # role "bot", author_bot_id=card.bot_id, tainted=card.tainted, then publishes {"type": "message", ...}
```

**`roost/talk/instructions.py`** (Task 4). These are the model-facing texts:

```python
ASKED_FOR_HELP_TEXT = "Asked: the user has your request and will help. Stop here."
ASK_ONLY_IN_CHAT_TEXT = "Refused: you can ask for help only in your own chat with the user."
BAD_HELP_ARGS_TEXT = f"Refused: ask_for_help needs a reason of 1 to {STUCK_REASON_MAX_CHARS} characters."
STUCK_NOT_PERFORMED_TEXT = "Not performed: you are stuck and the user has been asked for help."
# {words} below come from a private _MODEL_REASON_WORDS ("a check that you are human", "a sign-in page", "a code check",
# "a refusal", "a request for the user's help"), never the bot-voiced REASON_WORDS.
def stuck_result_text(block: Block) -> str: ...     # "Stuck: {host} shows {words}. The user has been asked to clear it."
def blocked_result_text(block: Block) -> str: ...   # "Blocked: {host} shows {words}. You can't get past it in this task. Tell whoever asked that the site stopped you."
def refused_once_text(host: str, status: int) -> str: ...
    # "Not shown: {host} answered {status} and would not show the page. Try another way, or call ask_for_help if only the user can get past it."
```

The prompt also gets a new section, `_STUCK_TEXT`, placed right after `_COMPUTER_DESCRIPTION`. It names `ask_for_help`, Take control and give it back. It says to set `suggest_main_browser` only when the bot's own window can't do it, and says never to finish with an empty answer.

**`roost/talk/tool_catalog.py`** (Task 4): `ASK_FOR_HELP_SPEC` (name `ask_for_help`; properties `reason` (string, required) and `suggest_main_browser` (boolean)), added as `ToolDef(ASK_FOR_HELP_SPEC, "read")` after `GET_TIME_SPEC`. The description must not contain `" role"`.

**`roost/talk/tool_runner.py`** (Task 4):
- `ToolRunner.__init__` gains `cards: bool = False`: this run may open Stuck cards.
- Public state: `self.block: Block | None = None` and `self.last_url: str | None = None`.
- `run()` returns `STUCK_NOT_PERFORMED_TEXT` for every call once `self.block` is set.
- Rung 1 imports `STUCK_CHALLENGE_WAIT_SECONDS` by name, so tests patch `roost.talk.tool_runner.STUCK_CHALLENGE_WAIT_SECONDS`.
- The activity line during the wait is `f"waiting for {host} to let me in"`, and for ask_for_help it is `"asking you for help"`.

**`roost/talk/turn.py`** (Task 5):
- `TurnResult` gains `block: Block | None = None`.
- `_run_steps` returns right after the step whose calls set `tool_runner.block`.
- `_MODEL_KINDS` gains `"card_answer"`.
- `run_turn` passes `cards=_may_open_cards(inputs)`. That function returns `inputs.room is None and bool(inputs.items) and all(item.kind in (WorkKind.MESSAGE, WorkKind.CARD_ANSWER) for item in inputs.items)`.
- A blocked turn with no reply text stores no empty bubble.

**`roost/talk/runner.py`** (Task 5):
- `TurnRunner.__init__(..., *, queue=None, runs=None, rooms=None, domain=None, control=None, stuck: StuckStore | None = None)`.
- `async def settle(self, user_id: str, bot_id: str) -> None`: with no drain task running it awaits `_settle_status`. While a drain task runs, it adds a done-callback that settles again once the task ends, so a Give up that lands while a run is finishing never leaves a stale Stuck. The settle tasks are kept in `self._settling`, which `tests/team_helpers.wait_idle` also waits on, and their errors are logged, never swallowed.
- `_settle_status` picks `OFF_DUTY` if off duty, else `STUCK` if `open_for_bot`, else `RESTING`.
- `async def restore_stuck_on_boot(self) -> None`.

**`roost/work/models.py`** (Task 5): `ORIGIN_CARD = "you, after a Stuck card"`.

**`roost/talk/store.py`** (Task 5): `MessageKind` gains `"stuck"` and `"card_answer"`.

**`roost/talk/chats.py`** (Task 5):
- A `"stuck"` message previews as `(f"Stuck on {host}", "card")`, or `("Needs your help", "card")` without a host.
- A `"card_answer"` message previews like the user's own text.

**`roost/keeper/main_browser.py`** (Task 6):

```python
class MainBrowserOpenError(RuntimeError): ...
Runner = Callable[[Sequence[str], float], Awaitable[int]]     # (argv, timeout) -> exit code
class MainBrowserOpener:
    def __init__(self, *, runner: Runner | None = None) -> None: ...
    async def open(self, url: str) -> None: ...   # runs (*MAIN_BROWSER_OPEN_ARGV, url); non-zero / timeout / OSError → MainBrowserOpenError
```

Keeper route `POST /desks/{bot_id}/main-browser/open`:
- body `{"url": str}`, `extra="forbid"`, at most `MAIN_BROWSER_URL_MAX_CHARS`;
- signed; on success it answers `{"opened": true}`;
- 400 when `check_url` refuses; 401 when unsigned; 422 for a bad body; 500 `"failed to open the main browser"`;
- audit actions `"main_browser_open"` with `"ok" | "refused" | "error"`. The URL is never audited.

**`roost/desk/client.py`** (Task 6):
- `KeeperClient._request(..., refused_on_bad_request: bool = False)`: a 400 raises `UrlBlocked`.
- `async def open_in_main_browser(self, bot_id: str, url: str) -> None`.

**`roost/desk/main_browser.py`** (Task 6, gateway side):

```python
class MainBrowser(Protocol):
    async def open(self, bot_id: str, url: str) -> None: ...
class KeeperMainBrowser:            # KeeperClient(config).open_in_main_browser
    def __init__(self, config: RoostConfig, *, client: KeeperClient | None = None) -> None: ...
class FakeMainBrowser:              # records; self.opened: tuple[tuple[str, str], ...] (reassigned, never mutated)
    def __init__(self) -> None: ...
def make_main_browser(config: RoostConfig) -> MainBrowser: ...   # fake when config.desk_mode == "fake"
```

**`roost/stuck/service.py`** (Task 7):

```python
class StuckService:
    def __init__(self, store: StuckStore, talk: TalkStore, events: EventHub, turns: TurnRunner,
                 control: ControlLock, main_browser: MainBrowser) -> None: ...
    async def list_open(self, user_id: str) -> tuple[StuckCard, ...]: ...
    async def clear(self, user_id: str, card_id: str) -> StuckCard | None: ...        # None → 404; CardClosed → 409
    async def give_up(self, user_id: str, card_id: str) -> StuckCard | None: ...      # None → 404; CardClosed → 409
    async def open_in_main_browser(self, user_id: str, card_id: str) -> StuckCard | None: ...
        # None → 404; CardClosed → 409; NoAddress / UrlBlocked → 400; DeskUnavailable → 503
```

`clear` runs these steps in order:
1. Generate `item_id = str(uuid4())`.
2. `close(..., CLEARED, answer_item_id=item_id)`. A `None` here is a race and raises `CardClosed`.
3. `control.give_back(bot_id)`.
4. Post a `role="user"`, `kind="card_answer"` message with `continue_text(card)` and `tainted=card.tainted`, and publish it.
5. `turns.submit(user_id, WorkDraft(bot_id, thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD, body=text, tainted=card.tainted, message_id=msg.id, link_scope=(card.url,) if card.url else ()), item_id=item_id)`.
6. `publish_card`.
7. `await turns.settle(user_id, card.bot_id)`. A bot that can't start its continue run (daily run cap) must not keep showing Stuck.

### Wire shapes

- **The event** `{"type": "stuck_card", "card": StuckCardOut}` is published on every state change: open, cleared, given_up, blocked and main_opened.
- **The card message** has `kind: "stuck"`, `role: "bot"`, `author_bot_id: <bot>`. Its `tainted` is the card's flag, and its body is `stuck_message_body(card)` (JSON).
- **The continue line** has `kind: "card_answer"` and `role: "user"`.

### HTTP routes (every route has `CurrentUser`; every mutating route has `RequireOrigin`)

| Route | Task | Result |
|---|---|---|
| `GET /api/stuck` | 7 | 200 `StuckCardOut[]`: the user's open cards, newest first |
| `POST /api/stuck/{id}/clear` | 7 | 200 `StuckCardOut` (state `cleared`) · 404 `"Card not found"` · 409 `"This card is already closed."` |
| `POST /api/stuck/{id}/give-up` | 7 | 200 (state `given_up`) · 404 · 409 |
| `POST /api/stuck/{id}/open-in-main-browser` | 7 | 200 (`main_opened: true`) · 404 · 409 · 400 `"This card has no web address."` / `"That address can't be opened."` · 503 `"desk unavailable"` |
| keeper `POST /desks/{bot_id}/main-browser/open` | 6 | see Task 6 |

### Web names (Task 8)

- **`web/src/api/types.ts`:**
  - `StuckReason`
  - `StuckState`
  - `StuckCardOut` (the same fields as the Python wire shape)
  - `StuckCardFrame { type: "stuck_card"; seq: number; card: StuckCardOut }`, added to `ServerFrame`
  - `MessageKind` gains `"stuck" | "card_answer"`
  - `StuckMessageData { card_id; bot_id; reason; host; url; note; suggest_main_browser; line }`
- **`web/src/api/stuck.ts`:** `listStuck`, `clearStuck`, `giveUpStuck` and `openInMainBrowser`, one-liners over `apiRequest`.
- **`web/src/lib/stuck.ts`:** `parseStuckMessage(body: string): StuckMessageData | null` and `mergeStuck(rest: readonly StuckCardOut[], live: Readonly<Record<string, StuckCardOut>>): Record<string, StuckCardOut>`.
- **`web/src/store/live.ts`:** state `stuckCards: Record<string, StuckCardOut>`. A `"stuck_card"` frame upserts the card and advances `cursor`.
- **`web/src/components/StuckCard.tsx`:**
  - Props: `{ data: StuckMessageData; card: StuckCardOut | undefined; botName: string; tainted: boolean }`.
  - **Open:** Take control · Try again · Use my main Brave (only when `url`) · Give up.
  - **Holding:** "You have control. Clear it in {botName}'s window, then give it back." with Give it back and a "See its screen" link to `/bots/{bot_id}/profile?tab=computer`.
  - **After main Brave:** "Opened in your main Brave." with Done, carry on and Give up.
  - **Closed:** folds to "Cleared: {host}", "Stopped: {host}" or "Blocked: {host}".
  - **Tainted:** shows the note "This link came from a web page the bot read. Check it before you open it."
- **`MessageRow` / `MessageList`:** an optional `stuck?: Readonly<Record<string, StuckCardOut>>` prop, threaded through like `team`.
- **`Chat.tsx`:** loads `listStuck()` and merges it with the live state.
- **`Home`:** a **My turn** section, shown only when cards are open, listing "{bot} · Stuck on {host}" with a link to that bot's chat.
- **`lib/attention.ts`:** a `bot_status` frame with `status: "stuck"` gives the title `` `${bot.name} is stuck` ``.

### File structure

| File | Task | Responsibility |
|---|---|---|
| `roost/desk/stuck.py` (new) | 1 | the pure detector and `Block` |
| `roost/desk/__init__.py` | 1 | `PageText` signal fields |
| `roost/constants.py` | 1 (+6) | the stuck-flow constants section |
| `tests/fixtures/pages/*.json` (new) | 1 | challenge, login, code, refused, article and shop pages as `PageText` JSON |
| `roost/desk/cdp.py`, `roost/desk/browser.py` | 2 | status capture and DOM signals |
| `roost/desk/fake.py`, `roost/desk/fake_pages.py` (new) | 2 | scripted fake pages |
| `roost/db/migrations.py`, `tests/fixtures/schema_v11.sql` (new) | 3 | v12 |
| `roost/stuck/{__init__,models,store,texts,announce}.py` (new) | 3 | cards: data, words, announcing |
| `roost/talk/tool_runner.py`, `tool_catalog.py`, `instructions.py`, `roost/talk/stuck_check.py` (new) | 4 | rung 1 (`check_page`), blocks, `ask_for_help` (`AskForHelpArgs`) |
| `roost/talk/turn.py`, `runner.py`, `store.py`, `chats.py`, `roost/work/models.py`, `roost/gateway/app.py` (store + boot only) | 5 | the run stops and leaves a card |
| `roost/keeper/main_browser.py` (new), `roost/keeper/app.py`, `roost/desk/client.py`, `roost/desk/main_browser.py` (new) | 6 | open in the main Brave |
| `roost/stuck/service.py` (new), `roost/gateway/routes/stuck.py` (new), `roost/gateway/app.py` | 7 | the card's buttons |
| `web/src/...` | 8 | the card, My turn, attention |
| `web/e2e/stuck.spec.ts` (new), `web/e2e/fixtures/team-script.json`, docs | 9 | E2E and docs |

---

### Task 1: The detector: page signals and Block

Design R2 and R3 (they override §1's table):
- **Signals.** The accessibility text drops text boxes and frames, so the detector cannot see a password box or a captcha from `PageText.text` alone. `PageText` gains three trailing fields with defaults: `status`, `password_field` and `captcha_frame`. Every existing constructor keeps working. This task only adds the fields; Task 2 makes the real browser and `FakeDesk` fill them.
- **The detector** is one pure function, `detect_block(page) -> Block | None`. It has no I/O, no clock and no clicks. It never solves anything, and it never returns reason `"asked"` (only `ask_for_help`, in Task 4, raises that one).
- **Thin page:** a page whose text is at most `STUCK_THIN_PAGE_CHARS` (1500) long. A thin page is a wall; a long page is content.
- **The rules,** first match wins (challenge > login > code > refused). Every marker is matched against casefolded text.
  - `challenge`: a challenge title marker or `__cf_chl` in the URL, at any length; or challenge text markers or a visible captcha frame, but only on a thin page.
  - `login`: a password field, plus either a thin page or a login marker in the title or the URL **path** (not the host, not the query).
  - `code`: code markers in the text of a thin page.
  - `refused`: a status in `STUCK_REFUSED_STATUSES` (403, 429) with none of the above.
  - "Invisible reCAPTCHA frames never count" (R3) is kept by `STUCK_CAPTCHA_FRAME_SELECTOR`'s `:not([src*="size=invisible"])`, which Task 2 uses to set `captcha_frame`. The detector trusts that flag.
- **All the stuck-flow constants land now,** including `MAIN_BROWSER_*`, so later tasks only import them.

**Files:**
- Create:
  - `roost/desk/stuck.py`
  - `tests/test_stuck_detector.py`
  - `tests/fixtures/pages/challenge_title.json`, `challenge_thin_text.json`, `challenge_cf_url.json`, `captcha_thin.json`, `login_wall.json`, `login_by_title.json`, `code_2fa.json`, `refused_403.json`, `refused_429.json`, `article_mentions_verify.json`, `shop_with_header_login.json`, `normal.json`
- Modify:
  - `roost/desk/__init__.py` (`PageText` gains `status`, `password_field` and `captcha_frame`, last and defaulted)
  - `roost/constants.py` (the new section "Stuck flow (Piece A) — roost/desk/stuck.py, roost/stuck/", appended at the end)
- Test: `tests/test_stuck_detector.py`

**Interfaces:**
- Consumes: `PageText(url, title, text, truncated)` from `roost/desk/__init__.py`, as it is today. Nothing from earlier tasks.
- Produces:
  - `PageText.status: int | None = None`, `PageText.password_field: bool = False` and `PageText.captcha_frame: bool = False`.
  - From `roost.constants`: `STUCK_CHALLENGE_WAIT_SECONDS`, `STUCK_THIN_PAGE_CHARS`, `STUCK_REASON_MAX_CHARS`, `STUCK_REQUEST_MAX_CHARS`, `STUCK_LIST_LIMIT`, `STUCK_CHALLENGE_TITLE_MARKERS`, `STUCK_CHALLENGE_TEXT_MARKERS`, `STUCK_CHALLENGE_URL_MARKERS`, `STUCK_LOGIN_MARKERS`, `STUCK_CODE_MARKERS`, `STUCK_REFUSED_STATUSES`, `STUCK_PASSWORD_SELECTOR`, `STUCK_CAPTCHA_FRAME_SELECTOR`, `MAIN_BROWSER_OPEN_ARGV`, `MAIN_BROWSER_OPEN_TIMEOUT_S` and `MAIN_BROWSER_URL_MAX_CHARS`.
  - From `roost.desk.stuck`:
    - `BlockReason = Literal["challenge", "login", "code", "refused", "asked"]`
    - `Block(reason, url, host, note="", suggest_main_browser=False)` (frozen)
    - `host_of_url(url: str) -> str`
    - `is_thin(page: PageText) -> bool`
    - `detect_block(page: PageText) -> Block | None`
  - The fixture pages in `tests/fixtures/pages/` (each file holds exactly `PageText`'s seven fields). The loader `load_page(name: str) -> PageText` is local to `tests/test_stuck_detector.py`, and no later task imports it.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

The fixture pages first. Each file holds exactly `PageText`'s seven fields, so `PageText(**json.load(f))` builds it. The thin pages are a few lines long; `login_by_title.json`, `article_mentions_verify.json` and `shop_with_header_login.json` are longer than `STUCK_THIN_PAGE_CHARS` (1632, 1922 and 1709 characters of text).

Create `tests/fixtures/pages/normal.json`:

```json
{
  "url": "https://example.com/",
  "title": "Example Domain",
  "text": "Example Domain\nThis domain is for use in illustrative examples in documents. You may use this domain in literature without prior coordination or asking for permission.\nMore information...",
  "truncated": false,
  "status": 200,
  "password_field": false,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/challenge_title.json` (only the title is a marker; the status is 403, so this page also shows that a challenge outranks a refusal):

```json
{
  "url": "https://shop.example/products/42",
  "title": "Just a moment...",
  "text": "shop.example\nVerifying you are human. This may take a few seconds.\nshop.example needs to review the security of your connection before proceeding.\nRay ID: 8c2f5e1a9b3d4f60",
  "truncated": false,
  "status": 403,
  "password_field": false,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/challenge_thin_text.json` (only the text is a marker):

```json
{
  "url": "https://tickets.example/events/spring",
  "title": "tickets.example",
  "text": "tickets.example\nVerify you are human by completing the action below.\ntickets.example needs to review the security of your connection before proceeding.",
  "truncated": false,
  "status": 200,
  "password_field": false,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/challenge_cf_url.json` (only the address is a marker):

```json
{
  "url": "https://news.example/today?__cf_chl_rt_tk=Qx7Lm2Pz9",
  "title": "news.example",
  "text": "news.example\nOne more step\nPlease wait while your request is being checked.",
  "truncated": false,
  "status": 200,
  "password_field": false,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/captcha_thin.json` (only the visible captcha frame is a marker):

```json
{
  "url": "https://deals.example/",
  "title": "deals.example",
  "text": "deals.example\nOne more step\nPlease solve the puzzle below to continue to deals.example.",
  "truncated": false,
  "status": 200,
  "password_field": false,
  "captcha_frame": true
}
```

Create `tests/fixtures/pages/login_wall.json` (a thin page with a password box, and no login word anywhere):

```json
{
  "url": "https://accounts.example/v3/password",
  "title": "Example Accounts",
  "text": "Hi Ana\nEnter your password\nShow password\nForgot password?\nNext",
  "truncated": false,
  "status": 200,
  "password_field": true,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/login_by_title.json` (a long page with a password box and "Log in" in its title):

```json
{
  "url": "https://forum.example/session/new",
  "title": "Log in | Forum Example",
  "text": "Forum Example\nLog in\nUsername or email\nPassword\nRemember me\nLog in\nForgot your password?\nNew here? Create an account\nWelcome to Forum Example, a friendly place for people who grow things: balconies, allotments, back gardens and windowsills. Read the forum rules before your first post, and please search before asking, since most questions have been answered at least once.\nRecent topics\nWhich tomatoes grow best on a north-facing balcony?\n34 replies\nOur community allotment: photos from the first harvest\n12 replies\nSlugs ate every lettuce overnight. What actually works?\n57 replies\nIs it too late to sow broad beans in November?\n8 replies\nCompost that smells sour: too wet or too green?\n21 replies\nShow us your rain barrel setup\n16 replies\nPruning an old apple tree without killing it\n29 replies\nRaised beds: wood, metal or brick?\n44 replies\nSeed swap thread, spring edition\n103 replies\nWhy are my courgette flowers falling off?\n19 replies\nBest ground cover for dry shade under a birch\n11 replies\nOverwintering chillies indoors: share your tips\n26 replies\nHedgehog house: where should it go?\n14 replies\nLeaf mould in bin bags, how long does it take?\n9 replies\nGrowing garlic in pots on a windowsill\n6 replies\nWildflower meadow from a lawn: year one diary\n38 replies\nBlight on potatoes again. Resistant varieties?\n23 replies\nCheap cold frame from old windows\n17 replies\nWorm bins in a flat: does it smell?\n31 replies\nClimbing beans that survive strong wind\n7 replies\nSaving seed from squash without crosses\n15 replies\nFirst frost dates near the coast\n10 replies\nMembers online: 37\nForum rules\nContact the moderators\nPrivacy\nCookies",
  "truncated": false,
  "status": 200,
  "password_field": true,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/code_2fa.json`:

```json
{
  "url": "https://bank.example/auth/verify",
  "title": "Bank Example",
  "text": "Two-step verification\nWe sent a 6-digit code to the phone number ending in 42.\nEnter the code\nVerify\nDidn't get it? Send a new code",
  "truncated": false,
  "status": 200,
  "password_field": false,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/refused_403.json`:

```json
{
  "url": "https://data.example/reports/2026.csv",
  "title": "403 Forbidden",
  "text": "403 Forbidden\nnginx",
  "truncated": false,
  "status": 403,
  "password_field": false,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/refused_429.json`:

```json
{
  "url": "https://api.example/search?q=garden+tools",
  "title": "429 Too Many Requests",
  "text": "Too Many Requests\nYou have sent too many requests in a given amount of time. Please try again later.",
  "truncated": false,
  "status": 429,
  "password_field": false,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/article_mentions_verify.json` (a long article that quotes "Verify you are human", "press and hold", "Checking if the site connection is secure", "verification code" and "two-factor"):

```json
{
  "url": "https://blog.example/posts/how-sites-tell-people-from-bots",
  "title": "How sites tell people from bots | Blog Example",
  "text": "How sites tell people from bots\nBlog Example | Security notes | 12 March 2026\nMost of us meet a bot check a few times a week and barely notice it. A page says \"Just a moment\" or \"Checking if the site connection is secure\", a spinner turns for a second or two, and the real page appears. Behind that pause the site is asking one question: is this a person in a normal browser, or a script hammering the server?\nThe quiet checks\nThe cheapest checks are invisible. The site looks at how the browser connects, whether cookies and JavaScript work, and how fast the requests come. A normal visit passes without a single click. When the signals look odd, the site asks for more.\nThe visible checks\nThe next step is a box that says \"Verify you are human\", sometimes with a checkbox, sometimes with a puzzle. Some sites ask you to press and hold a button until it fills up. Others show a grid of photos and ask you to pick every bus or every traffic light. Each of these costs a real person a few seconds and costs a script a great deal more.\nCodes are a different thing\nBot checks are not the same as sign-in checks. When a bank sends a verification code to your phone, it already knows who you claim to be and wants proof that you hold the phone. That is two-factor sign-in, and it protects your account rather than the site's servers.\nWhat this means for you\nIf a check appears on every visit, try another network, clear the site's cookies, or update your browser. If a page keeps asking you to verify you are human after you have passed, the site may be blocking your whole network for a while. Waiting a few minutes usually helps, and so does writing to the site's support team with the time of the visit.\nComments (14)\nAna: The press and hold ones always take me three tries.\nBen: Good read. I had no idea the quiet checks happen on every visit.\nRelated posts\nWhy a password manager is worth it\nA short history of the CAPTCHA",
  "truncated": false,
  "status": 200,
  "password_field": false,
  "captcha_frame": false
}
```

Create `tests/fixtures/pages/shop_with_header_login.json` (a long shop page whose header has a sign-in box: a password field, "Sign in" only in the text, no login word in the title or the path):

```json
{
  "url": "https://shop.example/garden/tools",
  "title": "Garden tools | Shop Example",
  "text": "Shop Example\nSign in\nEmail\nPassword\nForgot your password?\nBasket (0)\nHome > Garden > Garden tools\nGarden tools\n48 products\nSort by: Most popular\nStainless steel hand trowel\nRust-proof blade, ash wood handle, 30 cm\nEUR 14.99\nAdd to basket\nBypass pruning shears\nCuts branches up to 2 cm, safety lock\nEUR 22.50\nAdd to basket\nLong-handled garden fork\nFour forged tines, 120 cm handle\nEUR 39.00\nAdd to basket\nFolding pruning saw\nFine teeth for green wood, 18 cm blade\nEUR 18.75\nAdd to basket\nWeeding knife\nHooked tip for cracks between paving stones\nEUR 9.95\nAdd to basket\nGarden kneeler and seat\nFlips over into a low stool, holds 120 kg\nEUR 34.90\nAdd to basket\nLeaf rake, 22 tines\nAdjustable width, lightweight steel\nEUR 19.99\nAdd to basket\nWatering can, 10 litres\nRemovable rose for gentle watering\nEUR 16.40\nAdd to basket\nHedge shears\nWavy blades that grip thick stems\nEUR 27.80\nAdd to basket\nBulb planter\nDepth marks in centimetres, soft grip\nEUR 11.25\nAdd to basket\nBorder spade\nNarrow blade for tight beds, 100 cm\nEUR 31.50\nAdd to basket\nGarden gloves, pack of 3\nBreathable backs, latex palms, size M\nEUR 12.60\nAdd to basket\nSoil scoop\nHolds 1 litre, measuring marks inside\nEUR 7.80\nAdd to basket\nTwine dispenser with cutter\n100 m of jute twine included\nEUR 8.95\nAdd to basket\nDibber\nOak, with depth rings every 2 cm\nEUR 6.50\nAdd to basket\nPruning saw holster\nClips onto any belt\nEUR 5.90\nAdd to basket\nGalvanised wheelbarrow, 85 litres\nPuncture-proof tyre\nEUR 79.00\nAdd to basket\nGarden hose, 25 m\nKink-free, with spray gun\nEUR 29.95\nAdd to basket\nFree delivery on orders over EUR 50\nReturns within 30 days\nCustomer service: Monday to Friday, 9:00 to 18:00\nAbout us | Delivery | Returns | Privacy | Cookies",
  "truncated": false,
  "status": 200,
  "password_field": true,
  "captcha_frame": false
}
```

Create `tests/test_stuck_detector.py`:

```python
"""The stuck detector (stuck flow Piece A, design R2/R3): which pages are a wall and which are content.

Every fixture page in ``tests/fixtures/pages/`` holds exactly ``PageText``'s fields. A page whose text is
at most ``STUCK_THIN_PAGE_CHARS`` long is thin (a wall); words and boxes that block a thin page are only
an article or a site header on a long one."""

from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

from roost.constants import (
    MAIN_BROWSER_OPEN_ARGV,
    STUCK_CHALLENGE_TEXT_MARKERS,
    STUCK_CHALLENGE_TITLE_MARKERS,
    STUCK_CHALLENGE_URL_MARKERS,
    STUCK_CODE_MARKERS,
    STUCK_LOGIN_MARKERS,
    STUCK_THIN_PAGE_CHARS,
)
from roost.desk import PageText
from roost.desk.stuck import Block, detect_block, host_of_url, is_thin

PAGES = Path(__file__).parent / "fixtures" / "pages"

THIN_PAGES = ("normal", "challenge_title", "challenge_thin_text", "challenge_cf_url", "captcha_thin",
              "login_wall", "code_2fa", "refused_403", "refused_429")
LONG_PAGES = ("login_by_title", "article_mentions_verify", "shop_with_header_login")
EXPECTED_REASONS = {
    "challenge_title": "challenge",
    "challenge_thin_text": "challenge",
    "challenge_cf_url": "challenge",
    "captcha_thin": "challenge",
    "login_wall": "login",
    "login_by_title": "login",
    "code_2fa": "code",
    "refused_403": "refused",
    "refused_429": "refused",
    "article_mentions_verify": None,
    "shop_with_header_login": None,
    "normal": None,
}
# Plain content, well past the thin limit, with no marker of any kind in it.
_LONG_TEXT = "Plain news of the day. " * 100


def load_page(name: str) -> PageText:
    """``tests/fixtures/pages/<name>.json`` as a ``PageText``."""
    return PageText(**json.loads((PAGES / f"{name}.json").read_text(encoding="utf-8")))


def _reason_of(page: PageText) -> str | None:
    block = detect_block(page)
    return None if block is None else block.reason


def test_a_page_text_built_the_old_way_has_no_signals():
    page = PageText(url="https://example.com/", title="Example Domain", text="Hello", truncated=False)
    assert (page.status, page.password_field, page.captcha_frame) == (None, False, False)
    assert PageText("https://example.com/", "Example Domain", "Hello", False) == page


def test_every_fixture_page_has_exactly_the_page_text_fields():
    names = sorted(path.stem for path in PAGES.glob("*.json"))
    assert names == sorted((*THIN_PAGES, *LONG_PAGES)) == sorted(EXPECTED_REASONS)
    field_names = {field.name for field in fields(PageText)}
    for name in names:
        assert set(json.loads((PAGES / f"{name}.json").read_text(encoding="utf-8"))) == field_names, name


@pytest.mark.parametrize("name", THIN_PAGES)
def test_the_thin_fixture_pages_are_thin(name):
    assert is_thin(load_page(name))


@pytest.mark.parametrize("name", LONG_PAGES)
def test_the_long_fixture_pages_are_long(name):
    assert not is_thin(load_page(name))


@pytest.mark.parametrize(("name", "reason"), EXPECTED_REASONS.items())
def test_each_fixture_page_gets_its_reason(name, reason):
    assert _reason_of(load_page(name)) == reason


def test_a_block_carries_the_page_address_and_its_host():
    block = detect_block(load_page("login_wall"))
    assert block == Block(reason="login", url="https://accounts.example/v3/password", host="accounts.example")
    assert (block.note, block.suggest_main_browser) == ("", False)


def test_a_long_page_with_a_password_box_is_not_a_login_wall():
    shop = load_page("shop_with_header_login")
    assert shop.password_field and not is_thin(shop) and "sign in" in shop.text.casefold()
    assert detect_block(shop) is None


def test_a_long_article_that_mentions_verify_you_are_human_is_not_a_challenge():
    article = load_page("article_mentions_verify")
    assert "verify you are human" in article.text.casefold() and not is_thin(article)
    assert detect_block(article) is None


def test_a_challenge_title_or_address_counts_on_a_page_of_any_length():
    titled = replace(load_page("challenge_title"), text=_LONG_TEXT)
    addressed = replace(load_page("challenge_cf_url"), text=_LONG_TEXT)
    assert not is_thin(titled) and not is_thin(addressed)
    assert _reason_of(titled) == _reason_of(addressed) == "challenge"


def test_challenge_words_or_a_captcha_frame_count_only_on_a_thin_page():
    words = load_page("challenge_thin_text")
    frame = load_page("captcha_thin")
    assert detect_block(replace(words, text=f"{words.text}\n{_LONG_TEXT}")) is None
    assert detect_block(replace(frame, text=f"{frame.text}\n{_LONG_TEXT}")) is None


def test_markers_match_in_any_letter_case():
    normal = load_page("normal")
    assert _reason_of(replace(normal, title="JUST A MOMENT...")) == "challenge"
    assert _reason_of(replace(normal, url="https://example.com/?__CF_CHL_TK=abc")) == "challenge"
    assert _reason_of(replace(normal, text="Please VERIFY YOU ARE HUMAN")) == "challenge"
    assert _reason_of(replace(normal, text="ENTER THE CODE we sent you")) == "code"
    assert _reason_of(replace(load_page("shop_with_header_login"), title="LOG IN | Shop Example")) == "login"


def test_a_login_marker_in_the_title_or_the_address_path_makes_a_password_page_a_login_wall():
    shop = load_page("shop_with_header_login")
    assert _reason_of(replace(shop, url="https://shop.example/account/sign-in?next=/cart")) == "login"
    assert _reason_of(replace(shop, url="https://shop.example/Account/Login")) == "login"
    assert _reason_of(replace(shop, title="Sign in | Shop Example")) == "login"


def test_a_login_marker_only_in_the_host_or_the_query_does_not_count():
    shop = load_page("shop_with_header_login")
    assert detect_block(replace(shop, url="https://login.example/garden/tools")) is None
    assert detect_block(replace(shop, url="https://shop.example/garden/tools?came_from=login")) is None


def test_a_login_page_without_a_password_box_is_not_a_login_wall():
    assert detect_block(replace(load_page("login_by_title"), password_field=False)) is None
    assert detect_block(replace(load_page("login_wall"), password_field=False)) is None


def test_code_words_count_only_on_a_thin_page():
    code = load_page("code_2fa")
    assert detect_block(replace(code, text=f"{code.text}\n{_LONG_TEXT}")) is None


def test_a_challenge_outranks_a_login_a_login_outranks_a_code_and_any_block_outranks_a_refusal():
    login = load_page("login_wall")
    code = load_page("code_2fa")
    assert _reason_of(replace(login, title="Just a moment...")) == "challenge"
    assert _reason_of(replace(code, password_field=True)) == "login"
    assert _reason_of(replace(code, status=429)) == "code"
    assert _reason_of(replace(login, status=403)) == "login"
    assert load_page("challenge_title").status == 403
    assert _reason_of(load_page("challenge_title")) == "challenge"


@pytest.mark.parametrize(("status", "reason"), [
    (403, "refused"), (429, "refused"), (200, None), (404, None), (500, None), (None, None),
])
def test_only_403_and_429_are_a_refusal(status, reason):
    assert _reason_of(replace(load_page("normal"), status=status)) == reason


def test_the_detector_never_says_asked():
    reasons = {_reason_of(load_page(name)) for name in EXPECTED_REASONS}
    assert "asked" not in reasons and reasons == {"challenge", "login", "code", "refused", None}


def test_a_page_is_thin_up_to_the_limit_and_long_past_it():
    normal = load_page("normal")
    assert is_thin(replace(normal, text="x" * STUCK_THIN_PAGE_CHARS))
    assert not is_thin(replace(normal, text="x" * (STUCK_THIN_PAGE_CHARS + 1)))


@pytest.mark.parametrize(("url", "host"), [
    ("https://Shop.Example:8443/cart?x=1", "shop.example"),
    ("about:blank", "about:blank"),
    ("", ""),
    ("http://[::1", "http://[::1"),
])
def test_host_of_url_is_the_lowercased_host_or_the_address_itself(url, host):
    assert host_of_url(url) == host


def test_an_address_that_cannot_be_parsed_does_not_crash_the_detector():
    broken = "http://[::1/login"
    assert detect_block(replace(load_page("shop_with_header_login"), url=broken)) is None
    assert detect_block(replace(load_page("refused_403"), url=broken)) == Block(
        reason="refused", url=broken, host=broken)


def test_every_marker_is_already_casefolded():
    markers = (*STUCK_CHALLENGE_TITLE_MARKERS, *STUCK_CHALLENGE_TEXT_MARKERS, *STUCK_CHALLENGE_URL_MARKERS,
               *STUCK_LOGIN_MARKERS, *STUCK_CODE_MARKERS)
    assert markers and all(marker == marker.casefold() for marker in markers)


def test_the_main_brave_command_names_open_by_its_absolute_path():
    """A changed PATH can never swap in another ``open`` (design §3, Task 6)."""
    assert MAIN_BROWSER_OPEN_ARGV == ("/usr/bin/open", "-a", "Brave Browser")
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_detector.py -q`
Expected: FAIL with 1 error during collection: `ImportError: cannot import name 'MAIN_BROWSER_OPEN_ARGV' from 'roost.constants'`. (Once the constants exist, the next failure is `ModuleNotFoundError: No module named 'roost.desk.stuck'`.)

- [ ] **Step 4: Implement — the constants**

`roost/constants.py`: the new section goes at the end of the file. Find these last lines:

```python
# A chat row's one-line preview of its newest message, in characters (… included).
CHAT_PREVIEW_CHARS = 120
```

Replace them with:

```python
# A chat row's one-line preview of its newest message, in characters (… included).
CHAT_PREVIEW_CHARS = 120

# ---------------------------------------------------------------------------
# Stuck flow (Piece A) — roost/desk/stuck.py, roost/stuck/
# ---------------------------------------------------------------------------

# All markers are lowercase: the detector matches them against casefolded text.
STUCK_CHALLENGE_WAIT_SECONDS = 8.0      # rung 1: wait this long, then repeat the call once
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
```

- [ ] **Step 5: Implement — the page signals**

`roost/desk/__init__.py`. Find:

```python
@dataclass(frozen=True)
class PageText:
    url: str
    title: str
    text: str
    truncated: bool
```

Replace it with:

```python
@dataclass(frozen=True)
class PageText:
    """What the bot's browser shows. The last three fields are the stuck detector's signals
    (``roost/desk/stuck.py``); they default to "nothing seen", so every older constructor still works."""

    url: str
    title: str
    text: str
    truncated: bool
    status: int | None = None       # main document HTTP status; None when unknown (read_page)
    password_field: bool = False    # an <input type="password"> is on the page
    captcha_frame: bool = False     # a visible hCaptcha / reCAPTCHA / Turnstile frame is on the page
```

Nothing else in `roost/` changes in this task. `DeskBrowserPage.read_page` (which `KeeperDesk` delegates to), `FakeDesk` and the test doubles in `tests/test_keeper_client.py` and `tests/test_claude_sdk_options.py` all build `PageText` with the four old fields, and that still works. Nothing serializes `PageText` with `asdict`; `roost/gateway/routes/desk.py` picks its fields by name, so no wire shape changes. Task 2 fills the new fields.

- [ ] **Step 6: Implement — the detector**

Create `roost/desk/stuck.py`:

```python
"""Is the bot stuck on this page? (stuck flow Piece A, design R2/R3).

``detect_block`` is a pure function of one ``PageText``: no I/O, no clock, no clicks. It never
solves anything and never changes the browser. It never returns reason ``"asked"``: only the bot's
own ``ask_for_help`` call raises that one.

A page whose text is at most ``STUCK_THIN_PAGE_CHARS`` long is *thin*: a wall, not content. Words
like "verify you are human", a captcha frame or a password box block a thin page, but on a long
page they are an article or a site header. When several rules match, the first wins:
challenge > login > code > refused. Every marker (``roost/constants.py``) is matched against
casefolded text.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from roost.constants import (
    STUCK_CHALLENGE_TEXT_MARKERS,
    STUCK_CHALLENGE_TITLE_MARKERS,
    STUCK_CHALLENGE_URL_MARKERS,
    STUCK_CODE_MARKERS,
    STUCK_LOGIN_MARKERS,
    STUCK_REFUSED_STATUSES,
    STUCK_THIN_PAGE_CHARS,
)
from roost.desk import PageText

BlockReason = Literal["challenge", "login", "code", "refused", "asked"]


@dataclass(frozen=True)
class Block:
    """Why the bot can't go on, and where. ``note`` is the bot's own words (``ask_for_help``'s
    reason) and ``suggest_main_browser`` its own suggestion; the detector leaves both empty."""

    reason: BlockReason
    url: str
    host: str
    note: str = ""
    suggest_main_browser: bool = False


def host_of_url(url: str) -> str:
    """The URL's host name, lowercased. A URL with no host (``about:blank``) or one that can't be
    parsed is its own host, and ``""`` stays ``""``."""
    try:
        return urlsplit(url).hostname or url
    except ValueError:
        return url


def is_thin(page: PageText) -> bool:
    return len(page.text) <= STUCK_THIN_PAGE_CHARS


def detect_block(page: PageText) -> Block | None:
    """The block this page puts in the bot's way, or ``None`` when it is ordinary content."""
    reason = _reason(page)
    if reason is None:
        return None
    return Block(reason=reason, url=page.url, host=host_of_url(page.url))


def _reason(page: PageText) -> BlockReason | None:
    thin = is_thin(page)
    if _is_challenge(page, thin):
        return "challenge"
    if _is_login(page, thin):
        return "login"
    if _is_code(page, thin):
        return "code"
    if page.status in STUCK_REFUSED_STATUSES:
        return "refused"
    return None


def _is_challenge(page: PageText, thin: bool) -> bool:
    """A challenge title or a ``__cf_chl`` address counts at any length; challenge words and a
    visible captcha frame count only on a thin page."""
    if _has_marker(page.title, STUCK_CHALLENGE_TITLE_MARKERS) or _has_marker(page.url, STUCK_CHALLENGE_URL_MARKERS):
        return True
    return thin and (page.captcha_frame or _has_marker(page.text, STUCK_CHALLENGE_TEXT_MARKERS))


def _is_login(page: PageText, thin: bool) -> bool:
    """A password box on a thin page, or under a login title or address path. The host and the
    query never count: ``login.example/garden`` or ``?came_from=login`` is not a sign-in page."""
    if not page.password_field:
        return False
    if thin:
        return True
    return _has_marker(page.title, STUCK_LOGIN_MARKERS) or _has_marker(_url_path(page.url), STUCK_LOGIN_MARKERS)


def _is_code(page: PageText, thin: bool) -> bool:
    return thin and _has_marker(page.text, STUCK_CODE_MARKERS)


def _has_marker(haystack: str, markers: Iterable[str]) -> bool:
    folded = haystack.casefold()
    return any(marker in folded for marker in markers)


def _url_path(url: str) -> str:
    try:
        return urlsplit(url).path
    except ValueError:
        return ""
```

`roost/talk/tool_runner.py` keeps its own `host_of` for now; Task 4 imports `host_of_url` from here for the stuck texts.

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_detector.py -q`
Expected: PASS (52 passed).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_detector.py --cov=roost.desk.stuck --cov-report=term-missing -q`
Expected: PASS, `roost/desk/stuck.py` at 100%.

Run the files that build or read `PageText`, which must stay green: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_fake_desk.py tests/test_cdp_client.py tests/test_keeper_client.py tests/test_desk_api.py tests/test_claude_sdk_options.py tests/test_tool_runner_taint.py tests/test_computer_control_runs.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/constants.py roost/desk/__init__.py roost/desk/stuck.py tests/test_stuck_detector.py \
  tests/fixtures/pages/challenge_title.json tests/fixtures/pages/challenge_thin_text.json \
  tests/fixtures/pages/challenge_cf_url.json tests/fixtures/pages/captcha_thin.json \
  tests/fixtures/pages/login_wall.json tests/fixtures/pages/login_by_title.json tests/fixtures/pages/code_2fa.json \
  tests/fixtures/pages/refused_403.json tests/fixtures/pages/refused_429.json \
  tests/fixtures/pages/article_mentions_verify.json tests/fixtures/pages/shop_with_header_login.json \
  tests/fixtures/pages/normal.json
git commit -m "feat: the stuck detector tells a challenge, a sign-in wall or a code check from an ordinary page"
```

---

### Task 2: The bot's browser reports status, password fields and captcha frames; FakeDesk serves scripted pages

Design §1 ("HTTP status"), R2, R3 and R11:
- `DeskBrowserPage` enables `Network` and records the **main document's** HTTP status from `Network.responseReceived` (`type == "Document"`, `frameId` == the main frame). An iframe's Document or a sub-resource never counts. `open_page` returns that status; `read_page` loads nothing, so its `status` stays `None`.
- The accessibility text drops text boxes and frames, so `read_page` fills `password_field` and `captcha_frame` with `DOM.getDocument` + `DOM.querySelectorAll` and the shared selectors. That is Chromium's own selector engine over the parsed DOM: **no page script runs, and `Runtime.evaluate` is still never sent**. Invisible reCAPTCHA frames never count (the `:not([src*="size=invisible"])` in `STUCK_CAPTCHA_FRAME_SELECTOR`).
- `CdpClient.wait_event` gains a `predicate`, so one `Network.responseReceived` can be picked out of the many a page sends.
- A DOM error reply (for example the page navigating away between `DOM.getDocument` and `DOM.querySelectorAll`) gives no signals and a warning log, instead of failing the read. `KeeperDesk._call_with_reconnect` treats every `CdpClientError`, `CdpReplyError` included, as a dead connection and would replace the bot's tab, so a failed read would lose the page.
- `FakeDesk` serves scripted pages: a `pages` table (default `FAKE_PAGES`) and `serve(url, *pages)`. Each `open_page`/`read_page` of a served URL returns its next page, and the last page repeats. A `ROOST_DESK=fake` gateway (the E2E, R11) can then show a sign-in wall at `https://login.example/`. `check_url` accepts both fake hosts: `.example` is not a local suffix and its last label is not a number. This was checked against `roost/desk/url_policy.py`, and `check_url("https://login.example/") == "https://login.example/"`.

`roost/desk/__init__.py` is not touched: Task 1 already gave `PageText` its three fields. `KeeperDesk` (`roost/desk/client.py`) is not touched either: it delegates `open_page`/`read_page` to `DeskBrowserPage`. The `Desk` protocol has no `reload` (R4: rung 1 repeats the same call).

**Files:**
- Create:
  - `roost/desk/fake_pages.py` (`FAKE_PAGES` and its four pages)
- Modify:
  - `roost/desk/cdp.py` (`wait_event(..., predicate=None)`; `_route` skips a waiter whose predicate rejects the event; a predicate that raises skips the event and never ends the reader task)
  - `roost/desk/browser.py` (`_ensure_session` also sends `Network.enable` and `Page.getFrameTree` and stores `_main_frame_id`; new `_navigate`; `open_page` returns `replace(read_page(), status=status)`; `read_page` fills `password_field` / `captcha_frame` through DOM queries)
  - `roost/desk/fake.py` (`pages` keyword, `serve()`, scripted sequence, default `FAKE_PAGES`)
- Test:
  - `tests/test_cdp_client.py` (new `_FakeCdpServer` branches and knobs, two exact-sequence tests updated, 12 new tests)
  - `tests/test_fake_desk.py` (14 new tests)

**Interfaces:**
- Consumes (Task 1):
  - `PageText(url, title, text, truncated, status: int | None = None, password_field: bool = False, captcha_frame: bool = False)` from `roost.desk`.
  - `STUCK_PASSWORD_SELECTOR`, `STUCK_CAPTCHA_FRAME_SELECTOR` from `roost.constants`.
  - `detect_block(page: PageText) -> Block | None` from `roost.desk.stuck`, used in one test that checks the fake pages.
- Consumes (existing): `check_url` / `UrlBlocked` (`roost/desk/url_policy.py`), `PAGE_LOAD_EVENT_TIMEOUT_S`, `CdpReplyError`.
- Produces:
  - `CdpClient.wait_event(self, method: str, session_id: str | None = None, timeout: float = 20.0, predicate: Callable[[dict[str, Any]], bool] | None = None) -> dict | None`, with the alias `roost.desk.cdp.EventPredicate`.
  - `DeskBrowserPage._main_frame_id: str | None` and `DeskBrowserPage._navigate(self, session_id: str, url: str) -> int | None`.
  - `DeskBrowserPage.open_page(url) -> PageText` with `status` set. `read_page() -> PageText` has `status=None` and real `password_field` / `captcha_frame`.
  - `FakeDesk(bot_id: str, *, force_unavailable: bool = False, pages: Mapping[str, Sequence[PageText]] | None = None)` and `FakeDesk.serve(url: str, *pages: PageText) -> None`.
  - `roost.desk.fake_pages`: `FAKE_PAGES: Mapping[str, tuple[PageText, ...]]`, `LOGIN_URL`, `CHALLENGE_URL`, `LOGIN_WALL`, `SIGNED_IN`, `CHALLENGE`, `CLEARED`.
  - Later tasks use these:
    - `FakeDesk.serve(url, *pages)` with their own local pages: Task 4 on a `FakeDesk` it builds, Task 5 on `rig.desks.for_bot(bot.id)` and Task 7 on `app.state.desks.for_bot(bot.id)` (`DeskFactory.for_bot` caches one desk per bot, so the served pages stay).
    - `FAKE_PAGES` by default: Task 9's E2E opens `https://login.example/`, and its pytest mirror imports `LOGIN_URL` and `SIGNED_IN`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Task 1 must be in place (the `PageText` signal fields, the selectors and the detector).
Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/desk/stuck.py && grep -n "^STUCK_PASSWORD_SELECTOR\|^STUCK_CAPTCHA_FRAME_SELECTOR\|captcha_frame: bool = False" roost/constants.py roost/desk/__init__.py`
Expected: three matching lines. If the command prints nothing or fails, stop: Task 1 is not done.

- [ ] **Step 2: Write the failing tests**

**`tests/test_cdp_client.py`**

Replace the import block at the top. Find:

```python
import asyncio
import base64
import itertools
import json
from typing import Any

import pytest
import websockets

import roost.desk.browser as browser_module
from roost.constants import PAGE_TEXT_LIMIT
```

Replace with:

```python
import asyncio
import base64
import itertools
import json
import re
from typing import Any

import pytest
import websockets

import roost.desk.browser as browser_module
from roost.constants import PAGE_TEXT_LIMIT, STUCK_CAPTCHA_FRAME_SELECTOR, STUCK_PASSWORD_SELECTOR
```

Right after the `_OVERSIZED_AX_NODES = [...]` line, before `class _FakeCdpServer:`, insert:

```python
_MAIN_FRAME_ID = "frame-1"
_ROOT_NODE_ID = 1

# Stuck flow (Task 2): responses a real page sends besides its own document.
_IFRAME_DOCUMENT = {"type": "Document", "frameId": "frame-2", "response": {"status": 403}}
_MAIN_FRAME_SCRIPT = {"type": "Script", "frameId": _MAIN_FRAME_ID, "response": {"status": 404}}

_HCAPTCHA_SRC = "https://newassets.hcaptcha.com/captcha/v1/1a2b3c/static/hcaptcha.html#frame=checkbox"
_VISIBLE_RECAPTCHA_SRC = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=site-key&size=normal"
_INVISIBLE_RECAPTCHA_SRC = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=site-key&size=invisible"
_AD_FRAME_SRC = "https://ads.example/frame?slot=top"

# The CSS subset STUCK_CAPTCHA_FRAME_SELECTOR uses: iframe[src*="…"], optionally with :not([src*="…"]).
_FRAME_RULE = re.compile(r'iframe\[src\*="(?P<has>[^"]+)"\](?::not\(\[src\*="(?P<hasnt>[^"]+)"\]\))?')


def _frame_selector_matches(selector: str, src: str) -> bool:
    """Evaluate ``selector`` on one iframe ``src`` the way Chromium's selector engine would, for the
    subset above -- so the fake DOM answers like a real one and the tests check the real selector."""
    for rule in selector.split(","):
        found = _FRAME_RULE.fullmatch(rule.strip())
        if found is not None and found["has"] in src and not (found["hasnt"] and found["hasnt"] in src):
            return True
    return False
```

Replace the **whole `_FakeCdpServer` class**. That is the current lines 46–138: from `class _FakeCdpServer:` down to and including the catch-all line `await connection.send(json.dumps({"id": msg_id, "error": {"message": f"unhandled {method}"}}))`. The new class:

```python
class _FakeCdpServer:
    """Answers exactly the handshake/read sequence the brief specifies.
    Records every inbound message (for call-sequence assertions) and the
    desk-token header presented on connect.

    Stuck flow (Task 2): after ``Page.navigate`` it sends
    ``pre_responses`` first (an iframe's or a sub-resource's), then the
    main document's ``Network.responseReceived`` (``doc_status``; None
    sends none), always before ``Page.loadEventFired``, as a real tab
    does. Its DOM has ``password_fields`` password boxes and one iframe
    per ``frame_srcs`` entry; ``dom_error`` makes every DOM call an error
    reply."""

    def __init__(
        self, *, fire_load_event: bool = True, oversized_ax_tree: bool = False, open_pages: bool = True,
        fail_first_screenshot: bool = False, doc_status: int | None = 200,
        pre_responses: tuple[dict[str, Any], ...] = (), password_fields: int = 0,
        frame_srcs: tuple[str, ...] = (), dom_error: bool = False,
    ) -> None:
        self.received_token: str | None = None
        self.received: list[dict[str, Any]] = []
        self._fire_load_event = fire_load_event
        self._oversized_ax_tree = oversized_ax_tree
        self._open_pages = open_pages
        # S1.8 Fix round 1, finding 1: the *first* Page.captureScreenshot
        # answers a CDP-level error reply (the tab behind that session
        # closed) -- every one after that succeeds, so a test can prove
        # DeskBrowserPage.capture_screenshot retries once instead of
        # failing every poll.
        self._fail_first_screenshot = fail_first_screenshot
        self._screenshot_calls = 0
        self._doc_status = doc_status
        self._pre_responses = pre_responses
        self._password_fields = password_fields
        self._frame_srcs = frame_srcs
        self._dom_error = dom_error
        self._target_ids = itertools.count(1)
        self._server: websockets.server.Server | None = None

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle, "127.0.0.1", 0)

    async def stop(self) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    @property
    def url(self) -> str:
        assert self._server is not None
        port = self._server.sockets[0].getsockname()[1]
        return f"ws://127.0.0.1:{port}"

    async def _handle(self, connection: Any) -> None:
        self.received_token = connection.request.headers.get("X-Roost-Desk-Token")
        async for raw in connection:
            message = json.loads(raw)
            self.received.append(message)
            await self._respond(connection, message)

    async def _respond(self, connection: Any, message: dict[str, Any]) -> None:
        method = message["method"]
        msg_id = message["id"]
        if method == "Page.captureScreenshot":
            await self._respond_to_screenshot(connection, msg_id)
            return
        result = self._result_for(method, message.get("params") or {})
        if result is None:
            await connection.send(json.dumps({"id": msg_id, "error": {"message": f"unhandled {method}"}}))
            return
        await connection.send(json.dumps({"id": msg_id, "result": result}))
        if method == "Page.navigate":
            await self._send_navigation_events(connection, message.get("sessionId"))

    def _result_for(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if method == "Target.createTarget":
            return {"targetId": f"target-{next(self._target_ids)}"}
        if method == "Target.attachToTarget":
            return {"sessionId": "session-1"}
        if method in ("Page.enable", "Network.enable"):
            return {}
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": _MAIN_FRAME_ID}}}
        if method == "Page.navigate":
            return {"frameId": _MAIN_FRAME_ID}
        if method == "Accessibility.getFullAXTree":
            # Fix round 1, finding 4: a real page's accessibility tree
            # routinely exceeds websockets.connect's own 1 MiB default
            # `max_size` -- this fakes that, a single node whose name is
            # well over it, to prove CdpClient asks for a larger one.
            return {"nodes": _OVERSIZED_AX_NODES if self._oversized_ax_tree else _AX_NODES}
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"title": "Example Page", "url": "https://example.com/"}}
        if method == "Target.getTargets":
            infos = [{"targetId": "target-0", "type": "page", "url": "https://example.com/"}] if self._open_pages else []
            return {"targetInfos": infos}
        if method.startswith("DOM.") and not self._dom_error:
            return self._dom_result(method, params)
        return None

    def _dom_result(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if method == "DOM.getDocument":
            return {"root": {"nodeId": _ROOT_NODE_ID, "nodeName": "#document"}}
        if method != "DOM.querySelectorAll" or params.get("nodeId") != _ROOT_NODE_ID:
            return None
        selector = params.get("selector", "")
        if selector == STUCK_PASSWORD_SELECTOR:
            return {"nodeIds": list(range(100, 100 + self._password_fields))}
        return {"nodeIds": [200 + i for i, src in enumerate(self._frame_srcs) if _frame_selector_matches(selector, src)]}

    async def _send_navigation_events(self, connection: Any, session_id: str | None) -> None:
        main = ({"type": "Document", "frameId": _MAIN_FRAME_ID, "response": {"status": self._doc_status}},)
        for params in (*self._pre_responses, *(main if self._doc_status is not None else ())):
            await connection.send(
                json.dumps({"method": "Network.responseReceived", "sessionId": session_id, "params": params})
            )
        if self._fire_load_event:
            await connection.send(json.dumps({"method": "Page.loadEventFired", "sessionId": session_id, "params": {}}))

    async def _respond_to_screenshot(self, connection: Any, msg_id: int) -> None:
        self._screenshot_calls += 1
        if self._fail_first_screenshot and self._screenshot_calls == 1:
            await connection.send(json.dumps({"id": msg_id, "error": {"message": "Session with given id not found"}}))
            return
        data = base64.b64encode(b"\xff\xd8jpeg").decode()
        await connection.send(json.dumps({"id": msg_id, "result": {"data": data}}))
```

Update the exact-sequence test. In `test_open_page_runs_the_exact_handshake_and_read_sequence`, find:

```python
    assert methods == [
        "Target.createTarget",
        "Target.attachToTarget",
        "Page.enable",
        "Page.navigate",
        "Accessibility.getFullAXTree",
        "Target.getTargetInfo",
    ]
    assert result.url == "https://example.com/"
    assert result.title == "Example Page"
    assert "Welcome" in result.text
```

Replace with:

```python
    assert methods == [
        "Target.createTarget",
        "Target.attachToTarget",
        "Page.enable",
        "Network.enable",
        "Page.getFrameTree",
        "Page.navigate",
        "Accessibility.getFullAXTree",
        "Target.getTargetInfo",
        "DOM.getDocument",
        "DOM.querySelectorAll",
        "DOM.querySelectorAll",
    ]
    assert result.url == "https://example.com/"
    assert result.title == "Example Page"
    assert "Welcome" in result.text
    assert result.status == 200
```

`test_read_page_reuses_the_session_from_open_page` also asserts an exact list, because `read_page` now sends the DOM queries. Find:

```python
    assert "Target.createTarget" not in methods
    assert "Target.attachToTarget" not in methods
    assert methods == ["Accessibility.getFullAXTree", "Target.getTargetInfo"]
```

Replace with:

```python
    assert "Target.createTarget" not in methods
    assert "Target.attachToTarget" not in methods
    assert "Network.enable" not in methods
    assert methods == [
        "Accessibility.getFullAXTree",
        "Target.getTargetInfo",
        "DOM.getDocument",
        "DOM.querySelectorAll",
        "DOM.querySelectorAll",
    ]
```

Insert these two tests right after `test_send_raises_on_a_cdp_level_error_reply`, before the `# -- DeskBrowserPage ---` line:

```python
async def test_wait_event_skips_an_event_its_predicate_rejects(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._pre_responses = (_IFRAME_DOCUMENT,)   # an iframe's Document (403) arrives first
    waiter = asyncio.create_task(
        connected_client.wait_event(
            "Network.responseReceived", session_id="s1", timeout=5,
            predicate=lambda event: event["params"]["frameId"] == _MAIN_FRAME_ID,
        )
    )
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    event = await waiter
    assert event is not None
    assert event["params"]["frameId"] == _MAIN_FRAME_ID
    assert event["params"]["response"]["status"] == 200


async def test_a_predicate_that_raises_skips_the_event_and_keeps_the_connection(
    connected_client: CdpClient,
) -> None:
    """An error inside a filter must not end the reader task: that would fail
    every pending send on a socket that is still fine."""

    def broken(event: dict[str, Any]) -> bool:
        raise KeyError("params")

    waiter = asyncio.create_task(
        connected_client.wait_event("Page.loadEventFired", session_id="s1", timeout=0.3, predicate=broken)
    )
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    assert await waiter is None
    reply = await connected_client.send("Target.createTarget", {"url": "about:blank"})
    assert reply["result"]["targetId"] == "target-1"
```

Insert these tests right before the `# -- page-text building (pure helpers) ---` line:

```python
# -- DeskBrowserPage: the stuck flow's page signals (design §1, R2, R3) --


async def test_open_page_reports_the_main_document_status(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._doc_status = 403
    result = await DeskBrowserPage(connected_client).open_page("https://example.com/")
    assert result.status == 403


async def test_an_iframe_document_or_a_sub_resource_never_sets_the_status(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """A page's own frames and files answer too: an ad frame's 403 or a
    missing script's 404 is not the page refusing the bot. Only the main
    frame's Document response is the page's status."""
    fake_server._pre_responses = (_IFRAME_DOCUMENT, _MAIN_FRAME_SCRIPT)
    result = await DeskBrowserPage(connected_client).open_page("https://example.com/")
    assert result.status == 200


async def test_a_page_with_no_document_response_has_no_status_and_no_extra_wait(
    fake_server: _FakeCdpServer, connected_client: CdpClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The response wait shares the load event's timeout. Once the load
    # event is in, the status is caught or never coming, so open_page must
    # not sit out the rest of that timeout (2 s here, 20 s for real).
    monkeypatch.setattr(browser_module, "PAGE_LOAD_EVENT_TIMEOUT_S", 2.0)
    fake_server._doc_status = None
    fake_server._pre_responses = (_IFRAME_DOCUMENT,)   # only an iframe answered
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await DeskBrowserPage(connected_client).open_page("https://example.com/")
    assert result.status is None
    assert loop.time() - started < 1.0


async def test_read_page_reports_no_status(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    """read_page loads nothing, so it never knows a status (the user may have navigated since)."""
    page = DeskBrowserPage(connected_client)
    assert (await page.open_page("https://example.com/")).status == 200
    assert (await page.read_page()).status is None


async def test_a_password_box_is_reported_as_a_password_field(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._password_fields = 1
    result = await DeskBrowserPage(connected_client).read_page()
    assert (result.password_field, result.captcha_frame) == (True, False)


async def test_a_visible_captcha_frame_is_reported(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    fake_server._frame_srcs = (_AD_FRAME_SRC, _HCAPTCHA_SRC)
    result = await DeskBrowserPage(connected_client).read_page()
    assert (result.password_field, result.captcha_frame) == (False, True)


async def test_a_plain_page_has_no_password_field_and_no_captcha_frame(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._frame_srcs = (_AD_FRAME_SRC,)
    result = await DeskBrowserPage(connected_client).read_page()
    assert (result.password_field, result.captcha_frame) == (False, False)


async def test_the_signals_are_dom_queries_on_the_bots_own_session(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    await DeskBrowserPage(connected_client).read_page()
    queries = [m for m in fake_server.received if m["method"] == "DOM.querySelectorAll"]
    assert [q["params"] for q in queries] == [
        {"nodeId": _ROOT_NODE_ID, "selector": STUCK_PASSWORD_SELECTOR},
        {"nodeId": _ROOT_NODE_ID, "selector": STUCK_CAPTCHA_FRAME_SELECTOR},
    ]
    assert {q["sessionId"] for q in queries} == {"session-1"}
    assert "Runtime.evaluate" not in [m["method"] for m in fake_server.received]


async def test_an_invisible_recaptcha_frame_is_not_a_captcha_frame(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """Review Focus 1: an invisible reCAPTCHA runs quietly behind many
    normal pages (a shop's checkout, a sign-up form) and must not make the
    bot Stuck. Chromium's selector engine does the excluding, so what
    matters is the exact selector sent; the fake DOM evaluates it."""
    fake_server._frame_srcs = (_INVISIBLE_RECAPTCHA_SRC,)
    page = DeskBrowserPage(connected_client)
    assert (await page.read_page()).captcha_frame is False
    sent = [m["params"]["selector"] for m in fake_server.received if m["method"] == "DOM.querySelectorAll"]
    assert sent == [STUCK_PASSWORD_SELECTOR, STUCK_CAPTCHA_FRAME_SELECTOR]
    assert ':not([src*="size=invisible"])' in STUCK_CAPTCHA_FRAME_SELECTOR
    fake_server._frame_srcs = (_INVISIBLE_RECAPTCHA_SRC, _VISIBLE_RECAPTCHA_SRC)
    assert (await page.read_page()).captcha_frame is True   # a visible checkbox on the same page still counts


async def test_a_page_whose_dom_cannot_be_read_still_returns_its_text(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """A DOM error reply (the page navigating away mid-read) gives no
    signals instead of failing the read: KeeperDesk treats any CDP error as
    a dead connection and would replace the bot's tab, losing the page."""
    fake_server._dom_error = True
    result = await DeskBrowserPage(connected_client).read_page()
    assert "Welcome" in result.text
    assert (result.password_field, result.captcha_frame) == (False, False)
```

**`tests/test_fake_desk.py`**

Replace the import block. Find:

```python
import pytest

from roost.desk import DeskStatus, DeskUnavailable, ExecResult
from roost.desk.fake import FakeDesk
from roost.desk.url_policy import UrlBlocked

_BOT_ID = "bot-1"
```

Replace with:

```python
from dataclasses import replace

import pytest

from roost.desk import DeskStatus, DeskUnavailable, ExecResult, PageText
from roost.desk.fake import FakeDesk
from roost.desk.fake_pages import CHALLENGE, CLEARED, FAKE_PAGES, LOGIN_WALL, SIGNED_IN
from roost.desk.stuck import detect_block
from roost.desk.url_policy import UrlBlocked, check_url

_BOT_ID = "bot-1"
_SHOP = "https://shop.example/"


def _page(title: str, *, status: int | None = 200) -> PageText:
    return PageText(url=_SHOP, title=title, text=f"{title} text", truncated=False, status=status)
```

Append at the end of the file:

```python
# -- scripted pages (stuck flow, design R11) ----------------------------


async def test_a_served_url_returns_its_pages_in_order_and_the_last_one_repeats():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("first", status=403), _page("second"))
    titles = [(await desk.open_page(_SHOP)).title for _ in range(3)]
    assert titles == ["first", "second", "second"]
    assert desk.open_page_calls == [_SHOP, _SHOP, _SHOP]


async def test_open_page_keeps_the_served_status_and_read_page_drops_it():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("wall", status=403), _page("inside", status=200))
    opened = await desk.open_page(_SHOP)
    read = await desk.read_page()
    assert (opened.title, opened.status) == ("wall", 403)
    assert (read.title, read.status) == ("inside", None)


async def test_an_unserved_url_still_gets_the_plain_fake_page():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("served"))
    opened = await desk.open_page("https://example.com/")
    assert opened == PageText(
        url="https://example.com/", title="Fake Page", text="Fake content for https://example.com/", truncated=False
    )
    read = await desk.read_page()
    assert read == PageText(url="https://example.com/", title="Fake Page", text="Fake content", truncated=False)


async def test_serving_a_url_again_starts_its_pages_over():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("one"), _page("two"))
    await desk.open_page(_SHOP)
    desk.serve(_SHOP, _page("again"), _page("after"))
    assert (await desk.open_page(_SHOP)).title == "again"


def test_serve_needs_at_least_one_page():
    with pytest.raises(ValueError, match="at least one page"):
        FakeDesk(_BOT_ID).serve(_SHOP)


def test_serving_an_address_the_bot_may_not_open_is_refused():
    with pytest.raises(UrlBlocked):
        FakeDesk(_BOT_ID).serve("http://127.0.0.1/", _page("never"))


async def test_a_served_page_is_found_without_its_trailing_slash():
    desk = FakeDesk(_BOT_ID)
    desk.serve(_SHOP, _page("served"))
    assert (await desk.open_page("https://shop.example")).title == "served"


async def test_the_default_pages_include_the_login_wall_then_the_signed_in_page():
    desk = FakeDesk(_BOT_ID)
    wall = await desk.open_page("https://login.example/")
    assert wall == LOGIN_WALL
    assert (wall.password_field, wall.status) == (True, 200)
    assert await desk.read_page() == replace(SIGNED_IN, status=None)
    assert await desk.read_page() == replace(SIGNED_IN, status=None)   # the last page repeats


async def test_the_default_challenge_stays_for_two_loads_then_clears():
    desk = FakeDesk(_BOT_ID)
    first = await desk.open_page("https://challenge.example/")
    again = await desk.open_page("https://challenge.example/")   # rung 1 repeats the same call
    after = await desk.read_page()                                 # the continue run reads the page again
    assert (first, again) == (CHALLENGE, CHALLENGE)
    assert after == replace(CLEARED, status=None)


async def test_each_desk_keeps_its_own_place_in_the_default_pages():
    one, two = FakeDesk("bot-1"), FakeDesk("bot-2")
    await one.open_page("https://login.example/")
    assert await two.open_page("https://login.example/") == LOGIN_WALL


async def test_an_empty_pages_table_serves_nothing():
    desk = FakeDesk(_BOT_ID, pages={})
    assert (await desk.open_page("https://login.example/")).title == "Fake Page"


def test_the_fake_page_addresses_pass_the_url_policy():
    """check_url refuses every local address, so the fake pages live on
    reserved .example hosts that it lets through unchanged."""
    assert [check_url(url) for url in FAKE_PAGES] == list(FAKE_PAGES)
    assert set(FAKE_PAGES) == {"https://login.example/", "https://challenge.example/"}


def test_the_fake_pages_read_as_the_blocks_they_stand_for():
    """The E2E (design R11) relies on these: the wall is a sign-in block,
    the check is a challenge, and the pages behind them are clear."""
    reasons = [getattr(detect_block(page), "reason", None) for page in (LOGIN_WALL, CHALLENGE, SIGNED_IN, CLEARED)]
    assert reasons == ["login", "challenge", None, None]


def test_the_fake_pages_table_cannot_be_changed():
    with pytest.raises(TypeError):
        FAKE_PAGES["https://login.example/"] = ()  # type: ignore[index]
```

- [ ] **Step 3: Run them to see them fail**

Run them one file at a time: a collection error in one file interrupts the whole session, so a combined run would hide the other file's failures.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_fake_desk.py -q`
Expected: FAIL, `1 error during collection`: `ModuleNotFoundError: No module named 'roost.desk.fake_pages'`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_client.py -q`
Expected: FAIL, `11 failed, 27 passed`.
- In `tests/test_cdp_client.py`:
  - `test_open_page_runs_the_exact_handshake_and_read_sequence` and `test_read_page_reuses_the_session_from_open_page` fail on the method lists: no `Network.enable`, `Page.getFrameTree` or `DOM.*`.
  - `test_wait_event_skips_an_event_its_predicate_rejects` and `test_a_predicate_that_raises_skips_the_event_and_keeps_the_connection` fail with `TypeError: CdpClient.wait_event() got an unexpected keyword argument 'predicate'`.
  - `test_open_page_reports_the_main_document_status` fails with `assert None == 403`. `test_an_iframe_document_or_a_sub_resource_never_sets_the_status` and `test_read_page_reports_no_status` fail with `assert None == 200`.
  - `test_a_password_box_is_reported_as_a_password_field` and `test_a_visible_captcha_frame_is_reported` fail on the `(password_field, captcha_frame)` tuple.
  - `test_the_signals_are_dom_queries_on_the_bots_own_session` and `test_an_invisible_recaptcha_frame_is_not_a_captcha_frame` fail because no `DOM.querySelectorAll` was sent (`[] == [...]`).
- These guards already pass and must stay green: `test_a_page_with_no_document_response_has_no_status_and_no_extra_wait`, `test_a_plain_page_has_no_password_field_and_no_captcha_frame` and `test_a_page_whose_dom_cannot_be_read_still_returns_its_text`.

- [ ] **Step 4: Implement — `roost/desk/cdp.py` (event predicates)**

Docstring. Find:

```python
waiting on that reply's ``id``, or to any ``wait_event()`` call waiting
on that event's ``method``/``sessionId``.
"""
```

Replace with:

```python
waiting on that reply's ``id``, or to any ``wait_event()`` call waiting
on that event's ``method``/``sessionId`` (and accepted by that wait's
``predicate``, when it has one).
"""
```

Imports. Find:

```python
import asyncio
import contextlib
import itertools
import json
from typing import Any

import websockets

from roost.constants import CDP_MAX_MESSAGE_BYTES, CDP_SEND_TIMEOUT_S

_DESK_TOKEN_HEADER = "X-Roost-Desk-Token"
```

Replace with:

```python
import asyncio
import contextlib
import itertools
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets

from roost.constants import CDP_MAX_MESSAGE_BYTES, CDP_SEND_TIMEOUT_S

_DESK_TOKEN_HEADER = "X-Roost-Desk-Token"

logger = logging.getLogger(__name__)

# A ``wait_event`` filter: True when this event is the one being waited for.
EventPredicate = Callable[[dict[str, Any]], bool]


def _accepts(predicate: EventPredicate | None, message: dict[str, Any]) -> bool:
    """Whether ``predicate`` takes ``message`` (no predicate takes every event).
    A predicate that raises skips the event and is logged: an error here would
    otherwise end the reader task and fail every pending ``send`` on a socket
    that is still fine."""
    if predicate is None:
        return True
    try:
        return bool(predicate(message))
    except Exception:
        logger.warning("a CDP event filter failed on %s; the event is skipped", message.get("method"), exc_info=True)
        return False
```

Waiter list in `__init__`. Find:

```python
        # Each waiter is (method, session_id, future); session_id=None
        # matches an event on any session (or none).
        self._event_waiters: list[tuple[str, str | None, asyncio.Future[dict[str, Any]]]] = []
```

Replace with:

```python
        # Each waiter is (method, session_id, predicate, future);
        # session_id=None matches an event on any session (or none), and
        # predicate=None takes every event that gets that far.
        self._event_waiters: list[
            tuple[str, str | None, EventPredicate | None, asyncio.Future[dict[str, Any]]]
        ] = []
```

`wait_event`. Find the whole method:

```python
    async def wait_event(self, method: str, session_id: str | None = None, timeout: float = 20.0) -> dict | None:
        """Wait up to ``timeout`` seconds for the next unsolicited event
        named ``method`` (optionally scoped to ``session_id``). Returns
        ``None`` on timeout rather than raising — callers that can
        tolerate a slow/never-firing event (``DeskBrowserPage.open_page``)
        decide what "give up and continue anyway" means, not this client.
        """
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        waiter = (method, session_id, future)
```

Replace with:

```python
    async def wait_event(
        self,
        method: str,
        session_id: str | None = None,
        timeout: float = 20.0,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict | None:
        """Wait up to ``timeout`` seconds for the next unsolicited event
        named ``method`` (optionally scoped to ``session_id``). Returns
        ``None`` on timeout rather than raising — callers that can
        tolerate a slow/never-firing event (``DeskBrowserPage.open_page``)
        decide what "give up and continue anyway" means, not this client.

        ``predicate``, when given, picks one event out of many with the
        same name (the stuck flow: the main frame's ``Document`` response
        among every iframe's and sub-resource's
        ``Network.responseReceived``). An event it rejects is skipped and
        the wait goes on.
        """
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        waiter = (method, session_id, predicate, future)
```

The rest of `wait_event` (the `append`, `wait_for`, `finally: remove`) stays as it is.

`_route`. Find:

```python
        method = message.get("method")
        session_id = message.get("sessionId")
        for waiter_method, waiter_session, future in list(self._event_waiters):
            if future.done():
                continue
            if waiter_method == method and (waiter_session is None or waiter_session == session_id):
                future.set_result(message)
```

Replace with:

```python
        method = message.get("method")
        session_id = message.get("sessionId")
        for waiter_method, waiter_session, predicate, future in list(self._event_waiters):
            if future.done():
                continue
            if waiter_method != method or (waiter_session is not None and waiter_session != session_id):
                continue
            if _accepts(predicate, message):
                future.set_result(message)
```

- [ ] **Step 5: Implement — `roost/desk/browser.py` (status and DOM signals)**

Module docstring, first part. Find:

```python
``Page.enable`` (needed before ``Page.loadEventFired`` will ever fire).
Every later call reuses that one session — the bot gets one tab, not a
fresh one per navigation.
```

Replace with:

```python
``Page.enable`` (needed before ``Page.loadEventFired`` will ever fire) →
``Network.enable`` (each response's HTTP status, for the stuck flow) →
``Page.getFrameTree`` (the main frame's id, which tells the page's own
document apart from its iframes'). Every later call reuses that one
session — the bot gets one tab, not a fresh one per navigation.
```

Module docstring, end. Find:

```python
computation of what's rendered, not the page's.
"""
```

Replace with:

```python
computation of what's rendered, not the page's. The stuck flow's two
page signals (a password box, a visible captcha frame) come from
``DOM.querySelectorAll`` for the same reason: Chromium's own selector
engine over the parsed DOM, with no page script run.
"""
```

Imports. Find:

```python
import asyncio
import base64
from typing import Any

from roost.constants import PAGE_LOAD_EVENT_TIMEOUT_S, PAGE_TEXT_LIMIT, SCREENSHOT_JPEG_QUALITY
from roost.desk import DeskAsleep, PageText
from roost.desk.cdp import CdpClient, CdpReplyError
from roost.desk.url_policy import check_url
```

Replace with:

```python
import asyncio
import base64
import logging
from dataclasses import replace
from typing import Any

from roost.constants import (
    PAGE_LOAD_EVENT_TIMEOUT_S,
    PAGE_TEXT_LIMIT,
    SCREENSHOT_JPEG_QUALITY,
    STUCK_CAPTCHA_FRAME_SELECTOR,
    STUCK_PASSWORD_SELECTOR,
)
from roost.desk import DeskAsleep, PageText
from roost.desk.cdp import CdpClient, CdpReplyError
from roost.desk.url_policy import check_url

logger = logging.getLogger(__name__)
```

Module constants. Find:

```python
_LOAD_EVENT_METHOD = "Page.loadEventFired"
```

Replace with:

```python
_LOAD_EVENT_METHOD = "Page.loadEventFired"
_RESPONSE_EVENT_METHOD = "Network.responseReceived"
# CDP's ``Network.ResourceType`` for a frame's own HTML; scripts, images and XHRs have other types.
_DOCUMENT_TYPE = "Document"
# ``DOM.getDocument`` depth: CDP's documented default and smallest allowed value (only the root's
# own children come back); ``DOM.querySelectorAll`` searches the whole tree from the root anyway.
_DOCUMENT_DEPTH = 1
# (password_field, captcha_frame) when the page's DOM cannot be read.
_NO_SIGNALS = (False, False)


def _status_of(response_event: asyncio.Future[dict[str, Any] | None]) -> int | None:
    """The HTTP status in a finished ``Network.responseReceived`` wait, or None
    when the wait has not finished, ran out, or the event carries no number."""
    if not response_event.done() or response_event.cancelled():
        return None
    params = (response_event.result() or {}).get("params") or {}
    status = (params.get("response") or {}).get("status")
    return status if isinstance(status, int) else None
```

`__init__`. Find:

```python
        self._target_id: str | None = None
        self._session_id: str | None = None
        self._view_session_id: str | None = None
```

Replace with:

```python
        self._target_id: str | None = None
        self._session_id: str | None = None
        self._view_session_id: str | None = None
        self._main_frame_id: str | None = None
```

`_ensure_session`. Find:

```python
        await self._client.send("Page.enable", session_id=session_id)

        self._target_id = target_id
        self._session_id = session_id
        return session_id
```

Replace with:

```python
        await self._client.send("Page.enable", session_id=session_id)
        # Stuck flow (design §1): Network events carry each response's HTTP
        # status, and the main frame's id (stable across top-level
        # navigations) picks the page's own document out of its iframes'.
        await self._client.send("Network.enable", session_id=session_id)
        tree = await self._client.send("Page.getFrameTree", session_id=session_id)

        self._target_id = target_id
        self._main_frame_id = tree.get("result", {}).get("frameTree", {}).get("frame", {}).get("id")
        self._session_id = session_id
        return session_id
```

`open_page` and `read_page`. Find both whole methods:

```python
    async def open_page(self, url: str) -> PageText:
        checked_url = check_url(url)
        session_id = await self._ensure_session()

        # The wait is armed *before* `Page.navigate` is sent, not after —
        # otherwise a load event that fires faster than this coroutine
        # gets scheduled back (a real risk once the keeper relay and the
        # browser are both local processes with near-zero latency) would
        # already have come and gone by the time anything was listening
        # for it, turning a near-instant navigation into a full 20 s wait
        # for nothing.
        load_event = asyncio.ensure_future(
            self._client.wait_event(_LOAD_EVENT_METHOD, session_id=session_id, timeout=PAGE_LOAD_EVENT_TIMEOUT_S)
        )
        await self._client.send("Page.navigate", {"url": checked_url}, session_id=session_id)
        await load_event

        return await self.read_page()

    async def read_page(self) -> PageText:
        session_id = await self._ensure_session()

        tree = await self._client.send("Accessibility.getFullAXTree", session_id=session_id)
        nodes = tree.get("result", {}).get("nodes", [])
        text, truncated = _build_page_text(nodes)

        info = await self._client.send(
            "Target.getTargetInfo", {"targetId": self._target_id}, session_id=session_id
        )
        target_info = info.get("result", {}).get("targetInfo", {})

        return PageText(
            url=target_info.get("url", ""),
            title=target_info.get("title", ""),
            text=text,
            truncated=truncated,
        )
```

Replace with:

```python
    async def open_page(self, url: str) -> PageText:
        checked_url = check_url(url)
        session_id = await self._ensure_session()
        status = await self._navigate(session_id, checked_url)
        return replace(await self.read_page(), status=status)

    async def _navigate(self, session_id: str, url: str) -> int | None:
        """Navigate the bot's tab to ``url``. Returns the main document's HTTP
        status, or None when none arrived (a DNS error, a page that never answered).

        Both waits are armed *before* `Page.navigate` is sent, not after —
        otherwise a load event that fires faster than this coroutine
        gets scheduled back (a real risk once the keeper relay and the
        browser are both local processes with near-zero latency) would
        already have come and gone by the time anything was listening
        for it, turning a near-instant navigation into a full 20 s wait
        for nothing. ``CdpClient`` routes frames in socket order, and the
        main document's ``responseReceived`` always comes before
        ``loadEventFired``: once the load event is in, the status is
        caught or never coming, so it is read without waiting any longer.
        A redirect's 3xx never fires ``responseReceived``, so the status is
        the final page's.
        """
        load_event = asyncio.ensure_future(
            self._client.wait_event(_LOAD_EVENT_METHOD, session_id=session_id, timeout=PAGE_LOAD_EVENT_TIMEOUT_S)
        )
        response_event = asyncio.ensure_future(
            self._client.wait_event(
                _RESPONSE_EVENT_METHOD, session_id=session_id, timeout=PAGE_LOAD_EVENT_TIMEOUT_S,
                predicate=self._is_main_document,
            )
        )
        try:
            await self._client.send("Page.navigate", {"url": url}, session_id=session_id)
            await load_event
            return _status_of(response_event)
        finally:
            load_event.cancel()
            response_event.cancel()

    def _is_main_document(self, event: dict[str, Any]) -> bool:
        """The page's own HTML response: a Document in the main frame, never an iframe's or a file's."""
        params = event.get("params") or {}
        return (
            self._main_frame_id is not None
            and params.get("type") == _DOCUMENT_TYPE
            and params.get("frameId") == self._main_frame_id
        )

    async def read_page(self) -> PageText:
        session_id = await self._ensure_session()

        tree = await self._client.send("Accessibility.getFullAXTree", session_id=session_id)
        nodes = tree.get("result", {}).get("nodes", [])
        text, truncated = _build_page_text(nodes)

        info = await self._client.send(
            "Target.getTargetInfo", {"targetId": self._target_id}, session_id=session_id
        )
        target_info = info.get("result", {}).get("targetInfo", {})
        password_field, captcha_frame = await self._read_signals(session_id)

        return PageText(
            url=target_info.get("url", ""),
            title=target_info.get("title", ""),
            text=text,
            truncated=truncated,
            password_field=password_field,
            captcha_frame=captcha_frame,
        )

    async def _read_signals(self, session_id: str) -> tuple[bool, bool]:
        """``(password_field, captcha_frame)`` for the stuck detector (design R2).

        The accessibility text drops text boxes and frames, so these come from
        ``DOM.querySelectorAll`` with the shared selectors -- Chromium's own
        selector engine, no page script, still no ``Runtime.evaluate``. A DOM
        that cannot be read right now (the page navigating away mid-read)
        gives no signals rather than failing the read: ``KeeperDesk`` treats
        any CDP error as a dead connection and would replace the bot's tab."""
        try:
            document = await self._client.send("DOM.getDocument", {"depth": _DOCUMENT_DEPTH}, session_id=session_id)
            root_id = document.get("result", {}).get("root", {}).get("nodeId")
            if root_id is None:
                logger.warning("DOM.getDocument gave no root node; the page's signals are unknown")
                return _NO_SIGNALS
            return (
                await self._any_match(session_id, root_id, STUCK_PASSWORD_SELECTOR),
                await self._any_match(session_id, root_id, STUCK_CAPTCHA_FRAME_SELECTOR),
            )
        except CdpReplyError as exc:
            logger.warning("could not read the page's DOM signals: %s", exc)
            return _NO_SIGNALS

    async def _any_match(self, session_id: str, root_id: int, selector: str) -> bool:
        found = await self._client.send(
            "DOM.querySelectorAll", {"nodeId": root_id, "selector": selector}, session_id=session_id
        )
        return bool(found.get("result", {}).get("nodeIds"))
```

`capture_screenshot`, `_send_capture` and `_attach_view` stay as they are. A view session never runs `_ensure_session`, so viewing never sends `Network.enable` or any DOM query.

- [ ] **Step 6: Implement — `roost/desk/fake_pages.py` (new) and `roost/desk/fake.py`**

Create `roost/desk/fake_pages.py`:

```python
"""``FAKE_PAGES`` -- the scripted pages every ``FakeDesk`` serves by default
(stuck flow, design R11).

``ROOST_DESK=fake`` runs (every test, the Playwright E2E) never reach a real
web page, and ``check_url`` refuses every local address, so a page that stops
the bot has to live here. The hosts are under ``.example`` (RFC 2606), which
no real site can ever use, and ``check_url`` lets them through unchanged.

- ``https://login.example/`` shows a sign-in page (``LOGIN_WALL``) first, then
  the signed-in page (``SIGNED_IN``): the bot opens it and gets stuck, you
  give it back, and its next read is clear.
- ``https://challenge.example/`` shows a "Just a moment..." check twice (the
  first open and rung 1's repeat), then the page behind it (``CLEARED``).

Each page carries what the real browser reports for an ``open_page``.
``FakeDesk.read_page`` drops the ``status``, as the real ``read_page`` does.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from roost.desk import PageText

LOGIN_URL = "https://login.example/"
CHALLENGE_URL = "https://challenge.example/"

LOGIN_WALL = PageText(
    url=LOGIN_URL,
    title="Sign in · Login Example",
    text="Sign in\nEmail\nPassword\nSign in\nForgot your password?",
    truncated=False,
    status=200,
    password_field=True,
)

SIGNED_IN = PageText(
    url=LOGIN_URL,
    title="Your orders",
    text="Your orders\nOrder 1042: a kettle, delivered on 12 October.\nOrder 1043: a toaster, on its way.",
    truncated=False,
    status=200,
)

CHALLENGE = PageText(
    url=CHALLENGE_URL,
    title="Just a moment...",
    text=(
        "challenge.example\nVerify you are human by completing the action below.\n"
        "challenge.example needs to review the security of your connection before proceeding."
    ),
    truncated=False,
    status=403,
    captcha_frame=True,
)

CLEARED = PageText(
    url=CHALLENGE_URL,
    title="Prices",
    text="Prices\nA kettle costs 24 euros.\nA toaster costs 31 euros.",
    truncated=False,
    status=200,
)

FAKE_PAGES: Mapping[str, tuple[PageText, ...]] = MappingProxyType(
    {
        LOGIN_URL: (LOGIN_WALL, SIGNED_IN),
        CHALLENGE_URL: (CHALLENGE, CHALLENGE, CLEARED),
    }
)
```

`roost/desk/fake.py`, imports. Find:

```python
import base64
from typing import Literal

from roost.constants import EXEC_TIMEOUT_S
from roost.desk import DeskAsleep, DeskStatus, DeskUnavailable, ExecResult, PageText, build_shell_argv
from roost.desk.url_policy import check_url
```

Replace with:

```python
import base64
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from roost.constants import EXEC_TIMEOUT_S
from roost.desk import DeskAsleep, DeskStatus, DeskUnavailable, ExecResult, PageText, build_shell_argv
from roost.desk.fake_pages import FAKE_PAGES
from roost.desk.url_policy import check_url
```

Helpers, between `FAKE_JPEG` and the class. Find:

```python
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwAooopnyJ//2Q=="
)


class FakeDesk:
```

Replace with:

```python
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwAooopnyJ//2Q=="
)


def _page_key(url: str) -> str:
    """The key a served page is kept under: the checked URL, with an empty path
    read as "/" the way a browser reads it (``https://login.example`` finds
    ``https://login.example/``'s pages). Raises ``UrlBlocked`` like ``check_url``."""
    parts = urlsplit(check_url(url))
    return urlunsplit(parts._replace(path=parts.path or "/"))


def _scripts(pages: Mapping[str, Sequence[PageText]]) -> dict[str, tuple[PageText, ...]]:
    """``pages`` keyed for lookup, each URL's pages as a tuple. A URL the bot may
    not open (``UrlBlocked``) or one with no page (``ValueError``) is a mistake
    in the script, so it fails here, not on the first open."""
    scripts = {_page_key(url): tuple(script) for url, script in pages.items()}
    for url, script in scripts.items():
        if not script:
            raise ValueError(f"a served address needs at least one page: {url}")
    return scripts


class FakeDesk:
```

Class docstring and `__init__`. Find:

```python
    ``force_unavailable`` makes every method raise ``DeskUnavailable`` —
    used by ``tests/test_desk_api.py`` to exercise the gateway desk
    routes' "keeper down -> 503" path without needing a real keeper to
    actually be down.
    """

    def __init__(self, bot_id: str, *, force_unavailable: bool = False) -> None:
        self.bot_id = bot_id
        self.force_unavailable = force_unavailable
        self._browser: Literal["running", "stopped"] = "stopped"
        self._workspace: Literal["running", "stopped", "absent"] = "absent"
        self.exec_calls: list[tuple[list[str], int]] = []
        self.open_page_calls: list[str] = []
        self.retired = False
```

Replace with:

```python
    ``force_unavailable`` makes every method raise ``DeskUnavailable`` —
    used by ``tests/test_desk_api.py`` to exercise the gateway desk
    routes' "keeper down -> 503" path without needing a real keeper to
    actually be down.

    ``pages`` scripts what a URL shows (the stuck flow). Each
    ``open_page``/``read_page`` of a served URL returns its next page,
    and the last one repeats. ``open_page`` keeps the page's ``status``;
    ``read_page`` drops it, as the real browser does. ``pages=None``
    serves ``FAKE_PAGES`` (``roost/desk/fake_pages.py``), so a
    ``ROOST_DESK=fake`` gateway (the E2E) can show a sign-in wall. Every
    other URL gets the plain "Fake Page", exactly as before.
    """

    def __init__(
        self,
        bot_id: str,
        *,
        force_unavailable: bool = False,
        pages: Mapping[str, Sequence[PageText]] | None = None,
    ) -> None:
        self.bot_id = bot_id
        self.force_unavailable = force_unavailable
        self._browser: Literal["running", "stopped"] = "stopped"
        self._workspace: Literal["running", "stopped", "absent"] = "absent"
        self.exec_calls: list[tuple[list[str], int]] = []
        self.open_page_calls: list[str] = []
        self.retired = False
        self._pages: dict[str, tuple[PageText, ...]] = _scripts(FAKE_PAGES if pages is None else pages)
        self._page_reads: dict[str, int] = {}
```

`serve` and `_next_page`. Find:

```python
    def _require_available(self) -> None:
        if self.force_unavailable:
            raise DeskUnavailable(f"desk unavailable for bot {self.bot_id}")
```

Replace with:

```python
    def _require_available(self) -> None:
        if self.force_unavailable:
            raise DeskUnavailable(f"desk unavailable for bot {self.bot_id}")

    def serve(self, url: str, *pages: PageText) -> None:
        """Script what ``url`` shows from now on: each ``open_page``/``read_page``
        of it returns the next of ``pages``, and the last one repeats. Serving a
        URL again starts its pages over. The tables are replaced, never mutated."""
        key = _page_key(url)
        self._pages = {**self._pages, **_scripts({url: pages})}
        self._page_reads = {served: reads for served, reads in self._page_reads.items() if served != key}

    def _next_page(self, url: str) -> PageText | None:
        """The next scripted page for ``url`` (the last one repeats), or None when ``url`` is not served."""
        key = _page_key(url)
        script = self._pages.get(key)
        if script is None:
            return None
        reads = self._page_reads.get(key, 0)
        self._page_reads = {**self._page_reads, key: reads + 1}
        return script[min(reads, len(script) - 1)]
```

`open_page` and `read_page`. Find:

```python
    async def open_page(self, url: str) -> PageText:
        self._require_available()
        checked_url = check_url(url)
        self.open_page_calls.append(checked_url)
        return PageText(
            url=checked_url, title="Fake Page", text=f"Fake content for {checked_url}", truncated=False
        )

    async def read_page(self) -> PageText:
        self._require_available()
        url = self.open_page_calls[-1] if self.open_page_calls else "about:blank"
        return PageText(url=url, title="Fake Page", text="Fake content", truncated=False)
```

Replace with:

```python
    async def open_page(self, url: str) -> PageText:
        self._require_available()
        checked_url = check_url(url)
        self.open_page_calls.append(checked_url)
        served = self._next_page(checked_url)
        if served is not None:
            return served
        return PageText(
            url=checked_url, title="Fake Page", text=f"Fake content for {checked_url}", truncated=False
        )

    async def read_page(self) -> PageText:
        self._require_available()
        if not self.open_page_calls:
            return PageText(url="about:blank", title="Fake Page", text="Fake content", truncated=False)
        url = self.open_page_calls[-1]
        served = self._next_page(url)
        if served is not None:
            return replace(served, status=None)
        return PageText(url=url, title="Fake Page", text="Fake content", truncated=False)
```

`DeskFactory.for_bot` already builds `FakeDesk(bot_id)`, which now serves `FAKE_PAGES`; it needs no change. No existing test opens `login.example` or `challenge.example`, so every unserved URL behaves exactly as before.

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_client.py tests/test_fake_desk.py -q`
Expected: PASS (71 passed: 38 in `test_cdp_client.py`, 33 in `test_fake_desk.py`).

Run the related files, which must stay green:
Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_keeper_client.py tests/test_desk_api.py tests/test_computer_api.py tests/test_computer_control_runs.py tests/test_tool_runner_taint.py tests/test_turn.py tests/test_handoff.py tests/test_every_bot_tools.py tests/test_task_tools.py tests/test_url_policy.py tests/test_claude_sdk_options.py tests/test_bots_api.py -q`
Expected: PASS.

Check coverage of the new code:
Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_client.py tests/test_fake_desk.py --cov=roost.desk.cdp --cov=roost.desk.browser --cov=roost.desk.fake --cov=roost.desk.fake_pages --cov-report=term-missing -q`
Expected: the new lines are covered: `_accepts`, `_status_of`, `_navigate`, `_is_main_document`, `_read_signals` (both the `CdpReplyError` branch and the no-signals branch), `_any_match`, `serve`, `_next_page`, `_page_key` and `_scripts`. The only lines that may stay uncovered are the `root_id is None` warning in `_read_signals` and pre-existing ones.

Run the whole suite.
Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/desk/cdp.py roost/desk/browser.py roost/desk/fake.py roost/desk/fake_pages.py \
  tests/test_cdp_client.py tests/test_fake_desk.py
git commit -m "feat: the bot's browser reports page status, password fields and captcha frames; FakeDesk serves scripted pages"
```

---

### Task 3: Stuck cards: schema v12, store, texts and announcing

Design §2 ("Schema v12", "When a block is found"), R6, R7 and R9. A Stuck card is one encrypted row in the new `stuck_cards` table. This task only gives the card a home, its words and its two announcements; nothing opens a card yet (Task 5 does).
- **Schema v12** is exactly the contract's table, plus `REFERENCES threads(id) ON DELETE CASCADE` on `thread_id`. Checked against the real code: the table is `threads` (`roost/db/schema.sql`), `work_items` already carries the same FK (v1), and threads are only ever deleted through their bot's cascade (`BotStore.delete` is the only `DELETE` on bots/threads). A card therefore goes with its bot **and** with its chat.
- **The store** keeps `url`, `note` and `request` as `enc:v2` under `user_aad(user_id, "stuck_cards:<column>")`. `note` is nullable (`encrypt_field` / `decrypt_field`): an empty note is stored as NULL and reads back as `""`. An address that fails its column check reads back as `""` (no address: fewer links, never more, as `WorkQueue._decode_scope` does).
- **One open card per bot.** `open` simply inserts; the partial unique index refuses a second open row (`aiosqlite.IntegrityError`), and `open` then returns the card already open. No read-then-write race.
- **State changes** are guarded `UPDATE ... WHERE id = ? AND user_id = ? AND state = ? RETURNING <columns>`, so of two presses exactly one wins and the loser gets `None`.
- `open` clips `request` to `STUCK_REQUEST_MAX_CHARS`.

**Files:**
- Create:
  - `tests/fixtures/schema_v11.sql` (generated in Step 2, before `migrations.py` changes)
  - `roost/stuck/__init__.py`, `roost/stuck/models.py`, `roost/stuck/store.py`, `roost/stuck/texts.py`, `roost/stuck/announce.py`
- Modify:
  - `roost/db/migrations.py` (`_STUCK_CARDS` and `Migration(12, "stuck cards", ...)`)
  - `tests/test_migrations_v10.py` (the hard-coded 11 becomes `latest_version()`)
- Test:
  - `tests/test_migrations_v11.py`, `tests/test_stuck_store.py`, `tests/test_stuck_texts.py`, `tests/test_stuck_announce.py`

**Interfaces:**
- Consumes:
  - Task 1: `Block`, `BlockReason` and `host_of_url` from `roost/desk/stuck.py`; `STUCK_LIST_LIMIT` and `STUCK_REQUEST_MAX_CHARS` from `roost/constants.py`.
  - Existing: `TalkStore.add_message(user_id, thread_id, role, body, tainted=False, *, message_id=None, kind="text", author_bot_id=None)`, `message_out`, `Message`, `MessageKind`; `EventHub.publish(user_id, event)`; `get_user_dek`, `encrypt`, `encrypt_field`, `decrypt_field`, `user_aad`; `db_session`; `BotStore.delete(user_id, bot_id)`.
- Produces (exactly the Shared Contract):
  - Schema v12: `stuck_cards`, `idx_stuck_cards_one_open`, `idx_stuck_cards_user`; `tests/fixtures/schema_v11.sql`.
  - `roost/stuck/models.py`: `CardState`, `CardDraft`, `StuckCard` (with `.host`), `StuckCardOut`, `stuck_card_out(card)`, `CardClosed`, `NoAddress`.
  - `roost/stuck/store.py`: `StuckStore(config)` with `open`, `get`, `list_open`, `open_for_bot`, `close(..., *, answer_item_id=None)`, `mark_blocked`, `mark_main_opened`, `card_for_answer`, `open_bots`. `open` raises `ValueError` for an unknown reason, or when the bot or chat no longer exists. `close` raises `ValueError` when asked to close a card as `open`.
  - `roost/stuck/texts.py`: `REASON_WORDS`, `GIVE_UP_LINE`, `stuck_line(card)`, `blocked_line(host, request)`, `continue_text(card)`, `stuck_message_body(card)`.
  - `roost/stuck/announce.py`: `publish_card(events, user_id, card)`, `post_bot_line(talk, events, user_id, card, body, *, kind)`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm that Task 1 has landed, since this task imports from it:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f roost/desk/stuck.py && grep -n "^STUCK_LIST_LIMIT\|^STUCK_REQUEST_MAX_CHARS" roost/constants.py`
Expected: two lines, `STUCK_REQUEST_MAX_CHARS = 2000 ...` and `STUCK_LIST_LIMIT = 50 ...`. If the file or either constant is missing, stop: Task 1 comes first.

- [ ] **Step 2: Freeze the current schema (v11), then write the failing tests**

**2a. Freeze schema v11.** This must run **before** `roost/db/migrations.py` changes. The script builds a throwaway database in `$TMPDIR`, never in `~/Roost/data`:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run python - <<'PY'
import asyncio, sqlite3, tempfile
from pathlib import Path
import aiosqlite
from roost.db.migrations import apply_migrations, latest_version

assert latest_version() == 11, f"expected schema v11 before the stuck flow, got {latest_version()}"

async def build(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(Path("roost/db/schema.sql").read_text())
        await db.commit()
        await apply_migrations(db)

path = Path(tempfile.mkdtemp(prefix="roost-v11-")) / "v11.db"
asyncio.run(build(path))
con = sqlite3.connect(path)
rows = con.execute(
    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
).fetchall()
con.close()
header = ("-- Roost schema version 11, frozen by stuck-flow Task 3 (schema.sql + migrations 1-11).\n"
          "-- The live ~/Roost/data/roost.db runs this schema at the start of the stuck flow. Never edit.\n\n")
Path("tests/fixtures/schema_v11.sql").write_text(header + ";\n\n".join(r[0] for r in rows) + ";\n")
print("tables/indexes:", len(rows))
PY
grep -c "CREATE" tests/fixtures/schema_v11.sql                              # 39
grep -c "notify INTEGER NOT NULL DEFAULT 1" tests/fixtures/schema_v11.sql   # 1
grep -c "stuck_cards" tests/fixtures/schema_v11.sql                         # 0
diff <(sed 1,3d tests/fixtures/schema_v10.sql) <(sed 1,3d tests/fixtures/schema_v11.sql)
```

Expected:
- The script prints `tables/indexes: 39`.
- The file starts with exactly these lines:

```sql
-- Roost schema version 11, frozen by stuck-flow Task 3 (schema.sql + migrations 1-11).
-- The live ~/Roost/data/roost.db runs this schema at the start of the stuck flow. Never edit.

CREATE TABLE users (
```

- The `diff` shows one changed line only, in `CREATE TABLE bots`. The line `updated_at TEXT NOT NULL, off_duty INTEGER NOT NULL DEFAULT 0, is_primary INTEGER NOT NULL DEFAULT 0,` gains ` notify INTEGER NOT NULL DEFAULT 1,` before its trailing comma.

**2b. The migration test from v11, with rows.** Create `tests/test_migrations_v11.py`:

```python
"""Migrating from the schema the live gateway runs at the start of the stuck flow (version 11).

``tests/fixtures/schema_v11.sql`` was frozen by stuck-flow Task 3. Rows go in
every table the user's account uses today (the v10 test's rows); v12 adds the
``stuck_cards`` table, one open card per bot, gone with its bot or its chat."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from test_migrations_v10 import _EXPECTED as _V10_EXPECTED
from test_migrations_v10 import _ROWS as _V10_ROWS
from test_migrations_v8 import _NOW

_V11_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v11.sql"
_STUCK_COLUMNS = {
    "id", "user_id", "bot_id", "thread_id", "work_item_id", "reason", "url", "note", "request",
    "suggest_main_browser", "tainted", "main_opened", "state", "answer_item_id", "created_at", "closed_at",
}
_CARD = ("INSERT INTO stuck_cards (id, user_id, bot_id, thread_id, reason, url, request, state, created_at) "
         "VALUES (?, 'u1', 'b2', ?, ?, 'enc:u', 'enc:r', ?, ?)")


def _query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _version(db_path: Path) -> int:
    return _query(db_path, "PRAGMA user_version")[0][0]


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _V10_EXPECTED}


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


@pytest.fixture
def seeded_v11():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V11_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 11")
        for statement in _V10_ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v11_database_migrates_to_latest_and_keeps_every_row(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    assert latest_version() >= 12
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == _V10_EXPECTED


async def test_v11_database_gains_the_stuck_cards_table(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(stuck_cards)")} == _STUCK_COLUMNS
    indexes = {row[0] for row in _query(
        db_path, "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'stuck_cards'",
    )}
    assert {"idx_stuck_cards_one_open", "idx_stuck_cards_user"} <= indexes
    assert _query(db_path, "SELECT COUNT(*) FROM stuck_cards") == [(0,)]


async def test_a_bot_can_have_only_one_open_stuck_card(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute(_CARD, ("c1", "t1", "login", "cleared", _NOW))
        con.execute(_CARD, ("c2", "t1", "login", "open", _NOW))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_CARD, ("c3", "t1", "challenge", "open", _NOW))
    finally:
        con.close()


async def test_a_stuck_cards_reason_and_state_are_checked(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    con = _connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_CARD, ("c1", "t1", "bored", "open", _NOW))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_CARD, ("c2", "t1", "login", "paused", _NOW))
    finally:
        con.close()


async def test_a_stuck_card_goes_with_its_chat_and_with_its_bot(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute("INSERT INTO threads (id, user_id, bot_id, kind, created_at, updated_at) "
                    f"VALUES ('t3','u1','b2','chat','{_NOW}','{_NOW}')")
        con.execute(_CARD, ("c1", "t1", "login", "open", _NOW))
        con.execute(_CARD, ("c2", "t3", "code", "cleared", _NOW))
        con.execute("DELETE FROM threads WHERE id = 't1'")
        assert [row[0] for row in con.execute("SELECT id FROM stuck_cards")] == ["c2"]
        con.execute("DELETE FROM bots WHERE id = 'b2'")
        assert con.execute("SELECT COUNT(*) FROM stuck_cards").fetchone() == (0,)
    finally:
        con.close()


async def test_migrating_v11_twice_is_a_no_op_and_backs_up_once(seeded_v11):
    cfg, db_path = seeded_v11
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _V10_EXPECTED
    [backup] = sorted(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))
    assert _version(backup) == 11
```

**2c. Stop pinning v11 in the v10 test.** In `tests/test_migrations_v10.py`, find:

```python
async def test_v10_database_migrates_to_v11_and_keeps_every_row(seeded_v10):
    cfg, db_path = seeded_v10
    await init_db(cfg)
    assert latest_version() == 11
    assert _query(db_path, "PRAGMA user_version")[0][0] == 11
    assert _counts(db_path) == _EXPECTED
```

Replace it with:

```python
async def test_v10_database_migrates_to_latest_and_keeps_every_row(seeded_v10):
    cfg, db_path = seeded_v10
    await init_db(cfg)
    assert latest_version() >= 11
    assert _query(db_path, "PRAGMA user_version")[0][0] == latest_version()
    assert _counts(db_path) == _EXPECTED
```

Then find:

```python
    assert len(list(db_path.parent.glob("roost.db.pre-v11-*.bak"))) == 1
```

Replace it with:

```python
    assert len(list(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))) == 1
```

**2d. The store.** Create `tests/test_stuck_store.py`:

```python
"""Stuck cards (stuck flow §2, R6–R9): encrypted on disk, one open card per bot,
guarded state changes, and every query scoped to its user."""

from __future__ import annotations

import asyncio

import pytest

import roost.stuck.store as store_module
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import STUCK_REQUEST_MAX_CHARS
from roost.db.connection import db_session, init_db
from roost.desk.stuck import Block, host_of_url
from roost.gateway.auth import register_user
from roost.stuck.models import CardDraft, CardState
from roost.stuck.store import StuckStore
from roost.talk.store import TalkStore
from team_helpers import make_bot

LOGIN_URL = "https://login.example/account"
REQUEST = "book a table for two at 8"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _chat(cfg, user_id: str, name: str = "Helper") -> tuple[str, str]:
    bot = await make_bot(cfg, user_id, name)
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    return bot.id, thread.id


@pytest.fixture
async def chat(cfg, user_id):
    return await _chat(cfg, user_id)


def _draft(bot_id: str, thread_id: str, *, reason: str = "login", url: str = LOGIN_URL, note: str = "",
           suggest: bool = False, request: str = REQUEST, tainted: bool = False,
           work_item_id: str | None = "item-0") -> CardDraft:
    block = Block(reason=reason, url=url, host=host_of_url(url), note=note, suggest_main_browser=suggest)
    return CardDraft(bot_id=bot_id, thread_id=thread_id, work_item_id=work_item_id, block=block,
                     request=request, tainted=tainted)


async def _raw(cfg, card_id: str):
    async with db_session(cfg) as db:
        return await (await db.execute(
            "SELECT url, note, request FROM stuck_cards WHERE id = ?", (card_id,),
        )).fetchone()


async def _count(cfg) -> int:
    async with db_session(cfg) as db:
        return (await (await db.execute("SELECT COUNT(*) FROM stuck_cards")).fetchone())[0]


async def _three_open_cards(cfg, user_id: str, store: StuckStore) -> tuple:
    cards: tuple = ()
    for name in ("Ann", "Ben", "Cat"):
        bot_id, thread_id = await _chat(cfg, user_id, name)
        cards = (*cards, await store.open(user_id, _draft(bot_id, thread_id)))
    return cards


async def test_url_note_and_request_are_ciphertext_on_disk(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id, reason="asked", note="approve the payment"))
    row = await _raw(cfg, card.id)
    assert all(row[column].startswith("enc:v2:") for column in ("url", "note", "request"))
    assert "login.example" not in row["url"] and "payment" not in row["note"] and "table" not in row["request"]
    again = await store.get(user_id, card.id)
    assert (again.url, again.note, again.request) == (LOGIN_URL, "approve the payment", REQUEST)


async def test_a_card_without_a_note_stores_no_note(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    assert (await _raw(cfg, card.id))["note"] is None
    assert (await store.get(user_id, card.id)).note == ""


async def test_a_new_card_is_open_and_keeps_what_stopped_the_bot(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id, suggest=True, tainted=True))
    assert (card.user_id, card.bot_id, card.thread_id, card.work_item_id) == (user_id, bot_id, thread_id, "item-0")
    assert (card.reason, card.url, card.host) == ("login", LOGIN_URL, "login.example")
    assert (card.suggest_main_browser, card.tainted, card.main_opened) == (True, True, False)
    assert (card.state, card.answer_item_id, card.closed_at) == (CardState.OPEN, None, None)
    assert await store.get(user_id, card.id) == card
    assert await store.open_for_bot(user_id, bot_id) == card


async def test_a_bot_has_at_most_one_open_card(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    first = await store.open(user_id, _draft(bot_id, thread_id))
    second = await store.open(user_id, _draft(bot_id, thread_id, reason="challenge", url="https://other.example/"))
    assert second == first
    assert await _count(cfg) == 1


async def test_two_cards_opened_at_once_for_one_bot_become_one(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    a, b = await asyncio.gather(
        store.open(user_id, _draft(bot_id, thread_id)),
        store.open(user_id, _draft(bot_id, thread_id, reason="code")),
    )
    assert a.id == b.id
    assert await _count(cfg) == 1


async def test_after_a_card_closes_the_bot_can_get_a_new_one(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    first = await store.open(user_id, _draft(bot_id, thread_id))
    await store.close(user_id, first.id, CardState.GIVEN_UP)
    second = await store.open(user_id, _draft(bot_id, thread_id))
    assert second.id != first.id and second.state is CardState.OPEN


async def test_close_works_only_on_an_open_card_and_keeps_the_answer_item(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    cleared = await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    assert (cleared.state, cleared.answer_item_id) == (CardState.CLEARED, "item-1")
    assert cleared.closed_at is not None
    assert await store.close(user_id, card.id, CardState.GIVEN_UP) is None
    assert await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-2") is None
    assert await store.get(user_id, card.id) == cleared
    assert await store.open_for_bot(user_id, bot_id) is None


async def test_giving_up_closes_the_card_without_an_answer_item(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    given_up = await store.close(user_id, card.id, CardState.GIVEN_UP)
    assert (given_up.state, given_up.answer_item_id) == (CardState.GIVEN_UP, None)


async def test_a_card_is_never_closed_as_open(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    with pytest.raises(ValueError, match="can't be closed"):
        await store.close(user_id, card.id, CardState.OPEN)
    assert (await store.get(user_id, card.id)).state is CardState.OPEN


async def test_mark_blocked_only_from_cleared(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    assert await store.mark_blocked(user_id, card.id) is None          # still open: rung 4 only follows a clear
    await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    blocked = await store.mark_blocked(user_id, card.id)
    assert (blocked.state, blocked.answer_item_id) == (CardState.BLOCKED, "item-1")
    assert await store.mark_blocked(user_id, card.id) is None


async def test_mark_main_opened_only_while_open(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    marked = await store.mark_main_opened(user_id, card.id)
    assert (marked.main_opened, marked.state) == (True, CardState.OPEN)
    cleared = await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    assert cleared.main_opened is True
    assert await store.mark_main_opened(user_id, card.id) is None


async def test_card_for_answer_finds_the_card_its_continue_item_answers(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    assert (await store.card_for_answer(user_id, "item-1")).id == card.id
    assert await store.card_for_answer(user_id, "item-2") is None


async def test_list_open_is_newest_first_and_leaves_out_closed_cards(cfg, user_id):
    store = StuckStore(cfg)
    ann, ben, cat = await _three_open_cards(cfg, user_id, store)
    await store.close(user_id, ben.id, CardState.GIVEN_UP)
    assert [card.id for card in await store.list_open(user_id)] == [cat.id, ann.id]


async def test_list_open_stops_at_the_list_limit(cfg, user_id, monkeypatch):
    monkeypatch.setattr(store_module, "STUCK_LIST_LIMIT", 2)
    store = StuckStore(cfg)
    ann, ben, cat = await _three_open_cards(cfg, user_id, store)
    assert [card.id for card in await store.list_open(user_id)] == [cat.id, ben.id]


async def test_another_users_card_is_not_found_and_not_changed(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    card = await store.open(user_id, _draft(bot_id, thread_id))
    assert await store.get(bob, card.id) is None
    assert await store.open_for_bot(bob, bot_id) is None
    assert await store.list_open(bob) == ()
    assert await store.mark_main_opened(bob, card.id) is None
    assert await store.close(bob, card.id, CardState.CLEARED, answer_item_id="item-1") is None
    assert await store.get(user_id, card.id) == card
    await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1")
    assert await store.mark_blocked(bob, card.id) is None
    assert await store.card_for_answer(bob, "item-1") is None
    assert (await store.get(user_id, card.id)).state is CardState.CLEARED


async def test_open_bots_lists_every_users_bots_with_an_open_card(cfg, user_id, chat):
    store = StuckStore(cfg)
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bot_id, thread_id = chat
    quiet_bot, quiet_thread = await _chat(cfg, user_id, "Quiet")
    bob_bot, bob_thread = await _chat(cfg, bob, "Scout")
    await store.open(user_id, _draft(bot_id, thread_id))
    done = await store.open(user_id, _draft(quiet_bot, quiet_thread))
    await store.close(user_id, done.id, CardState.CLEARED, answer_item_id="item-9")
    await store.open(bob, _draft(bob_bot, bob_thread))
    assert await store.open_bots() == ((user_id, bot_id), (bob, bob_bot))


async def test_retiring_a_bot_removes_its_cards(cfg, user_id, chat):
    """Review Focus 4: ON DELETE CASCADE; the open list (GET /api/stuck) no longer has it."""
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    assert await BotStore(cfg).delete(user_id, bot_id) is True
    assert await store.get(user_id, card.id) is None
    assert await store.list_open(user_id) == ()
    assert await store.open_for_bot(user_id, bot_id) is None
    assert await store.open_bots() == ()
    assert await store.close(user_id, card.id, CardState.CLEARED, answer_item_id="item-1") is None
    assert await _count(cfg) == 0


async def test_a_card_for_a_chat_that_does_not_exist_is_refused(cfg, user_id, chat):
    bot_id, _ = chat
    with pytest.raises(ValueError, match="no longer exists"):
        await StuckStore(cfg).open(user_id, _draft(bot_id, "no-such-thread"))
    assert await _count(cfg) == 0


async def test_a_card_with_an_unknown_reason_is_refused(cfg, user_id, chat):
    bot_id, thread_id = chat
    with pytest.raises(ValueError, match="Unknown Stuck reason"):
        await StuckStore(cfg).open(user_id, _draft(bot_id, thread_id, reason="bored"))
    assert await _count(cfg) == 0


async def test_a_long_request_is_kept_up_to_the_limit(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id, request="x" * (STUCK_REQUEST_MAX_CHARS + 50)))
    assert len(card.request) == STUCK_REQUEST_MAX_CHARS
    assert (await store.get(user_id, card.id)).request == card.request


async def test_an_address_that_fails_its_column_check_reads_as_no_address(cfg, user_id, chat):
    bot_id, thread_id = chat
    store = StuckStore(cfg)
    card = await store.open(user_id, _draft(bot_id, thread_id))
    async with db_session(cfg) as db:
        await db.execute("UPDATE stuck_cards SET url = request WHERE id = ?", (card.id,))
        await db.commit()
    again = await store.get(user_id, card.id)
    assert (again.url, again.host, again.request) == ("", "", REQUEST)
```

**2e. The words.** Create `tests/test_stuck_texts.py`:

```python
"""The Stuck flow's words (design §2, R6, R7): the exact line for every branch."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import get_args

import pytest

from roost.desk.stuck import BlockReason
from roost.stuck.models import CardState, StuckCard
from roost.stuck.texts import (
    GIVE_UP_LINE, REASON_WORDS, blocked_line, continue_text, stuck_line, stuck_message_body,
)

REQUEST = "buy two tickets for Friday"
CARD = StuckCard(
    id="card-1", user_id="u1", bot_id="bot-1", thread_id="t1", work_item_id="item-0", reason="login",
    url="https://shop.example/checkout?step=2", note="", request=REQUEST, suggest_main_browser=False,
    tainted=False, main_opened=False, state=CardState.OPEN, answer_item_id=None,
    created_at="2026-10-14T08:00:00+00:00", closed_at=None,
)


def test_every_reason_has_its_words():
    assert dict(REASON_WORDS) == {
        "challenge": "a check that I'm human", "login": "a sign-in page", "code": "a code check",
        "refused": "the site refusing me", "asked": "something only you can do",
    }
    assert set(REASON_WORDS) == set(get_args(BlockReason))


def test_the_card_host_is_the_urls_host_and_empty_without_a_url():
    assert CARD.host == "shop.example"
    assert replace(CARD, url="").host == ""


@pytest.mark.parametrize(("reason", "line"), [
    ("challenge", "I'm stuck on shop.example: a check that I'm human. Take control to clear it, then give it back."),
    ("login", "I'm stuck on shop.example: a sign-in page. Take control to clear it, then give it back."),
    ("code", "I'm stuck on shop.example: a code check. Take control to clear it, then give it back."),
    ("refused", "I'm stuck on shop.example: the site refusing me. Take control to clear it, then give it back."),
])
def test_the_stuck_line_names_the_site_and_what_stopped_the_bot(reason, line):
    assert stuck_line(replace(CARD, reason=reason)) == line


def test_a_bot_that_asked_quotes_its_reason_with_the_site():
    card = replace(CARD, reason="asked", note="approve the payment of 40 euros")
    assert stuck_line(card) == (
        "I need your help on shop.example: approve the payment of 40 euros. "
        "Take control to clear it, then give it back."
    )


def test_a_bot_that_asked_without_a_page_still_quotes_its_reason():
    card = replace(CARD, reason="asked", url="", note="approve the payment of 40 euros")
    assert stuck_line(card) == (
        "I need your help: approve the payment of 40 euros. Take control to clear it, then give it back."
    )


def test_a_reason_that_ends_its_own_sentence_gets_no_second_full_stop():
    card = replace(CARD, reason="asked", url="", note="  approve the payment.  ")
    assert stuck_line(card) == "I need your help: approve the payment. Take control to clear it, then give it back."


def test_the_bot_can_suggest_the_main_brave():
    card = replace(CARD, reason="challenge", suggest_main_browser=True)
    assert stuck_line(card) == (
        "I'm stuck on shop.example: a check that I'm human. Take control to clear it, then give it back. "
        "I think this needs your main Brave."
    )


def test_the_blocked_line_says_what_was_not_finished():
    assert blocked_line("shop.example", REQUEST) == (
        "Blocked: shop.example keeps stopping me. I didn't finish: buy two tickets for Friday"
    )


def test_the_give_up_line():
    assert GIVE_UP_LINE == "OK, I stopped that task."


def test_the_continue_text_after_the_user_cleared_the_block():
    assert continue_text(CARD) == (
        "I cleared the block on shop.example. Read the page again and carry on with: buy two tickets for Friday"
    )


def test_the_continue_text_after_the_main_brave():
    assert continue_text(replace(CARD, main_opened=True)) == (
        "I did this step in my own browser on shop.example. "
        "Read your page again and carry on with: buy two tickets for Friday"
    )


def test_the_continue_text_when_the_card_had_no_page():
    card = replace(CARD, reason="asked", url="", note="approve the payment.")
    assert continue_text(card) == "I helped with: approve the payment. Carry on with: buy two tickets for Friday"


def test_the_card_message_body_is_the_card_as_json():
    card = replace(CARD, suggest_main_browser=True)
    assert json.loads(stuck_message_body(card)) == {
        "card_id": "card-1", "bot_id": "bot-1", "reason": "login", "host": "shop.example",
        "url": "https://shop.example/checkout?step=2", "note": "", "suggest_main_browser": True,
        "line": ("I'm stuck on shop.example: a sign-in page. Take control to clear it, then give it back. "
                 "I think this needs your main Brave."),
    }
```

**2f. Announcing.** Create `tests/test_stuck_announce.py`:

```python
"""Announcing a Stuck card (R7): the ``stuck_card`` frame, and the bot's own lines in its chat."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.desk.stuck import Block, host_of_url
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.stuck.announce import post_bot_line, publish_card
from roost.stuck.models import CardDraft, StuckCard, stuck_card_out
from roost.stuck.store import StuckStore
from roost.stuck.texts import GIVE_UP_LINE, stuck_message_body
from roost.talk.store import TalkStore, message_out
from team_helpers import frames_so_far, make_bot

URL = "https://login.example/account"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _card(cfg, user_id: str, *, tainted: bool = False) -> StuckCard:
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    block = Block(reason="login", url=URL, host=host_of_url(URL))
    return await StuckStore(cfg).open(user_id, CardDraft(
        bot_id=bot.id, thread_id=thread.id, work_item_id=None, block=block,
        request="pay the gas bill", tainted=tainted,
    ))


async def test_the_wire_shape_has_no_user_id_and_no_request(cfg, user_id):
    card = await _card(cfg, user_id)
    assert stuck_card_out(card).model_dump(mode="json") == {
        "id": card.id, "bot_id": card.bot_id, "thread_id": card.thread_id, "reason": "login",
        "host": "login.example", "url": URL, "note": "", "suggest_main_browser": False, "tainted": False,
        "main_opened": False, "state": "open", "created_at": card.created_at, "closed_at": None,
    }


async def test_publish_card_sends_the_cards_wire_shape(cfg, user_id):
    events = EventHub(cfg)
    subscription = events.subscribe(user_id)
    card = await _card(cfg, user_id)
    await publish_card(events, user_id, card)
    frames = [frame for frame in await frames_so_far(subscription) if frame["type"] == "stuck_card"]
    assert [frame["card"] for frame in frames] == [stuck_card_out(card).model_dump(mode="json")]


async def test_the_card_frame_is_kept_for_replay_and_encrypted_at_rest(cfg, user_id):
    events = EventHub(cfg)
    card = await _card(cfg, user_id)
    await publish_card(events, user_id, card)
    replayed = [event for event in await events.since(user_id, 0) if event["type"] == "stuck_card"]
    assert [event["card"]["id"] for event in replayed] == [card.id]
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT payload FROM events WHERE user_id = ? AND kind = 'stuck_card'", (user_id,),
        )).fetchall()
    assert len(rows) == 1
    assert rows[0]["payload"].startswith("enc:v2:") and "login.example" not in rows[0]["payload"]


async def test_the_card_message_is_the_bots_and_carries_the_cards_taint(cfg, user_id):
    talk, events = TalkStore(cfg), EventHub(cfg)
    subscription = events.subscribe(user_id)
    card = await _card(cfg, user_id, tainted=True)
    message = await post_bot_line(talk, events, user_id, card, stuck_message_body(card), kind="stuck")
    assert (message.role, message.kind, message.author_bot_id, message.tainted, message.thread_id) == (
        "bot", "stuck", card.bot_id, True, card.thread_id,
    )
    [stored] = await talk.list_messages(user_id, card.thread_id)
    assert stored == message
    frames = [frame for frame in await frames_so_far(subscription) if frame["type"] == "message"]
    assert [(frame["thread_id"], frame["message"]) for frame in frames] == [(card.thread_id, message_out(message))]


async def test_a_plain_bot_line_uses_the_kind_it_is_given(cfg, user_id):
    talk, events = TalkStore(cfg), EventHub(cfg)
    card = await _card(cfg, user_id)
    message = await post_bot_line(talk, events, user_id, card, GIVE_UP_LINE, kind="text")
    assert (message.role, message.kind, message.body, message.tainted) == ("bot", "text", GIVE_UP_LINE, False)
```

`kind="stuck"` is a plain string at runtime. Task 5 adds it to the `MessageKind` Literal, and `messages.kind` has no CHECK, so the test needs nothing from Task 5.

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_store.py tests/test_stuck_texts.py tests/test_stuck_announce.py -q`
Expected: three collection errors, `ModuleNotFoundError: No module named 'roost.stuck'`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations_v11.py tests/test_migrations_v10.py -q`
Expected: FAIL, `6 failed, 3 passed`:
- `test_v11_database_migrates_to_latest_and_keeps_every_row` fails with `assert 11 >= 12`.
- `test_v11_database_gains_the_stuck_cards_table` fails with `set() == {...}`.
- The three row tests fail with `sqlite3.OperationalError: no such table: stuck_cards`.
- `test_migrating_v11_twice_is_a_no_op_and_backs_up_once` fails with `ValueError: not enough values to unpack (expected 1, got 0)`, because nothing is pending, so nothing is backed up.
- The three v10 tests still pass: the latest version is still 11.

- [ ] **Step 4: Implement migration v12**

In `roost/db/migrations.py`, find:

```python
MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "work queue", (
```

Replace it with:

```python
# Stuck flow (Piece A): one row per Stuck card. url, note and request are enc:v2
# under stuck_cards:<column> (note is NULL when empty); ids, reason, state, flags
# and times are plaintext. A card goes with its bot and with its chat (CASCADE),
# so "Retire this bot" removes its cards. answer_item_id is the card_answer work
# item that /clear queued, which rung 4 looks the card up by.
_STUCK_CARDS = """
CREATE TABLE IF NOT EXISTS stuck_cards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    work_item_id TEXT,
    reason TEXT NOT NULL CHECK (reason IN ('challenge','login','code','refused','asked')),
    url TEXT NOT NULL,                 -- enc:v2, AAD stuck_cards:url
    note TEXT,                         -- enc:v2, AAD stuck_cards:note (nullable)
    request TEXT NOT NULL,             -- enc:v2, AAD stuck_cards:request
    suggest_main_browser INTEGER NOT NULL DEFAULT 0,
    tainted INTEGER NOT NULL DEFAULT 0,
    main_opened INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','cleared','given_up','blocked')),
    answer_item_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
)"""

MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "work queue", (
```

Then find the end of the tuple:

```python
    Migration(11, "bot notify", (
        # S1.10: tell the user when this bot finishes or needs them. Plaintext flag, default on.
        AddColumn("bots", "notify", "INTEGER NOT NULL DEFAULT 1"),
    )),
)
```

Replace it with:

```python
    Migration(11, "bot notify", (
        # S1.10: tell the user when this bot finishes or needs them. Plaintext flag, default on.
        AddColumn("bots", "notify", "INTEGER NOT NULL DEFAULT 1"),
    )),
    Migration(12, "stuck cards", (
        _STUCK_CARDS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_stuck_cards_one_open ON stuck_cards(user_id, bot_id) "
        "WHERE state = 'open'",
        "CREATE INDEX IF NOT EXISTS idx_stuck_cards_user ON stuck_cards(user_id, state, created_at)",
    )),
)
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations_v11.py tests/test_migrations_v10.py tests/test_migrations.py tests/test_migrations_v8.py tests/test_migrations_v4.py -q`
Expected: PASS.

- [ ] **Step 5: Implement the package and its models**

Create `roost/stuck/__init__.py`:

```python
"""Stuck cards (stuck flow, Piece A): a bot that meets a block it can't pass stops and asks you in its chat."""
```

Create `roost/stuck/models.py`:

```python
"""Stuck cards (stuck flow §2, R6–R9): frozen dataclasses for the store and the
run, plus the one pydantic wire shape the face gets (no ``user_id``, no
``request``)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict

from roost.desk.stuck import Block, BlockReason, host_of_url


class CardState(str, Enum):
    OPEN = "open"
    CLEARED = "cleared"
    GIVEN_UP = "given_up"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CardDraft:
    """What a stopped run hands the store: the block, and the request to carry on with."""

    bot_id: str
    thread_id: str
    work_item_id: str | None
    block: Block
    request: str
    tainted: bool


@dataclass(frozen=True)
class StuckCard:
    id: str
    user_id: str
    bot_id: str
    thread_id: str
    work_item_id: str | None
    reason: BlockReason
    url: str
    note: str
    request: str
    suggest_main_browser: bool
    tainted: bool
    main_opened: bool
    state: CardState
    answer_item_id: str | None
    created_at: str
    closed_at: str | None

    @property
    def host(self) -> str:
        return host_of_url(self.url)


class StuckCardOut(BaseModel):
    """The card's wire shape: ``GET /api/stuck`` and the ``stuck_card`` frame."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    bot_id: str
    thread_id: str
    reason: BlockReason
    host: str
    url: str
    note: str
    suggest_main_browser: bool
    tainted: bool
    main_opened: bool
    state: CardState
    created_at: str
    closed_at: str | None


def stuck_card_out(card: StuckCard) -> StuckCardOut:
    return StuckCardOut(
        id=card.id, bot_id=card.bot_id, thread_id=card.thread_id, reason=card.reason, host=card.host,
        url=card.url, note=card.note, suggest_main_browser=card.suggest_main_browser, tainted=card.tainted,
        main_opened=card.main_opened, state=card.state, created_at=card.created_at, closed_at=card.closed_at,
    )


class CardClosed(Exception):
    """The card is no longer open (cleared, given up or blocked): the route answers 409."""


class NoAddress(Exception):
    """The card has no web address to open: the route answers 400."""
```

- [ ] **Step 6: Implement the store**

Create `roost/stuck/store.py`:

```python
"""``StuckStore`` — the Stuck cards (stuck flow §2, R6–R9; schema v12).

``url``, ``note`` and ``request`` are user content, ``enc:v2`` under
``stuck_cards:<column>``; ids, reason, state, flags and times stay plaintext.
Every per-user query has ``user_id`` in its ``WHERE``, so another user's card
id reads as "no such card". ``open_bots`` runs once at boot, across users,
like ``WorkQueue.bots_with_queued``.

One open card per bot: the partial unique index ``idx_stuck_cards_one_open``
refuses a second open row, and ``open`` then returns the card that is already
open. State changes are guarded ``UPDATE ... RETURNING`` statements, so of two
presses on one card exactly one wins; the other gets ``None``."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, get_args
from uuid import uuid4

import aiosqlite

from roost.config import RoostConfig
from roost.constants import STUCK_LIST_LIMIT, STUCK_REQUEST_MAX_CHARS
from roost.crypto.encryption import decrypt_field, encrypt, encrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.desk.stuck import BlockReason
from roost.stuck.models import CardDraft, CardState, StuckCard

_COLUMNS = (
    "id, user_id, bot_id, thread_id, work_item_id, reason, url, note, request, suggest_main_browser, "
    "tainted, main_opened, state, answer_item_id, created_at, closed_at"
)
_INSERT = (
    "INSERT INTO stuck_cards (id, user_id, bot_id, thread_id, work_item_id, reason, url, note, request, "
    "suggest_main_browser, tainted, state, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_REASONS = frozenset(get_args(BlockReason))
_CLOSING_STATES = frozenset({CardState.CLEARED, CardState.GIVEN_UP, CardState.BLOCKED})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"stuck_cards:{column}")


def _row_to_card(row: aiosqlite.Row, dek: bytes) -> StuckCard:
    user_id = row["user_id"]
    return StuckCard(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"], thread_id=row["thread_id"],
        work_item_id=row["work_item_id"], reason=row["reason"],
        # An address that can't be read is no address: the card can't open it anywhere.
        url=decrypt_field(row["url"], dek, _aad(user_id, "url"), fallback="") or "",
        note=decrypt_field(row["note"], dek, _aad(user_id, "note")) or "",
        request=decrypt_field(row["request"], dek, _aad(user_id, "request")) or "",
        suggest_main_browser=bool(row["suggest_main_browser"]), tainted=bool(row["tainted"]),
        main_opened=bool(row["main_opened"]), state=CardState(row["state"]),
        answer_item_id=row["answer_item_id"], created_at=row["created_at"], closed_at=row["closed_at"],
    )


def _new_card(user_id: str, draft: CardDraft) -> StuckCard:
    block = draft.block
    if block.reason not in _REASONS:
        raise ValueError(f"Unknown Stuck reason: {block.reason!r}.")
    return StuckCard(
        id=str(uuid4()), user_id=user_id, bot_id=draft.bot_id, thread_id=draft.thread_id,
        work_item_id=draft.work_item_id, reason=block.reason, url=block.url, note=block.note,
        request=draft.request[:STUCK_REQUEST_MAX_CHARS], suggest_main_browser=block.suggest_main_browser,
        tainted=draft.tainted, main_opened=False, state=CardState.OPEN, answer_item_id=None,
        created_at=_now_iso(), closed_at=None,
    )


def _insert_params(card: StuckCard, dek: bytes) -> tuple:
    user_id = card.user_id
    return (
        card.id, user_id, card.bot_id, card.thread_id, card.work_item_id, card.reason,
        encrypt(card.url, dek, _aad(user_id, "url")),
        encrypt_field(card.note or None, dek, _aad(user_id, "note")),
        encrypt(card.request, dek, _aad(user_id, "request")),
        int(card.suggest_main_browser), int(card.tainted), card.state.value, card.created_at,
    )


class StuckStore:
    def __init__(self, config: RoostConfig) -> None:
        self._config = config

    async def open(self, user_id: str, draft: CardDraft) -> StuckCard:
        """Open a card for ``draft.bot_id``. A bot has at most one open card:
        when one is open already, that card comes back and nothing is written."""
        card = _new_card(user_id, draft)
        dek = await get_user_dek(self._config, user_id)
        if await self._insert(card, dek):
            return card
        existing = await self.open_for_bot(user_id, draft.bot_id)
        if existing is None:
            raise ValueError("Can't open a Stuck card: that bot or its chat no longer exists.")
        return existing

    async def get(self, user_id: str, card_id: str) -> StuckCard | None:
        found = await self._select(user_id, "WHERE id = ? AND user_id = ?", (card_id, user_id))
        return found[0] if found else None

    async def list_open(self, user_id: str) -> tuple[StuckCard, ...]:
        """The user's open cards, newest first (Home's My turn, ``GET /api/stuck``)."""
        return await self._select(
            user_id, "WHERE user_id = ? AND state = 'open' ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (user_id, STUCK_LIST_LIMIT),
        )

    async def open_for_bot(self, user_id: str, bot_id: str) -> StuckCard | None:
        found = await self._select(
            user_id, "WHERE user_id = ? AND bot_id = ? AND state = 'open' LIMIT 1", (user_id, bot_id),
        )
        return found[0] if found else None

    async def close(self, user_id: str, card_id: str, state: CardState, *,
                    answer_item_id: str | None = None) -> StuckCard | None:
        """Close an open card as ``state``. ``None`` when the card is not the
        user's or is no longer open (a second press, another tab)."""
        target = CardState(state)
        if target not in _CLOSING_STATES:
            raise ValueError(f"A Stuck card can't be closed as {target.value!r}.")
        return await self._transition(
            user_id, card_id, CardState.OPEN,
            "state = ?, answer_item_id = ?, closed_at = ?", (target.value, answer_item_id, _now_iso()),
        )

    async def mark_blocked(self, user_id: str, card_id: str) -> StuckCard | None:
        """Rung 4: the continue run this card queued was stopped again. Only from ``cleared``."""
        return await self._transition(user_id, card_id, CardState.CLEARED, "state = ?, closed_at = ?",
                                      (CardState.BLOCKED.value, _now_iso()))

    async def mark_main_opened(self, user_id: str, card_id: str) -> StuckCard | None:
        """The user opened the card's page in their main Brave. Only while open."""
        return await self._transition(user_id, card_id, CardState.OPEN, "main_opened = 1", ())

    async def card_for_answer(self, user_id: str, item_id: str) -> StuckCard | None:
        """The card whose ``/clear`` queued the ``card_answer`` item ``item_id``."""
        found = await self._select(
            user_id, "WHERE user_id = ? AND answer_item_id = ? LIMIT 1", (user_id, item_id),
        )
        return found[0] if found else None

    async def open_bots(self) -> tuple[tuple[str, str], ...]:
        """Boot only, across users: every (user_id, bot_id) with an open card."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                "SELECT user_id, bot_id FROM stuck_cards WHERE state = 'open' ORDER BY created_at, rowid",
            )).fetchall()
        return tuple((row["user_id"], row["bot_id"]) for row in rows)

    async def _insert(self, card: StuckCard, dek: bytes) -> bool:
        """False when the database refuses the row: the bot already has an
        open card, or the bot or chat is gone."""
        async with db_session(self._config) as db:
            try:
                await db.execute(_INSERT, _insert_params(card, dek))
                await db.commit()
            except aiosqlite.IntegrityError:
                await db.rollback()
                return False
        return True

    async def _transition(self, user_id: str, card_id: str, from_state: CardState,
                          assignments: str, params: tuple) -> StuckCard | None:
        async with db_session(self._config) as db:
            cursor = await db.execute(
                f"UPDATE stuck_cards SET {assignments} WHERE id = ? AND user_id = ? AND state = ? "
                f"RETURNING {_COLUMNS}",
                (*params, card_id, user_id, from_state.value),
            )
            rows = await cursor.fetchall()
            await db.commit()
        found = await self._cards(user_id, rows)
        return found[0] if found else None

    async def _select(self, user_id: str, where: str, params: tuple) -> tuple[StuckCard, ...]:
        async with db_session(self._config) as db:
            rows = await (await db.execute(f"SELECT {_COLUMNS} FROM stuck_cards {where}", params)).fetchall()
        return await self._cards(user_id, rows)

    async def _cards(self, user_id: str, rows: Sequence[aiosqlite.Row]) -> tuple[StuckCard, ...]:
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_card(row, dek) for row in rows)
```

- [ ] **Step 7: Implement the words**

Create `roost/stuck/texts.py`:

```python
"""The Stuck flow's words (stuck flow §2, R6, R7): what the bot says in its chat,
and the continue line posted for you. They are user-facing and chat-facing, so
they live in one place. The model-facing tool results are in
``roost/talk/instructions.py``."""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Mapping

from roost.stuck.models import StuckCard

REASON_WORDS: Mapping[str, str] = MappingProxyType({
    "challenge": "a check that I'm human",
    "login": "a sign-in page",
    "code": "a code check",
    "refused": "the site refusing me",
    "asked": "something only you can do",
})
GIVE_UP_LINE = "OK, I stopped that task."
_HAND_BACK = " Take control to clear it, then give it back."
_MAIN_BRAVE_HINT = " I think this needs your main Brave."


def _clause(text: str) -> str:
    """The bot's own words, ready to end with our full stop (never two)."""
    return text.strip().rstrip(".")


def _opening(card: StuckCard) -> str:
    if card.reason == "asked":
        note = _clause(card.note)
        return f"I need your help on {card.host}: {note}." if card.host else f"I need your help: {note}."
    return f"I'm stuck on {card.host}: {REASON_WORDS[card.reason]}."


def stuck_line(card: StuckCard) -> str:
    hint = _MAIN_BRAVE_HINT if card.suggest_main_browser else ""
    return _opening(card) + _HAND_BACK + hint


def blocked_line(host: str, request: str) -> str:
    return f"Blocked: {host} keeps stopping me. I didn't finish: {request}"


def continue_text(card: StuckCard) -> str:
    """The user's line that a ``card_answer`` item carries to the model (R6)."""
    if not card.host:
        return f"I helped with: {_clause(card.note)}. Carry on with: {card.request}"
    if card.main_opened:
        return (f"I did this step in my own browser on {card.host}. "
                f"Read your page again and carry on with: {card.request}")
    return f"I cleared the block on {card.host}. Read the page again and carry on with: {card.request}"


def stuck_message_body(card: StuckCard) -> str:
    """The ``kind="stuck"`` message's body: the card as JSON, like the Created card."""
    return json.dumps({
        "card_id": card.id, "bot_id": card.bot_id, "reason": card.reason, "host": card.host,
        "url": card.url, "note": card.note, "suggest_main_browser": card.suggest_main_browser,
        "line": stuck_line(card),
    })
```

- [ ] **Step 8: Implement announcing**

Create `roost/stuck/announce.py`:

```python
"""Announcing a Stuck card (stuck flow R7): the ``stuck_card`` frame that every
state change publishes, and the bot's own lines in its chat (the card message,
the blocked line, the give-up line)."""

from __future__ import annotations

from roost.events.hub import EventHub
from roost.stuck.models import StuckCard, stuck_card_out
from roost.talk.store import Message, MessageKind, TalkStore, message_out


async def publish_card(events: EventHub, user_id: str, card: StuckCard) -> None:
    """Sent on open, cleared, given_up, blocked and main_opened. Stored encrypted like every frame."""
    await events.publish(user_id, {"type": "stuck_card", "card": stuck_card_out(card).model_dump(mode="json")})


async def post_bot_line(
    talk: TalkStore, events: EventHub, user_id: str, card: StuckCard, body: str, *, kind: MessageKind,
) -> Message:
    """Post ``body`` in the card's chat as the card's bot, with the card's taint, and publish it live."""
    message = await talk.add_message(
        user_id, card.thread_id, role="bot", body=body, tainted=card.tainted,
        kind=kind, author_bot_id=card.bot_id,
    )
    await events.publish(user_id, {"type": "message", "thread_id": card.thread_id, "message": message_out(message)})
    return message
```

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations_v11.py tests/test_migrations_v10.py tests/test_stuck_store.py tests/test_stuck_texts.py tests/test_stuck_announce.py -q`
Expected: PASS, `51 passed` (6 + 3 + 21 + 16 + 5).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_store.py tests/test_stuck_texts.py tests/test_stuck_announce.py --cov=roost.stuck --cov-report=term-missing -q`
Expected: PASS. Every file under `roost/stuck/` is at 80% or more; 100% is expected, since every branch has a test.

The related existing tests must stay green:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations.py tests/test_migrations_v4.py tests/test_migrations_v8.py tests/test_db.py tests/test_db_connection.py tests/test_bot_store.py tests/test_main_bot.py tests/test_bots_api.py tests/test_events_hub.py tests/test_work_queue.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/db/migrations.py roost/stuck/__init__.py roost/stuck/models.py roost/stuck/store.py \
  roost/stuck/texts.py roost/stuck/announce.py tests/fixtures/schema_v11.sql tests/test_migrations_v10.py \
  tests/test_migrations_v11.py tests/test_stuck_store.py tests/test_stuck_texts.py tests/test_stuck_announce.py
git status --short   # nothing from this task may still be listed as modified or untracked
git commit -m "feat: Stuck cards: schema v12, encrypted store, card words and announcing"
```

---

### Task 4: ToolRunner: rung 1, blocks and ask_for_help

Design §1 and refinements R1, R3, R4 and R5:
- Every page the bot opens or reads goes through `detect_block` (Task 1).
- **`challenge` (rung 1):** the runner says "waiting for {host} to let me in", waits `STUCK_CHALLENGE_WAIT_SECONDS`, then repeats **the same call** once: `open_page(url)` again, or `read_page()` again. It never reloads. If the user took control during the wait, the repeat is skipped (Review Focus 2).
- **`login` and `code`:** these are blocks at once, with no wait.
- **`refused`:** the first refusal on a host in a run is only a result (`refused_once_text`). A second refusal on the same host is a block.
- **A block that stays:**
  - In your own chat (`cards=True`), it sets `ToolRunner.block` and returns `stuck_result_text`.
  - In every other run, it returns the loud `blocked_result_text` and sets no block.
  - Either way, the blocked page's text never reaches the model. The page still counts as read: it sets taint, host and URL, and its address (only its address, never the links in its text) joins the link scope.
- **`ask_for_help(reason, suggest_main_browser=False)`:** a `read` tool. Only in your own chat, it sets `Block("asked", url, host, reason, suggest_main_browser)`. `url` is `last_url` as `check_url` returns it, or `""` when there is no web page to point at: nothing opened yet, or a fresh tab's `about:blank`. A card then never names a page it can't open, its continue line says "I helped with: …" (Task 3), and rung 4 never matches it by host (Task 5).
- **After a block:** once `self.block` is set, every later call in the step returns `STUCK_NOT_PERFORMED_TEXT` and does nothing.
- **The model's words:** `stuck_result_text` and `blocked_result_text` name what stopped the bot through `instructions.py`'s own private `_MODEL_REASON_WORDS` ("a check that you are human", "a sign-in page", "a code check", "a refusal", "a request for the user's help"). They never use Task 3's `REASON_WORDS`, which speak in the bot's own voice to the user ("a check that I'm human") and stay exactly as they are, like every user-facing text.

This task opens no card and does not touch `turn.py`. `cards` defaults to `False`, so until Task 5 passes `cards=_may_open_cards(inputs)`, every real run gets the loud result.

**Files:**
- Create:
  - `roost/talk/stuck_check.py` (rung 1 and `AskForHelpArgs`, kept out of `tool_runner.py`)
  - `tests/test_stuck_tool_runner.py`
- Modify:
  - `roost/talk/instructions.py`:
    - the model-facing stuck texts from the contract, and their private `_MODEL_REASON_WORDS`;
    - the `_STUCK_TEXT` prompt section, right after `_COMPUTER_DESCRIPTION` (that section stays word for word).
  - `roost/talk/tool_catalog.py`: `ASK_FOR_HELP_SPEC`, plus `ToolDef(ASK_FOR_HELP_SPEC, "read")` right after `GET_TIME_SPEC`.
  - `roost/talk/tool_runner.py`:
    - the `cards` keyword, and public `block` and `last_url`;
    - the early `STUCK_NOT_PERFORMED_TEXT`;
    - the page check after `open_page` / `read_page`;
    - `ask_for_help` dispatch.
  - `tests/test_instructions.py`: the prompt names `ask_for_help`, and the stuck texts.
- Test:
  - `tests/test_stuck_tool_runner.py` and `tests/test_instructions.py`.
  - These stay green without edits:
    - `tests/test_gate.py`: `test_every_allowed_tool_decides_do` is parametrized over `sorted(CATALOG)` and gains an `ask_for_help` case; `test_every_catalog_tool_has_a_gate_kind` also passes.
    - `tests/test_every_bot_tools.py`: `ask_for_help` lands in `EVERY_BOT_TOOLS`, and its description has no `" role"`.
    - `tests/test_computer_control_runs.py`: no catalog name contains `"control"`.
    - `tests/test_tool_runner_taint.py`
    - `tests/test_turn.py`: the blocked-URL and desk-unavailable paths still return the same texts and leave the run untainted.

**Interfaces:**
- Consumes:
  - **Task 1:**
    - `roost.desk.stuck`: `Block(reason, url, host, note="", suggest_main_browser=False)`, `detect_block(page: PageText) -> Block | None` (which returns `Block(reason=…, url=page.url, host=host_of_url(page.url))`) and `host_of_url(url: str) -> str`.
    - `roost.desk.stuck.BlockReason = Literal["challenge", "login", "code", "refused", "asked"]`, which `_MODEL_REASON_WORDS` covers key for key.
    - `PageText(url, title, text, truncated, status=None, password_field=False, captcha_frame=False)`.
    - `roost.constants.STUCK_CHALLENGE_WAIT_SECONDS` and `STUCK_REASON_MAX_CHARS`.
  - **Task 2:** `FakeDesk.serve(url: str, *pages: PageText) -> None`. Each `open_page(url)` / `read_page()` of a served URL returns the next page, and the last one repeats. `open_page` keeps the served `status`; `read_page` gives `status=None`. `open_page_calls` still records every `open_page`, and `force_unavailable` still applies to served URLs.
  - **Task 3:** nothing. `instructions.py` keeps its own model-facing `_MODEL_REASON_WORDS` and does not import `roost.stuck`. `roost.stuck.texts.REASON_WORDS` stays the user-facing words, unchanged.
  - **Existing:**
    - `roost.records.tool_text.ToolText`
    - `check_url` / `UrlBlocked` (`roost/desk/url_policy.py`, lexical only, no network)
    - `ControlLock.held` / `take` (`roost/desk/control.py`)
    - `ToolRunner._announce`
    - `LinkScope.with_page`
- Produces (Task 5 relies on these):
  - `roost.talk.instructions`:
    - `ASKED_FOR_HELP_TEXT`, `ASK_ONLY_IN_CHAT_TEXT`, `BAD_HELP_ARGS_TEXT` and `STUCK_NOT_PERFORMED_TEXT`;
    - `stuck_result_text(block: Block) -> str`, `blocked_result_text(block: Block) -> str` and `refused_once_text(host: str, status: int) -> str`;
    - the `_STUCK_TEXT` prompt section.
  - `roost.talk.tool_catalog.ASK_FOR_HELP_SPEC`, and `CATALOG["ask_for_help"].kind == "read"`.
  - `roost.talk.tool_runner.ToolRunner(..., control=None, cards: bool = False)`, with:
    - public `self.block: Block | None` and `self.last_url: str | None`;
    - `run()` returns `STUCK_NOT_PERFORMED_TEXT` once `block` is set.
  - `roost.talk.stuck_check`:
    - `AskForHelpArgs`
    - `Checked(page, block)`
    - `Fetch = Callable[[], Awaitable[PageText]]`
    - `async check_page(page, fetch, *, wait_seconds, announce, hands_taken) -> Checked`

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_stuck_tool_runner.py`:

```python
"""ToolRunner and the stuck ladder (stuck flow, Task 4): rung 1's wait and
repeat, blocks, the refused-once rule and ask_for_help. Pages come from
FakeDesk.serve (Task 2). The 8-second wait is patched on the name
tool_runner imported (roost.talk.tool_runner.STUCK_CHALLENGE_WAIT_SECONDS)."""

from __future__ import annotations

import asyncio
import time

import pytest

import roost.talk.tool_runner as tool_runner_module
from roost.bots.status import ActivityBoard
from roost.config import load_config
from roost.constants import STUCK_REASON_MAX_CHARS
from roost.db.connection import init_db
from roost.desk import PageText
from roost.desk.control import ControlLock
from roost.desk.fake import FakeDesk
from roost.desk.stuck import Block
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested
from roost.talk.gate import Gate
from roost.talk.instructions import (
    ASK_ONLY_IN_CHAT_TEXT, ASKED_FOR_HELP_TEXT, BAD_HELP_ARGS_TEXT, STUCK_NOT_PERFORMED_TEXT,
    blocked_result_text, refused_once_text, stuck_result_text,
)
from roost.talk.tool_catalog import CATALOG
from roost.talk.tool_runner import ToolRunner, wrap_page
from team_helpers import make_bot, until

_URL = "https://shop.example/item"
_HOST = "shop.example"
_OTHER_URL = "https://other.example/item"
_WAITING = f"waiting for {_HOST} to let me in"
_UNAVAILABLE = "Your computer is unavailable right now."


def _page(title: str, text: str, *, url: str = _URL, status: int | None = 200,
          password_field: bool = False) -> PageText:
    return PageText(url=url, title=title, text=text, truncated=False, status=status,
                    password_field=password_field)


_ARTICLE = _page("Blue kettle", "The blue kettle costs 40 euros and ships in two days.")
_CHALLENGE = _page("Just a moment...", "Checking your browser before accessing shop.example.", status=403)
_LOGIN = _page("Sign in", "Sign in to continue. Email. Forgot your password?", password_field=True)
_CODE = _page("Two-step verification",
              "Enter the verification code we sent to your phone. No code? https://help.example/2fa")
_REFUSED = _page("Forbidden", "Access denied.", status=403)
_OTHER_REFUSED = _page("Too many requests", "Slow down.", url=_OTHER_URL, status=429)


class _Lines(ActivityBoard):
    """Keeps every activity line the runner announced, in order."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: tuple[str, ...] = ()

    def set(self, bot_id: str, text: str | None, *, tainted: bool = False) -> None:
        super().set(bot_id, text, tainted=tainted)
        if text is not None:
            self.lines = (*self.lines, text)


class _TakesControlDesk(FakeDesk):
    """The user presses Take control as the challenge loads, so the hold is there for the whole wait."""

    def __init__(self, bot_id: str, lock: ControlLock) -> None:
        super().__init__(bot_id)
        self._lock = lock

    async def open_page(self, url: str) -> PageText:
        page = await super().open_page(url)
        if page.title == _CHALLENGE.title:
            self._lock.take(self.bot_id)
        return page


class _DownBeforeTheRepeatDesk(FakeDesk):
    """The keeper goes away between the first load and rung 1's repeat."""

    async def open_page(self, url: str) -> PageText:
        page = await super().open_page(url)
        self.force_unavailable = True
        return page


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def ids(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    return user_id, (await make_bot(cfg, user_id, "Scout")).id


@pytest.fixture(autouse=True)
def _short_wait(monkeypatch):
    """Rung 1 waits STUCK_CHALLENGE_WAIT_SECONDS (8 s). tool_runner imports the name, so it is patched there."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)


def _runner(cfg, ids, desk: FakeDesk, *, cards: bool, control: ControlLock | None = None) -> ToolRunner:
    user_id, bot_id = ids
    return ToolRunner(
        user_id=user_id, bot_id=bot_id, desk=desk, gate=Gate(cfg), activity=_Lines(), events=EventHub(cfg),
        allowed=frozenset(CATALOG), cards=cards, control=control,
    )


def _served(ids, *pages: PageText, url: str = _URL) -> FakeDesk:
    desk = FakeDesk(ids[1])
    desk.serve(url, *pages)
    return desk


def _open(url: str = _URL, call_id: str = "p") -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name="open_page", arguments={"url": url})


def _read(call_id: str = "r") -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name="read_page", arguments={})


def _ask(reason: object = "a payment check on the card form", call_id: str = "h",
         **extra: object) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name="ask_for_help", arguments={"reason": reason, **extra})


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------

def test_ask_for_help_is_a_read_tool_right_after_get_time():
    names = list(CATALOG)
    tool = CATALOG["ask_for_help"]
    assert tool.kind == "read"
    assert names.index("ask_for_help") == names.index("get_time") + 1
    assert tool.spec.input_schema["required"] == ["reason"]
    assert set(tool.spec.input_schema["properties"]) == {"reason", "suggest_main_browser"}
    assert " role" not in tool.spec.description and "control" not in tool.spec.description


# ---------------------------------------------------------------------------
# Rung 1: wait, then repeat the same call once
# ---------------------------------------------------------------------------

async def test_a_page_with_no_block_comes_back_as_usual(cfg, ids):
    desk = _served(ids, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open()) == wrap_page(_ARTICLE)
    assert runner.block is None
    assert (runner.last_host, runner.last_url, runner.tainted) == (_HOST, _URL, True)
    assert desk.open_page_calls == [_URL]
    assert _WAITING not in runner._activity.lines


async def test_a_challenge_that_clears_after_the_wait_returns_the_cleared_page(cfg, ids):
    desk = _served(ids, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open()) == wrap_page(_ARTICLE)
    assert runner.block is None
    assert desk.open_page_calls == [_URL, _URL]          # R4: the same call, repeated once
    assert _WAITING in runner._activity.lines


async def test_rung_one_waits_the_patched_wait_before_the_repeat(cfg, ids, monkeypatch):
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.2)
    runner = _runner(cfg, ids, _served(ids, _CHALLENGE, _ARTICLE), cards=True)
    started = time.monotonic()
    await runner.run(_open())
    assert time.monotonic() - started >= 0.2


async def test_a_challenge_on_read_page_repeats_read_page(cfg, ids):
    desk = _served(ids, _ARTICLE, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    await runner.run(_open())
    assert await runner.run(_read()) == wrap_page(_ARTICLE)
    assert runner.block is None
    assert desk.open_page_calls == [_URL]                 # the repeat was read_page again, not open_page


async def test_a_challenge_that_stays_sets_the_block_in_your_own_chat(cfg, ids):
    desk = _served(ids, _CHALLENGE)
    runner = _runner(cfg, ids, desk, cards=True)
    text = await runner.run(_open())
    assert runner.block == Block(reason="challenge", url=_URL, host=_HOST)
    assert text == stuck_result_text(runner.block)
    assert "Checking your browser" not in text            # the wall's own text never reaches the model
    assert desk.open_page_calls == [_URL, _URL]
    assert (runner.last_host, runner.last_url, runner.tainted) == (_HOST, _URL, True)
    assert runner.link_scope.allows(_URL)


async def test_a_challenge_that_stays_in_any_other_run_is_a_loud_result_and_no_block(cfg, ids):
    desk = _served(ids, _CHALLENGE)
    runner = _runner(cfg, ids, desk, cards=False)
    text = await runner.run(_open())
    assert text == blocked_result_text(Block(reason="challenge", url=_URL, host=_HOST))
    assert text.startswith("Blocked: ") and runner.block is None
    assert desk.open_page_calls == [_URL, _URL]           # R5: rung 1 runs in every run
    assert runner.tainted is True


@pytest.mark.parametrize(("page", "reason"), [(_LOGIN, "login"), (_CODE, "code")])
async def test_a_sign_in_page_or_a_code_check_is_a_block_at_once_with_no_wait(cfg, ids, page, reason):
    desk = _served(ids, page, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    text = await runner.run(_open())
    assert runner.block == Block(reason=reason, url=_URL, host=_HOST)
    assert text == stuck_result_text(runner.block)
    assert desk.open_page_calls == [_URL]
    assert not any(line.startswith("waiting for") for line in runner._activity.lines)
    assert runner.link_scope.as_tuple() == (_URL,)       # the wall's own links were never shown, so never join


async def test_an_address_the_bot_may_not_open_is_refused_before_any_check(cfg, ids):
    desk = FakeDesk(ids[1])
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open("http://127.0.0.1/")) == "Blocked: that address is not allowed."
    assert runner.block is None and runner.tainted is False and desk.open_page_calls == []


async def test_taking_control_during_the_wait_skips_the_repeat(cfg, ids, monkeypatch):
    """Review Focus 2: the user presses Take control while rung 1 waits. The bot must not
    navigate under the user's hands: no repeat, and the block stands (the card opens)."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.3)
    lock = ControlLock(wait_seconds=0.05)
    desk = _served(ids, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True, control=lock)
    call = asyncio.create_task(runner.run(_open()))
    await until(lambda: runner._activity.get(ids[1]) == _WAITING)
    lock.take(ids[1])
    assert await call == stuck_result_text(Block(reason="challenge", url=_URL, host=_HOST))
    assert desk.open_page_calls == [_URL]
    assert runner.block == Block(reason="challenge", url=_URL, host=_HOST)


async def test_control_taken_as_the_challenge_loads_also_skips_the_repeat(cfg, ids):
    lock = ControlLock(wait_seconds=0.05)
    desk = _TakesControlDesk(ids[1], lock)
    desk.serve(_URL, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True, control=lock)
    text = await runner.run(_open())
    assert desk.open_page_calls == [_URL]
    assert runner.block == Block(reason="challenge", url=_URL, host=_HOST)
    assert text == stuck_result_text(runner.block)


async def test_a_computer_that_goes_down_before_the_repeat_says_so(cfg, ids):
    desk = _DownBeforeTheRepeatDesk(ids[1])
    desk.serve(_URL, _CHALLENGE, _ARTICLE)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open()) == _UNAVAILABLE
    assert runner.block is None and runner.tainted is False


# ---------------------------------------------------------------------------
# Refused: a result the first time per host, a block the second time
# ---------------------------------------------------------------------------

async def test_a_first_refusal_on_a_host_is_a_result_not_a_block(cfg, ids):
    desk = _served(ids, _REFUSED)
    runner = _runner(cfg, ids, desk, cards=True)
    text = await runner.run(_open())
    assert text == refused_once_text(_HOST, 403)
    assert "Access denied" not in text
    assert runner.block is None
    assert desk.open_page_calls == [_URL]                 # a refusal gets no wait and no repeat


async def test_a_second_refusal_on_the_same_host_is_a_block(cfg, ids):
    runner = _runner(cfg, ids, _served(ids, _REFUSED), cards=True)
    await runner.run(_open(call_id="p1"))
    text = await runner.run(_open(call_id="p2"))
    assert runner.block == Block(reason="refused", url=_URL, host=_HOST)
    assert text == stuck_result_text(runner.block)


async def test_refusals_are_counted_per_host(cfg, ids):
    desk = _served(ids, _REFUSED)
    desk.serve(_OTHER_URL, _OTHER_REFUSED)
    runner = _runner(cfg, ids, desk, cards=True)
    assert await runner.run(_open(_URL, "p1")) == refused_once_text(_HOST, 403)
    assert await runner.run(_open(_OTHER_URL, "p2")) == refused_once_text("other.example", 429)
    assert runner.block is None


# ---------------------------------------------------------------------------
# After a block, nothing else in the step runs (R1)
# ---------------------------------------------------------------------------

async def test_after_a_block_every_later_call_is_not_performed(cfg, ids):
    desk = _served(ids, _LOGIN)
    runner = _runner(cfg, ids, desk, cards=True)
    await runner.run(_open(call_id="p1"))
    assert await runner.run(_open(_OTHER_URL, "p2")) == STUCK_NOT_PERFORMED_TEXT
    assert await runner.run(ToolCallRequested(id="t", name="get_time", arguments={})) == STUCK_NOT_PERFORMED_TEXT
    assert desk.open_page_calls == [_URL]


# ---------------------------------------------------------------------------
# ask_for_help
# ---------------------------------------------------------------------------

async def test_ask_for_help_in_your_own_chat_sets_an_asked_block_on_the_open_page(cfg, ids):
    runner = _runner(cfg, ids, _served(ids, _ARTICLE), cards=True)
    await runner.run(_open())
    text = await runner.run(_ask("The shop wants an ID check before checkout.", suggest_main_browser=True))
    assert text == ASKED_FOR_HELP_TEXT
    assert runner.block == Block(reason="asked", url=_URL, host=_HOST,
                                 note="The shop wants an ID check before checkout.", suggest_main_browser=True)
    assert runner._activity.lines[-1] == "asking you for help"


async def test_ask_for_help_before_any_page_has_no_address(cfg, ids):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    assert await runner.run(_ask()) == ASKED_FOR_HELP_TEXT
    assert runner.block == Block(reason="asked", url="", host="", note="a payment check on the card form")


async def test_ask_for_help_on_a_blank_tab_has_no_address(cfg, ids):
    """A fresh tab reads as about:blank. That is no web page, so the card names none
    (never "Stuck on about:blank", never a continue line about about:blank)."""
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    await runner.run(_read())
    assert runner.last_url == "about:blank" and runner.block is None
    assert await runner.run(_ask()) == ASKED_FOR_HELP_TEXT
    assert runner.block == Block(reason="asked", url="", host="", note="a payment check on the card form")


async def test_ask_for_help_outside_your_own_chat_is_refused(cfg, ids):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=False)
    assert await runner.run(_ask()) == ASK_ONLY_IN_CHAT_TEXT
    assert runner.block is None


@pytest.mark.parametrize("arguments", [
    {}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * (STUCK_REASON_MAX_CHARS + 1)}, {"reason": 42},
])
async def test_ask_for_help_needs_a_reason_of_1_to_the_cap(cfg, ids, arguments):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    call = ToolCallRequested(id="h", name="ask_for_help", arguments=arguments)
    assert await runner.run(call) == BAD_HELP_ARGS_TEXT
    assert runner.block is None


async def test_ask_for_help_keeps_the_reason_as_plain_text(cfg, ids):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    await runner.run(_ask("Ana&#x27;s card &amp; ID"))
    assert runner.block is not None and runner.block.note == "Ana's card & ID"


async def test_asking_twice_in_one_step_is_not_performed_the_second_time(cfg, ids):
    runner = _runner(cfg, ids, FakeDesk(ids[1]), cards=True)
    await runner.run(_ask("first", call_id="h1"))
    assert await runner.run(_ask("second", call_id="h2")) == STUCK_NOT_PERFORMED_TEXT
    assert runner.block is not None and runner.block.note == "first"
```

In `tests/test_instructions.py`, find:

```python
from zoneinfo import ZoneInfo

from roost.bots.models import Avatar, BotStatus, Bot
from roost.talk.instructions import Teammate, build_instructions
```

Replace with:

```python
from typing import get_args
from zoneinfo import ZoneInfo

from roost.bots.models import Avatar, BotStatus, Bot
from roost.constants import STUCK_REASON_MAX_CHARS
from roost.desk.stuck import Block, BlockReason
from roost.talk.instructions import (
    ASK_ONLY_IN_CHAT_TEXT, ASKED_FOR_HELP_TEXT, BAD_HELP_ARGS_TEXT, STUCK_NOT_PERFORMED_TEXT, Teammate,
    blocked_result_text, build_instructions, refused_once_text, stuck_result_text,
)
```

Then append at the end of `tests/test_instructions.py`, after `test_other_bots_are_told_to_send_the_user_to_the_main_bot`:

```python


def test_every_bot_is_told_how_to_ask_for_help_and_never_to_end_empty():
    prompt = build_instructions(_bot())
    assert "call ask_for_help with the reason and stop" in prompt
    assert "The user will Take control of your computer, clear it, then give it back" in prompt
    assert "Set suggest_main_browser only when your own browser window can't do it." in prompt
    assert "Never finish with an empty answer" in prompt


def test_the_help_section_comes_right_after_the_computer_section():
    prompt = build_instructions(_bot())
    computer = prompt.index("You cannot type, click, submit, buy, send or run commands yet.")
    assert computer < prompt.index("ask_for_help") < prompt.index("The current date and time")


def test_a_stuck_result_names_the_host_and_what_stopped_the_bot():
    block = Block(reason="login", url="https://shop.example/account", host="shop.example")
    assert stuck_result_text(block) == "Stuck: shop.example shows a sign-in page. The user has been asked to clear it."


def test_a_blocked_result_tells_the_model_to_say_the_site_stopped_it():
    block = Block(reason="challenge", url="https://shop.example/", host="shop.example")
    assert blocked_result_text(block) == (
        "Blocked: shop.example shows a check that you are human. You can't get past it in this task. "
        "Tell whoever asked that the site stopped you."
    )


def test_the_model_reads_every_reason_in_its_own_words_never_the_bots():
    """The tool results speak to the model. REASON_WORDS (roost.stuck.texts) are the bot's
    own voice to the user ("a check that I'm human") and must not leak into them."""
    words = {
        "challenge": "a check that you are human", "login": "a sign-in page", "code": "a code check",
        "refused": "a refusal", "asked": "a request for the user's help",
    }
    assert set(words) == set(get_args(BlockReason))
    for reason, word in words.items():
        block = Block(reason=reason, url="https://shop.example/", host="shop.example")
        assert stuck_result_text(block) == f"Stuck: shop.example shows {word}. The user has been asked to clear it."
        assert blocked_result_text(block).startswith(f"Blocked: shop.example shows {word}. ")
        assert "I'm" not in stuck_result_text(block) + blocked_result_text(block)


def test_a_first_refusal_names_the_status_and_offers_ask_for_help():
    assert refused_once_text("shop.example", 429) == (
        "Not shown: shop.example answered 429 and would not show the page. "
        "Try another way, or call ask_for_help if only the user can get past it."
    )


def test_a_host_in_a_stuck_text_cannot_smuggle_a_tag():
    block = Block(reason="code", url="https://x.example/", host="<x>")
    for text in (stuck_result_text(block), blocked_result_text(block), refused_once_text("<x>", 403)):
        assert "<x>" not in text and "&lt;x&gt;" in text


def test_the_help_refusals_are_fixed_texts_that_give_the_cap():
    assert BAD_HELP_ARGS_TEXT == f"Refused: ask_for_help needs a reason of 1 to {STUCK_REASON_MAX_CHARS} characters."
    assert ASK_ONLY_IN_CHAT_TEXT == "Refused: you can ask for help only in your own chat with the user."
    assert ASKED_FOR_HELP_TEXT == "Asked: the user has your request and will help. Stop here."
    assert STUCK_NOT_PERFORMED_TEXT == "Not performed: you are stuck and the user has been asked for help."
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_tool_runner.py tests/test_instructions.py -q`
Expected: FAIL with 2 collection errors, both `ImportError: cannot import name 'ASK_ONLY_IN_CHAT_TEXT' from 'roost.talk.instructions'`.

- [ ] **Step 4: Implement — the model-facing texts and the prompt section (`roost/talk/instructions.py`)**

Find:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from roost.bots.models import Bot
from roost.rooms.models import RoomContext
```

Replace with:

```python
from datetime import datetime
from types import MappingProxyType
from typing import Mapping
from zoneinfo import ZoneInfo

from roost.bots.models import Bot
from roost.constants import STUCK_REASON_MAX_CHARS
from roost.desk.stuck import Block
from roost.rooms.models import RoomContext
```

`instructions.py` does not import `roost.stuck`: the user-facing `REASON_WORDS` speak in the bot's voice, and the model gets its own words below.

Find (the computer section, kept word for word):

```python
_COMPUTER_DESCRIPTION = (
    "You have your own computer with your own browser window. You can open and read web pages. "
    "You cannot type, click, submit, buy, send or run commands yet."
)
```

Replace with:

```python
_COMPUTER_DESCRIPTION = (
    "You have your own computer with your own browser window. You can open and read web pages. "
    "You cannot type, click, submit, buy, send or run commands yet."
)

# Stuck flow (Piece A): how a bot gets past a check only the user can clear, and never ends empty.
_STUCK_TEXT = (
    "When a site stops you with a check that you are human, a sign-in page or a code check, your tool result "
    "says so, and in your own chat the user is asked to clear it. If something else only the user can do stops you, such as a "
    "payment or identity check, call ask_for_help with the reason and stop. The user will Take control of your "
    "computer, clear it, then give it back, and you carry on. Set suggest_main_browser only when your own "
    "browser window can't do it. Never finish with an empty answer: if you could not do the task, say what "
    "stopped you."
)
```

Find:

```python
CONTROL_HANDED_BACK_TEXT = (
    "Not performed: the user just gave your computer back and the page may have changed. Read the page again "
    "with read_page before you go on."
)
```

Replace with:

```python
CONTROL_HANDED_BACK_TEXT = (
    "Not performed: the user just gave your computer back and the page may have changed. Read the page again "
    "with read_page before you go on."
)

# Stuck flow (Piece A): what ask_for_help, a blocked page or a stuck run returns to the model.
ASKED_FOR_HELP_TEXT = "Asked: the user has your request and will help. Stop here."
ASK_ONLY_IN_CHAT_TEXT = "Refused: you can ask for help only in your own chat with the user."
BAD_HELP_ARGS_TEXT = f"Refused: ask_for_help needs a reason of 1 to {STUCK_REASON_MAX_CHARS} characters."
STUCK_NOT_PERFORMED_TEXT = "Not performed: you are stuck and the user has been asked for help."

# What stopped the bot, in words for the model (one per BlockReason). Kept apart from
# roost.stuck.texts.REASON_WORDS, which speak in the bot's own voice to the user
# ("a check that I'm human") and would read oddly in a tool result.
_MODEL_REASON_WORDS: Mapping[str, str] = MappingProxyType({
    "challenge": "a check that you are human",
    "login": "a sign-in page",
    "code": "a code check",
    "refused": "a refusal",
    "asked": "a request for the user's help",
})
```

Find (the end of `_interrupted_section`):

```python
    return (f"Your previous run stopped while this call was running: {calls}. "
            "Its outcome is unknown. Check whether it already happened before you repeat it.")
```

Replace with:

```python
    return (f"Your previous run stopped while this call was running: {calls}. "
            "Its outcome is unknown. Check whether it already happened before you repeat it.")


def _block_words(block: Block) -> tuple[str, str]:
    """The block's host, escaped because it comes from a page's address, and the model's words for what stopped the bot."""
    return _escape_tags(block.host), _MODEL_REASON_WORDS[block.reason]


def stuck_result_text(block: Block) -> str:
    """What the model sees when its page stayed blocked in your own chat: a Stuck card opens."""
    host, words = _block_words(block)
    return f"Stuck: {host} shows {words}. The user has been asked to clear it."


def blocked_result_text(block: Block) -> str:
    """R5: the same block in any other run (a handoff, a room, a routine). No card, and never an empty answer."""
    host, words = _block_words(block)
    return (f"Blocked: {host} shows {words}. You can't get past it in this task. "
            "Tell whoever asked that the site stopped you.")


def refused_once_text(host: str, status: int) -> str:
    """Design §1: a site's first 403 or 429 in a run is only a result, and the bot may try another way."""
    return (f"Not shown: {_escape_tags(host)} answered {status} and would not show the page. "
            "Try another way, or call ask_for_help if only the user can get past it.")
```

In `build_instructions`, find:

```python
        _COMPUTER_DESCRIPTION,
        _time_section(moment),
```

Replace with:

```python
        _COMPUTER_DESCRIPTION,
        _STUCK_TEXT,
        _time_section(moment),
```

- [ ] **Step 5: Implement — the tool (`roost/talk/tool_catalog.py`)**

Find:

```python
from roost.constants import AVATAR_SHAPES
```

Replace with:

```python
from roost.constants import AVATAR_SHAPES, STUCK_REASON_MAX_CHARS
```

Find:

```python
GET_TIME_SPEC = ToolSpec(
    name="get_time",
    description="Get the current date and time, in Europe/Madrid.",
    input_schema={"type": "object", "properties": {}},
)
```

Replace with:

```python
GET_TIME_SPEC = ToolSpec(
    name="get_time",
    description="Get the current date and time, in Europe/Madrid.",
    input_schema={"type": "object", "properties": {}},
)

# Stuck flow (Piece A). The description must not contain " role" or "control"
# (tests/test_every_bot_tools.py, tests/test_computer_control_runs.py).
ASK_FOR_HELP_SPEC = ToolSpec(
    name="ask_for_help",
    description=(
        "Ask the user to do a step only they can do on the page you have open, such as a payment or identity "
        "check, then stop. They clear it in your own browser window and you carry on afterwards. Works only in "
        "your own chat with the user."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": f"What you need the user to do, in plain words (up to {STUCK_REASON_MAX_CHARS} "
                               "characters).",
            },
            "suggest_main_browser": {
                "type": "boolean",
                "description": "True only when your own browser window can't do this step and the user should "
                               "do it in their main Brave.",
            },
        },
        "required": ["reason"],
    },
)
```

Find:

```python
# Every tool a model can ever be offered, with its gate kind. ask_bot and
# suggest_bot change none of the user's records (a handoff queues work, a
# card creates nothing), so they are "read" for the gate.
CATALOG: Mapping[str, ToolDef] = _catalog((
    ToolDef(OPEN_PAGE_SPEC, "read"),
    ToolDef(READ_PAGE_SPEC, "read"),
    ToolDef(GET_TIME_SPEC, "read"),
```

Replace with:

```python
# Every tool a model can ever be offered, with its gate kind. ask_bot,
# suggest_bot and ask_for_help change none of the user's records (a handoff
# queues work, a card creates nothing, a Stuck card only asks the user), so
# they are "read" for the gate.
CATALOG: Mapping[str, ToolDef] = _catalog((
    ToolDef(OPEN_PAGE_SPEC, "read"),
    ToolDef(READ_PAGE_SPEC, "read"),
    ToolDef(GET_TIME_SPEC, "read"),
    ToolDef(ASK_FOR_HELP_SPEC, "read"),
```

`roost/talk/tools.py` needs no change. `ask_for_help` is in none of `TEAM_TOOLS`, `LEAD_TOOLS`, `CREATOR_TOOLS` or `PARALLEL_TOOLS`, so every bot gets it in every run. Outside your own chat the runner refuses it.

- [ ] **Step 6: Implement — rung 1 and the help arguments (`roost/talk/stuck_check.py`, new)**

```python
"""Rung 1 of the stuck ladder and ask_for_help's arguments (stuck flow, Task 4).

Split out of ``roost/talk/tool_runner.py`` so the runner stays a dispatcher.
Nothing here clicks, types or solves anything (design §1). It reads the page
the bot's own browser already loaded. For a ``challenge`` it waits, then
repeats the same call once (R4): ``open_page(url)`` again, or ``read_page()``
again, never a reload. The wait is passed in by the caller, so tests patch
``roost.talk.tool_runner.STUCK_CHALLENGE_WAIT_SECONDS``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field

from roost.constants import STUCK_REASON_MAX_CHARS
from roost.desk import PageText
from roost.desk.stuck import Block, detect_block
from roost.records.tool_text import ToolText

Fetch = Callable[[], Awaitable[PageText]]
Announce = Callable[[str], Awaitable[None]]
HandsTaken = Callable[[], bool]


class AskForHelpArgs(BaseModel):
    """ask_for_help's arguments. The reason is kept as plain text (the card shows it as text, never HTML)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    reason: ToolText = Field(min_length=1, max_length=STUCK_REASON_MAX_CHARS)
    suggest_main_browser: bool = False


@dataclass(frozen=True)
class Checked:
    """The page a browser call ends with, and the block it shows (``None``: the page is fine)."""

    page: PageText
    block: Block | None


async def check_page(page: PageText, fetch: Fetch, *, wait_seconds: float, announce: Announce,
                     hands_taken: HandsTaken) -> Checked:
    """Rung 1. A challenge gets one wait and one repeat of the same call. A sign-in
    page, a code check or a refusal gets neither. If the user took control during
    the wait, the repeat is skipped (Review Focus 2): the bot never navigates under
    the user's hands, and the block stands."""
    block = detect_block(page)
    if block is None or block.reason != "challenge":
        return Checked(page, block)
    await announce(f"waiting for {block.host} to let me in")
    await asyncio.sleep(wait_seconds)
    if hands_taken():
        return Checked(page, block)
    again = await fetch()
    return Checked(again, detect_block(again))
```

- [ ] **Step 7: Implement — blocks and ask_for_help in the runner (`roost/talk/tool_runner.py`)**

Find (the imports):

```python
import html
from dataclasses import replace
from datetime import datetime
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.constants import INFLIGHT_DESCRIPTION_CHARS
from roost.desk import Desk, DeskUnavailable, PageText
from roost.desk.control import ControlLock
from roost.desk.url_policy import UrlBlocked
from roost.events.hub import EventHub
from roost.llm.types import ToolCallRequested
from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.gate import REFUSAL_TEXT, Gate, GateContext
from roost.talk.instructions import CONTROL_HANDED_BACK_TEXT, CONTROL_HELD_TEXT, MADRID_TZ
from roost.talk.link_scope import LinkScope
from roost.talk.outcome import ToolOutcome
from roost.talk.team_tools import TeamTools
```

Replace with:

```python
import html
from dataclasses import replace
from datetime import datetime
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from pydantic import ValidationError

from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
# STUCK_CHALLENGE_WAIT_SECONDS is imported by name and read at call time, so tests patch this module's copy.
from roost.constants import INFLIGHT_DESCRIPTION_CHARS, STUCK_CHALLENGE_WAIT_SECONDS
from roost.desk import Desk, DeskUnavailable, PageText
from roost.desk.control import ControlLock
from roost.desk.stuck import Block, host_of_url
from roost.desk.url_policy import UrlBlocked, check_url
from roost.events.hub import EventHub
from roost.llm.types import ToolCallRequested
from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.gate import REFUSAL_TEXT, Gate, GateContext
from roost.talk.instructions import (
    ASK_ONLY_IN_CHAT_TEXT, ASKED_FOR_HELP_TEXT, BAD_HELP_ARGS_TEXT, CONTROL_HANDED_BACK_TEXT, CONTROL_HELD_TEXT,
    MADRID_TZ, STUCK_NOT_PERFORMED_TEXT, blocked_result_text, refused_once_text, stuck_result_text,
)
from roost.talk.link_scope import LinkScope
from roost.talk.outcome import ToolOutcome
from roost.talk.stuck_check import AskForHelpArgs, Fetch, check_page
from roost.talk.team_tools import TeamTools
```

Find (the end of the constructor's signature):

```python
        control: ControlLock | None = None,
    ) -> None:
```

Replace with:

```python
        control: ControlLock | None = None, cards: bool = False,
    ) -> None:
```

Find (the end of the constructor):

```python
        self._control = control
        self.link_scope = link_scope
        self.tainted = tainted
        self.last_host: str | None = None
```

Replace with:

```python
        self._control = control
        self._cards = cards                                   # this run may open Stuck cards (your own chat, R5)
        self._refused_hosts: frozenset[str] = frozenset()      # hosts that refused once in this run
        self.link_scope = link_scope
        self.tainted = tainted
        self.last_host: str | None = None
        self.last_url: str | None = None
        self.block: Block | None = None                       # a page that stayed blocked, or ask_for_help
```

Find:

```python
    async def run(self, call: ToolCallRequested) -> str:
        verdict = await self._gate.decide(self._user_id, self._bot_id, call.name, call.arguments, self._context())
```

Replace with:

```python
    async def run(self, call: ToolCallRequested) -> str:
        if self.block is not None:
            return STUCK_NOT_PERFORMED_TEXT   # R1: the turn stops after this step, and nothing more runs in it
        verdict = await self._gate.decide(self._user_id, self._bot_id, call.name, call.arguments, self._context())
```

Find (in `_dispatch`):

```python
            return (await self._team.create_bot(call.arguments, tainted=self.tainted, announce=self._announce)).text
        if self._domain is not None and self._domain.handles(call.name):
```

Replace with:

```python
            return (await self._team.create_bot(call.arguments, tainted=self.tainted, announce=self._announce)).text
        if call.name == "ask_for_help":
            return await self._ask_for_help(call.arguments)   # needs no browser: never behind _hands_refusal
        if self._domain is not None and self._domain.handles(call.name):
```

Find (the page methods, through `_absorb_page`):

```python
    async def _open_page(self, arguments: dict[str, Any]) -> str:
        url = str(arguments.get("url", ""))
        await self._announce(f"opening {host_of(url)}")
        try:
            page = await self._desk.open_page(url)
        except UrlBlocked:
            return _BLOCKED_TEXT
        except DeskUnavailable:
            return _DESK_UNAVAILABLE_TEXT
        return self._absorb_page(page)

    async def _read_page(self) -> str:
        await self._announce(f"reading {self.last_host}" if self.last_host else "reading the page")
        try:
            page = await self._desk.read_page()
        except DeskUnavailable:
            return _DESK_UNAVAILABLE_TEXT
        return self._absorb_page(page)

    def _absorb_page(self, page: PageText) -> str:
        self.last_host = host_of(page.url)
        self.tainted = True
        self.link_scope = self.link_scope.with_page(page.url, page.text)
        return wrap_page(page)
```

Replace with:

```python
    async def _open_page(self, arguments: dict[str, Any]) -> str:
        url = str(arguments.get("url", ""))
        await self._announce(f"opening {host_of(url)}")
        return await self._load(lambda: self._desk.open_page(url))

    async def _read_page(self) -> str:
        await self._announce(f"reading {self.last_host}" if self.last_host else "reading the page")
        return await self._load(self._desk.read_page)

    async def _load(self, fetch: Fetch) -> str:
        """Loads a page and runs rung 1 on it. The repeat is the same call (R4), so it
        keeps the URL check, the status capture and the reconnect."""
        try:
            page = await fetch()
            checked = await check_page(page, fetch, wait_seconds=STUCK_CHALLENGE_WAIT_SECONDS,
                                       announce=self._announce, hands_taken=self._hands_taken)
        except UrlBlocked:
            return _BLOCKED_TEXT
        except DeskUnavailable:
            return _DESK_UNAVAILABLE_TEXT
        if checked.block is None:
            return self._absorb_page(checked.page)
        return self._answer_block(checked.page, checked.block)

    def _hands_taken(self) -> bool:
        """The user holds this bot's computer right now (Take control)."""
        return self._control is not None and self._control.held(self._bot_id) is not None

    def _answer_block(self, page: PageText, block: Block) -> str:
        """A page still blocked after rung 1. It counts as read (taint, host, URL), but its
        text never reaches the model, so only its address joins the link scope, never the
        links in its text. The first refusal on a host is only a result (design §1).
        Outside your own chat a block is a loud result and never a card (R5)."""
        self._note_page(replace(page, text=""))
        if block.reason == "refused" and block.host not in self._refused_hosts:
            self._refused_hosts = self._refused_hosts | {block.host}
            return refused_once_text(block.host, page.status or 0)   # a refusal always carries 403 or 429
        if not self._cards:
            return blocked_result_text(block)
        self.block = block
        return stuck_result_text(block)

    def _note_page(self, page: PageText) -> None:
        self.last_host = host_of(page.url)
        self.last_url = page.url
        self.tainted = True
        self.link_scope = self.link_scope.with_page(page.url, page.text)

    def _absorb_page(self, page: PageText) -> str:
        self._note_page(page)
        return wrap_page(page)

    async def _ask_for_help(self, arguments: dict[str, Any]) -> str:
        """A block the detector can't see, such as a payment or identity check. The bot
        asks, and the turn stops after this step. Only in your own chat (R5)."""
        if not self._cards:
            return ASK_ONLY_IN_CHAT_TEXT
        try:
            args = AskForHelpArgs.model_validate(arguments)
        except ValidationError:
            return BAD_HELP_ARGS_TEXT
        url = self._card_address()
        await self._announce("asking you for help")
        self.block = Block(reason="asked", url=url, host=host_of_url(url), note=args.reason,
                           suggest_main_browser=args.suggest_main_browser)
        return ASKED_FOR_HELP_TEXT

    def _card_address(self) -> str:
        """The open page's address for an asked card, as ``check_url`` returns it, or ``""``
        when there is no web page to point at: nothing opened yet, or a fresh tab's
        ``about:blank``. The card then never names a page it can't open (Task 7 answers 400)."""
        if not self.last_url:
            return ""
        try:
            return check_url(self.last_url)
        except UrlBlocked:
            return ""
```

`_hands_refusal`, `_absorb_answer`, `_announce` and `_set_inflight` stay as they are. `tool_runner.py` ends at about 300 lines. Each function stays under 25 lines.

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_tool_runner.py tests/test_instructions.py -q`
Expected: PASS.
- `test_stuck_tool_runner.py` collects 28 tests: 23 functions, with the two parametrized ones expanding to 2 and 5 cases.
- `test_instructions.py` gains 8 tests.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_gate.py tests/test_every_bot_tools.py tests/test_computer_control_runs.py tests/test_control_lock.py tests/test_tool_runner_taint.py tests/test_turn.py tests/test_claude_sdk_options.py tests/test_fake_desk.py -q`
Expected: PASS, with no edits to these files. `test_every_allowed_tool_decides_do[ask_for_help]` is a new passing case.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_tool_runner.py tests/test_instructions.py --cov=roost.talk.stuck_check --cov=roost.talk.tool_runner --cov=roost.talk.instructions --cov-report=term-missing -q`
Expected:
- `roost/talk/stuck_check.py` at 100%.
- No new line of `tool_runner.py` or `instructions.py` in the Missing column. The only misses in `tool_runner.py` are the team branches, which other test files cover.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git -C /Users/blckit/Desktop/Code_Projects/roost add roost/talk/stuck_check.py roost/talk/tool_runner.py roost/talk/tool_catalog.py roost/talk/instructions.py tests/test_stuck_tool_runner.py tests/test_instructions.py
git -C /Users/blckit/Desktop/Code_Projects/roost commit -m "feat: rung 1 wait-and-repeat, Stuck blocks and ask_for_help in the tool runner"
```

---

### Task 5: The run stops and leaves a Stuck card

Design D-A5, R1, R5, R6, R7 and R9:
- A chat run whose tool call set `ToolRunner.block` stops right after that step (`_run_steps`), and `TurnResult` carries the block back to `TurnRunner`.
- On the success path of `_execute`, before the status settles, `TurnRunner._on_block` turns the block into a Stuck card: a `stuck_cards` row, a `kind="stuck"` bot message whose body is the card as JSON, and a `stuck_card` frame. The bot then settles to **Stuck**.
- **Rung 4:** a continue run (a `card_answer` item) blocked again on its card's host opens no new card. The card becomes `blocked`, the bot says `blocked_line(...)`, and the status settles to Resting. A continue run blocked on another host opens a new card that keeps the first request.
- **One open card per bot:** a run blocked while an older card is still open opens no second card. The open card is posted in that run's own chat instead, so no blocked chat run ends with nothing said.
- Cards open only in runs made of your own messages and continue items, outside rooms (`_may_open_cards`). Every other run gets the block back as a loud tool result (Task 4), so its model still answers.
- A blocked turn that said nothing stores no empty bubble. A `card_answer` line reaches the model as your turn.
- `_settle_status` shows Stuck while a card is open. The public `settle` never leaves a stale status: with no drain task running it settles at once; while one runs, it registers a done-callback on that task and settles once the task ends. So Give up pressed while a run is ending (after the run settled itself to Stuck) never leaves the bot Stuck with no open card. Back on duty settles, and the gateway's boot calls `restore_stuck_on_boot` after `reset_on_boot`.

**Files:**
- Create: `tests/test_stuck_runs.py`
- Modify:
  - `roost/talk/turn.py` (`TurnResult.block`, `_MODEL_KINDS` gains `"card_answer"`, `_may_open_cards`, the early return in `_run_steps`, `cards=` passed to `ToolRunner`, `_finish_reply` with no empty bubble for a blocked turn)
  - `roost/talk/runner.py` (`stuck=` keyword, `_on_block` / `_answered_card` / `_block_card`, `_settle_status` picks Stuck, public `settle` with its done-callback settle (`_settle_after` / `_forget_settle` / `_settle_logged`, `_settling`), `restore_stuck_on_boot`, back on duty settles)
  - `tests/team_helpers.py` (`wait_idle` also waits for the settles that run after a drain task ends)
  - `roost/work/models.py` (`ORIGIN_CARD`)
  - `roost/talk/store.py` (`MessageKind` gains `"stuck"` and `"card_answer"`)
  - `roost/talk/chats.py` (the Stuck card's preview)
  - `roost/gateway/app.py` (`app.state.stuck`, `TurnRunner(..., stuck=...)`, the boot restore)
- Test: `tests/test_stuck_runs.py`

**Interfaces:**
- Consumes:
  - Task 1: `Block(reason, url, host, note="", suggest_main_browser=False)` from `roost.desk.stuck`, and the defaulted `PageText` fields `status`, `password_field` and `captcha_frame`.
  - Task 2: `FakeDesk.serve(url: str, *pages: PageText) -> None` (each `open_page`/`read_page` of a served URL returns its next page; the last one repeats).
  - Task 3:
    - `StuckStore(config)` with `open`, `get`, `list_open`, `open_for_bot`, `close(..., answer_item_id=)`, `mark_blocked`, `card_for_answer` and `open_bots`.
    - `CardDraft`, `CardState`, `StuckCard` (and its `host` property) and `stuck_card_out`.
    - `stuck_line`, `blocked_line(host, request)`, `continue_text(card)` and `stuck_message_body(card)`.
    - `publish_card(events, user_id, card)` and `post_bot_line(talk, events, user_id, card, body, *, kind)`.
  - Task 4:
    - `ToolRunner(..., cards: bool = False)` and `ToolRunner.block`.
    - The `ask_for_help` tool and `blocked_result_text(block)`.
    - `roost.talk.tool_runner.STUCK_CHALLENGE_WAIT_SECONDS`, which tests patch.
    - **Assumed from the contract:** a run built with `cards=False` never sets `ToolRunner.block`; it returns `blocked_result_text` instead. Otherwise `_run_steps` would stop a handoff run before its model answers (R5). `test_a_handoff_run_that_hits_a_block_opens_no_card_and_reports_it_loudly` checks this.
- Produces:
  - `TurnResult.block: Block | None = None` and `_may_open_cards(inputs: RunInputs) -> bool` in `roost/talk/turn.py`. `_MODEL_KINDS` contains `"card_answer"`.
  - `TurnRunner(..., *, queue=None, runs=None, rooms=None, domain=None, control=None, stuck: StuckStore | None = None)`.
  - `async TurnRunner.settle(user_id, bot_id) -> None`: never leaves a stale status. With no drain task running it awaits `_settle_status` at once. While the bot's drain task runs, it adds a done-callback to that task and returns; once the task ends, `settle` runs again in a task of its own (kept in `TurnRunner._settling`, errors logged). Task 7 calls it after `/clear` and `/give-up`.
  - `tests/team_helpers.py`: `wait_idle(runner)` also waits until `runner._settling` is empty, so a test (and Task 7's `_signed_in`) sees the settle that runs after a drain task ends.
  - `async TurnRunner.restore_stuck_on_boot() -> None`.
  - `ORIGIN_CARD = "you, after a Stuck card"`. Task 7 queues continue items with it.
  - `MessageKind` gains `"stuck"` and `"card_answer"`.
  - The `"stuck"` chat preview: `("Stuck on {host}", "card")`, or `("Needs your help", "card")` when there is no host.
  - `app.state.stuck` (one `StuckStore`). Task 7 builds `StuckService` on it.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_stuck_runs.py`:

```python
"""The Stuck flow's run side (Piece A, Task 5): a blocked chat run stops and
leaves a Stuck card, the bot shows Stuck while a card is open, and a continue
run blocked again on the same host marks its card blocked (rung 4)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import get_args
from uuid import uuid4

import pytest

import roost.talk.runner as runner_module
import roost.talk.tool_runner as tool_runner_module
from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import CHAT_PREVIEW_CHARS
from roost.db.connection import init_db
from roost.desk import PageText
from roost.desk.stuck import Block
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import TextDelta, ToolCallRequested, TurnDone
from roost.rooms.models import RoomContext
from roost.rooms.store import RoomStore
from roost.stuck.models import CardDraft, CardState, StuckCard, stuck_card_out
from roost.stuck.store import StuckStore
from roost.stuck.texts import blocked_line, continue_text, stuck_line, stuck_message_body
from roost.talk.chats import chat_preview, chat_rows
from roost.talk.instructions import blocked_result_text
from roost.talk.notices import preview
from roost.talk.runner import TurnRunner
from roost.talk.store import Message, MessageKind, TalkStore
from roost.talk.turn import RunInputs, _may_open_cards
from roost.work.models import ORIGIN_CARD, ORIGIN_YOU, RunOutcome, WorkDraft, WorkItem, WorkKind, WorkState
from roost.work.runs import RunLog
from team_helpers import (
    GatedModel, Rig, ask, frames_so_far, make_bot, make_rig, say, send, team_model, until, wait_idle,
)

SHOP = "https://shop.example/"
NEWS = "https://news.example/"
BANK = "https://bank.example/"

CHALLENGE = PageText(url=SHOP, title="Just a moment...", text="Checking your browser before you reach the shop.",
                     truncated=False, status=403)
CLEAR = PageText(url=SHOP, title="Kettles", text="Blue kettle, 30 EUR. Red kettle, 35 EUR.", truncated=False,
                 status=200)
LOGIN_WALL = PageText(url=BANK, title="Sign in", text="Sign in to your bank.", truncated=False, status=200,
                      password_field=True)
ROOM = RoomContext(room_id="r1", name="Saturday", members=(), coordinator_id=None)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture(autouse=True)
def _no_challenge_wait(monkeypatch):
    """Rung 1 waits STUCK_CHALLENGE_WAIT_SECONDS (8 s) before it repeats the call; tests don't."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)


def _call(call_id: str, name: str, **arguments) -> ToolCallRequested:
    return ToolCallRequested(id=call_id, name=name, arguments=arguments)


def _open_step(url: str, call_id: str = "p"):
    return [_call(call_id, "open_page", url=url), TurnDone("tool_use")]


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


async def _status(rig: Rig, user_id: str, bot_id: str) -> BotStatus:
    return (await rig.bots.get(user_id, bot_id)).status


def _draft(bot_id: str, thread_id: str) -> CardDraft:
    return CardDraft(bot_id=bot_id, thread_id=thread_id, work_item_id=None,
                     block=Block(reason="login", url=BANK, host="bank.example"), request="pay the bill",
                     tainted=False)


async def _run_in_new_chat(rig: Rig, user_id: str, bot_id: str, text: str):
    """Send ``text`` in a new chat with ``bot_id`` and wait until the run is over; returns the thread."""
    thread = await rig.talk.create_thread(user_id, bot_id)
    await send(rig, user_id, bot_id, thread.id, text)
    await wait_idle(rig.runner, timeout=8)
    return thread


async def _clear(rig: Rig, stuck: StuckStore, user_id: str, card: StuckCard) -> tuple[StuckCard, WorkItem]:
    """What Task 7's ``/clear`` does (without the control hold and the frame):
    close the card, post the continue line, queue the continue item."""
    item_id = str(uuid4())
    cleared = await stuck.close(user_id, card.id, CardState.CLEARED, answer_item_id=item_id)
    text = continue_text(cleared)
    line = await rig.talk.add_message(user_id, cleared.thread_id, "user", text, cleared.tainted, kind="card_answer")
    item = await rig.runner.submit(user_id, WorkDraft(
        bot_id=cleared.bot_id, thread_id=cleared.thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD,
        body=text, tainted=cleared.tainted, message_id=line.id, link_scope=(cleared.url,),
    ), item_id=item_id)
    return cleared, item


def _item(kind: WorkKind, n: int = 0) -> WorkItem:
    return WorkItem(
        id=f"i{n}", user_id="u", bot_id="b", thread_id="t", kind=kind, origin=ORIGIN_YOU, body="hi",
        tainted=False, depth=0, parent_item_id=None, message_id=None, state=WorkState.CLAIMED, run_id="r",
        inflight=None, result=None, result_tainted=False, created_at="2026-10-14T10:00:00+00:00",
        updated_at="2026-10-14T10:00:00+00:00",
    )


def _message(body: str, *, role: str = "bot", kind: str = "text") -> Message:
    return Message(id="m", user_id="u", thread_id="t", role=role, body=body, tainted=False, seq=1,
                   created_at="2026-10-14T10:00:00+00:00", kind=kind)


class _HeldFinish(RunLog):
    """A run log whose ``finish`` waits for ``release``. ``_run_batch`` calls it
    after the turn and after the run's own status settle, so the run is held
    while it ends: the status is already settled, and the drain task is alive."""

    def __init__(self, config) -> None:
        super().__init__(config)
        self.reached = asyncio.Event()
        self.release = asyncio.Event()

    async def finish(self, user_id: str, run_id: str, outcome: RunOutcome) -> None:
        self.reached.set()
        await self.release.wait()
        await super().finish(user_id, run_id, outcome)


async def _ending_run(cfg, user_id: str, bot_id: str) -> tuple[Rig, _HeldFinish]:
    """Send "hello" to ``bot_id`` and hold that run at ``finish``: it has
    answered and settled its status, and its drain task is still alive."""
    runs = _HeldFinish(cfg)
    rig = make_rig(cfg, team_model({"Helper": [say("Done.")]}))
    rig = replace(rig, runner=TurnRunner(cfg, rig.bots, rig.talk, rig.events, rig.desks, rig.model,
                                         ActivityBoard(), runs=runs))
    thread = await rig.talk.create_thread(user_id, bot_id)
    await send(rig, user_id, bot_id, thread.id, "hello")
    await asyncio.wait_for(runs.reached.wait(), timeout=3)
    return rig, runs


async def test_a_challenge_that_stays_ends_the_run_with_a_stuck_card(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [
        [_call("n", "open_page", url=NEWS), _call("s", "open_page", url=SHOP), TurnDone("tool_use")],
        say("never asked"),
    ]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await rig.talk.create_thread(user_id, bot.id)
    sub = rig.events.subscribe(user_id)
    request = f"check {NEWS} then {SHOP}"
    item = await send(rig, user_id, bot.id, thread.id, request)
    await wait_idle(rig.runner, timeout=8)

    assert len(rig.model.requests) == 1                     # the turn stopped calling the model
    card = await StuckStore(cfg).open_for_bot(user_id, bot.id)
    assert (card.reason, card.host, card.url, card.thread_id, card.state) == (
        "challenge", "shop.example", SHOP, thread.id, CardState.OPEN)
    assert (card.work_item_id, card.request, card.tainted) == (item.id, request, True)   # it read news.example
    [line] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "stuck"]
    assert (line.role, line.author_bot_id, line.tainted, line.body) == ("bot", bot.id, True, stuck_message_body(card))
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK
    frames = await frames_so_far(sub)
    assert [f["card"] for f in frames if f["type"] == "stuck_card"] == [stuck_card_out(card).model_dump(mode="json")]
    assert [f["status"] for f in frames if f["type"] == "bot_status"][-1] == "stuck"


async def test_a_challenge_that_clears_after_the_wait_opens_no_card_and_the_run_goes_on(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), say("The blue kettle is 30 EUR.")]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE, CLEAR)
    thread = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")

    assert len(rig.model.requests) == 2
    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.kind, m.body) for m in messages][1:] == [("bot", "text", "The blue kettle is 30 EUR.")]
    assert await StuckStore(cfg).open_for_bot(user_id, bot.id) is None
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING


async def test_ask_for_help_opens_an_asked_card(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    reason = "The council site wants a payment approval on your phone"
    rig = make_rig(cfg, team_model({"Helper": [
        [_call("h", "ask_for_help", reason=reason, suggest_main_browser=True), TurnDone("tool_use")],
        say("never asked"),
    ]}))
    thread = await _run_in_new_chat(rig, user_id, bot.id, "renew my parking permit")

    assert len(rig.model.requests) == 1
    card = await StuckStore(cfg).open_for_bot(user_id, bot.id)
    assert (card.reason, card.note, card.suggest_main_browser, card.url, card.request) == (
        "asked", reason, True, "", "renew my parking permit")
    [line] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "stuck"]
    assert json.loads(line.body)["line"] == stuck_line(card)
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_blocked_turn_that_said_nothing_leaves_no_empty_bubble(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP)]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await rig.talk.create_thread(user_id, bot.id)
    sub = rig.events.subscribe(user_id)
    await send(rig, user_id, bot.id, thread.id, f"price the kettle at {SHOP}")
    await wait_idle(rig.runner, timeout=8)

    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.kind) for m in messages] == [("user", "text"), ("bot", "stuck")]
    frames = await frames_so_far(sub)
    placeholder_id = next(f["message"]["id"] for f in frames if f["type"] == "message" and f["message"]["body"] == "")
    assert any(f["type"] == "message_done" and f["message_id"] == placeholder_id for f in frames)
    assert placeholder_id not in {m.id for m in messages}


async def test_a_blocked_turn_keeps_what_it_said_before_the_block(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [[TextDelta("Let me look at the shop."), *_open_step(SHOP)]]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")

    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.kind, m.body) for m in messages][1:2] == [("bot", "text", "Let me look at the shop.")]
    assert [m.kind for m in messages] == ["text", "text", "stuck"]


async def test_a_handoff_run_that_hits_a_block_opens_no_card_and_reports_it_loudly(cfg, user_id):
    chief = await make_bot(cfg, user_id, "Chief", "leads the team")
    scout = await make_bot(cfg, user_id, "Scout", "finds prices")
    rig = make_rig(cfg, team_model({
        "Chief": [[ask("c1", "Scout", f"price the kettle at {SHOP}"), TurnDone("tool_use")],
                  say("Scout couldn't get into the shop.")],
        "Scout": [_open_step(SHOP), say("The shop stopped me with a check that I'm human.")],
    }))
    rig.desks.for_bot(scout.id).serve(SHOP, CHALLENGE)
    await _run_in_new_chat(rig, user_id, chief.id, f"price the kettle at {SHOP}")

    scout_requests = [r for r in rig.model.requests if r.agent == "Scout"]
    assert len(scout_requests) == 2                         # R5: the run went on and its model answered
    assert _tool_texts(scout_requests[-1]) == [
        blocked_result_text(Block(reason="challenge", url=SHOP, host="shop.example"))]
    assert await StuckStore(cfg).list_open(user_id) == ()
    assert await _status(rig, user_id, scout.id) is BotStatus.RESTING


@pytest.mark.parametrize(("kinds", "room", "expected"), [
    ((), None, False),                                      # a run outside the queue
    ((WorkKind.MESSAGE,), None, True),
    ((WorkKind.CARD_ANSWER,), None, True),
    ((WorkKind.MESSAGE, WorkKind.CARD_ANSWER), None, True),
    ((WorkKind.HANDOFF,), None, False),
    ((WorkKind.MESSAGE, WorkKind.HANDOFF), None, False),
    ((WorkKind.ROOM_POST,), None, False),
    ((WorkKind.ROUTINE,), None, False),
    ((WorkKind.TRIGGER,), None, False),
    ((WorkKind.MESSAGE,), ROOM, False),                     # your own message, but in a room
])
def test_cards_open_only_in_runs_of_your_own_messages_and_continue_items(kinds, room, expected):
    inputs = RunInputs(items=tuple(_item(kind, n) for n, kind in enumerate(kinds)), room=room)
    assert _may_open_cards(inputs) is expected


async def test_a_continue_run_blocked_again_on_the_same_host_marks_the_card_blocked(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), _open_step(SHOP, "p2")]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    stuck = StuckStore(cfg)
    request = f"price the kettle at {SHOP}"
    thread = await _run_in_new_chat(rig, user_id, bot.id, request)
    card = await stuck.open_for_bot(user_id, bot.id)
    sub = rig.events.subscribe(user_id)

    await _clear(rig, stuck, user_id, card)
    await wait_idle(rig.runner, timeout=8)

    assert (await stuck.get(user_id, card.id)).state is CardState.BLOCKED
    assert await stuck.open_for_bot(user_id, bot.id) is None            # rung 4: no new card on the same host
    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.author_bot_id, m.body) for m in messages if m.role == "bot" and m.kind == "text"] == [
        (bot.id, blocked_line("shop.example", request))]
    assert len([m for m in messages if m.kind == "stuck"]) == 1
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING
    assert [f["card"]["state"] for f in await frames_so_far(sub) if f["type"] == "stuck_card"] == ["blocked"]


async def test_a_continue_run_blocked_on_another_host_opens_a_new_card_with_the_first_request(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), _open_step(BANK, "p2")]}))
    desk = rig.desks.for_bot(bot.id)
    desk.serve(SHOP, CHALLENGE)
    desk.serve(BANK, LOGIN_WALL)
    stuck = StuckStore(cfg)
    request = f"price the kettle at {SHOP} and pay for it at {BANK}"
    thread = await _run_in_new_chat(rig, user_id, bot.id, request)
    first = await stuck.open_for_bot(user_id, bot.id)

    _, continue_item = await _clear(rig, stuck, user_id, first)
    await wait_idle(rig.runner, timeout=8)

    second = await stuck.open_for_bot(user_id, bot.id)
    assert second.id != first.id
    assert (second.reason, second.host, second.request, second.work_item_id) == (
        "login", "bank.example", request, continue_item.id)
    assert (await stuck.get(user_id, first.id)).state is CardState.CLEARED
    assert len([m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "stuck"]) == 2
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_continue_line_reaches_the_model_as_your_turn_and_the_run_finishes(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [
        _open_step(SHOP), [_call("r", "read_page"), TurnDone("tool_use")], say("The blue kettle is 30 EUR."),
    ]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE, CHALLENGE, CLEAR)   # open + rung-1 repeat, then cleared
    stuck = StuckStore(cfg)
    thread = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")
    card = await stuck.open_for_bot(user_id, bot.id)

    cleared, _ = await _clear(rig, stuck, user_id, card)
    await wait_idle(rig.runner, timeout=8)

    assert ("user", continue_text(cleared)) in [(t.role, t.text) for t in rig.model.requests[1].turns]
    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [(m.role, m.kind) for m in messages] == [
        ("user", "text"), ("bot", "stuck"), ("user", "card_answer"), ("bot", "text")]
    assert messages[-1].body == "The blue kettle is 30 EUR."
    assert (await stuck.get(user_id, card.id)).state is CardState.CLEARED
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING


async def test_a_new_message_while_a_card_is_open_is_answered_and_the_bot_stays_stuck(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), say("Yes, I'm waiting for you on the shop.")]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    thread = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")

    await send(rig, user_id, bot.id, thread.id, "are you still on it?")
    await wait_idle(rig.runner, timeout=8)

    messages = await rig.talk.list_messages(user_id, thread.id)
    assert [m.body for m in messages if m.role == "bot" and m.kind == "text"] == [
        "Yes, I'm waiting for you on the shop."]
    assert len(await StuckStore(cfg).list_open(user_id)) == 1
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_a_block_in_another_chat_while_a_card_is_open_shows_the_open_card_there(cfg, user_id):
    """One open card per bot: a second blocked run opens no second card, and its own chat is never left empty."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP), _open_step(BANK, "p2")]}))
    desk = rig.desks.for_bot(bot.id)
    desk.serve(SHOP, CHALLENGE)
    desk.serve(BANK, LOGIN_WALL)
    stuck = StuckStore(cfg)
    first_chat = await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")
    card = await stuck.open_for_bot(user_id, bot.id)

    second_chat = await _run_in_new_chat(rig, user_id, bot.id, f"pay the bill at {BANK}")

    assert [c.id for c in await stuck.list_open(user_id)] == [card.id]
    [shown] = [m for m in await rig.talk.list_messages(user_id, second_chat.id) if m.kind == "stuck"]
    assert (shown.role, shown.author_bot_id, shown.body) == ("bot", bot.id, stuck_message_body(card))
    assert len([m for m in await rig.talk.list_messages(user_id, first_chat.id) if m.kind == "stuck"]) == 1
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_settle_leaves_a_running_bot_on_it_and_settles_when_its_run_ends(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, GatedModel(["Done."]))
    stuck = StuckStore(cfg)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "hello")
    await until(lambda: len(rig.model.requests) == 1)            # the run is on, held inside the model
    card = await stuck.open(user_id, _draft(bot.id, thread.id))

    await rig.runner.settle(user_id, bot.id)
    assert await _status(rig, user_id, bot.id) is BotStatus.ON_IT    # not now: it settles when the run ends

    rig.model.release.set()
    await wait_idle(rig.runner)
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK   # the run's own settle, then settle's, saw the card

    await stuck.close(user_id, card.id, CardState.GIVEN_UP)
    await rig.runner.settle(user_id, bot.id)                     # no drain task: at once
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING


async def test_give_up_while_a_run_ends_settles_after_the_run(cfg, user_id):
    """R9: Give up pressed while a run is ending (the run already settled itself
    to Stuck, its drain task is still alive) must not leave the bot Stuck with no
    open card. The run is held at ``finish``, not in the model: a run held in the
    model would settle after the card closed, and show Resting even with the old
    no-op ``settle``."""
    bot = await make_bot(cfg, user_id, "Helper")
    stuck = StuckStore(cfg)
    card = await stuck.open(user_id, _draft(bot.id, (await TalkStore(cfg).create_thread(user_id, bot.id)).id))
    rig, runs = await _ending_run(cfg, user_id, bot.id)
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK   # the run's own settle saw the card

    await stuck.close(user_id, card.id, CardState.GIVEN_UP)          # what /give-up does to the card
    await rig.runner.settle(user_id, bot.id)
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK   # the drain task is alive: not yet

    runs.release.set()
    await wait_idle(rig.runner)
    assert await _status(rig, user_id, bot.id) is BotStatus.RESTING
    assert rig.runner._settling == frozenset()                       # the settle task ended and was let go


async def test_a_settle_that_fails_after_the_run_is_logged(cfg, user_id, caplog, monkeypatch):
    """Nobody awaits the settle that runs after a drain task ends, so its error is logged, never lost."""
    bot = await make_bot(cfg, user_id, "Helper")
    rig, runs = await _ending_run(cfg, user_id, bot.id)

    async def _db_gone(user_id: str, bot_id: str) -> None:
        raise RuntimeError("database is gone")

    monkeypatch.setattr(rig.runner, "_settle_status", _db_gone)
    await rig.runner.settle(user_id, bot.id)
    runs.release.set()
    await wait_idle(rig.runner)

    assert f"Settling the status after a run failed for bot {bot.id}" in caplog.text
    assert "RuntimeError: database is gone" in caplog.text
    assert rig.runner._settling == frozenset()


async def test_boot_puts_a_bot_with_an_open_card_back_to_stuck(cfg, user_id):
    """Review Focus #5: the old process died between opening the card and settling (the bot was On it)."""
    bot = await make_bot(cfg, user_id, "Helper")
    thread = await TalkStore(cfg).create_thread(user_id, bot.id)
    card = await StuckStore(cfg).open(user_id, _draft(bot.id, thread.id))
    await BotStore(cfg).set_status(user_id, bot.id, BotStatus.ON_IT)
    app = create_app()
    async with app.router.lifespan_context(app):
        assert (await app.state.bots.get(user_id, bot.id)).status is BotStatus.STUCK
        assert [c.id for c in await app.state.stuck.list_open(user_id)] == [card.id]


async def test_boot_leaves_an_off_duty_bot_with_an_open_card_off_duty(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await rig.bots.set_off_duty(user_id, bot.id, True)
    await StuckStore(cfg).open(user_id, _draft(bot.id, thread.id))

    await rig.runner.restore_stuck_on_boot()

    assert await _status(rig, user_id, bot.id) is BotStatus.OFF_DUTY


async def test_back_on_duty_with_an_open_card_shows_stuck(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await rig.runner.set_off_duty(user_id, bot.id, True)
    await StuckStore(cfg).open(user_id, _draft(bot.id, thread.id))

    back = await rig.runner.set_off_duty(user_id, bot.id, False)
    await wait_idle(rig.runner)

    assert back.status is BotStatus.STUCK
    assert await _status(rig, user_id, bot.id) is BotStatus.STUCK


async def test_the_card_keeps_the_request_up_to_its_cap(cfg, user_id, monkeypatch):
    monkeypatch.setattr(runner_module, "STUCK_REQUEST_MAX_CHARS", 12)
    bot = await make_bot(cfg, user_id, "Helper")
    rig = make_rig(cfg, team_model({"Helper": [_open_step(SHOP)]}))
    rig.desks.for_bot(bot.id).serve(SHOP, CHALLENGE)
    await _run_in_new_chat(rig, user_id, bot.id, f"price the kettle at {SHOP}")

    assert (await StuckStore(cfg).open_for_bot(user_id, bot.id)).request == "price the ke"


def test_a_stuck_card_previews_as_stuck_on_its_host():
    assert chat_preview(_message(json.dumps({"card_id": "c1", "host": "shop.example"}), kind="stuck")) == (
        "Stuck on shop.example", "card")
    assert chat_preview(_message(json.dumps({"card_id": "c1", "host": ""}), kind="stuck")) == (
        "Needs your help", "card")
    assert chat_preview(_message("not json", kind="stuck")) == ("Needs your help", "card")
    assert chat_preview(_message("[1, 2]", kind="stuck")) == ("Needs your help", "card")


async def test_a_continue_line_previews_like_your_own_words(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Helper")
    talk = TalkStore(cfg)
    thread = await talk.create_thread(user_id, bot.id)
    text = "I cleared the block on shop.example. Read the page again and carry on with: price the kettle"
    await talk.add_message(user_id, thread.id, "user", text, kind="card_answer")
    [row] = await chat_rows(user_id=user_id, bots=BotStore(cfg), talk=talk, rooms=RoomStore(cfg))
    assert (row["preview"], row["preview_kind"], row["from_you"]) == (preview(text, CHAT_PREVIEW_CHARS), "text", True)


def test_the_card_message_kinds_and_the_continue_origin_exist():
    assert {"stuck", "card_answer"} <= set(get_args(MessageKind))
    assert ORIGIN_CARD == "you, after a Stuck card"
```

`test_a_continue_line_previews_like_your_own_words` passes as soon as the file imports: a `card_answer` line already falls through to `chat_preview`'s "text" branch. It guards that fallback, which Task 8's Home relies on.

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_runs.py -q`
Expected: FAIL at collection with `ImportError: cannot import name '_may_open_cards' from 'roost.talk.turn'`. `ORIGIN_CARD` is missing as well. With only the imports fixed, the run tests fail on their assertions:
- `open_for_bot` returns `None`, so `card.reason` raises `AttributeError: 'NoneType' object has no attribute 'reason'`;
- the status is `resting`, not `stuck`;
- `AttributeError: 'TurnRunner' object has no attribute 'settle'` and `'restore_stuck_on_boot'`;
- the stuck-card preview reads `("{...json...}", "text")`.

A `settle` that only returns while the drain task runs (no done-callback) still fails `test_give_up_while_a_run_ends_settles_after_the_run` on its last status assertion: the bot stays `stuck` with no open card.

- [ ] **Step 4: Implement the origin, the message kinds and the previews**

`roost/work/models.py`. Find:

```python
"""Work queue domain model (spec §4.2 "Work queue", §11 step 5) — frozen
dataclasses only. A ``WorkItem`` is one durable unit a bot must handle:
your message, another bot's handoff or a room post (routine, trigger and
card answer are reserved for later steps)."""
```

Replace with:

```python
"""Work queue domain model (spec §4.2 "Work queue", §11 step 5) — frozen
dataclasses only. A ``WorkItem`` is one durable unit a bot must handle:
your message, another bot's handoff, a room post, or a continue item after
you clear a Stuck card (routine and trigger are reserved for later steps)."""
```

Find:

```python
# Origin labels: where a run came from, quoted in its instructions (§6.1).
ORIGIN_YOU = "you, in your chat"
```

Replace with:

```python
# Origin labels: where a run came from, quoted in its instructions (§6.1).
ORIGIN_YOU = "you, in your chat"
# Stuck flow R6: the continue item queued when you clear a Stuck card (Give it back / Try again).
ORIGIN_CARD = "you, after a Stuck card"
```

`roost/talk/store.py`. Find:

```python
MessageKind = Literal[
    "text", "handoff", "suggestion", "notice", "dropped", "interrupted", "daily_limit", "bot_created",
]
```

Replace with:

```python
MessageKind = Literal[
    "text", "handoff", "suggestion", "notice", "dropped", "interrupted", "daily_limit", "bot_created",
    "stuck",         # Stuck flow: a bot's Stuck card; body = stuck_message_body(card), JSON
    "card_answer",   # Stuck flow R6: your continue line after clearing a card (role "user")
]
```

`messages.kind` has no CHECK constraint, so this needs no migration.

`roost/talk/chats.py`. Find:

```python
def chat_preview(message: Message) -> tuple[str, PreviewKind]:
    if message.kind == "bot_created":
        return f"Created {_card_name(message.body)}", "card"
    if message.kind == "suggestion":
        return f"Suggested {_card_name(message.body)}", "card"
```

Replace with:

```python
def _card_host(body: str) -> str:
    """A Stuck card's host, or "" for a card with no web address (an
    ``ask_for_help`` card) or a body that isn't the card's JSON."""
    try:
        host = json.loads(body).get("host")
    except (ValueError, AttributeError):
        return ""
    return host if isinstance(host, str) else ""


def chat_preview(message: Message) -> tuple[str, PreviewKind]:
    """A ``card_answer`` line (role "user") previews like your own words: the last branch."""
    if message.kind == "bot_created":
        return f"Created {_card_name(message.body)}", "card"
    if message.kind == "suggestion":
        return f"Suggested {_card_name(message.body)}", "card"
    if message.kind == "stuck":
        host = _card_host(message.body)
        return (f"Stuck on {host}" if host else "Needs your help"), "card"
```

- [ ] **Step 5: Implement the turn that stops (`roost/talk/turn.py`)**

Find:

```python
from roost.desk import Desk
from roost.desk.control import ControlLock
```

Replace with:

```python
from roost.desk import Desk
from roost.desk.control import ControlLock
from roost.desk.stuck import Block
```

Find:

```python
@dataclass(frozen=True)
class TurnResult:
    reply: str
    tainted: bool
    capped: bool
    link_scope: tuple[str, ...] = ()
```

Replace with:

```python
@dataclass(frozen=True)
class TurnResult:
    reply: str
    tainted: bool
    capped: bool
    link_scope: tuple[str, ...] = ()
    block: Block | None = None   # Stuck flow: the block that ended this run (only in a run that may open cards)
```

Find:

```python
# Only conversation text reaches the model: activity rows, notices and
# suggestion cards are UI, and an incoming handoff (role "user", kind
# "handoff") is the task the bot must answer.
_MODEL_KINDS = frozenset({"text", "handoff"})
```

Replace with:

```python
# Only conversation text reaches the model: activity rows, notices,
# suggestion cards and Stuck cards are UI; an incoming handoff (role
# "user", kind "handoff") is the task the bot must answer; and a continue
# line (role "user", kind "card_answer", Stuck flow R6) is your go-ahead
# after you cleared a Stuck card. A work item's body never reaches the model.
_MODEL_KINDS = frozenset({"text", "handoff", "card_answer"})
```

Find:

```python
def _user_started(items: tuple[WorkItem, ...]) -> bool:
    """Ruling 29: only a run made entirely of the user's own messages may create
    bots — never a handoff, a room post, a routine or a run outside the queue."""
    return bool(items) and all(item.kind is WorkKind.MESSAGE for item in items)
```

Replace with:

```python
def _user_started(items: tuple[WorkItem, ...]) -> bool:
    """Ruling 29: only a run made entirely of the user's own messages may create
    bots — never a handoff, a room post, a routine or a run outside the queue."""
    return bool(items) and all(item.kind is WorkKind.MESSAGE for item in items)


def _may_open_cards(inputs: RunInputs) -> bool:
    """Stuck flow R5: a Stuck card opens only in a run made of your own
    messages and continue items, outside rooms. Every other run (a handoff,
    a room post, a routine, a run outside the queue) gets a block back as a
    loud tool result, and its model answers with it."""
    return inputs.room is None and bool(inputs.items) and all(
        item.kind in (WorkKind.MESSAGE, WorkKind.CARD_ANSWER) for item in inputs.items
    )
```

In `_run_steps`, find:

```python
    """The step loop itself: returns ``(reply_text, step_capped)``.
    Exits early (``step_capped=False``) the moment a step produces no
    tool calls -- a natural ``TurnDone``. Falls through to the ``for``
    loop's ``else`` (``step_capped=True``) only if every one of
    ``MAX_STEPS`` iterations asked for another tool call."""
```

Replace with:

```python
    """The step loop itself: returns ``(reply_text, step_capped)``.
    Exits early (``step_capped=False``) the moment a step produces no
    tool calls -- a natural ``TurnDone`` -- or right after the step whose
    calls set ``tool_runner.block`` (Stuck flow R1). Falls through to the
    ``for`` loop's ``else`` (``step_capped=True``) only if every one of
    ``MAX_STEPS`` iterations asked for another tool call."""
```

Then find:

```python
        turns = turns + await _run_calls(tool_runner, tool_calls)

    return reply_text, True
```

Replace with:

```python
        turns = turns + await _run_calls(tool_runner, tool_calls)
        if tool_runner.block is not None:
            # D-A5: a Stuck run ends here; TurnRunner leaves the card.
            return reply_text, False

    return reply_text, True
```

Add this function right after `_keep_cut_short`:

```python
async def _finish_reply(
    *, talk: TalkStore, events: EventHub, user_id: str, thread_id: str, reply_id: str,
    bot_id: str, text: str, tainted: bool, capped: bool, blocked: bool,
) -> None:
    """Store and publish the turn's reply, then close its placeholder. A
    blocked turn that said nothing stores no empty bubble: the Stuck card
    ``TurnRunner`` posts next speaks for it. The placeholder always closes."""
    if blocked and not text.strip():
        await _close_placeholder(events, user_id, thread_id, reply_id)
        return
    try:
        await _persist_reply(
            talk=talk, events=events, user_id=user_id, thread_id=thread_id, reply_id=reply_id,
            bot_id=bot_id, text=text, tainted=tainted, capped=capped,
        )
    except BaseException:
        await _close_placeholder(events, user_id, thread_id, reply_id)
        raise
```

In `run_turn`, find:

```python
        sees_records=True, control=inputs.control,
    )
```

Replace with:

```python
        sees_records=True, control=inputs.control, cards=_may_open_cards(inputs),
    )
```

Then find:

```python
    try:
        await _persist_reply(
            talk=talk, events=events, user_id=user_id, thread_id=thread_id, reply_id=reply_id,
            bot_id=bot.id, text=reply_text, tainted=tool_runner.tainted, capped=capped,
        )
    except BaseException:
        await _close_placeholder(events, user_id, thread_id, reply_id)
        raise
    return TurnResult(reply=reply_text, tainted=tool_runner.tainted, capped=capped, link_scope=tool_runner.link_scope.as_tuple())
```

Replace with:

```python
    await _finish_reply(
        talk=talk, events=events, user_id=user_id, thread_id=thread_id, reply_id=reply_id, bot_id=bot.id,
        text=reply_text, tainted=tool_runner.tainted, capped=capped, blocked=tool_runner.block is not None,
    )
    return TurnResult(reply=reply_text, tainted=tool_runner.tainted, capped=capped,
                      link_scope=tool_runner.link_scope.as_tuple(), block=tool_runner.block)
```

`run_turn` stays under 50 lines, and `turn.py` stays at about 525 lines.

- [ ] **Step 6: Implement the runner that leaves the card (`roost/talk/runner.py`)**

Find the end of the module docstring:

```python
Still the error boundary ``run_turn`` relies on: an unexpected exception
becomes a "something went wrong" notice, a hung turn hits the wall-time
cap, and the bot always settles back to Resting.
"""
```

Replace with:

```python
Still the error boundary ``run_turn`` relies on: an unexpected exception
becomes a "something went wrong" notice, a hung turn hits the wall-time
cap, and the bot always settles back to Resting (Stuck while one of its
Stuck cards is open, Off duty when it is off duty).

Stuck flow (Piece A): a chat run that ended on a block leaves a Stuck card
(``_on_block``); a continue run blocked again on the same host marks its
card blocked instead (rung 4).
"""
```

Find:

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
```

Replace with:

```python
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import partial
```

Find:

```python
from roost.constants import DAILY_RUN_CAP, HANDOFF_TIMEOUT_S, MAX_HANDOFF_DEPTH, MAX_RUN_SECONDS
```

Replace with:

```python
from roost.constants import (
    DAILY_RUN_CAP, HANDOFF_TIMEOUT_S, MAX_HANDOFF_DEPTH, MAX_RUN_SECONDS, STUCK_REQUEST_MAX_CHARS,
)
```

Find:

```python
from roost.talk.store import TalkStore
from roost.talk.turn import EMPTY_RESULT, RunInputs, TurnResult
from roost.talk.turn import run_turn as run_one_turn
from roost.work.models import (
    ClaimedBatch, DropReport, HandoffResult, RunOutcome, WorkDraft, WorkItem, WorkState,
)
```

Replace with:

```python
from roost.stuck.announce import post_bot_line, publish_card
from roost.stuck.models import CardDraft, StuckCard
from roost.stuck.store import StuckStore
from roost.stuck.texts import blocked_line, stuck_message_body
from roost.talk.store import TalkStore
from roost.talk.turn import EMPTY_RESULT, RunInputs, TurnResult
from roost.talk.turn import run_turn as run_one_turn
from roost.work.models import (
    ClaimedBatch, DropReport, HandoffResult, RunOutcome, WorkDraft, WorkItem, WorkKind, WorkState,
)
```

Import the `roost.stuck` submodules directly, never the package `roost.stuck`. Task 7's `service.py` takes a `TurnRunner`.

Find:

```python
def _by_thread(items: Sequence[WorkItem]) -> tuple[tuple[str, tuple[WorkItem, ...]], ...]:
    thread_ids = tuple(dict.fromkeys(item.thread_id for item in items))
    return tuple((tid, tuple(i for i in items if i.thread_id == tid)) for tid in thread_ids)
```

Replace with:

```python
def _by_thread(items: Sequence[WorkItem]) -> tuple[tuple[str, tuple[WorkItem, ...]], ...]:
    thread_ids = tuple(dict.fromkeys(item.thread_id for item in items))
    return tuple((tid, tuple(i for i in items if i.thread_id == tid)) for tid in thread_ids)


def _request_text(items: Sequence[WorkItem]) -> str:
    """What a new Stuck card keeps to carry on with: the run's own items,
    oldest first, capped at ``STUCK_REQUEST_MAX_CHARS``."""
    return "\n".join(item.body for item in items)[:STUCK_REQUEST_MAX_CHARS]
```

In `TurnRunner.__init__`, find:

```python
        domain: DomainTools | None = None, control: ControlLock | None = None,
    ) -> None:
```

Replace with:

```python
        domain: DomainTools | None = None, control: ControlLock | None = None, stuck: StuckStore | None = None,
    ) -> None:
```

Find:

```python
        self._rooms = rooms if rooms is not None else RoomStore(config)
        self._tasks: dict[str, "asyncio.Task[None]"] = {}
```

Replace with:

```python
        self._rooms = rooms if rooms is not None else RoomStore(config)
        self._stuck = stuck if stuck is not None else StuckStore(config)
        self._tasks: dict[str, "asyncio.Task[None]"] = {}
        # R9: settles that run after a drain task ended, kept until they finish so none is garbage-collected.
        self._settling: frozenset["asyncio.Task[None]"] = frozenset()
```

Find:

```python
    async def set_off_duty(self, user_id: str, bot_id: str, off_duty: bool) -> Bot | None:
        bot = await self._bots.set_off_duty(user_id, bot_id, off_duty)
        if bot is None:
            return None
        await self._events.publish(user_id, {"type": "bot_updated", "bot": bot_out(bot, self._activity.get(bot_id))})
        if not off_duty:
            await self.kick(user_id, bot_id)
        return bot
```

Replace with:

```python
    async def set_off_duty(self, user_id: str, bot_id: str, off_duty: bool) -> Bot | None:
        bot = await self._bots.set_off_duty(user_id, bot_id, off_duty)
        if bot is None:
            return None
        if not off_duty:
            # R9: back on duty with an open Stuck card shows Stuck, not Resting. Settle BEFORE the
            # kick, so it shows at once: once a drain task exists, settle waits for it to end.
            await self.settle(user_id, bot_id)
            bot = await self._bots.get(user_id, bot_id) or bot
        await self._events.publish(user_id, {"type": "bot_updated", "bot": bot_out(bot, self._activity.get(bot_id))})
        if not off_duty:
            await self.kick(user_id, bot_id)
        return bot
```

Find:

```python
    async def resume_all(self) -> None:
        for user_id, bot_id in await self._queue.bots_with_queued():
            await self.kick(user_id, bot_id)
```

Replace with:

```python
    async def resume_all(self) -> None:
        for user_id, bot_id in await self._queue.bots_with_queued():
            await self.kick(user_id, bot_id)

    async def restore_stuck_on_boot(self) -> None:
        """R9 / Review Focus #5: after a restart, a bot whose Stuck card is
        still open shows Stuck again. The old process may have died between
        opening the card and settling. An off-duty bot stays Off duty."""
        for user_id, bot_id in await self._stuck.open_bots():
            await self._settle_status(user_id, bot_id)

    async def settle(self, user_id: str, bot_id: str) -> None:
        """R9: put the bot's status right after one of its cards changed
        (``/clear``, ``/give-up``, back on duty). With no drain task running it
        settles at once. While one runs, it settles once that task ends: the
        run settles its own status, but a card closed after that (Give up
        pressed while the run was ending) would leave the bot Stuck with no
        open card."""
        running = self._tasks.get(bot_id)
        if running is not None and not running.done():
            running.add_done_callback(partial(self._settle_after, user_id, bot_id))
            return
        await self._settle_status(user_id, bot_id)

    def _settle_after(self, user_id: str, bot_id: str, finished: "asyncio.Task[None]") -> None:
        """``settle``'s done-callback on a drain task. A callback can't await, so
        the settle runs in a task of its own, kept in ``_settling`` until it ends
        so it is never garbage-collected (the tests' ``wait_idle`` waits on it)."""
        task = finished.get_loop().create_task(self._settle_logged(user_id, bot_id))
        self._settling = self._settling | {task}
        task.add_done_callback(self._forget_settle)

    def _forget_settle(self, task: "asyncio.Task[None]") -> None:
        self._settling = self._settling - {task}

    async def _settle_logged(self, user_id: str, bot_id: str) -> None:
        """``settle`` again, not ``_settle_status`` straight away: a drain task
        kicked in the meantime is waited for in turn, so its On it run is never
        shown Resting. Nobody awaits this task, so an error is logged here."""
        try:
            await self.settle(user_id, bot_id)
        except Exception:
            logger.exception("Settling the status after a run failed for bot %s", bot_id)
```

`partial` is already imported in `runner.py` (`from functools import partial`).

In `_execute`, find:

```python
            outcome: RunOutcome = "step_cap" if result.capped else "done"
        except TimeoutError:
```

Replace with:

```python
            outcome: RunOutcome = "step_cap" if result.capped else "done"
            # D-A5: the card exists before the status settles below, so the bot settles to Stuck.
            await self._on_block(user_id, bot.id, thread_id, inputs.items, result)
        except TimeoutError:
```

`_on_block` runs inside `_execute`'s error boundary. If opening the card fails, the user gets the existing "Something went wrong on my side. Please try again." notice, the outcome is `"error"`, and the bot still settles.

Then replace `_settle_status`, the last method in the file. Find:

```python
    async def _settle_status(self, user_id: str, bot_id: str) -> None:
        bot = await self._bots.get(user_id, bot_id)
        if bot is None:
            return
        status = BotStatus.OFF_DUTY if bot.off_duty else BotStatus.RESTING
        self._activity.set(bot_id, None)
        await self._bots.set_status(user_id, bot_id, status)
        await self._events.publish(user_id, {
            "type": "bot_status", "bot_id": bot_id, "status": status.value, "activity": None,
        })
```

Replace with:

```python
    async def _on_block(
        self, user_id: str, bot_id: str, thread_id: str, items: tuple[WorkItem, ...], result: TurnResult,
    ) -> None:
        """D-A5: a chat run that ended on a block leaves a Stuck card: a row,
        a ``kind="stuck"`` bot message and a ``stuck_card`` frame. Rung 4: a
        continue run blocked again on its card's host opens no new card. That
        card becomes blocked and the bot names what it didn't finish. A block
        with no host (``ask_for_help`` before any page) is never "the same host"."""
        block = result.block
        if block is None:
            return
        prior = await self._answered_card(user_id, items)
        if prior is not None and block.host and prior.host == block.host:
            await self._block_card(user_id, prior)
            return
        draft = CardDraft(
            bot_id=bot_id, thread_id=thread_id, work_item_id=items[0].id if items else None, block=block,
            request=prior.request if prior is not None else _request_text(items), tainted=result.tainted,
        )
        card = await self._stuck.open(user_id, draft)
        # One open card per bot: while an older card is open, open() returns it. It is shown in THIS
        # run's chat, so a run blocked in another chat never ends there with nothing said.
        shown = replace(card, thread_id=thread_id)
        await post_bot_line(self._talk, self._events, user_id, shown, stuck_message_body(card), kind="stuck")
        await publish_card(self._events, user_id, card)

    async def _answered_card(self, user_id: str, items: Sequence[WorkItem]) -> StuckCard | None:
        """The card a claimed continue item answers (its ``answer_item_id``), if any."""
        for item in items:
            if item.kind is not WorkKind.CARD_ANSWER:
                continue
            card = await self._stuck.card_for_answer(user_id, item.id)
            if card is not None:
                return card
        return None

    async def _block_card(self, user_id: str, prior: StuckCard) -> None:
        """Rung 4, never an empty result: the card says Blocked and the bot says what it didn't finish."""
        card = await self._stuck.mark_blocked(user_id, prior.id) or prior
        await post_bot_line(self._talk, self._events, user_id, card, blocked_line(card.host, card.request),
                            kind="text")
        await publish_card(self._events, user_id, card)

    async def _settle_status(self, user_id: str, bot_id: str) -> None:
        bot = await self._bots.get(user_id, bot_id)
        if bot is None:
            return
        status = await self._idle_status(user_id, bot)
        self._activity.set(bot_id, None)
        await self._bots.set_status(user_id, bot_id, status)
        await self._events.publish(user_id, {
            "type": "bot_status", "bot_id": bot_id, "status": status.value, "activity": None,
        })

    async def _idle_status(self, user_id: str, bot: Bot) -> BotStatus:
        """Off duty first; then Stuck while one of its Stuck cards is open (R9); else Resting."""
        if bot.off_duty:
            return BotStatus.OFF_DUTY
        if await self._stuck.open_for_bot(user_id, bot.id) is not None:
            return BotStatus.STUCK
        return BotStatus.RESTING
```

Then teach the tests' `wait_idle` about those settles. `tests/team_helpers.py`, find:

```python
async def wait_idle(runner: TurnRunner, timeout: float = 5.0) -> None:
    """Wait until no bot has a drain loop running (a handoff can start new ones)."""
    async with asyncio.timeout(timeout):
        while True:
            running = [task for task in runner._tasks.values() if not task.done()]
            if not running:
                return
            await asyncio.wait(running, timeout=0.05)
```

Replace with:

```python
def _busy(runner: TurnRunner) -> list["asyncio.Task[None]"]:
    """Drain loops still running, and settles still waiting to finish after one (stuck flow R9)."""
    return [task for task in (*runner._tasks.values(), *runner._settling) if not task.done()]


async def wait_idle(runner: TurnRunner, timeout: float = 5.0) -> None:
    """Wait until no bot has a drain loop running (a handoff can start new ones)
    and no ``TurnRunner.settle`` still waits to finish after one."""
    async with asyncio.timeout(timeout):
        while True:
            running = _busy(runner)
            if not running:
                await asyncio.sleep(0)     # a drain loop that just ended may still have a settle to start
                running = _busy(runner)
            if not running:
                return
            await asyncio.wait(running, timeout=0.05)
```

The `sleep(0)` matters: a drain task's done-callbacks run one loop step after it ends, so `wait_idle` could otherwise see the task done before `_settle_after` has put its settle in `_settling`.

Notes on this code:
- `settle`'s done-callback runs `settle` again, not `_settle_status`: a drain task kicked between the end of the old one and the callback is waited for in turn, so a bot that is On it is never shown Resting. A drain task that ends through `stop()` or `cancel()` fires the callback too; that settle only repeats the status `stop()` set (or finds no bot after `cancel`).
- `stop()` and `_stop_children` already call `_settle_status`, so a stopped bot with an open card also shows Stuck.
- Cards open only in `message` / `card_answer` runs. No handoff waiter ever waits on a run that left a card, so `RunOutcome` and `HandoffStatus` stay unchanged.
- A bot has one open card at most (`StuckStore.open` returns the open one). A run blocked while an older card is open opens no second card: that card is posted in the blocked run's own chat, so that chat never ends with nothing said (`test_a_block_in_another_chat_while_a_card_is_open_shows_the_open_card_there`). For a new card, `replace(card, thread_id=thread_id)` is the card itself.
- `runner.py` grows to about 490 lines, and every function stays under 50 lines.

- [ ] **Step 7: Wire the gateway (`roost/gateway/app.py`)**

Find:

```python
from roost.rooms.store import RoomStore
from roost.talk.runner import TurnRunner
```

Replace with:

```python
from roost.rooms.store import RoomStore
from roost.stuck.store import StuckStore
from roost.talk.runner import TurnRunner
```

Find:

```python
        await app.state.bots.reset_on_boot(app.state.events)
        # S1 D4: every account has its main bot from the start (stars a Chief, or creates one).
```

Replace with:

```python
        await app.state.bots.reset_on_boot(app.state.events)
        # Stuck flow R9: a bot whose Stuck card is still open shows Stuck again
        # (after reset_on_boot, which moved an interrupted On it bot to Resting).
        await app.state.turns.restore_stuck_on_boot()
        # S1 D4: every account has its main bot from the start (stars a Chief, or creates one).
```

Find:

```python
    app.state.control = ControlLock()
    app.state.turns = TurnRunner(
        resolved_config, app.state.bots, app.state.talk, app.state.events,
        app.state.desks, make_model(resolved_config), app.state.activity_board,
        rooms=app.state.rooms, control=app.state.control,
    )
```

Replace with:

```python
    app.state.control = ControlLock()
    app.state.stuck = StuckStore(resolved_config)
    app.state.turns = TurnRunner(
        resolved_config, app.state.bots, app.state.talk, app.state.events,
        app.state.desks, make_model(resolved_config), app.state.activity_board,
        rooms=app.state.rooms, control=app.state.control, stuck=app.state.stuck,
    )
```

Task 7 builds `app.state.stuck_service` after `turns`, the same way `RoomService` is built.

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_runs.py -q`
Expected: PASS (31 tests: 21 plain tests, and the `_may_open_cards` test runs 10 cases).

Run the files that drive the turn loop, the runner, the boot and the previews:
`cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_turn.py tests/test_work_runner.py tests/test_work_controls.py tests/test_work_queue.py tests/test_work_api.py tests/test_handoff.py tests/test_room_runs.py tests/test_rooms_api.py tests/test_computer_control_runs.py tests/test_tool_runner_taint.py tests/test_create_bot.py tests/test_suggest_bot.py tests/test_chats_api.py tests/test_main_bot.py tests/test_bot_store.py tests/test_events_ws.py tests/test_every_bot_tools.py -q`
Expected: PASS.

Run the earlier stuck-flow tests, then the full suite with the coverage gate:
`cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest -q -k stuck && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/talk/turn.py roost/talk/runner.py roost/talk/store.py roost/talk/chats.py roost/work/models.py \
  roost/gateway/app.py tests/test_stuck_runs.py tests/team_helpers.py
git commit -m "feat: a blocked chat run stops and leaves a Stuck card; the bot shows Stuck while it is open"
```

---

### Task 6: Open in your main Brave: keeper endpoint, client and gateway seam

Design §3, D-A3/D-A4 and R8. "Use my main Brave" only **opens** the card's address in the user's own Brave:
- The keeper gets a signed `POST /desks/{bot_id}/main-browser/open {"url": ...}`. It validates the bot id and the body (`extra="forbid"`, at most `MAIN_BROWSER_URL_MAX_CHARS`). It runs `check_url`, then an injected `MainBrowserOpener`. The opener runs the argv `("/usr/bin/open", "-a", "Brave Browser", <checked url>)` as a list, with no shell. There is no debug port, no profile access and no automation.
- The keeper answers `{"opened": true}`, 400 for a refused address, 401 unsigned, 422 for a bad body and 500 `"failed to open the main browser"`.
- Every decision is audited as `"main_browser_open"` with `"ok"`, `"refused"` or `"error"`. The address is never audited, logged or echoed back in a 422.
- `check_url` only lets `http` and `https` through, so the address can never start with `-` and be read by `open` as a flag. The route passes on the **canonical** URL that `check_url` returns, never the raw input.
- On the gateway side, `KeeperClient` learns to turn the keeper's 400 into `UrlBlocked` (`refused_on_bad_request`), instead of folding it into `DeskUnavailable` (503). `roost/desk/main_browser.py` adds the seam that Task 7 puts on `app.state.main_browser`:
  - `KeeperMainBrowser` in keeper mode;
  - `FakeMainBrowser` in fake mode (every test and E2E run). It checks the address the way the keeper does and records `(bot_id, checked_url)` in an immutable tuple.
- No test ever runs `/usr/bin/open`. Every test injects a fake runner, or patches `asyncio.create_subprocess_exec`.

This task does not touch `roost/gateway/app.py`. Task 7 adds `app.state.main_browser = make_main_browser(resolved_config)` and the `/api/stuck/{id}/open-in-main-browser` route.

**Files:**
- Create:
  - `roost/keeper/main_browser.py`: `MainBrowserOpenError`, `Runner`, `_run_open` (the default runner) and `MainBrowserOpener`.
  - `roost/desk/main_browser.py`: `MainBrowser`, `KeeperMainBrowser`, `FakeMainBrowser` and `make_main_browser`.
  - `tests/test_keeper_main_browser.py` and `tests/test_main_browser_seam.py`.
- Modify:
  - `roost/constants.py` is **not** changed: Task 1 already added the three `MAIN_BROWSER_*` constants at the end of its "Stuck flow (Piece A)" section. Step 4 only checks that they are there.
  - `roost/keeper/app.py`:
    - the docstring line, the imports, `_MainBrowserOpenBody` and `_parse_main_browser_open_body`;
    - `_open_in_main_browser`, and `app.state.main_browser = MainBrowserOpener()`;
    - the route `POST /desks/{bot_id}/main-browser/open`.
  - `roost/desk/client.py`: `_request(..., refused_on_bad_request=False)` and `KeeperClient.open_in_main_browser`.
- Test:
  - `tests/test_keeper_main_browser.py` (new) and `tests/test_main_browser_seam.py` (new).
  - `tests/test_keeper_client.py`: imports, plus the appended "open in your main Brave" tests.

**Interfaces:**
- Consumes:
  - From Task 1: the `roost/constants.py` section headed `# Stuck flow (Piece A) — roost/desk/stuck.py, roost/stuck/`, which ends with `MAIN_BROWSER_OPEN_ARGV = ("/usr/bin/open", "-a", "Brave Browser")`, `MAIN_BROWSER_OPEN_TIMEOUT_S = 10.0` and `MAIN_BROWSER_URL_MAX_CHARS = 2048`.
  - Existing code:
    - `check_url(url: str) -> str` and `UrlBlocked(ValueError)` (`roost/desk/url_policy.py`);
    - `require_signed_body`, `_require_valid_bot_id` and `AuditLog.record(action, bot_id, result)` (keeper);
    - `KeeperClient._request`, `DeskUnavailable` and `RoostConfig.desk_mode`.
- Produces (Task 7 relies on these exact names):
  - `roost.keeper.main_browser`:
    - `MainBrowserOpenError(RuntimeError)`;
    - `Runner = Callable[[Sequence[str], float], Awaitable[int]]`;
    - `MainBrowserOpener(*, runner: Runner | None = None)`, with `async open(url: str) -> None`.
  - Keeper route `POST /desks/{bot_id}/main-browser/open`. Body `{"url": str}`. It answers 200 `{"opened": true}`, 400 `{"detail": "that address can't be opened"}`, 401, 422 or 500 `{"detail": "failed to open the main browser"}`.
  - `roost.desk.client`: `KeeperClient._request(..., refused_on_bad_request: bool = False)`, where a 400 raises `UrlBlocked`, and `async KeeperClient.open_in_main_browser(bot_id: str, url: str) -> None`.
  - `roost.desk.main_browser`:
    - `MainBrowser` (Protocol: `async open(bot_id, url) -> None`);
    - `KeeperMainBrowser(config, *, client: KeeperClient | None = None)`;
    - `FakeMainBrowser()`, with `opened: tuple[tuple[str, str], ...]` and a public `fail: bool`. It also accepts `FakeMainBrowser(fail=True)`. `fail` raises `DeskUnavailable`, and a refused address raises `UrlBlocked`.
    - Both seams refuse an address longer than `MAIN_BROWSER_URL_MAX_CHARS` as `UrlBlocked` before anything else. The keeper would answer that body 422, and `KeeperClient` turns a 422 into `DeskUnavailable`, so without this check a long sign-in URL would show the user a 503 "desk unavailable" instead of the 400 "That address can't be opened.".
    - `make_main_browser(config: RoostConfig) -> MainBrowser`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_keeper_main_browser.py`:

```python
"""Open in your main Brave, keeper side (stuck flow, Task 6; design §3, R8).

``POST /desks/{bot_id}/main-browser/open`` is exercised against the real
keeper app over ``TestClient``, with a recording runner in place of
``/usr/bin/open``. No test here ever opens a real browser (Global
Constraints: "Tests never run it: they inject a fake runner"). The
``MainBrowserOpener`` tests at the bottom cover the opener itself. They
include its real default runner, with ``asyncio.create_subprocess_exec``
patched out, plus one plain ``sleep`` to prove a hung process is killed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import roost.keeper.main_browser as main_browser_module
from roost.config import RoostConfig
from roost.constants import MAIN_BROWSER_OPEN_TIMEOUT_S, MAIN_BROWSER_URL_MAX_CHARS
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app
from roost.keeper.main_browser import MainBrowserOpener, MainBrowserOpenError, _run_open

_SECRET = "k" * 32
_VALID_BOT_ID = "77777777-7777-4777-8777-777777777777"
_OPEN_PATH = f"/desks/{_VALID_BOT_ID}/main-browser/open"
_URL = "https://example.com/"
_OPEN_ARGV = ["/usr/bin/open", "-a", "Brave Browser"]


class _RecordingRunner:
    """Stands in for ``/usr/bin/open``. It records each ``(argv, timeout)``
    and answers ``exit_code``, or raises ``error`` when one is given. It never
    runs anything."""

    def __init__(self, exit_code: int = 0, error: BaseException | None = None) -> None:
        self.calls: list[tuple[list[str], float]] = []
        self._exit_code = exit_code
        self._error = error

    async def __call__(self, argv, timeout_s):
        self.calls.append((list(argv), timeout_s))
        if self._error is not None:
            raise self._error
        return self._exit_code


class _FakeProcess:
    """What the patched ``asyncio.create_subprocess_exec`` hands back.
    ``wait()`` answers ``returncode`` at once, or, with ``hang``, only
    after ``kill()``."""

    def __init__(self, returncode: int = 0, *, hang: bool = False) -> None:
        self.returncode = returncode
        self.killed = False
        self._done = asyncio.Event()
        if not hang:
            self._done.set()

    async def wait(self) -> int:
        await self._done.wait()
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._done.set()


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
    )


@pytest.fixture
def runner() -> _RecordingRunner:
    return _RecordingRunner()


def _client(config: RoostConfig, runner: _RecordingRunner) -> TestClient:
    app = create_app(config)
    app.state.main_browser = MainBrowserOpener(runner=runner)
    return TestClient(app)


@pytest.fixture
def client(config: RoostConfig, runner: _RecordingRunner) -> TestClient:
    return _client(config, runner)


def _signed_post(client: TestClient, path: str, payload: dict | bytes):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = signed_headers(_SECRET, "POST", path, body)
    return client.post(path, headers=headers, content=body)


def _audit_entries(config: RoostConfig) -> list[dict]:
    path = config.database_dir / "keeper-audit.log"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [json.loads(line) for line in lines]


def _main_browser_results(config: RoostConfig) -> list[str]:
    return [entry["result"] for entry in _audit_entries(config) if entry["action"] == "main_browser_open"]


def _patch_exec(monkeypatch: pytest.MonkeyPatch, process: _FakeProcess) -> list[tuple[tuple, dict]]:
    calls: list[tuple[tuple, dict]] = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return process

    monkeypatch.setattr(main_browser_module.asyncio, "create_subprocess_exec", fake_exec)
    return calls


# -- the route -----------------------------------------------------------------


def test_open_runs_open_a_brave_browser_with_the_checked_url(
    client: TestClient, runner: _RecordingRunner, config: RoostConfig
):
    response = _signed_post(client, _OPEN_PATH, {"url": _URL})
    assert (response.status_code, response.json()) == (200, {"opened": True})
    assert runner.calls == [([*_OPEN_ARGV, _URL], MAIN_BROWSER_OPEN_TIMEOUT_S)]
    assert _main_browser_results(config) == ["ok"]


def test_open_passes_on_the_canonical_address_not_the_raw_one(client: TestClient, runner: _RecordingRunner):
    response = _signed_post(client, _OPEN_PATH, {"url": "https://EXAMPLE.com/Path?q=1"})
    assert response.status_code == 200
    assert runner.calls[0][0] == [*_OPEN_ARGV, "https://example.com/Path?q=1"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "http://127.0.0.1/"])
def test_a_refused_address_is_400_and_never_opened(
    client: TestClient, runner: _RecordingRunner, config: RoostConfig, url: str
):
    response = _signed_post(client, _OPEN_PATH, {"url": url})
    assert (response.status_code, response.json()) == (400, {"detail": "that address can't be opened"})
    assert runner.calls == []
    assert _main_browser_results(config) == ["refused"]


def test_open_is_signed(client: TestClient, runner: _RecordingRunner):
    response = client.post(_OPEN_PATH, content=json.dumps({"url": _URL}).encode())
    assert response.status_code == 401
    assert runner.calls == []


def test_an_extra_body_field_is_422_and_never_opened(client: TestClient, runner: _RecordingRunner):
    response = _signed_post(client, _OPEN_PATH, {"url": _URL, "app": "Safari"})
    assert response.status_code == 422
    assert runner.calls == []


@pytest.mark.parametrize("payload", [{}, {"url": ""}, b"not json", b""])
def test_a_missing_or_empty_address_is_422(client: TestClient, runner: _RecordingRunner, payload):
    response = _signed_post(client, _OPEN_PATH, payload)
    assert response.status_code == 422
    assert runner.calls == []


def test_an_address_over_the_limit_is_422_and_never_echoed_back(client: TestClient, runner: _RecordingRunner):
    url = "https://example.com/" + "a" * MAIN_BROWSER_URL_MAX_CHARS
    response = _signed_post(client, _OPEN_PATH, {"url": url})
    assert response.status_code == 422
    assert "example.com" not in response.text
    assert runner.calls == []


def test_a_bad_bot_id_is_400(client: TestClient, runner: _RecordingRunner):
    response = _signed_post(client, "/desks/..etc/main-browser/open", {"url": _URL})
    assert (response.status_code, response.json()) == (400, {"detail": "bot_id must be a UUID4"})
    assert runner.calls == []


def test_a_failing_open_is_a_clean_500_with_a_fixed_detail(config: RoostConfig):
    response = _signed_post(_client(config, _RecordingRunner(exit_code=1)), _OPEN_PATH, {"url": _URL})
    assert (response.status_code, response.json()) == (500, {"detail": "failed to open the main browser"})
    assert _main_browser_results(config) == ["error"]


def test_the_audit_log_and_the_logs_never_hold_the_address(config: RoostConfig, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG)
    private_url = "https://private-bank.example/statement?id=12345"
    working = _client(config, _RecordingRunner())
    _signed_post(working, _OPEN_PATH, {"url": private_url})
    _signed_post(working, _OPEN_PATH, {"url": "javascript:alert('private-bank')"})
    _signed_post(_client(config, _RecordingRunner(exit_code=1)), _OPEN_PATH, {"url": private_url})

    audit_text = (config.database_dir / "keeper-audit.log").read_text(encoding="utf-8")
    assert _main_browser_results(config) == ["ok", "refused", "error"]
    assert "private-bank" not in audit_text
    assert "private-bank" not in caplog.text
    assert all(set(entry) == {"action", "bot_id", "result", "ts"} for entry in _audit_entries(config))


# -- MainBrowserOpener ---------------------------------------------------------


async def test_the_opener_runs_the_fixed_argv_plus_the_address_with_its_timeout():
    runner = _RecordingRunner()
    await MainBrowserOpener(runner=runner).open(_URL)
    assert runner.calls == [([*_OPEN_ARGV, _URL], MAIN_BROWSER_OPEN_TIMEOUT_S)]


async def test_a_non_zero_exit_is_an_open_error():
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener(runner=_RecordingRunner(exit_code=1)).open(_URL)


async def test_a_timeout_is_an_open_error():
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener(runner=_RecordingRunner(error=asyncio.TimeoutError())).open(_URL)


async def test_an_open_that_cannot_start_is_an_open_error():
    missing = FileNotFoundError(2, "No such file or directory", "/usr/bin/open")
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener(runner=_RecordingRunner(error=missing)).open(_URL)


async def test_the_default_runner_execs_an_argv_list_with_no_shell(monkeypatch: pytest.MonkeyPatch):
    calls = _patch_exec(monkeypatch, _FakeProcess(returncode=0))
    await MainBrowserOpener().open(_URL)
    assert calls == [
        ((*_OPEN_ARGV, _URL), {"stdout": asyncio.subprocess.DEVNULL, "stderr": asyncio.subprocess.DEVNULL})
    ]


async def test_the_default_runner_reports_a_failed_open(monkeypatch: pytest.MonkeyPatch):
    _patch_exec(monkeypatch, _FakeProcess(returncode=1))
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener().open(_URL)


async def test_the_default_runner_kills_open_when_it_hangs(monkeypatch: pytest.MonkeyPatch):
    process = _FakeProcess(hang=True)
    _patch_exec(monkeypatch, process)
    monkeypatch.setattr(main_browser_module, "MAIN_BROWSER_OPEN_TIMEOUT_S", 0.05)
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener().open(_URL)
    assert process.killed is True


async def test_the_default_runner_turns_a_missing_open_into_an_open_error(monkeypatch: pytest.MonkeyPatch):
    async def missing(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "/usr/bin/open")

    monkeypatch.setattr(main_browser_module.asyncio, "create_subprocess_exec", missing)
    with pytest.raises(MainBrowserOpenError):
        await MainBrowserOpener().open(_URL)


async def test_the_real_default_runner_kills_a_process_that_hangs():
    """A plain system command, never ``open`` or Brave. This is the same style
    as ``test_run_docker_kills_and_reports_timed_out_on_a_slow_command``."""
    with pytest.raises(asyncio.TimeoutError):
        await _run_open(["sleep", "5"], 0.1)
```

Create `tests/test_main_browser_seam.py`:

```python
"""The gateway's seam to "Use my main Brave" (stuck flow, Task 6; design R8).

``make_main_browser`` picks ``KeeperMainBrowser`` in keeper mode and the
recording ``FakeMainBrowser`` in fake mode, so no test or E2E run ever
reaches a keeper or a real Brave. ``KeeperMainBrowser`` is run here against
the real keeper app over ``httpx.ASGITransport``, with a recording runner
in place of ``/usr/bin/open``.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from roost.config import RoostConfig
from roost.constants import MAIN_BROWSER_URL_MAX_CHARS
from roost.desk import DeskUnavailable
from roost.desk.client import KeeperClient
from roost.desk.main_browser import FakeMainBrowser, KeeperMainBrowser, MainBrowser, make_main_browser
from roost.desk.url_policy import UrlBlocked
from roost.keeper.app import create_app
from roost.keeper.main_browser import MainBrowserOpener

_BOT_ID = "77777777-7777-4777-8777-777777777777"
_SECRET = "k" * 32
_URL = "https://example.com/"
_OVERLONG_URL = "https://example.com/" + "a" * MAIN_BROWSER_URL_MAX_CHARS


class _FakeOpenRunner:
    """Stands in for ``/usr/bin/open``. It records each argv and answers
    exit code 0. It never runs anything."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def __call__(self, argv, timeout_s):
        self.calls.append(list(argv))
        return 0


def _config(tmp_path: Path, desk_mode: str) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
        desk_mode=desk_mode,
    )


def _keeper_main_browser(config: RoostConfig, runner: _FakeOpenRunner) -> KeeperMainBrowser:
    keeper = create_app(config)
    keeper.state.main_browser = MainBrowserOpener(runner=runner)
    client = KeeperClient(config, transport=httpx.ASGITransport(app=keeper))
    return KeeperMainBrowser(config, client=client)


def test_fake_mode_gets_the_recording_fake(tmp_path: Path):
    assert isinstance(make_main_browser(_config(tmp_path, "fake")), FakeMainBrowser)


def test_keeper_mode_gets_the_keeper_main_browser(tmp_path: Path):
    browser: MainBrowser = make_main_browser(_config(tmp_path, "keeper"))
    assert isinstance(browser, KeeperMainBrowser)


async def test_the_fake_records_each_open_in_a_new_tuple():
    fake = FakeMainBrowser()
    before = fake.opened
    await fake.open("bot-1", _URL)
    after_first = fake.opened
    await fake.open("bot-2", "https://login.example/")
    assert before == ()
    assert after_first == (("bot-1", _URL),)
    assert fake.opened == (("bot-1", _URL), ("bot-2", "https://login.example/"))


async def test_the_fake_records_the_canonical_address():
    fake = FakeMainBrowser()
    await fake.open("bot-1", "https://EXAMPLE.com/Path")
    assert fake.opened == (("bot-1", "https://example.com/Path"),)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "http://127.0.0.1/"])
async def test_the_fake_refuses_what_the_keeper_refuses(url: str):
    fake = FakeMainBrowser()
    with pytest.raises(UrlBlocked):
        await fake.open("bot-1", url)
    assert fake.opened == ()


async def test_a_failing_fake_is_desk_unavailable():
    fake = FakeMainBrowser(fail=True)
    with pytest.raises(DeskUnavailable):
        await fake.open("bot-1", _URL)
    assert fake.opened == ()


async def test_the_fakes_fail_flag_can_be_switched_on_later():
    """API tests flip it through ``app.state`` the way they flip ``FakeDesk.force_unavailable``."""
    fake = FakeMainBrowser()
    fake.fail = True
    with pytest.raises(DeskUnavailable):
        await fake.open("bot-1", _URL)


async def test_the_keeper_main_browser_opens_through_the_signed_keeper_route(tmp_path: Path):
    runner = _FakeOpenRunner()
    await _keeper_main_browser(_config(tmp_path, "keeper"), runner).open(_BOT_ID, _URL)
    assert runner.calls == [["/usr/bin/open", "-a", "Brave Browser", _URL]]


async def test_the_keeper_main_browser_passes_on_a_refusal_as_url_blocked(tmp_path: Path):
    runner = _FakeOpenRunner()
    with pytest.raises(UrlBlocked):
        await _keeper_main_browser(_config(tmp_path, "keeper"), runner).open(_BOT_ID, "javascript:alert(1)")
    assert runner.calls == []


async def test_the_keeper_main_browser_with_the_keeper_down_is_desk_unavailable(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    config = _config(tmp_path, "keeper")
    browser = KeeperMainBrowser(config, client=KeeperClient(config, transport=httpx.MockTransport(handler)))
    with pytest.raises(DeskUnavailable):
        await browser.open(_BOT_ID, _URL)


async def test_the_keeper_main_browser_refuses_an_overlong_address_as_url_blocked(tmp_path: Path):
    """The keeper answers an over-long body 422, which ``KeeperClient`` turns into
    ``DeskUnavailable`` (503). The seam refuses it first, so the user sees a 400."""
    runner = _FakeOpenRunner()
    with pytest.raises(UrlBlocked):
        await _keeper_main_browser(_config(tmp_path, "keeper"), runner).open(_BOT_ID, _OVERLONG_URL)
    assert runner.calls == []


async def test_the_fake_refuses_an_overlong_address_like_the_keeper_seam():
    fake = FakeMainBrowser()
    with pytest.raises(UrlBlocked):
        await fake.open("bot-1", _OVERLONG_URL)
    assert fake.opened == ()
```

In `tests/test_keeper_client.py`, replace these import lines:

```python
from roost.desk.client import KeeperClient, KeeperDesk, _connect_page, _relay_url
from roost.keeper.app import create_app
from roost.keeper.browsers import BraveLauncher
from roost.keeper.workspaces import WorkspaceManager, _RunOutcome
```

with:

```python
from roost.desk.client import KeeperClient, KeeperDesk, _connect_page, _relay_url
from roost.desk.url_policy import UrlBlocked
from roost.keeper.app import create_app
from roost.keeper.browsers import BraveLauncher
from roost.keeper.main_browser import MainBrowserOpener
from roost.keeper.workspaces import WorkspaceManager, _RunOutcome
```

Then append this to the end of `tests/test_keeper_client.py`:

```python


# -- Stuck flow (Task 6): open in your main Brave --


class _FakeOpenRunner:
    """Stands in for ``/usr/bin/open`` behind the real keeper app. It records
    each argv and answers ``exit_code``. It never runs anything."""

    def __init__(self, exit_code: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._exit_code = exit_code

    async def __call__(self, argv, timeout_s):
        self.calls.append(list(argv))
        return self._exit_code


async def test_open_in_main_browser_opens_the_address_through_the_real_keeper(
    config: RoostConfig, keeper_app, transport: httpx.ASGITransport
) -> None:
    opener = _FakeOpenRunner()
    keeper_app.state.main_browser = MainBrowserOpener(runner=opener)
    client = KeeperClient(config, transport=transport)

    assert await client.open_in_main_browser(_BOT_ID, "https://example.com/") is None
    assert opener.calls == [["/usr/bin/open", "-a", "Brave Browser", "https://example.com/"]]


async def test_open_in_main_browser_refused_address_is_url_blocked_not_desk_unavailable(
    config: RoostConfig, keeper_app, transport: httpx.ASGITransport
) -> None:
    opener = _FakeOpenRunner()
    keeper_app.state.main_browser = MainBrowserOpener(runner=opener)
    client = KeeperClient(config, transport=transport)

    with pytest.raises(UrlBlocked):
        await client.open_in_main_browser(_BOT_ID, "javascript:alert(1)")
    assert opener.calls == []


async def test_open_in_main_browser_failure_is_desk_unavailable(
    config: RoostConfig, keeper_app, transport: httpx.ASGITransport
) -> None:
    keeper_app.state.main_browser = MainBrowserOpener(runner=_FakeOpenRunner(exit_code=1))
    client = KeeperClient(config, transport=transport)

    with pytest.raises(DeskUnavailable):
        await client.open_in_main_browser(_BOT_ID, "https://example.com/")


async def test_open_in_main_browser_with_the_keeper_down_is_desk_unavailable(config: RoostConfig) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = KeeperClient(config, transport=httpx.MockTransport(handler))
    with pytest.raises(DeskUnavailable):
        await client.open_in_main_browser(_BOT_ID, "https://example.com/")


async def test_a_400_from_any_other_keeper_call_is_still_desk_unavailable(config: RoostConfig) -> None:
    """``refused_on_bad_request`` is opt-in: only ``open_in_main_browser`` turns a 400 into ``UrlBlocked``."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bot_id must be a UUID4"})

    client = KeeperClient(config, transport=httpx.MockTransport(handler))
    with pytest.raises(DeskUnavailable):
        await client.get_desk(_BOT_ID)
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_keeper_main_browser.py tests/test_main_browser_seam.py tests/test_keeper_client.py -q`
Expected: FAIL with three collection errors:
- `tests/test_keeper_main_browser.py` and `tests/test_keeper_client.py`: `ModuleNotFoundError: No module named 'roost.keeper.main_browser'`.
- `tests/test_main_browser_seam.py`: `ModuleNotFoundError: No module named 'roost.desk.main_browser'`.

The existing tests in `tests/test_keeper_client.py` error too until Step 5, because the file's imports fail.

- [ ] **Step 4: Check the constants (Task 1 added them)**

Run: `grep -n "^MAIN_BROWSER_" /Users/blckit/Desktop/Code_Projects/roost/roost/constants.py`
Expected: exactly these three lines (any line numbers), which Task 1 put at the end of the "Stuck flow (Piece A) — roost/desk/stuck.py, roost/stuck/" section:

```python
MAIN_BROWSER_OPEN_ARGV = ("/usr/bin/open", "-a", "Brave Browser")
MAIN_BROWSER_OPEN_TIMEOUT_S = 10.0
MAIN_BROWSER_URL_MAX_CHARS = 2048
```

If any is missing or different, Task 1 has not landed as planned: stop and report it. Do not add or change them here, so the constants keep one owner. This task does not edit `roost/constants.py`.

- [ ] **Step 5: Implement the opener (`roost/keeper/main_browser.py`)**

Create `roost/keeper/main_browser.py`:

```python
"""Open in your main Brave: the keeper side (stuck flow, piece A; design §3,
D-A3/D-A4, R8).

This is the keeper's only action on the user's own Brave. It runs the fixed argv
``MAIN_BROWSER_OPEN_ARGV + (url,)`` (``/usr/bin/open -a "Brave Browser" <url>``)
as an argument list, never through a shell. There is no debug port, no profile
access and no automation. ``open`` hands the address to Launch Services, and
Brave opens it in a tab like any link the user clicked.

The address that reaches ``MainBrowserOpener.open`` has already passed
``check_url`` in the route (``roost/keeper/app.py``). So it is always an
``http``/``https`` URL, and it can never start with ``-`` and be read by
``open`` as a flag.

``runner`` is injectable, the same pattern as ``roost.keeper.workspaces.Runner``.
Tests can then assert on the exact argv and never launch a real browser.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Awaitable, Callable, Sequence

from roost.constants import MAIN_BROWSER_OPEN_ARGV, MAIN_BROWSER_OPEN_TIMEOUT_S


class MainBrowserOpenError(RuntimeError):
    """Raised when ``open`` could not start, timed out or exited non-zero. The route answers a
    fixed 500 ``"failed to open the main browser"``. The message never carries the address."""


# (argv, timeout in seconds) -> the process's exit code. Raises
# asyncio.TimeoutError on a timeout, and OSError when the process can't start.
Runner = Callable[[Sequence[str], float], Awaitable[int]]


async def _run_open(argv: Sequence[str], timeout_s: float) -> int:
    """The real runner. It runs an argv list (no shell), discards the output, and kills the process on a timeout."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        return await asyncio.wait_for(proc.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        raise


class MainBrowserOpener:
    """Opens one checked address in the user's own Brave. ``create_app`` builds one, as
    ``app.state.main_browser``. Tests replace it with one that has a fake ``runner``."""

    def __init__(self, *, runner: Runner | None = None) -> None:
        self._run: Runner = runner if runner is not None else _run_open

    async def open(self, url: str) -> None:
        argv = (*MAIN_BROWSER_OPEN_ARGV, url)
        try:
            exit_code = await self._run(argv, MAIN_BROWSER_OPEN_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            raise MainBrowserOpenError(f"open did not finish within {MAIN_BROWSER_OPEN_TIMEOUT_S} s") from exc
        except OSError as exc:
            raise MainBrowserOpenError(f"open could not start: {exc.strerror or type(exc).__name__}") from exc
        if exit_code != 0:
            raise MainBrowserOpenError(f"open exited with code {exit_code}")
```

- [ ] **Step 6: Implement the keeper route (`roost/keeper/app.py`)**

1. Module docstring. Replace these lines:

```python
field). The browser lifecycle, the workspace container lifecycle
(``roost/keeper/workspaces.py``) and ``DELETE /desks/{bot_id}`` (retire
both at once) all land here.
```

with:

```python
field). The browser lifecycle, the workspace container lifecycle
(``roost/keeper/workspaces.py``), ``DELETE /desks/{bot_id}`` (retire
both at once) and ``POST /desks/{bot_id}/main-browser/open`` all land
here. That last route is the stuck flow's "Use my main Brave": it runs
``/usr/bin/open -a "Brave Browser" <url>`` for one checked address and
nothing more (``roost/keeper/main_browser.py``).
```

2. Imports. Replace these lines:

```python
from roost.config import RoostConfig
from roost.desk.signing import NonceCache
from roost.keeper.audit import AuditLog
from roost.keeper.auth import require_signed_body
from roost.keeper.browsers import BraveLauncher, BrowserStartError
from roost.keeper.paths import desk_dir
```

with:

```python
from roost.config import RoostConfig
from roost.constants import MAIN_BROWSER_URL_MAX_CHARS
from roost.desk.signing import NonceCache
from roost.desk.url_policy import UrlBlocked, check_url
from roost.keeper.audit import AuditLog
from roost.keeper.auth import require_signed_body
from roost.keeper.browsers import BraveLauncher, BrowserStartError
from roost.keeper.main_browser import MainBrowserOpener, MainBrowserOpenError
from roost.keeper.paths import desk_dir
```

3. Fixed texts. Replace this line:

```python
_BAD_BOT_ID_DETAIL = "bot_id must be a UUID4"
```

with:

```python
_BAD_BOT_ID_DETAIL = "bot_id must be a UUID4"

# POST /desks/{bot_id}/main-browser/open (stuck flow, Task 6). Neither text,
# nor anything else this route answers or audits, ever carries the address.
_MAIN_BROWSER_OPEN_ACTION = "main_browser_open"
_URL_REFUSED_DETAIL = "that address can't be opened"
_MAIN_BROWSER_FAILED_DETAIL = "failed to open the main browser"
```

4. The body model. Replace these lines:

```python
    argv: list[str] = Field(min_length=1)
    timeout_s: int = Field(ge=1, le=120)
```

with:

```python
    argv: list[str] = Field(min_length=1)
    timeout_s: int = Field(ge=1, le=120)


class _MainBrowserOpenBody(BaseModel):
    """``POST /desks/{bot_id}/main-browser/open``'s body, exactly one address.
    ``extra="forbid"`` turns a smuggled ``app`` or ``args`` field into a 422,
    so nothing but the checked address ever reaches ``open``'s argv."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=MAIN_BROWSER_URL_MAX_CHARS)
```

5. The parser and the handler body. Replace these lines:

```python
def _parse_workspace_exec_body(body: bytes) -> _WorkspaceExecBody:
    try:
        return _WorkspaceExecBody.model_validate_json(body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
```

with:

```python
def _parse_workspace_exec_body(body: bytes) -> _WorkspaceExecBody:
    try:
        return _WorkspaceExecBody.model_validate_json(body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _parse_main_browser_open_body(body: bytes) -> _MainBrowserOpenBody:
    """Like ``_parse_workspace_exec_body``, except the 422 detail never echoes the input.
    A rejected body may still carry the address, and ``KeeperClient`` puts a non-2xx
    response's text into its ``DeskUnavailable`` message."""
    try:
        return _MainBrowserOpenBody.model_validate_json(body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_input=False, include_url=False)) from exc


async def _open_in_main_browser(app: FastAPI, bot_id: str, body: bytes) -> dict[str, bool]:
    """Stuck flow (design §3, R8): open one checked address in the user's own Brave.

    The order is bot id (400), body (422), ``check_url`` (400, audited
    ``refused``), then the opener (500, audited ``error``). The canonical URL
    ``check_url`` returns is what is opened, never the raw input. The audit
    line holds only the action, the bot id and the result."""
    _require_valid_bot_id(bot_id)
    open_body = _parse_main_browser_open_body(body)
    try:
        checked_url = check_url(open_body.url)
    except UrlBlocked as exc:
        app.state.audit.record(_MAIN_BROWSER_OPEN_ACTION, bot_id, "refused")
        raise HTTPException(status_code=400, detail=_URL_REFUSED_DETAIL) from exc
    try:
        await app.state.main_browser.open(checked_url)
    except MainBrowserOpenError as exc:
        app.state.audit.record(_MAIN_BROWSER_OPEN_ACTION, bot_id, "error")
        raise HTTPException(status_code=500, detail=_MAIN_BROWSER_FAILED_DETAIL) from exc
    app.state.audit.record(_MAIN_BROWSER_OPEN_ACTION, bot_id, "ok")
    return {"opened": True}
```

6. App state. Replace this line:

```python
    app.state.relays = RelayRegistry()
```

with:

```python
    app.state.relays = RelayRegistry()
    app.state.main_browser = MainBrowserOpener()
```

7. The route. Replace these lines:

```python
    @app.delete("/desks/{bot_id}")
    async def retire_desk(bot_id: str, body: bytes = Depends(require_signed_body)):
```

with:

```python
    @app.post("/desks/{bot_id}/main-browser/open")
    async def open_main_browser(bot_id: str, body: bytes = Depends(require_signed_body)):
        """Stuck flow: "Use my main Brave" (see ``_open_in_main_browser``)."""
        return await _open_in_main_browser(app, bot_id, body)

    @app.delete("/desks/{bot_id}")
    async def retire_desk(bot_id: str, body: bytes = Depends(require_signed_body)):
```

- [ ] **Step 7: Implement the client (`roost/desk/client.py`)**

1. Imports. Replace this line:

```python
from roost.desk.signing import signed_headers
```

with:

```python
from roost.desk.signing import signed_headers
from roost.desk.url_policy import UrlBlocked
```

2. `_request`'s signature. Replace these lines:

```python
    async def _request(
        self, method: str, path: str, body: bytes = b"", *, timeout: float = _CONTROL_REQUEST_TIMEOUT_S,
        asleep_on_conflict: bool = False,
    ) -> dict[str, Any]:
```

with:

```python
    async def _request(
        self, method: str, path: str, body: bytes = b"", *, timeout: float = _CONTROL_REQUEST_TIMEOUT_S,
        asleep_on_conflict: bool = False, refused_on_bad_request: bool = False,
    ) -> dict[str, Any]:
```

3. The 400 check. Replace these lines:

```python
        if asleep_on_conflict and response.status_code == 409:
            raise DeskAsleep(f"the browser of {path} is closed")
```

with:

```python
        if asleep_on_conflict and response.status_code == 409:
            raise DeskAsleep(f"the browser of {path} is closed")
        if refused_on_bad_request and response.status_code == 400:
            # Stuck flow (Task 6): the keeper's check_url refused the address. That is
            # the user's 400 ("That address can't be opened."), not a down desk's 503.
            raise UrlBlocked(f"the keeper refused the address sent to {method} {path}")
```

4. The new method. Replace these lines:

```python
    async def attach_browser(self, bot_id: str) -> dict[str, Any]:
        """The running browser's relay token. Never starts it: 409 → ``DeskAsleep`` (S1.8)."""
        return await self._request("POST", f"/desks/{bot_id}/browser/attach", asleep_on_conflict=True)
```

with:

```python
    async def attach_browser(self, bot_id: str) -> dict[str, Any]:
        """The running browser's relay token. Never starts it: 409 → ``DeskAsleep`` (S1.8)."""
        return await self._request("POST", f"/desks/{bot_id}/browser/attach", asleep_on_conflict=True)

    async def open_in_main_browser(self, bot_id: str, url: str) -> None:
        """Stuck flow (Task 6): the keeper opens ``url`` in the user's own Brave.

        A refused address raises ``UrlBlocked``. An unreachable keeper or a failed
        open raises ``DeskUnavailable``. The keeper's own ``MAIN_BROWSER_OPEN_TIMEOUT_S``
        (10 s) runs out before this call's 15 s request timeout."""
        body = json.dumps({"url": url}).encode()
        await self._request(
            "POST", f"/desks/{bot_id}/main-browser/open", body=body, refused_on_bad_request=True
        )
```

- [ ] **Step 8: Implement the gateway seam (`roost/desk/main_browser.py`)**

Create `roost/desk/main_browser.py`:

```python
"""Open in your main Brave: the gateway's seam (stuck flow, Task 6; design §3, R8).

The gateway never runs ``open`` itself. ``make_main_browser`` builds what Task 7
puts on ``app.state.main_browser``, chosen by ``config.desk_mode`` the way
``DeskFactory`` chooses a desk:

- ``KeeperMainBrowser`` (keeper mode) sends the keeper's signed
  ``POST /desks/{bot_id}/main-browser/open`` through ``KeeperClient``. A refused
  address raises ``UrlBlocked``, and a down keeper or a failed open raises
  ``DeskUnavailable``.
- ``FakeMainBrowser`` (fake mode: every test and E2E run) never reaches a keeper
  or a browser. It checks the address the way the keeper does and records
  ``(bot_id, checked_url)``.

Both refuse an address longer than ``MAIN_BROWSER_URL_MAX_CHARS`` as ``UrlBlocked``
first. The keeper answers such a body 422, and ``KeeperClient`` turns every non-2xx
except a 400 into ``DeskUnavailable``, which the user would see as a 503.
"""

from __future__ import annotations

from typing import Protocol

from roost.config import RoostConfig
from roost.constants import MAIN_BROWSER_URL_MAX_CHARS
from roost.desk import DeskUnavailable
from roost.desk.client import KeeperClient
from roost.desk.url_policy import UrlBlocked, check_url


class MainBrowser(Protocol):
    async def open(self, bot_id: str, url: str) -> None: ...


def _refuse_overlong(url: str) -> None:
    """The keeper's body limit, applied before the request so it stays a refusal (400), not a 503."""
    if len(url) > MAIN_BROWSER_URL_MAX_CHARS:
        raise UrlBlocked(f"the address is longer than {MAIN_BROWSER_URL_MAX_CHARS} characters")


class KeeperMainBrowser:
    """The real seam: ``KeeperClient(config).open_in_main_browser``. Tests pass a ``client``
    built on an ``httpx`` transport that reaches the keeper app in process."""

    def __init__(self, config: RoostConfig, *, client: KeeperClient | None = None) -> None:
        self._client = client if client is not None else KeeperClient(config)

    async def open(self, bot_id: str, url: str) -> None:
        _refuse_overlong(url)
        await self._client.open_in_main_browser(bot_id, url)


class FakeMainBrowser:
    """Records every open, and opens nothing.

    ``opened`` is a tuple of ``(bot_id, checked_url)``. It is reassigned on every
    open and never mutated, so a reference taken earlier keeps its old value.
    ``fail`` makes every open raise ``DeskUnavailable``. Tests set it either as the
    keyword or as the attribute, which they flip through ``app.state`` the way
    they flip ``FakeDesk.force_unavailable``."""

    def __init__(self, *, fail: bool = False) -> None:
        self.opened: tuple[tuple[str, str], ...] = ()
        self.fail = fail

    async def open(self, bot_id: str, url: str) -> None:
        if self.fail:
            raise DeskUnavailable(f"the main browser is unavailable for bot {bot_id}")
        _refuse_overlong(url)
        checked_url = check_url(url)
        self.opened = (*self.opened, (bot_id, checked_url))


def make_main_browser(config: RoostConfig) -> MainBrowser:
    """``app.state.main_browser`` (wired by Task 7): the fake in fake mode, the keeper otherwise."""
    if config.desk_mode == "fake":
        return FakeMainBrowser()
    return KeeperMainBrowser(config)
```

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_keeper_main_browser.py tests/test_main_browser_seam.py tests/test_keeper_client.py tests/test_keeper_auth.py tests/test_workspace_spec.py tests/test_desk_api.py tests/test_fake_desk.py tests/test_url_policy.py -q`
Expected: PASS. `test_keeper_auth.py`, `test_workspace_spec.py` and `test_url_policy.py` cover the keeper app and `check_url`, which this task reuses unchanged. `test_desk_api.py` and `test_fake_desk.py` cover the desk facade next to the new seam.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_keeper_main_browser.py tests/test_main_browser_seam.py tests/test_keeper_client.py --cov=roost.keeper.main_browser --cov=roost.desk.main_browser --cov-report=term-missing -q`
Expected: PASS. Both new modules show 100% line coverage, or at least 95%: only the Protocol's `...` line may be reported as missed.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/keeper/main_browser.py roost/keeper/app.py roost/desk/client.py \
  roost/desk/main_browser.py tests/test_keeper_main_browser.py tests/test_main_browser_seam.py \
  tests/test_keeper_client.py
git commit -m "feat: open a stuck page in your main Brave through the keeper"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the seven files above is still listed as modified or untracked.

---

### Task 7: The card's buttons: StuckService and /api/stuck

Design §2 "The card's buttons", R6, R8, R9 and R10. Task 5 opens Stuck cards. This task gives them their buttons:
- `GET /api/stuck` lists your open cards, newest first. Home's My turn and the chat's card read it (Task 8).
- `POST /api/stuck/{id}/clear` is behind Give it back, Try again and Done, carry on (R10). The steps run in the contract's exact order:
  1. Make the continue item's id.
  2. Close the card as `cleared` with that `answer_item_id`. Exactly one press wins: a second press, from a double click or another tab, gets 409 and queues nothing (Review Focus 3).
  3. Release any control hold. `ControlLock.give_back` is idempotent, so this works after a restart that already dropped the hold (Review Focus 5).
  4. Post your `role="user"`, `kind="card_answer"` line with `continue_text(card)`. The model reads the chat, never an item's body (R6).
  5. Queue the `card_answer` work item: `origin=ORIGIN_CARD`, the card's taint, `link_scope=(card.url,)`.
  6. Publish the `stuck_card` frame.
  7. Settle the bot's status through `TurnRunner.settle` (R9).

  Step 5's `submit` has just kicked the bot's drain task, so `settle` waits for that task to end and settles then. When the continue run runs, that gives what it settled (Resting, or Stuck again on a new card). When it can't start, because the daily run cap is reached, no run settles anything, and without step 7 the bot would keep showing Stuck with no open card; with it, the bot rests and the item waits in its queue. An off-duty bot already shows Off duty, so it needs no fix.
- `POST /api/stuck/{id}/give-up` closes the card as `given_up`. It releases the hold, and the bot says `GIVE_UP_LINE`. It publishes the frame and settles the bot's status through `TurnRunner.settle`, so an idle bot rests at once and a bot whose run is ending rests when that run ends.
- `POST /api/stuck/{id}/open-in-main-browser` opens the card's address in your own Brave (piece A: open only, D-A3). The gateway checks the address itself first and answers 400 (R8), because `KeeperClient` would turn a keeper refusal it did not expect into a 503. `FakeMainBrowser` stands in for the keeper in every test. The card remembers `main_opened`, so the next Done, carry on says "I did this step in my own browser".
- Every route has `CurrentUser`, and every button has `RequireOrigin`. Another user's card id is a 404, never the card.

The tests drive the real app over `httpx.AsyncClient` on the test's own event loop, not `TestClient`. `/clear` starts the bot's drain task, and `wait_idle` has to see that task finish before the test ends.

**Files:**
- Create:
  - `roost/stuck/service.py`: `StuckService`.
  - `roost/gateway/routes/stuck.py`: `stuck_router` and the four routes.
  - `tests/test_stuck_api.py`
- Modify:
  - `roost/gateway/app.py`:
    - three imports;
    - `app.state.main_browser = make_main_browser(resolved_config)` and `app.state.stuck_service = StuckService(...)`, both after `turns`;
    - `app.include_router(stuck_router)` before the static mount.
- Test: `tests/test_stuck_api.py` (new)

**Interfaces:**
- Consumes:
  - Task 1: `Block(reason, url, host, note="", suggest_main_browser=False)` and `host_of_url(url)` from `roost.desk.stuck`, and `PageText(..., status=...)`.
  - Task 2: `FakeDesk.serve(url: str, *pages: PageText) -> None`. Each `open_page` or `read_page` of a served URL returns its next page, and the last one repeats.
  - Task 3:
    - `CardState`, `CardDraft`, `StuckCard`, `StuckCardOut`, `stuck_card_out`, `CardClosed` and `NoAddress` (`roost.stuck.models`).
    - `StuckStore(config)`, with `open`, `get`, `list_open`, `close(user_id, card_id, state, *, answer_item_id=None)` and `mark_main_opened` (`roost.stuck.store`).
    - `GIVE_UP_LINE` and `continue_text(card)` (`roost.stuck.texts`).
    - `publish_card(events, user_id, card)` and `post_bot_line(talk, events, user_id, card, body, *, kind)` (`roost.stuck.announce`).
  - Task 4: `roost.talk.tool_runner.STUCK_CHALLENGE_WAIT_SECONDS`, which the end-to-end test patches, and rung 1, which repeats `open_page(url)` once.
  - Task 5:
    - `TurnRunner(..., stuck: StuckStore | None = None)` and `async TurnRunner.settle(user_id, bot_id)`, which settles at once when the bot has no drain task running and otherwise once that task ends (a done-callback).
    - `DAILY_RUN_CAP`, read by name in `roost.talk.runner` (`_next_batch`), which the cap test patches.
    - `tests/team_helpers.wait_idle`, which also waits for the settles that run after a drain task ends.
    - `ORIGIN_CARD = "you, after a Stuck card"`.
    - `MessageKind` gains `"stuck"` and `"card_answer"`, and `_MODEL_KINDS` contains `"card_answer"`.
    - `app.state.stuck`: the one `StuckStore` that `create_app` hands `TurnRunner`.
    - The run that leaves a card: the `kind="stuck"` bot message, the `stuck_card` frame and the Stuck status.
  - Task 6: `MainBrowser` (Protocol), `FakeMainBrowser` (`opened: tuple[tuple[str, str], ...]`, public `fail`) and `make_main_browser(config)` (`roost.desk.main_browser`).
  - Existing code:
    - `check_url` and `UrlBlocked` (`roost.desk.url_policy`), and `DeskUnavailable` (`roost.desk`);
    - `ControlLock.give_back`;
    - `TalkStore.add_message`, `message_out` and `EventHub.publish`;
    - `WorkDraft`, `WorkKind.CARD_ANSWER`, `TurnRunner.submit(..., item_id=)` and `WorkQueue.get`;
    - `CurrentUser` and `RequireOrigin` (`roost.gateway.deps`).
- Produces (Task 8's web client and Task 9's E2E rely on these):
  - `roost.stuck.service.StuckService(store, talk, events, turns, control, main_browser)`, with these methods:
    - `list_open(user_id) -> tuple[StuckCard, ...]`;
    - `clear(user_id, card_id) -> StuckCard | None`;
    - `give_up(user_id, card_id) -> StuckCard | None`;
    - `open_in_main_browser(user_id, card_id) -> StuckCard | None`.
  - `roost.gateway.routes.stuck.stuck_router` and its routes:
    - `GET /api/stuck` → 200 `StuckCardOut[]`.
    - `POST /api/stuck/{card_id}/clear` → 200 `StuckCardOut`, 404 `"Card not found"` or 409 `"This card is already closed."`.
    - `POST /api/stuck/{card_id}/give-up` → 200 `StuckCardOut`, 404 or 409.
    - `POST /api/stuck/{card_id}/open-in-main-browser` → 200 `StuckCardOut`, 404, 409, 400 `"This card has no web address."` / `"That address can't be opened."`, or 503 `"desk unavailable"`.
  - `app.state.main_browser` and `app.state.stuck_service`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_stuck_api.py`:

```python
"""The Stuck card's buttons over HTTP (stuck flow, Task 7; design §2, R6, R8–R10).

``GET /api/stuck`` lists your open cards. ``/clear`` (Give it back, Try again,
Done, carry on) posts your continue line and queues a ``card_answer`` item.
``/give-up`` ends the task. Both settle the bot's status. ``/open-in-main-browser`` opens the card's address
in your own Brave through ``app.state.main_browser``. Here that is always
``FakeMainBrowser``: no test opens a real browser.

These tests use ``httpx.AsyncClient`` on the test's own event loop, not
``TestClient``. ``/clear`` starts the bot's drain task, and ``wait_idle`` must
see it finish before the test ends.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest

import roost.talk.runner as runner_module
import roost.talk.tool_runner as tool_runner_module
from roost.bots.models import BotStatus
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.desk import PageText
from roost.desk.main_browser import FakeMainBrowser
from roost.desk.stuck import Block, host_of_url
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.stuck.models import CardClosed, CardDraft, CardState, StuckCard
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
from roost.stuck.texts import GIVE_UP_LINE
from roost.talk.runner import TurnRunner
from roost.talk.store import Message, TalkStore
from roost.work.models import ORIGIN_CARD, WorkKind, WorkState
from roost.work.queue import WorkQueue
from team_helpers import make_bot, say, team_model, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}
PASSWORD = "pw-123456"
SHOP_URL = "https://shop.example/kettle"
REQUEST = "Find the price of the blue kettle"
CLOSED = {"detail": "This card is already closed."}
NOT_FOUND = {"detail": "Card not found"}
BUTTONS = ("clear", "give-up", "open-in-main-browser")
CARD_FIELDS = {"id", "bot_id", "thread_id", "reason", "host", "url", "note", "suggest_main_browser", "tainted",
               "main_opened", "state", "created_at", "closed_at"}

CHALLENGE = PageText(url=SHOP_URL, title="Just a moment...", text="Checking your browser before you reach the shop.",
                     truncated=False, status=403)
CLEARED = PageText(url=SHOP_URL, title="Blue kettle", text="Blue kettle, 1.7 litres: 25 EUR. In stock.",
                   truncated=False, status=200)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def alice(cfg):
    return await register_user(cfg, "alice", PASSWORD)


@asynccontextmanager
async def _signed_in(app, username: str) -> AsyncIterator[httpx.AsyncClient]:
    """``username`` logged in over HTTP. On the way out, every drain task the requests started has finished."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        login = await client.post("/api/auth/login", json={"username": username, "password": PASSWORD}, headers=O)
        assert login.status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


async def _card(cfg, user_id: str, bot_id: str, *, url: str = SHOP_URL, reason: str = "challenge",
                note: str = "", tainted: bool = True) -> StuckCard:
    """An open Stuck card in a new chat with ``bot_id``, the way Task 5's run leaves one."""
    thread = await TalkStore(cfg).create_thread(user_id, bot_id)
    block = Block(reason=reason, url=url, host=host_of_url(url), note=note)
    return await StuckStore(cfg).open(user_id, CardDraft(
        bot_id=bot_id, thread_id=thread.id, work_item_id=None, block=block, request=REQUEST, tainted=tainted,
    ))


async def _frames(app, user_id: str, frame_type: str) -> list[dict]:
    return [frame for frame in await app.state.events.since(user_id, 0) if frame["type"] == frame_type]


async def _continue_items(cfg, user_id: str) -> int:
    async with db_session(cfg) as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM work_items WHERE user_id = ? AND kind = 'card_answer'", (user_id,),
        )).fetchone()
    return row[0]


async def _lines(app, user_id: str, card: StuckCard, kind: str) -> list[Message]:
    return [m for m in await app.state.talk.list_messages(user_id, card.thread_id) if m.kind == kind]


def _service_with(app, store: StuckStore, main_browser) -> StuckService:
    return StuckService(store, app.state.talk, app.state.events, app.state.turns, app.state.control, main_browser)


def _use_model(app, model) -> TurnRunner:
    """Drain with a scripted model. The service is rebuilt on the new runner, so
    ``/clear`` queues its continue item on the runner that runs it."""
    turns = TurnRunner(
        app.state.config, app.state.bots, app.state.talk, app.state.events, app.state.desks, model,
        app.state.activity_board, rooms=app.state.rooms, control=app.state.control, stuck=app.state.stuck,
    )
    app.state.turns = turns
    app.state.stuck_service = _service_with(app, app.state.stuck, app.state.main_browser)
    return turns


def _open_shop():
    return [ToolCallRequested(id="open-shop", name="open_page", arguments={"url": SHOP_URL}), TurnDone("tool_use")]


def _read_again():
    return [ToolCallRequested(id="read-again", name="read_page", arguments={}), TurnDone("tool_use")]


class _ReadBeforeTheOtherPress(StuckStore):
    """``get`` answers the card as this press read it, just before another press closed it."""

    def __init__(self, config, snapshot: StuckCard) -> None:
        super().__init__(config)
        self._snapshot = snapshot

    async def get(self, user_id: str, card_id: str) -> StuckCard | None:
        return self._snapshot


class _GivenUpWhileOpening:
    """A main Brave that is slow enough for the card to be given up in another tab while it opens."""

    def __init__(self, store: StuckStore, user_id: str, card_id: str) -> None:
        self._store = store
        self._user_id = user_id
        self._card_id = card_id
        self.opened: tuple[tuple[str, str], ...] = ()

    async def open(self, bot_id: str, url: str) -> None:
        self.opened = (*self.opened, (bot_id, url))
        await self._store.close(self._user_id, self._card_id, CardState.GIVEN_UP)


def test_the_gateway_wires_the_stuck_routes_and_a_fake_main_browser():
    app = create_app()
    assert isinstance(app.state.main_browser, FakeMainBrowser)          # ROOST_DESK=fake: no keeper, no real Brave
    assert isinstance(app.state.stuck_service, StuckService)
    assert {"/api/stuck", "/api/stuck/{card_id}/clear", "/api/stuck/{card_id}/give-up",
            "/api/stuck/{card_id}/open-in-main-browser"} <= {route.path for route in app.routes}


async def test_the_list_holds_only_your_open_cards_newest_first(cfg, alice):
    app = create_app()
    bob = await register_user(cfg, "bob", PASSWORD)
    helper, scout, quill = [await make_bot(cfg, alice.id, name) for name in ("Helper", "Scout", "Quill")]
    older = await _card(cfg, alice.id, helper.id)
    newer = await _card(cfg, alice.id, scout.id, reason="login")
    stopped = await _card(cfg, alice.id, quill.id)
    await StuckStore(cfg).close(alice.id, stopped.id, CardState.GIVEN_UP)
    await _card(cfg, bob.id, (await make_bot(cfg, bob.id, "Helper")).id)
    async with _signed_in(app, "alice") as client:
        listed = (await client.get("/api/stuck")).json()
    assert [card["id"] for card in listed] == [newer.id, older.id]
    assert set(listed[0]) == CARD_FIELDS                                  # no user_id, no request
    assert (listed[0]["reason"], listed[0]["host"], listed[0]["url"], listed[0]["state"]) == (
        "login", "shop.example", SHOP_URL, "open")


async def test_clear_queues_the_continue_item_and_gives_the_computer_back(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    app.state.control.take(bot.id)                                        # the user took control from the card
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert r.status_code == 200
    assert (r.json()["id"], r.json()["state"]) == (card.id, "cleared") and r.json()["closed_at"]
    assert app.state.control.held(bot.id) is None
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert (line.role, line.tainted, line.author_bot_id) == ("user", True, None)
    assert line.body == f"I cleared the block on shop.example. Read the page again and carry on with: {REQUEST}"
    stored = await StuckStore(cfg).get(alice.id, card.id)
    item = await WorkQueue(cfg).get(alice.id, stored.answer_item_id)
    assert (item.kind, item.origin, item.body, item.tainted) == (WorkKind.CARD_ANSWER, ORIGIN_CARD, line.body, True)
    assert (item.bot_id, item.thread_id, item.message_id, item.link_scope) == (
        bot.id, card.thread_id, line.id, (SHOP_URL,))
    assert (item.depth, item.parent_item_id) == (0, None)                 # not a handoff
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["cleared"]
    assert "card_answer" in [f["message"]["kind"] for f in await _frames(app, alice.id, "message")]


async def test_clearing_twice_queues_one_continue_item(cfg, alice):
    """Review Focus 3: Give it back pressed twice, by a double click or from two tabs."""
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        presses = await asyncio.gather(*(client.post(f"/api/stuck/{card.id}/clear", headers=O) for _ in range(2)))
        late = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert sorted(r.status_code for r in presses) == [200, 409]
    assert [r.json() for r in presses if r.status_code == 409] == [CLOSED]
    assert (late.status_code, late.json()) == (409, CLOSED)
    assert await _continue_items(cfg, alice.id) == 1
    assert len(await _lines(app, alice.id, card, "card_answer")) == 1
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["cleared"]


async def test_clear_works_with_no_control_hold(cfg, alice):
    """Review Focus 5: a restart forgets every hold, because ControlLock lives in
    memory, but the card is in the database. The restarted gateway holds nothing,
    and Give it back on the card still works."""
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    app = create_app()                                                    # the gateway after the restart
    assert app.state.control.held(bot.id) is None
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert (r.status_code, r.json()["state"]) == (200, "cleared")
    assert await _continue_items(cfg, alice.id) == 1
    assert app.state.control.held(bot.id) is None


async def test_clear_when_the_bot_cannot_run_does_not_leave_it_stuck(cfg, alice, monkeypatch):
    """R9: ``/clear`` settles the status. Here the continue run can't start (the
    daily run cap is reached), so no run settles it: without that settle the bot
    would keep showing Stuck with no open card. The continue item waits."""
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 0)
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    await app.state.bots.set_status(alice.id, bot.id, BotStatus.STUCK)       # the run that left the card did this
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert (r.status_code, r.json()["state"]) == (200, "cleared")
    assert (await app.state.bots.get(alice.id, bot.id)).status is BotStatus.RESTING
    assert [f["status"] for f in await _frames(app, alice.id, "bot_status")] == ["resting"]
    item = await WorkQueue(cfg).get(alice.id, (await StuckStore(cfg).get(alice.id, card.id)).answer_item_id)
    assert item.state is WorkState.QUEUED                                    # it runs after midnight
    assert "daily_limit" in [m.kind for m in await app.state.talk.list_messages(alice.id, card.thread_id)]


async def test_a_press_that_loses_the_race_posts_and_queues_nothing(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    await StuckStore(cfg).close(alice.id, card.id, CardState.CLEARED)    # the other tab's press landed first
    service = _service_with(app, _ReadBeforeTheOtherPress(cfg, card), app.state.main_browser)
    with pytest.raises(CardClosed):
        await service.clear(alice.id, card.id)
    with pytest.raises(CardClosed):
        await service.give_up(alice.id, card.id)
    assert await _continue_items(cfg, alice.id) == 0
    assert await app.state.talk.list_messages(alice.id, card.thread_id) == []
    assert await _frames(app, alice.id, "stuck_card") == []


async def test_give_up_stops_the_task_and_the_bot_rests(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    await app.state.bots.set_status(alice.id, bot.id, BotStatus.STUCK)
    app.state.control.take(bot.id)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/give-up", headers=O)
        after = [await client.post(f"/api/stuck/{card.id}/{button}", headers=O) for button in BUTTONS]
    assert (r.status_code, r.json()["state"]) == (200, "given_up") and r.json()["closed_at"]
    assert [(a.status_code, a.json()) for a in after] == [(409, CLOSED)] * 3
    [line] = [m for m in await app.state.talk.list_messages(alice.id, card.thread_id) if m.role == "bot"]
    assert (line.body, line.kind, line.author_bot_id, line.tainted) == (GIVE_UP_LINE, "text", bot.id, True)
    assert GIVE_UP_LINE == "OK, I stopped that task."
    assert (await app.state.bots.get(alice.id, bot.id)).status is BotStatus.RESTING
    assert [f["status"] for f in await _frames(app, alice.id, "bot_status")] == ["resting"]
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["given_up"]
    assert app.state.control.held(bot.id) is None
    assert await _continue_items(cfg, alice.id) == 0
    assert app.state.main_browser.opened == ()


async def test_open_in_main_browser_opens_the_cards_address_and_marks_the_card(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, reason="login")
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        [listed] = (await client.get("/api/stuck")).json()
    assert r.status_code == 200
    assert (r.json()["main_opened"], r.json()["state"]) == (True, "open")
    assert app.state.main_browser.opened == ((bot.id, SHOP_URL),)
    assert listed["main_opened"] is True
    assert [f["card"]["main_opened"] for f in await _frames(app, alice.id, "stuck_card")] == [True]
    assert await _continue_items(cfg, alice.id) == 0                      # opening the page is not carrying on


async def test_done_after_the_main_brave_says_you_did_the_step(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, reason="login")
    async with _signed_in(app, "alice") as client:
        await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        r = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert (r.status_code, r.json()["state"], r.json()["main_opened"]) == (200, "cleared", True)
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert line.body == (
        f"I did this step in my own browser on shop.example. Read your page again and carry on with: {REQUEST}"
    )
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["open", "cleared"]


async def test_a_card_without_an_address_is_400_and_carries_on_without_a_link(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, url="", reason="asked", note="Approve the payment in your bank app")
    async with _signed_in(app, "alice") as client:
        refused = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        cleared = await client.post(f"/api/stuck/{card.id}/clear", headers=O)
    assert (refused.status_code, refused.json()) == (400, {"detail": "This card has no web address."})
    assert app.state.main_browser.opened == ()
    assert cleared.status_code == 200
    item = await WorkQueue(cfg).get(alice.id, (await StuckStore(cfg).get(alice.id, card.id)).answer_item_id)
    assert item.link_scope == ()
    assert item.body == f"I helped with: Approve the payment in your bank app. Carry on with: {REQUEST}"


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "file:///etc/passwd", "javascript:alert(1)"])
async def test_an_address_the_url_check_refuses_is_never_opened(cfg, alice, url):
    """Design §5: the gateway's own check refuses a home-network address, ``file:`` and ``javascript:``."""
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, url=url)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        [listed] = (await client.get("/api/stuck")).json()
    assert (r.status_code, r.json()) == (400, {"detail": "That address can't be opened."})
    assert app.state.main_browser.opened == ()
    assert (listed["main_opened"], listed["state"]) == (False, "open")
    assert await _frames(app, alice.id, "stuck_card") == []


async def test_an_unreachable_main_brave_is_503_and_leaves_the_card_unmarked(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    app.state.main_browser.fail = True                                    # the keeper is down
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/open-in-main-browser", headers=O)
        [listed] = (await client.get("/api/stuck")).json()
    assert (r.status_code, r.json()) == (503, {"detail": "desk unavailable"})
    assert (listed["main_opened"], listed["state"]) == (False, "open")


async def test_a_card_given_up_while_the_main_brave_opens_is_card_closed(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    store = StuckStore(cfg)
    racing = _GivenUpWhileOpening(store, alice.id, card.id)
    with pytest.raises(CardClosed):
        await _service_with(app, store, racing).open_in_main_browser(alice.id, card.id)
    assert racing.opened == ((bot.id, SHOP_URL),)
    assert (await store.get(alice.id, card.id)).main_opened is False
    assert await _frames(app, alice.id, "stuck_card") == []


async def test_another_users_card_is_404_on_every_route(cfg, alice):
    app = create_app()
    await register_user(cfg, "bob", PASSWORD)
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "bob") as as_bob:
        listed = (await as_bob.get("/api/stuck")).json()
        answers = [await as_bob.post(f"/api/stuck/{card.id}/{button}", headers=O) for button in BUTTONS]
        unknown = await as_bob.post("/api/stuck/not-a-card/clear", headers=O)
    assert listed == []
    assert [(a.status_code, a.json()) for a in answers] == [(404, NOT_FOUND)] * 3
    assert (unknown.status_code, unknown.json()) == (404, NOT_FOUND)
    assert (await StuckStore(cfg).get(alice.id, card.id)).state is CardState.OPEN
    assert app.state.main_browser.opened == ()
    assert await _continue_items(cfg, alice.id) == 0


async def test_the_buttons_need_an_origin_and_the_list_needs_a_login(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        bare = [await client.post(f"/api/stuck/{card.id}/{button}") for button in BUTTONS]
        foreign = [await client.post(f"/api/stuck/{card.id}/{button}", headers=BAD_O) for button in BUTTONS]
    assert [r.status_code for r in bare + foreign] == [403] * 6
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as nobody:
        assert (await nobody.get("/api/stuck")).status_code == 401
    assert (await StuckStore(cfg).get(alice.id, card.id)).state is CardState.OPEN
    assert app.state.main_browser.opened == ()


async def test_a_bot_stuck_on_a_check_carries_on_after_you_clear_it(cfg, alice, monkeypatch):
    """End to end: a challenge that stays leaves a card, Give it back clears it,
    and the continue run reads the cleared page and answers."""
    monkeypatch.setattr(tool_runner_module, "STUCK_CHALLENGE_WAIT_SECONDS", 0.01)
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    model = team_model({"Helper": [_open_shop(), _read_again(), say("The blue kettle costs 25 EUR.")]})
    turns = _use_model(app, model)
    # open_page, then rung 1's one repeat of it, then the continue run's read_page
    app.state.desks.for_bot(bot.id).serve(SHOP_URL, CHALLENGE, CHALLENGE, CLEARED)
    ask = f"{REQUEST} on {SHOP_URL}"
    async with _signed_in(app, "alice") as client:
        thread = (await client.post(f"/api/bots/{bot.id}/threads", json={}, headers=O)).json()
        await client.post(f"/api/threads/{thread['id']}/messages", json={"text": ask}, headers=O)
        await wait_idle(turns, timeout=8)
        [card] = (await client.get("/api/stuck")).json()
        stuck_status = (await app.state.bots.get(alice.id, bot.id)).status
        cleared = await client.post(f"/api/stuck/{card['id']}/clear", headers=O)
        await wait_idle(turns, timeout=8)
        left_open = (await client.get("/api/stuck")).json()
    assert (card["reason"], card["host"], card["url"], card["state"]) == ("challenge", "shop.example", SHOP_URL, "open")
    assert stuck_status is BotStatus.STUCK
    assert (cleared.status_code, cleared.json()["state"], left_open) == (200, "cleared", [])
    messages = await app.state.talk.list_messages(alice.id, thread["id"])
    assert [(m.role, m.kind) for m in messages] == [
        ("user", "text"), ("bot", "stuck"), ("user", "card_answer"), ("bot", "text"),
    ]
    continue_line, reply = messages[2], messages[3]
    assert continue_line.body == f"I cleared the block on shop.example. Read the page again and carry on with: {ask}"
    assert reply.body == "The blue kettle costs 25 EUR."
    assert len(model.requests) == 3                                       # 1 step until the block, 2 after Give it back
    assert continue_line.body in [t.text for t in model.requests[1].turns if t.role == "user"]
    assert any("25 EUR" in t.text for t in model.requests[2].turns if t.role == "tool")
    assert app.state.desks.for_bot(bot.id).open_page_calls == [SHOP_URL, SHOP_URL]
    assert [f["card"]["state"] for f in await _frames(app, alice.id, "stuck_card")] == ["open", "cleared"]
    assert (await app.state.bots.get(alice.id, bot.id)).status is BotStatus.RESTING
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_api.py -q`
Expected: FAIL. Collection stops at `ERROR collecting tests/test_stuck_api.py` with `ModuleNotFoundError: No module named 'roost.stuck.service'`. Once the service exists but the routes and wiring do not, the route tests fail with 404 for `/api/stuck`, and with `AttributeError: 'State' object has no attribute 'main_browser'`.

- [ ] **Step 4: Implement the service (`roost/stuck/service.py`)**

Create `roost/stuck/service.py`:

```python
"""``StuckService``: the Stuck card's buttons (stuck flow, Task 7; design §2, R6, R8–R10).

``TurnRunner`` opens cards (Task 5), and this service closes them. It is built
after ``turns`` on ``app.state.stuck_service``, the way ``RoomService`` is, so
the runner never needs the service and the two never import each other in a
circle.

- ``clear`` is behind Give it back, Try again and Done, carry on. The card
  becomes ``cleared``, any control hold is released, your ``card_answer`` line
  is posted, and a ``card_answer`` item continues the task in the same thread.
  The line is posted because the model reads the chat, never an item's body
  (R6). The item carries the card's taint and its address as link scope.
  Then the status settles (R9): once the continue run ends, or, when that run
  can't start (the daily run cap), as soon as the drain task gives up.
- ``give_up``: the card becomes ``given_up``, the bot says ``GIVE_UP_LINE``,
  and its status settles (Resting, or Off duty; while a run is going, once it ends).
- ``open_in_main_browser``: the address is checked here first (R8), then opened
  in your own Brave through ``MainBrowser``. The card remembers ``main_opened``.

Every state change publishes a ``stuck_card`` frame. ``CardClosed`` covers a
card that was already closed, and one that another press closed between this
press's read and its write (a double click, or two tabs). ``StuckStore.close``
only moves a card out of ``open``, so exactly one press wins.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from roost.desk import DeskUnavailable
from roost.desk.control import ControlLock
from roost.desk.main_browser import MainBrowser
from roost.desk.url_policy import check_url
from roost.events.hub import EventHub
from roost.stuck.announce import post_bot_line, publish_card
from roost.stuck.models import CardClosed, CardState, NoAddress, StuckCard
from roost.stuck.store import StuckStore
from roost.stuck.texts import GIVE_UP_LINE, continue_text
from roost.talk.runner import TurnRunner
from roost.talk.store import Message, TalkStore, message_out
from roost.work.models import ORIGIN_CARD, WorkDraft, WorkKind

logger = logging.getLogger(__name__)


class StuckService:
    def __init__(self, store: StuckStore, talk: TalkStore, events: EventHub, turns: TurnRunner,
                 control: ControlLock, main_browser: MainBrowser) -> None:
        self._store = store
        self._talk = talk
        self._events = events
        self._turns = turns
        self._control = control
        self._main_browser = main_browser

    async def list_open(self, user_id: str) -> tuple[StuckCard, ...]:
        return await self._store.list_open(user_id)

    async def clear(self, user_id: str, card_id: str) -> StuckCard | None:
        """Give it back: the bot carries on with the task. ``None`` when the card
        is not the user's; ``CardClosed`` when it is no longer open. The last
        step settles the status (R9), so a bot whose continue run can't start
        never keeps showing Stuck with no open card."""
        if await self._open_card(user_id, card_id) is None:
            return None
        item_id = str(uuid4())
        card = await self._close(user_id, card_id, CardState.CLEARED, answer_item_id=item_id)
        self._control.give_back(card.bot_id)
        text = continue_text(card)
        line = await self._post_continue_line(user_id, card, text)
        await self._turns.submit(user_id, WorkDraft(
            bot_id=card.bot_id, thread_id=card.thread_id, kind=WorkKind.CARD_ANSWER, origin=ORIGIN_CARD,
            body=text, tainted=card.tainted, message_id=line.id,
            link_scope=(card.url,) if card.url else (),
        ), item_id=item_id)
        await publish_card(self._events, user_id, card)
        await self._turns.settle(user_id, card.bot_id)
        return card

    async def give_up(self, user_id: str, card_id: str) -> StuckCard | None:
        """Give up: the task ends, and the bot says so. ``None`` / ``CardClosed`` as for ``clear``."""
        if await self._open_card(user_id, card_id) is None:
            return None
        card = await self._close(user_id, card_id, CardState.GIVEN_UP)
        self._control.give_back(card.bot_id)
        await post_bot_line(self._talk, self._events, user_id, card, GIVE_UP_LINE, kind="text")
        await publish_card(self._events, user_id, card)
        await self._turns.settle(user_id, card.bot_id)
        return card

    async def open_in_main_browser(self, user_id: str, card_id: str) -> StuckCard | None:
        """Use my main Brave: open the card's address there (piece A: open only, D-A3).

        ``None`` when the card is not the user's. ``CardClosed`` when it is no
        longer open, ``NoAddress`` when it has no address, and ``UrlBlocked`` when
        the address check refuses it. ``DeskUnavailable`` when the keeper can't
        open it."""
        card = await self._open_card(user_id, card_id)
        if card is None:
            return None
        if not card.url:
            raise NoAddress(card_id)
        checked = check_url(card.url)
        try:
            await self._main_browser.open(card.bot_id, checked)
        except DeskUnavailable:
            logger.warning("The main browser could not open Stuck card %s of bot %s", card_id, card.bot_id)
            raise
        marked = await self._store.mark_main_opened(user_id, card_id)
        if marked is None:
            raise CardClosed(card_id)
        await publish_card(self._events, user_id, marked)
        return marked

    async def _open_card(self, user_id: str, card_id: str) -> StuckCard | None:
        """The user's card, while it is open. ``None`` when it is not theirs."""
        card = await self._store.get(user_id, card_id)
        if card is not None and card.state is not CardState.OPEN:
            raise CardClosed(card_id)
        return card

    async def _close(self, user_id: str, card_id: str, state: CardState, *,
                     answer_item_id: str | None = None) -> StuckCard:
        """Only one press wins. ``None`` here means another press closed the card first."""
        card = await self._store.close(user_id, card_id, state, answer_item_id=answer_item_id)
        if card is None:
            raise CardClosed(card_id)
        return card

    async def _post_continue_line(self, user_id: str, card: StuckCard, text: str) -> Message:
        """R6: the continue text is your own line, carrying the card's taint."""
        line = await self._talk.add_message(user_id, card.thread_id, role="user", body=text,
                                            tainted=card.tainted, kind="card_answer")
        await self._events.publish(user_id, {
            "type": "message", "thread_id": card.thread_id, "message": message_out(line),
        })
        return line
```

- [ ] **Step 5: Implement the routes (`roost/gateway/routes/stuck.py`)**

Create `roost/gateway/routes/stuck.py`:

```python
"""The Stuck card's buttons over HTTP (stuck flow, Task 7; design §2 "The card's buttons", R8–R10).

- ``GET /api/stuck``: your open cards, newest first (Home's My turn, the chat's card).
- ``POST /api/stuck/{card_id}/clear``: Give it back, Try again and Done, carry on.
- ``POST /api/stuck/{card_id}/give-up``: Give up.
- ``POST /api/stuck/{card_id}/open-in-main-browser``: Use my main Brave.

Every route has ``CurrentUser``, and every button has ``RequireOrigin``.
``StuckService`` does the work, and this module only turns its answers into
status codes. Another user's card id is a 404, never the card. The service
checks the address before the keeper is asked (R8), because ``KeeperClient``
turns a keeper refusal it did not expect into a 503.
"""

from __future__ import annotations

from typing import Awaitable

from fastapi import APIRouter, HTTPException, Request

from roost.desk import DeskUnavailable
from roost.desk.url_policy import UrlBlocked
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.stuck.models import CardClosed, NoAddress, StuckCard, StuckCardOut, stuck_card_out
from roost.stuck.service import StuckService

stuck_router = APIRouter(prefix="/api/stuck", tags=["stuck"])

CARD_NOT_FOUND_DETAIL = "Card not found"
CARD_CLOSED_DETAIL = "This card is already closed."
NO_ADDRESS_DETAIL = "This card has no web address."
ADDRESS_REFUSED_DETAIL = "That address can't be opened."
DESK_UNAVAILABLE_DETAIL = "desk unavailable"

# What each refusal from StuckService answers. No two of these types overlap.
_REFUSALS: tuple[tuple[type[Exception], int, str], ...] = (
    (CardClosed, 409, CARD_CLOSED_DETAIL),
    (NoAddress, 400, NO_ADDRESS_DETAIL),
    (UrlBlocked, 400, ADDRESS_REFUSED_DETAIL),
    (DeskUnavailable, 503, DESK_UNAVAILABLE_DETAIL),
)
_REFUSED: tuple[type[Exception], ...] = tuple(kind for kind, _status, _detail in _REFUSALS)


def _service(request: Request) -> StuckService:
    return request.app.state.stuck_service


def _refusal(exc: Exception) -> HTTPException:
    status, detail = next((status, detail) for kind, status, detail in _REFUSALS if isinstance(exc, kind))
    return HTTPException(status_code=status, detail=detail)


async def _answer(pending: Awaitable[StuckCard | None]) -> StuckCardOut:
    try:
        card = await pending
    except _REFUSED as exc:
        raise _refusal(exc) from exc
    if card is None:
        raise HTTPException(status_code=404, detail=CARD_NOT_FOUND_DETAIL)
    return stuck_card_out(card)


@stuck_router.get("")
async def list_stuck(request: Request, user: CurrentUser) -> list[StuckCardOut]:
    return [stuck_card_out(card) for card in await _service(request).list_open(user.id)]


@stuck_router.post("/{card_id}/clear", dependencies=[RequireOrigin])
async def clear_card(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    """Give it back, Try again, and Done, carry on (R10): the bot carries on with the task."""
    return await _answer(_service(request).clear(user.id, card_id))


@stuck_router.post("/{card_id}/give-up", dependencies=[RequireOrigin])
async def give_up_card(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    return await _answer(_service(request).give_up(user.id, card_id))


@stuck_router.post("/{card_id}/open-in-main-browser", dependencies=[RequireOrigin])
async def open_card_in_main_browser(card_id: str, request: Request, user: CurrentUser) -> StuckCardOut:
    """Use my main Brave: opens the card's address there, with no automation (D-A3)."""
    return await _answer(_service(request).open_in_main_browser(user.id, card_id))
```

- [ ] **Step 6: Wire the gateway (`roost/gateway/app.py`)**

These edits apply on top of Task 5, which added `from roost.stuck.store import StuckStore`, `app.state.stuck` and `stuck=app.state.stuck`.

Find:

```python
from roost.desk.control import ControlLock
from roost.documents.service import DocumentService
```

Replace with:

```python
from roost.desk.control import ControlLock
from roost.desk.main_browser import make_main_browser
from roost.documents.service import DocumentService
```

Find:

```python
from roost.gateway.routes.static import mount_static_if_built
from roost.gateway.routes.tasks import tasks_router
```

Replace with:

```python
from roost.gateway.routes.static import mount_static_if_built
from roost.gateway.routes.stuck import stuck_router
from roost.gateway.routes.tasks import tasks_router
```

Find:

```python
from roost.rooms.store import RoomStore
from roost.stuck.store import StuckStore
```

Replace with:

```python
from roost.rooms.store import RoomStore
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
```

Find:

```python
    app.state.room_service = RoomService(app.state.bots, app.state.talk, app.state.rooms, app.state.turns)
```

Replace with:

```python
    app.state.room_service = RoomService(app.state.bots, app.state.talk, app.state.rooms, app.state.turns)
    # Stuck flow (Task 7): the card's buttons. Built after `turns`, which `/clear` queues continue items on.
    # The main Brave seam is the fake in fake mode and the keeper otherwise (R8).
    app.state.main_browser = make_main_browser(resolved_config)
    app.state.stuck_service = StuckService(
        app.state.stuck, app.state.talk, app.state.events, app.state.turns,
        app.state.control, app.state.main_browser,
    )
```

Find:

```python
    app.include_router(chats_router)
```

Replace with:

```python
    app.include_router(chats_router)
    app.include_router(stuck_router)
```

This keeps `mount_static_if_built(app)` last, so the static mount never shadows `/api/stuck`.

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_api.py -q`
Expected: PASS (19 tests: 17 test functions, and the refused-address test runs 3 addresses).

Run the files that share the gateway wiring, the run loop, the store and the seam:
`cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_runs.py tests/test_stuck_store.py tests/test_stuck_announce.py tests/test_main_browser_seam.py tests/test_computer_api.py tests/test_threads_api.py tests/test_rooms_api.py tests/test_bots_api.py tests/test_work_api.py tests/test_events_ws.py tests/test_static.py tests/test_health_api.py -q`
Expected: PASS.

Check the coverage of the new modules:
`cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_api.py --cov=roost.stuck.service --cov=roost.gateway.routes.stuck --cov-report=term-missing -q`
Expected: PASS, with 100% line coverage on both modules.

Run the full suite with the coverage gate:
`cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/stuck/service.py roost/gateway/routes/stuck.py roost/gateway/app.py tests/test_stuck_api.py
git commit -m "feat: the Stuck card's buttons: give it back, give up and open in your main Brave"
```

---

### Task 8: The web: the Stuck card, My turn and the notification

Design §2 ("The card's buttons"), §3, R7, R9 and R10. The web side of the stuck flow:
- A `kind: "stuck"` bot message renders as a **Stuck card** in the chat (`StuckCard`, on the `FoldCard` shell). Its body is the card as it opened (`stuck_message_body`, Task 3). Its live state comes from `GET /api/stuck` merged with `stuck_card` frames, where the live copy wins.
  - **Open:** the bot's line, the full address (as text, never a link), then **Take control** · **Try again** · **Use my main Brave** (only when there is an address) · **Give up**. When the bot suggests the main Brave, that button is the highlighted one.
  - **Holding** (after Take control): "You have control. Clear it in {botName}'s window, then give it back." with **Give it back** (`/clear`, which also releases the hold) and a **See its screen** link to `/bots/{bot_id}/profile?tab=computer`.
  - **After main Brave:** "Opened in your main Brave." with **Done, carry on** (`/clear`) and **Give up**.
  - **Closed:** folds to one line: "Cleared: {host}", "Stopped: {host}" or "Blocked: {host}". A closed live copy always wins, so a cleared card that turns blocked (rung 4) shows Blocked.
  - **Tainted:** the note "This link came from a web page the bot read. Check it before you open it."
  - **Card not known** (an old card in a past conversation, or before the list loads): the bot's line only, with no buttons.
  - A failed button says why through `ErrorNotice` and leaves the card as it was.
- The live store keeps `stuckCards`, and a `stuck_card` frame advances the cursor, so a resume never replays it.
- Chat loads `listStuck()` once and merges it with the live cards. Home gets a **My turn** section, shown only while a card is open, listing "{bot} · Stuck on {host}" with a link to that bot's chat (on the card's thread).
  - Home loads the Stuck list on its own (`useStuckList`), apart from the bots and chats `Promise.all`, and on the same reload trigger (a stored message or a team change, shared through `useReloadOn`).
  - When `GET /api/stuck` fails, only My turn says so: it shows its own `ErrorNotice` with Retry, and the bots and chats still render.
- `attentionFor` turns a `bot_status` frame with `status: "stuck"` into "{bot} is stuck". The card's own `kind: "stuck"` message never notifies, because only `kind: "text"` replies do.
- A `kind: "card_answer"` message (your continue line) is an ordinary user bubble. Nothing new is needed for it beyond the type.

`ChatThreads.test.tsx` also renders `Chat`, so it gets the same `api/stuck` mock and the `stuckCards` field in its live state. Without them, its `findByRole("alert")` tests would see a second alert from a failed real fetch.

**Files:**
- Create:
  - `web/src/api/stuck.ts`: `listStuck`, `clearStuck`, `giveUpStuck` and `openInMainBrowser`.
  - `web/src/lib/stuck.ts`: `parseStuckMessage`, `mergeStuck`, `openStuckCards` and `stuckTitle`.
  - `web/src/components/StuckCard.tsx`: `StuckCard` and `StuckCardProps`.
  - `web/tests/stuck.test.ts` and `web/tests/StuckCard.test.tsx`.
- Modify:
  - `web/src/api/types.ts`: `StuckReason`, `StuckState`, `StuckCardOut`, `StuckMessageData` and `StuckCardFrame` (added to `ServerFrame`). `MessageKind` gains `"stuck" | "card_answer"`.
  - `web/src/store/live.ts`: `LiveState.stuckCards`, `initialLiveState`, and the `"stuck_card"` case.
  - `web/src/components/MessageRow.tsx`: the optional `stuck` prop, and a `RowBody` that dispatches `kind: "stuck"` to `StuckCard`.
  - `web/src/components/MessageList.tsx`: the optional `stuck` prop, passed through to each row.
  - `web/src/pages/Chat.tsx`: `useOpenStuck`, and `mergeStuck` into `MessageList`.
  - `web/src/pages/Home.tsx`: `useReloadOn` (the reload trigger, shared by `useHomeData` and `useStuckList`), `useStuckList` (`listStuck` with its own state and error), the `MyTurn` section with its own `ErrorNotice`, and the live merge.
  - `web/src/lib/attention.ts`: the `stuck` status title.
  - `web/src/hooks/useAttention.ts`: its comment only.
  - `web/src/styles/chat.css`: `.stuck-card__url` and `.stuck-card__state`.
  - `web/src/styles/home.css`: `.my-turn*`, and `.my-turn .error-notice`.
- Test:
  - `web/tests/fixtures.ts`: `STUCK_LINE`, `makeStuckCard` and `stuckBody`.
  - `web/tests/stuck.test.ts` (new) and `web/tests/StuckCard.test.tsx` (new).
  - Additions to `web/tests/live.test.ts`, `web/tests/MessageList.test.tsx`, `web/tests/attention.test.ts`, `web/tests/Home.test.tsx` and `web/tests/Chat.test.tsx`.
  - `web/tests/ChatThreads.test.tsx`: the `api/stuck` mock and `stuckCards` in `liveOf`.

**Interfaces:**
- Consumes:
  - From Task 3:
    - the wire shape `StuckCardOut` (`id, bot_id, thread_id, reason, host, url, note, suggest_main_browser, tainted, main_opened, state, created_at, closed_at`);
    - the card message body `stuck_message_body(card)` = JSON `{card_id, bot_id, reason, host, url, note, suggest_main_browser, line}`;
    - the event `{"type": "stuck_card", "card": StuckCardOut}`, to which the EventHub adds `seq`.
  - From Task 5: messages with `kind: "stuck"` (`role: "bot"`, `author_bot_id`, `tainted`) and `kind: "card_answer"` (`role: "user"`), and `bot_status` frames with `status: "stuck"`.
  - From Task 7:
    - `GET /api/stuck` → `StuckCardOut[]`;
    - `POST /api/stuck/{id}/clear`, `/give-up` and `/open-in-main-browser` → `StuckCardOut`, or 404 / 409 `"This card is already closed."` / 400 / 503 with a plain `detail`.
  - Existing:
    - `apiRequest`, `describeError` and `ApiError` (`api/client.ts`);
    - `computerApi.takeControl(botId) -> Promise<ControlOut>`;
    - `FoldCard`, `FoldedLine` and `ErrorNotice`;
    - `linkHost`;
    - `applyFrame` / `LiveState` and `useLiveState`;
    - `makeBot` / `makeMessage` (`tests/fixtures.ts`).
- Produces (Task 9's E2E relies on these exact texts):
  - `web/src/api/types.ts`: `StuckReason`, `StuckState`, `StuckCardOut`, `StuckMessageData`, `StuckCardFrame { type: "stuck_card"; seq: number; card: StuckCardOut }` (in `ServerFrame`), and `MessageKind` with `"stuck" | "card_answer"`.
  - `web/src/api/stuck.ts`:
    - `listStuck(): Promise<StuckCardOut[]>`;
    - `clearStuck(cardId)`, `giveUpStuck(cardId)` and `openInMainBrowser(cardId)`, each `Promise<StuckCardOut>`.
  - `web/src/lib/stuck.ts`:
    - `parseStuckMessage(body: string): StuckMessageData | null`;
    - `mergeStuck(rest: readonly StuckCardOut[], live: Readonly<Record<string, StuckCardOut>>): Record<string, StuckCardOut>`;
    - `openStuckCards(cards: Readonly<Record<string, StuckCardOut>>): StuckCardOut[]`;
    - `stuckTitle(host: string, url: string): string`: `Stuck on {host}`, or `Needs your help` when the address is not http(s).
    - `parseStuckMessage` keeps a card whose address is not http(s) (such as `about:blank`), with `url` and `host` set to `""`, so it keeps its buttons.
  - `LiveState.stuckCards: Readonly<Record<string, StuckCardOut>>`.
  - `StuckCard({ data, card, botName, tainted })`. On the page:
    - a group named `Stuck on {host}` (or `Needs your help` when there is no address);
    - buttons `Take control`, `Try again`, `Use my main Brave`, `Give up`, `Give it back` and `Done, carry on`;
    - the link `See its screen`;
    - the texts `You have control. Clear it in {botName}'s window, then give it back.` and `Opened in your main Brave.`;
    - the folded lines `Cleared: {host}`, `Stopped: {host}` and `Blocked: {host}`.
  - `MessageList` / `MessageRow`: `stuck?: Readonly<Record<string, StuckCardOut>>`.
  - Home: a region named `My turn` with links named `{bot} · Stuck on {host}` to `/bots/{bot_id}?thread={thread_id}`. When `GET /api/stuck` fails, the same region holds the `ErrorNotice` (an `alert` with a `Retry` button), and the "Chats" list still renders.
  - `attentionFor`: `{ title: "{bot} is stuck" }` for `bot_status` `stuck`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

In `web/tests/fixtures.ts`, replace the first line:

```ts
import type { BotOut, MessageOut } from "../src/api/types";
```

with:

```ts
import type { BotOut, MessageOut, StuckCardOut } from "../src/api/types";
```

and append at the end of the file:

```ts

// What roost/stuck/texts.py stuck_line says for a sign-in page (stuck flow, Task 3).
export const STUCK_LINE = "I'm stuck on shop.example: a sign-in page. Take control to clear it, then give it back.";

export function makeStuckCard(overrides: Partial<StuckCardOut> = {}): StuckCardOut {
  return {
    id: "card-1",
    bot_id: "bot-1",
    thread_id: "t-1",
    reason: "login",
    host: "shop.example",
    url: "https://shop.example/login",
    note: "",
    suggest_main_browser: false,
    tainted: false,
    main_opened: false,
    state: "open",
    created_at: "2026-10-14T10:00:00Z",
    closed_at: null,
    ...overrides,
  };
}

// A kind "stuck" message's body, shaped like roost/stuck/texts.py stuck_message_body.
export function stuckBody(card: StuckCardOut, line = STUCK_LINE): string {
  return JSON.stringify({
    card_id: card.id, bot_id: card.bot_id, reason: card.reason, host: card.host, url: card.url,
    note: card.note, suggest_main_browser: card.suggest_main_browser, line,
  });
}
```

Create `web/tests/stuck.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearStuck, giveUpStuck, listStuck, openInMainBrowser } from "../src/api/stuck";
import { mergeStuck, openStuckCards, parseStuckMessage, stuckTitle } from "../src/lib/stuck";
import { makeStuckCard, STUCK_LINE } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

const BODY = {
  card_id: "card-1", bot_id: "bot-1", reason: "login", host: "shop.example", url: "https://shop.example/login",
  note: "", suggest_main_browser: false, line: STUCK_LINE,
};

describe("parseStuckMessage", () => {
  it("reads the card a stuck message carries", () => {
    expect(parseStuckMessage(JSON.stringify(BODY))).toEqual(BODY);
  });

  it("keeps only the card's own fields", () => {
    expect(parseStuckMessage(JSON.stringify({ ...BODY, extra: "<b>x</b>" }))).toEqual(BODY);
  });

  it("reads a card with no address, when the bot asked for help", () => {
    const asked = { ...BODY, reason: "asked", host: "", url: "", note: "Approve the payment" };
    expect(parseStuckMessage(JSON.stringify(asked))).toEqual(asked);
  });

  it.each([
    ["card_id", 7], ["card_id", ""], ["bot_id", null], ["reason", "captcha"], ["host", 1],
    ["url", 5], ["note", undefined], ["suggest_main_browser", "yes"], ["line", 3],
  ])("refuses a body whose %s is %s", (field, value) => {
    expect(parseStuckMessage(JSON.stringify({ ...BODY, [field]: value }))).toBeNull();
  });

  // Task 4 already sends no address for a fresh tab's about:blank, but the body is still checked here.
  // The card must keep its buttons, or it could never be cleared from the chat, so only the address goes.
  it.each(["about:blank", "javascript:alert(1)", "file:///etc/passwd"])(
    "treats the address %s as none: the card stays, but never shows or opens it",
    (url) => {
      expect(parseStuckMessage(JSON.stringify({ ...BODY, url, host: url }))).toEqual({ ...BODY, url: "", host: "" });
    },
  );

  it("refuses a body that is not JSON or not an object", () => {
    expect(parseStuckMessage("I'm stuck")).toBeNull();
    expect(parseStuckMessage("null")).toBeNull();
    expect(parseStuckMessage("[]")).toBeNull();
  });
});

describe("mergeStuck and openStuckCards", () => {
  it("adds the live cards to the loaded ones, and the live copy wins", () => {
    const loaded = [makeStuckCard({ id: "a" }), makeStuckCard({ id: "b" })];
    const live = { b: makeStuckCard({ id: "b", state: "cleared" }), c: makeStuckCard({ id: "c" }) };
    const merged = mergeStuck(loaded, live);
    expect(Object.keys(merged).sort()).toEqual(["a", "b", "c"]);
    expect(merged.b.state).toBe("cleared");
    expect(loaded[1].state).toBe("open"); // never mutated
  });

  it("keeps the cards still open, newest first", () => {
    const cards = mergeStuck([
      makeStuckCard({ id: "old", created_at: "2026-10-14T09:00:00Z" }),
      makeStuckCard({ id: "new", created_at: "2026-10-14T11:00:00Z" }),
      makeStuckCard({ id: "done", state: "given_up" }),
    ], {});
    expect(openStuckCards(cards).map((card) => card.id)).toEqual(["new", "old"]);
  });
});

describe("stuckTitle", () => {
  it("names the site, or asks for help when the card has no web address", () => {
    expect(stuckTitle("shop.example", "https://shop.example/login")).toBe("Stuck on shop.example");
    expect(stuckTitle("", "")).toBe("Needs your help");
    expect(stuckTitle("about:blank", "about:blank")).toBe("Needs your help");
  });
});

describe("the Stuck API", () => {
  it("lists your open cards and presses each button with the card's id", async () => {
    const card = makeStuckCard();
    const fetchMock = vi.fn(async (_path: string, _init: RequestInit) =>
      new Response(JSON.stringify(card), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await listStuck();
    await clearStuck("card-1");
    await giveUpStuck("card-1");
    await openInMainBrowser("card-1");
    expect(fetchMock.mock.calls.map(([path, init]) => [init.method, path])).toEqual([
      ["GET", "/api/stuck"],
      ["POST", "/api/stuck/card-1/clear"],
      ["POST", "/api/stuck/card-1/give-up"],
      ["POST", "/api/stuck/card-1/open-in-main-browser"],
    ]);
  });
});
```

Create `web/tests/StuckCard.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { StuckCard } from "../src/components/StuckCard";
import { ApiError } from "../src/api/client";
import type { StuckCardOut, StuckMessageData } from "../src/api/types";
import { makeStuckCard, STUCK_LINE } from "./fixtures";

const computer = { takeControl: vi.fn() };
const stuck = { clearStuck: vi.fn(), giveUpStuck: vi.fn(), openInMainBrowser: vi.fn() };
vi.mock("../src/api/computer", () => ({ takeControl: (id: string) => computer.takeControl(id) }));
vi.mock("../src/api/stuck", () => ({
  clearStuck: (id: string) => stuck.clearStuck(id),
  giveUpStuck: (id: string) => stuck.giveUpStuck(id),
  openInMainBrowser: (id: string) => stuck.openInMainBrowser(id),
}));

const CARD = makeStuckCard();
const CLOSED_AT = "2026-10-14T10:05:00Z";
const dataOf = (card: StuckCardOut, line = STUCK_LINE): StuckMessageData => ({
  card_id: card.id, bot_id: card.bot_id, reason: card.reason, host: card.host, url: card.url, note: card.note,
  suggest_main_browser: card.suggest_main_browser, line,
});
const cardView = (card: StuckCardOut | undefined, data = dataOf(CARD), tainted = false) => (
  <MemoryRouter><StuckCard data={data} card={card} botName="Scout" tainted={tainted} /></MemoryRouter>
);
const renderCard = (card: StuckCardOut | undefined, data = dataOf(CARD), tainted = false) =>
  render(cardView(card, data, tainted));
const click = (name: string) => userEvent.click(screen.getByRole("button", { name }));

beforeEach(() => {
  stuck.clearStuck.mockResolvedValue({ ...CARD, state: "cleared", closed_at: CLOSED_AT });
  stuck.giveUpStuck.mockResolvedValue({ ...CARD, state: "given_up", closed_at: CLOSED_AT });
  stuck.openInMainBrowser.mockResolvedValue({ ...CARD, main_opened: true });
  computer.takeControl.mockResolvedValue({ held: true, since: "2026-10-14T10:01:00Z" });
});
afterEach(() => { cleanup(); [...Object.values(computer), ...Object.values(stuck)].forEach((m) => m.mockReset()); });

describe("StuckCard", () => {
  it("an open card shows the bot's line, the address and its four buttons", () => {
    renderCard(CARD);
    const card = screen.getByRole("group", { name: "Stuck on shop.example" });
    expect(card).toHaveTextContent(STUCK_LINE);
    expect(card).toHaveTextContent("https://shop.example/login");
    for (const name of ["Take control", "Try again", "Use my main Brave", "Give up"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("a card with no address is titled Needs your help and has no main Brave button", () => {
    const asked = makeStuckCard({ reason: "asked", host: "", url: "", note: "Approve the payment" });
    renderCard(asked, dataOf(asked, "I need your help: Approve the payment. Take control to clear it, then give it back."));
    expect(screen.getByRole("group", { name: "Needs your help" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use my main Brave" })).not.toBeInTheDocument();
  });

  it("Take control holds the computer and says how to give it back", async () => {
    renderCard(CARD);
    await click("Take control");
    expect(computer.takeControl).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByText("You have control. Clear it in Scout's window, then give it back.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See its screen" })).toHaveAttribute("href", "/bots/bot-1/profile?tab=computer");
    expect(screen.queryByRole("button", { name: "Take control" })).not.toBeInTheDocument();
  });

  it("Give it back clears the card, then it folds to Cleared", async () => {
    renderCard(CARD);
    await click("Take control");
    await screen.findByText("You have control. Clear it in Scout's window, then give it back.");
    await click("Give it back");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("Try again clears the card without taking control", async () => {
    renderCard(CARD);
    await click("Try again");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
    expect(computer.takeControl).not.toHaveBeenCalled();
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
  });

  it("Use my main Brave opens it there, then Done, carry on clears the card", async () => {
    renderCard(CARD);
    await click("Use my main Brave");
    expect(stuck.openInMainBrowser).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Opened in your main Brave.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Give up" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Take control" })).not.toBeInTheDocument();
    await click("Done, carry on");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
  });

  it("a card already opened in the main Brave offers Done, carry on and Give up", () => {
    renderCard({ ...CARD, main_opened: true });
    expect(screen.getByText("Opened in your main Brave.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done, carry on" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Give up" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("Give up stops the task, then it folds to Stopped", async () => {
    renderCard(CARD);
    await click("Give up");
    expect(stuck.giveUpStuck).toHaveBeenCalledWith("card-1");
    expect(await screen.findByText("Stopped: shop.example")).toBeInTheDocument();
  });

  it("the bot's suggestion makes Use my main Brave the highlighted button", () => {
    const suggested = makeStuckCard({ suggest_main_browser: true });
    renderCard(suggested, dataOf(suggested));
    expect(screen.getByRole("button", { name: "Use my main Brave" })).toHaveClass("btn--primary");
    expect(screen.getByRole("button", { name: "Take control" })).not.toHaveClass("btn--primary");
  });

  it("a card from a run that read the web warns before you open its link", () => {
    renderCard(CARD, dataOf(CARD), true);
    expect(screen.getByRole("note")).toHaveTextContent(
      "This link came from a web page the bot read. Check it before you open it.",
    );
  });

  it("a failed button says why and leaves the card open", async () => {
    stuck.clearStuck.mockRejectedValue(new ApiError(409, "This card is already closed."));
    renderCard(CARD);
    await click("Try again");
    expect(await screen.findByRole("alert")).toHaveTextContent("This card is already closed.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it.each([
    ["cleared", "Cleared: shop.example"],
    ["given_up", "Stopped: shop.example"],
    ["blocked", "Blocked: shop.example"],
  ] as const)("a %s card folds to one line", (state, line) => {
    renderCard({ ...CARD, state, closed_at: CLOSED_AT });
    expect(screen.getByRole("group", { name: line })).toHaveTextContent(line);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("a later live state wins over a button's answer: cleared, then blocked again", async () => {
    const view = renderCard(CARD);
    await click("Try again");
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
    view.rerender(cardView({ ...CARD, state: "blocked", closed_at: CLOSED_AT }));
    expect(screen.getByText("Blocked: shop.example")).toBeInTheDocument();
  });

  it("with no card known it shows the bot's line and no buttons", () => {
    renderCard(undefined);
    expect(screen.getByText(STUCK_LINE)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
```

In `web/tests/live.test.ts`, replace:

```ts
import { makeBot, makeMessage } from "./fixtures";
```

with:

```ts
import { makeBot, makeMessage, makeStuckCard } from "./fixtures";
```

and append at the end of the file:

```ts

describe("stuck frames", () => {
  it("starts with no Stuck cards", () => {
    expect(initialLiveState().stuckCards).toEqual({});
  });

  it("a stuck_card frame upserts the card by id and advances the cursor", () => {
    const card = makeStuckCard();
    const opened = applyFrame(initialLiveState(), { type: "stuck_card", seq: 9, card });
    const cleared = applyFrame(opened, {
      type: "stuck_card", seq: 10, card: { ...card, state: "cleared", closed_at: "2026-10-14T10:05:00Z" },
    });
    expect(opened.stuckCards).toEqual({ "card-1": card });
    expect(Object.keys(cleared.stuckCards)).toEqual(["card-1"]);
    expect(cleared.stuckCards["card-1"].state).toBe("cleared");
    expect(cleared.cursor).toBe(10);
    // The reducer never mutates its input (immutability rule).
    expect(opened.stuckCards["card-1"].state).toBe("open");
  });
});
```

In `web/tests/MessageList.test.tsx`, replace:

```tsx
import { makeBot, makeMessage } from "./fixtures";
```

with:

```tsx
import { makeBot, makeMessage, makeStuckCard, stuckBody, STUCK_LINE } from "./fixtures";
```

and append at the end of the file:

```tsx

describe("MessageList Stuck cards", () => {
  const CARD = makeStuckCard();
  const STUCK = makeMessage({ id: "s-1", kind: "stuck", author_bot_id: "bot-1", body: stuckBody(CARD) });

  it("renders a Stuck card with its buttons while its card is open", () => {
    render(
      <MemoryRouter>
        <MessageList messages={[STUCK]} botName="Scout" team={[makeBot()]} stuck={{ [CARD.id]: CARD }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("group", { name: "Stuck on shop.example" })).toHaveTextContent(STUCK_LINE);
    expect(screen.getByRole("button", { name: "Take control" })).toBeInTheDocument();
  });

  it("folds a Stuck card once its card is closed", () => {
    render(
      <MemoryRouter>
        <MessageList messages={[STUCK]} botName="Scout" stuck={{ [CARD.id]: { ...CARD, state: "given_up" } }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("group", { name: "Stopped: shop.example" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("a stuck message whose body is not a card stays plain text", () => {
    render(<MessageList messages={[makeMessage({ kind: "stuck", body: "not a card" })]} botName="Scout" />);
    expect(screen.getByText("not a card")).toBeInTheDocument();
  });

  it("your continue line is your own bubble", () => {
    const body = "I cleared the block on shop.example. Read the page again and carry on with: book a table";
    render(<MessageList messages={[makeMessage({ role: "user", kind: "card_answer", body })]} botName="Scout" />);
    expect(screen.getByText(body).closest("li")).toHaveClass("message--user");
  });
});
```

In `web/tests/attention.test.ts`, replace:

```ts
import { makeBot, makeMessage } from "./fixtures";
```

with:

```ts
import { makeBot, makeMessage, makeStuckCard, stuckBody } from "./fixtures";
```

Then find:

```ts
  it("Asking you asks for attention", () => {
    const frame: BotStatusFrame = { type: "bot_status", seq: 4, bot_id: "bot-1", status: "asking_you", activity: "Which day?" };
    expect(attentionFor(frame, { "bot-1": SCOUT })).toEqual({ botId: "bot-1", title: "Scout needs you", body: "Which day?" });
  });
```

and replace it with:

```ts
  it("Asking you asks for attention", () => {
    const frame: BotStatusFrame = { type: "bot_status", seq: 4, bot_id: "bot-1", status: "asking_you", activity: "Which day?" };
    expect(attentionFor(frame, { "bot-1": SCOUT })).toEqual({ botId: "bot-1", title: "Scout needs you", body: "Which day?" });
  });

  it("a bot that turns Stuck asks for attention", () => {
    const frame: BotStatusFrame = { type: "bot_status", seq: 5, bot_id: "bot-1", status: "stuck", activity: null };
    expect(attentionFor(frame, { "bot-1": SCOUT })).toEqual({ botId: "bot-1", title: "Scout is stuck", body: "" });
    expect(attentionFor(frame, { "bot-1": { ...SCOUT, notify: false } })).toBeNull();
  });

  it("the Stuck card's own message does not notify a second time", () => {
    expect(attentionFor(message({ kind: "stuck", body: stuckBody(makeStuckCard()) }), { "bot-1": SCOUT })).toBeNull();
  });
```

In `web/tests/Home.test.tsx`:
- Replace `import { act, cleanup, render, screen, waitFor } from "@testing-library/react";` with `import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";`.
- Replace `import { makeBot, makeMessage } from "./fixtures";` with `import { makeBot, makeMessage, makeStuckCard } from "./fixtures";`.
- Find:

```tsx
const logoutMock = vi.fn();
vi.mock("../src/api/bots", () => ({ listBots: () => listBotsMock() }));
vi.mock("../src/api/chats", () => ({ listChats: () => listChatsMock() }));
vi.mock("../src/api/rooms", () => ({ createRoom: vi.fn() }));
```

and replace it with:

```tsx
const logoutMock = vi.fn();
const listStuckMock = vi.fn();
vi.mock("../src/api/bots", () => ({ listBots: () => listBotsMock() }));
vi.mock("../src/api/chats", () => ({ listChats: () => listChatsMock() }));
vi.mock("../src/api/rooms", () => ({ createRoom: vi.fn() }));
vi.mock("../src/api/stuck", () => ({ listStuck: () => listStuckMock() }));
```

- Find:

```tsx
  listChatsMock.mockResolvedValue(ROWS);
});
```

and replace it with:

```tsx
  listChatsMock.mockResolvedValue(ROWS);
  listStuckMock.mockResolvedValue([]);
});
```

- Append at the end of the file:

```tsx

describe("Home — My turn", () => {
  const CARD = makeStuckCard({ bot_id: "bot-1", thread_id: "t-1" });

  it("lists each open Stuck card, linking to that bot's chat", async () => {
    listStuckMock.mockResolvedValue([CARD]);
    renderHome();
    const turn = await screen.findByRole("region", { name: "My turn" });
    expect(within(turn).getByRole("link", { name: "Scout · Stuck on shop.example" }))
      .toHaveAttribute("href", "/bots/bot-1?thread=t-1");
  });

  it("is hidden while nothing waits on you", async () => {
    renderHome();
    await screen.findByRole("list", { name: "Chats" });
    expect(screen.queryByRole("region", { name: "My turn" })).not.toBeInTheDocument();
  });

  it("follows live stuck_card frames without reloading", async () => {
    const view = renderHome();
    await screen.findByRole("list", { name: "Chats" });
    liveState = applyFrame(liveState, { type: "stuck_card", seq: 4, card: CARD });
    view.rerender(<MemoryRouter><Home /></MemoryRouter>);
    expect(await screen.findByRole("region", { name: "My turn" })).toBeInTheDocument();
    liveState = applyFrame(liveState, {
      type: "stuck_card", seq: 5, card: { ...CARD, state: "cleared", closed_at: "2026-10-14T10:05:00Z" },
    });
    view.rerender(<MemoryRouter><Home /></MemoryRouter>);
    expect(screen.queryByRole("region", { name: "My turn" })).not.toBeInTheDocument();
    expect(listStuckMock).toHaveBeenCalledTimes(1);
  });

  it("steps aside while you search, like the main bot", async () => {
    listStuckMock.mockResolvedValue([CARD]);
    renderHome();
    await screen.findByRole("region", { name: "My turn" });
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Search chats" }), "scout");
    expect(screen.queryByRole("region", { name: "My turn" })).not.toBeInTheDocument();
  });

  it("still shows the chats when the Stuck list fails", async () => {
    listStuckMock.mockRejectedValueOnce(new ApiError(500, "Could not load your Stuck cards."));
    renderHome();
    expect(await screen.findByRole("list", { name: "Chats" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chief, your main bot" })).toBeInTheDocument();
    const turn = await screen.findByRole("region", { name: "My turn" });
    expect(within(turn).getByRole("alert")).toHaveTextContent("Could not load your Stuck cards.");
    expect(screen.getAllByRole("alert")).toHaveLength(1);           // only My turn says so, never Home as a whole
    await userEvent.click(within(turn).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(listStuckMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("region", { name: "My turn" })).not.toBeInTheDocument());
    expect(listChatsMock).toHaveBeenCalledTimes(1);                 // Retry reloads the Stuck list only
  });
});
```

In `web/tests/Chat.test.tsx`:
- Replace `import { cleanup, render, screen } from "@testing-library/react";` with `import { cleanup, render, screen, within } from "@testing-library/react";`.
- Replace `import type { ThreadOut } from "../src/api/types";` with:

```tsx
import { ApiError } from "../src/api/client";
import type { ThreadOut } from "../src/api/types";
```

- Replace `import { makeBot, makeMessage } from "./fixtures";` with `import { makeBot, makeMessage, makeStuckCard, stuckBody, STUCK_LINE } from "./fixtures";`.
- Find:

```tsx
vi.mock("../src/api/bots", () => ({ getBot: () => Promise.resolve(makeBot({ id: "bot-1", name: "Scout" })) }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({ cursor: 0, bots: {}, messagesByThread: {}, streaming: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 } }),
}));
```

and replace it with:

```tsx
vi.mock("../src/api/bots", () => ({ getBot: () => Promise.resolve(makeBot({ id: "bot-1", name: "Scout" })) }));
const stuckApi = { listStuck: vi.fn() };
vi.mock("../src/api/stuck", () => ({ listStuck: () => stuckApi.listStuck() }));
vi.mock("../src/hooks/useLiveStore", () => ({
  useLiveState: () => ({
    cursor: 0, bots: {}, messagesByThread: {}, streaming: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 },
    stuckCards: {},
  }),
}));
```

- Find:

```tsx
  threadsApi.createThread.mockResolvedValue(thread("t-3", "2026-10-14T11:00:00Z"));
});
afterEach(() => { cleanup(); Object.values(threadsApi).forEach((m) => m.mockReset()); });
```

and replace it with:

```tsx
  threadsApi.createThread.mockResolvedValue(thread("t-3", "2026-10-14T11:00:00Z"));
  stuckApi.listStuck.mockResolvedValue([]);
});
afterEach(() => { cleanup(); [...Object.values(threadsApi), stuckApi.listStuck].forEach((m) => m.mockReset()); });
```

- Append at the end of the file:

```tsx

describe("Chat — Stuck cards", () => {
  const CARD = makeStuckCard({ thread_id: "t-2" });
  const STUCK = makeMessage({
    id: "m-9", thread_id: "t-2", kind: "stuck", author_bot_id: "bot-1", created_at: "2026-10-14T10:02:00Z",
    body: stuckBody(CARD),
  });

  it("loads your open cards once and shows this chat's card with its buttons", async () => {
    stuckApi.listStuck.mockResolvedValue([CARD]);
    threadsApi.listMessages.mockResolvedValue([STUCK]);
    renderChat();
    const card = await screen.findByRole("group", { name: "Stuck on shop.example" });
    expect(within(card).getByRole("button", { name: "Take control" })).toBeInTheDocument();
    expect(stuckApi.listStuck).toHaveBeenCalledTimes(1);
  });

  it("a card that is no longer open shows only the bot's line", async () => {
    threadsApi.listMessages.mockResolvedValue([STUCK]);
    renderChat();
    expect(await screen.findByText(STUCK_LINE)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Take control" })).not.toBeInTheDocument();
  });

  it("a failed card list says why in the dock, and the chat still shows", async () => {
    stuckApi.listStuck.mockRejectedValue(new ApiError(500, "Could not load your Stuck cards."));
    threadsApi.listMessages.mockResolvedValue([STUCK]);
    renderChat();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your Stuck cards.");
    expect(screen.getByText(STUCK_LINE)).toBeInTheDocument();
  });
});
```

In `web/tests/ChatThreads.test.tsx`, find:

```tsx
const liveOf = (cursor = 0, messagesByThread: Record<string, MessageOut[]> = {}) =>
  ({ cursor, bots: {}, messagesByThread, streaming: {}, boardVersion: BOARD });
let liveState = liveOf();
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => liveState }));
```

and replace it with:

```tsx
const liveOf = (cursor = 0, messagesByThread: Record<string, MessageOut[]> = {}) =>
  ({ cursor, bots: {}, messagesByThread, streaming: {}, boardVersion: BOARD, stuckCards: {} });
let liveState = liveOf();
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => liveState }));
// Chat loads your open Stuck cards on mount; none are open in these tests.
vi.mock("../src/api/stuck", () => ({ listStuck: () => Promise.resolve([]) }));
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/stuck.test.ts tests/StuckCard.test.tsx tests/live.test.ts tests/MessageList.test.tsx tests/attention.test.ts tests/Home.test.tsx tests/Chat.test.tsx tests/ChatThreads.test.tsx`

Expected: FAIL.
- `stuck.test.ts` and `StuckCard.test.tsx` do not load: `Failed to resolve import "../src/api/stuck"` and `"../src/components/StuckCard"`.
- `live.test.ts`: both "stuck frames" tests fail, because `stuckCards` is `undefined`.
- `MessageList.test.tsx`: "renders a Stuck card with its buttons while its card is open" fails (`Unable to find role="group" and name "Stuck on shop.example"`), and so does "folds a Stuck card once its card is closed".
- `attention.test.ts`: "a bot that turns Stuck asks for attention" fails (expected `null` to equal the signal).
- `Home.test.tsx`: "lists each open Stuck card…", "follows live stuck_card frames…", "steps aside while you search…" and "still shows the chats when the Stuck list fails" fail (`Unable to find role="region"`).
- `Chat.test.tsx`: all three "Chat — Stuck cards" tests fail. There is no card group, the bot's line is not shown on its own, and no alert appears.

Already green, because they describe behavior that holds today:
- "a stuck message whose body is not a card stays plain text";
- "your continue line is your own bubble";
- "the Stuck card's own message does not notify a second time";
- "is hidden while nothing waits on you";
- every earlier test, `ChatThreads.test.tsx` included.

- [ ] **Step 4: Implement the types, the API and the parser**

In `web/src/api/types.ts`, find:

```ts
export type MessageKind =
  | "text" | "handoff" | "suggestion" | "notice" | "dropped" | "interrupted" | "daily_limit" | "bot_created";
```

and replace it with:

```ts
export type MessageKind =
  | "text" | "handoff" | "suggestion" | "notice" | "dropped" | "interrupted" | "daily_limit" | "bot_created"
  | "stuck" | "card_answer";
```

Find:

```ts
// A "Created <name>" card's body (message kind "bot_created", S1.3).
export interface CreatedCardData {
  bot_id: string;
  name: string;
  job: string;
  instructions: string;
  avatar: AvatarOut;
}
```

and add after it:

```ts

// The stuck flow (Piece A): why a bot stopped, and where its card stands.
export type StuckReason = "challenge" | "login" | "code" | "refused" | "asked";
export type StuckState = "open" | "cleared" | "given_up" | "blocked";

// A Stuck card (roost/stuck/models.py StuckCardOut): GET /api/stuck, every button's answer and
// the stuck_card frame. `host` is "" when the bot asked for help with no web address.
export interface StuckCardOut {
  id: string;
  bot_id: string;
  thread_id: string;
  reason: StuckReason;
  host: string;
  url: string;
  note: string;
  suggest_main_browser: boolean;
  tainted: boolean;
  main_opened: boolean;
  state: StuckState;
  created_at: string;
  closed_at: string | null;
}

// A Stuck card's chat message body (message kind "stuck", roost/stuck/texts.py
// stuck_message_body): the card as it opened, plus the bot's line. Its live state is a StuckCardOut.
export interface StuckMessageData {
  card_id: string;
  bot_id: string;
  reason: StuckReason;
  host: string;
  url: string;
  note: string;
  suggest_main_browser: boolean;
  line: string;
}
```

Find:

```ts
export interface DocumentsChangedFrame {
  type: "documents_changed";
  seq: number;
  change: "created" | "updated" | "deleted";
  document_id: string;
  kind: DocumentKind;
}
```

and add after it:

```ts

// A Stuck card changed: it opened, was cleared, given up, blocked, or opened in the main Brave.
export interface StuckCardFrame {
  type: "stuck_card";
  seq: number;
  card: StuckCardOut;
}
```

Find:

```ts
  | NotesChangedFrame
  | DocumentsChangedFrame;
```

and replace it with:

```ts
  | NotesChangedFrame
  | DocumentsChangedFrame
  | StuckCardFrame;
```

Create `web/src/api/stuck.ts`:

```ts
// web/src/api/stuck.ts — the Stuck card's buttons and Home's My turn (stuck flow, Piece A).
import { apiRequest } from "./client";
import type { StuckCardOut } from "./types";

// Ids come from the server, but encoding keeps a stray "/" or "?" from ever reaching another route.
const cardPath = (cardId: string) => `/api/stuck/${encodeURIComponent(cardId)}`;

export const listStuck = () => apiRequest<StuckCardOut[]>("GET", "/api/stuck");
export const clearStuck = (cardId: string) => apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/clear`);
export const giveUpStuck = (cardId: string) => apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/give-up`);
export const openInMainBrowser = (cardId: string) =>
  apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/open-in-main-browser`);
```

Create `web/src/lib/stuck.ts`:

```ts
// web/src/lib/stuck.ts — reading a Stuck card's chat message (stuck flow, Piece A), and your
// cards as this page knows them: loaded once (GET /api/stuck), then kept current by stuck_card frames.
import type { StuckCardOut, StuckMessageData, StuckReason } from "../api/types";
import { linkHost } from "./linkHost";

const REASONS: readonly StuckReason[] = ["challenge", "login", "code", "refused", "asked"];

const isText = (value: unknown): value is string => typeof value === "string";
const isFilled = (value: unknown): value is string => isText(value) && value !== "";

// The body is the server's JSON, but its note was written by a model: check every field. A body
// that fails renders as plain text instead. Only an http(s) address is kept: any other (about:blank,
// when the bot asked for help before opening a page) means the card has no address. The card keeps
// its buttons, because a card that can't be cleared from the chat would leave the bot Stuck.
export function parseStuckMessage(body: string): StuckMessageData | null {
  try {
    const data = JSON.parse(body);
    const ok = isFilled(data?.card_id) && isFilled(data?.bot_id) && REASONS.includes(data?.reason)
      && isText(data?.host) && isText(data?.url) && isText(data?.note)
      && typeof data?.suggest_main_browser === "boolean" && isText(data?.line);
    if (!ok) return null;
    const web = linkHost(data.url) !== null;
    return {
      card_id: data.card_id, bot_id: data.bot_id, reason: data.reason,
      host: web ? data.host : "", url: web ? data.url : "",
      note: data.note, suggest_main_browser: data.suggest_main_browser, line: data.line,
    };
  } catch {
    return null; // not JSON: no card, the row renders as plain text instead
  }
}

// The card's title, in the chat and in Home's My turn: the site it is stuck on, or
// "Needs your help" when it has no web address.
export function stuckTitle(host: string, url: string): string {
  return host && linkHost(url) !== null ? `Stuck on ${host}` : "Needs your help";
}

// The loaded open cards with every live stuck_card frame on top: the live copy is the newer one.
export function mergeStuck(
  rest: readonly StuckCardOut[],
  live: Readonly<Record<string, StuckCardOut>>,
): Record<string, StuckCardOut> {
  return { ...Object.fromEntries(rest.map((card) => [card.id, card])), ...live };
}

// The cards still waiting on you, newest first (Home's My turn).
export function openStuckCards(cards: Readonly<Record<string, StuckCardOut>>): StuckCardOut[] {
  return Object.values(cards)
    .filter((card) => card.state === "open")
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}
```

- [ ] **Step 5: Implement the live store**

In `web/src/store/live.ts`, find:

```ts
// Live WS store for `/api/events` (contract: server->client frames
// snapshot/bot_status/message/text_delta/message_done/bot_removed/bot_updated,
// and the Board's tasks_changed/money_changed/notes_changed/documents_changed;
// client->server `resume`). Two parts, deliberately split:
```

and replace it with:

```ts
// Live WS store for `/api/events` (contract: server->client frames
// snapshot/bot_status/message/text_delta/message_done/bot_removed/bot_updated,
// the Board's tasks_changed/money_changed/notes_changed/documents_changed,
// and the Stuck cards' stuck_card; client->server `resume`). Two parts, deliberately split:
```

Find:

```ts
import type { BotOut, MessageDoneFrame, MessageOut, ServerFrame } from "../api/types";
```

and replace it with:

```ts
import type { BotOut, MessageDoneFrame, MessageOut, ServerFrame, StuckCardOut } from "../api/types";
```

Find:

```ts
  // Bumped by tasks_changed / money_changed / notes_changed / documents_changed: the Board reloads on a change.
  readonly boardVersion: Readonly<{ tasks: number; money: number; notes: number; documents: number }>;
}

export function initialLiveState(): LiveState {
  return { cursor: 0, bots: {}, messagesByThread: {}, streaming: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 } };
}
```

and replace it with:

```ts
  // Bumped by tasks_changed / money_changed / notes_changed / documents_changed: the Board reloads on a change.
  readonly boardVersion: Readonly<{ tasks: number; money: number; notes: number; documents: number }>;
  // Each Stuck card as its latest stuck_card frame left it, keyed by card id, open or closed:
  // the chat folds a card that is no longer open, and Home's My turn lists the open ones.
  readonly stuckCards: Readonly<Record<string, StuckCardOut>>;
}

export function initialLiveState(): LiveState {
  return {
    cursor: 0, bots: {}, messagesByThread: {}, streaming: {},
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 }, stuckCards: {},
  };
}
```

Find:

```ts
    case "documents_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, documents: state.boardVersion.documents + 1 } };

    default:
      return state;
```

and replace it with:

```ts
    case "documents_changed":
      return { ...state, cursor: frame.seq, boardVersion: { ...state.boardVersion, documents: state.boardVersion.documents + 1 } };

    // Every state change of a card (open, cleared, given up, blocked, opened in the main
    // Brave) replaces the copy kept here. Advancing the cursor means a resume never replays it.
    case "stuck_card":
      return { ...state, cursor: frame.seq, stuckCards: { ...state.stuckCards, [frame.card.id]: frame.card } };

    default:
      return state;
```

- [ ] **Step 6: Implement the card (`web/src/components/StuckCard.tsx`) and its styles**

Create `web/src/components/StuckCard.tsx`:

```tsx
// web/src/components/StuckCard.tsx — the Stuck card (stuck flow, Piece A). The bot hit a block
// it can't get past alone: a check that it's human, a sign-in page, a code check, a site that
// refused it, or something it asked you for. You clear it in the bot's own window (Take control,
// then Give it back), let it try again, open the page in your main Brave, or stop the task.
// Once the card is no longer open it folds to one line.
import { useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice } from "./ErrorNotice";
import { FoldCard, FoldedLine } from "./FoldCard";
import * as computerApi from "../api/computer";
import * as stuckApi from "../api/stuck";
import { describeError } from "../api/client";
import type { StuckCardOut, StuckMessageData, StuckState } from "../api/types";
import { stuckTitle } from "../lib/stuck";

export interface StuckCardProps {
  data: StuckMessageData;
  // The card's live state (GET /api/stuck merged with stuck_card frames). It is undefined when
  // this page has not heard of the card as open, e.g. an old card in a past conversation.
  card: StuckCardOut | undefined;
  botName: string;
  // The run that hit the block had read web content, so its address may be a planted one.
  tainted: boolean;
}

type View = "open" | "holding" | "main_opened";
type CardAction = (cardId: string) => Promise<StuckCardOut>;

const TAINT_NOTE = "This link came from a web page the bot read. Check it before you open it.";
const FOLDED: Record<Exclude<StuckState, "open">, { word: string; icon: string }> = {
  cleared: { word: "Cleared", icon: "✓" },
  given_up: { word: "Stopped", icon: "×" },
  blocked: { word: "Blocked", icon: "!" },
};

// The card as this page last heard of it. A closed live copy always wins, because a cleared card
// can still turn blocked. An open one gives way to what a button here just got back.
function latest(card: StuckCardOut | undefined, answered: StuckCardOut | null): StuckCardOut | undefined {
  if (!answered || (card && card.state !== "open")) return card;
  return answered;
}

// The buttons' calls: one at a time, and a failure is said on the card, never swallowed.
function useStuckActions(cardId: string) {
  const [answered, setAnswered] = useState<StuckCardOut | null>(null);
  const [holding, setHolding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const answer = (call: CardAction) => run(async () => setAnswered(await call(cardId)));
  return {
    answered, holding, busy, error,
    takeControl: (botId: string) => run(async () => setHolding((await computerApi.takeControl(botId)).held)),
    clear: () => answer(stuckApi.clearStuck),
    giveUp: () => answer(stuckApi.giveUpStuck),
    openInMain: () => answer(stuckApi.openInMainBrowser),
  };
}

type Actions = ReturnType<typeof useStuckActions>;

function StuckFooter({ view, data, actions }: { view: View; data: StuckMessageData; actions: Actions }) {
  const button = (label: string, onClick: () => Promise<void>, primary = false) => (
    <button type="button" className={`btn ${primary ? "btn--primary" : "btn--quiet"} btn--small`}
      disabled={actions.busy} onClick={() => void onClick()}>{label}</button>
  );
  if (view === "holding") {
    return (
      <>
        <Link className="btn btn--quiet btn--small" to={`/bots/${data.bot_id}/profile?tab=computer`}>See its screen</Link>
        {button("Give it back", actions.clear, true)}
      </>
    );
  }
  if (view === "main_opened") return <>{button("Done, carry on", actions.clear, true)}{button("Give up", actions.giveUp)}</>;
  return (
    <>
      {button("Take control", () => actions.takeControl(data.bot_id), !data.suggest_main_browser)}
      {button("Try again", actions.clear)}
      {data.url ? button("Use my main Brave", actions.openInMain, data.suggest_main_browser) : null}
      {button("Give up", actions.giveUp)}
    </>
  );
}

function StuckBody({ view, data, botName, tainted, error }: {
  view: View; data: StuckMessageData; botName: string; tainted: boolean; error: string | null;
}) {
  return (
    <>
      {data.url ? <p className="stuck-card__url"><bdi dir="ltr">{data.url}</bdi></p> : null}
      {tainted && data.url ? <p className="fold-card__taint" role="note">{TAINT_NOTE}</p> : null}
      {view === "holding" ? (
        <p className="stuck-card__state">{`You have control. Clear it in ${botName}'s window, then give it back.`}</p>
      ) : null}
      {view === "main_opened" ? <p className="stuck-card__state">Opened in your main Brave.</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
}

export function StuckCard({ data, card, botName, tainted }: StuckCardProps) {
  const actions = useStuckActions(data.card_id);
  const shown = latest(card, actions.answered);
  if (!shown) return <div className="message__body">{data.line}</div>;
  const state = shown.state;
  if (state !== "open") {
    const line = `${FOLDED[state].word}: ${data.host || data.note}`;
    return <FoldedLine icon={FOLDED[state].icon} ariaLabel={line}>{line}</FoldedLine>;
  }
  const view: View = actions.holding ? "holding" : shown.main_opened ? "main_opened" : "open";
  const title = stuckTitle(data.host, data.url);
  const hasBody = Boolean(data.url) || view !== "open" || actions.error !== null;
  return (
    <FoldCard ariaLabel={title} title={title} explanation={data.line}
      footer={<StuckFooter view={view} data={data} actions={actions} />}>
      {hasBody ? <StuckBody view={view} data={data} botName={botName} tainted={tainted} error={actions.error} /> : null}
    </FoldCard>
  );
}
```

In `web/src/styles/chat.css`, find:

```css
.fold-card--folded .btn {
  flex: none;
}
```

and replace it with:

```css
.fold-card--folded .btn {
  flex: none;
}

/* ---- The Stuck card (stuck flow): the full address, and where it stands */

.stuck-card__url {
  margin: 0;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: var(--sunken);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  overflow-wrap: anywhere;
}

.stuck-card__state {
  margin: 0;
  color: var(--text);
  font-size: var(--fs-sm);
  line-height: 1.45;
}
```

- [ ] **Step 7: Implement the message list dispatch**

In `web/src/components/MessageRow.tsx`, find:

```tsx
// One row of a conversation: a bubble (you on the right, a bot on the
// left), a quiet line (activity, a handoff between bots, a notice), a
// suggestion card or a "Created <name>" card. Split out of MessageList so the list stays a loop.
import { Avatar } from "./Avatar";
import { CreatedBotCard } from "./CreatedBotCard";
import { SuggestionCard } from "./SuggestionCard";
import { linkHost } from "../lib/linkHost";
import { parseCreatedCard, parseSuggestion } from "../lib/team";
import type { AvatarOut, BotOut, MessageOut } from "../api/types";
```

and replace it with:

```tsx
// One row of a conversation: a bubble (you on the right, a bot on the
// left), a quiet line (activity, a handoff between bots, a notice), a
// suggestion card, a "Created <name>" card or a Stuck card. Split out of MessageList so the list stays a loop.
import { Avatar } from "./Avatar";
import { CreatedBotCard } from "./CreatedBotCard";
import { StuckCard } from "./StuckCard";
import { SuggestionCard } from "./SuggestionCard";
import { linkHost } from "../lib/linkHost";
import { parseStuckMessage } from "../lib/stuck";
import { parseCreatedCard, parseSuggestion } from "../lib/team";
import type { AvatarOut, BotOut, MessageOut, StuckCardOut } from "../api/types";
```

Find:

```tsx
  team: readonly BotOut[];
  // Rooms only: a bot's text message gets a Reply that addresses its author.
  onReply?: (author: BotOut) => void;
}
```

and replace it with:

```tsx
  team: readonly BotOut[];
  // Every Stuck card this page knows, by card id: a "stuck" message folds once its card is closed.
  stuck?: Readonly<Record<string, StuckCardOut>>;
  // Rooms only: a bot's text message gets a Reply that addresses its author.
  onReply?: (author: BotOut) => void;
}
```

Find the whole `MessageRow` function:

```tsx
export function MessageRow({ message, runStart, liveText, fallbackName, fallbackAvatar, team, onReply }: MessageRowProps) {
  const kind = message.kind ?? "text";
  if (kind === "handoff" || message.role === "activity" || message.role === "system") {
    return <QuietRow message={message} kind={kind} />;
  }
  const isUser = message.role === "user";
  const author = authorOf(message, team);
  const name = isUser ? "You" : author?.name ?? fallbackName;
  const avatar = author?.avatar ?? fallbackAvatar;
  const created = kind === "bot_created" ? parseCreatedCard(message.body) : null;
  const suggestion = kind === "suggestion" ? parseSuggestion(message.body) : null;
  return (
    <li className={`message ${isUser ? "message--user" : "message--bot"}${runStart ? " message--run-start" : ""}`}>
      {!isUser && avatar ? (
        <span className="message__avatar">
          {runStart ? <Avatar avatar={avatar} status="resting" size={32} label={false} perch={false} decorative /> : null}
        </span>
      ) : null}
      <div className="message__content">
        <div className={`message__author${runStart && !isUser ? "" : " sr-only"}`}>{name}</div>
        {created ? (
          <CreatedBotCard card={created} team={team} />
        ) : suggestion ? (
          <SuggestionCard suggestion={suggestion} team={team} tainted={message.tainted} />
        ) : (
          <div className="message__body">{renderBody(liveText ?? message.body, message.id)}</div>
        )}
        {onReply && author && kind === "text" && !isUser ? (
          <button type="button" className="message__reply" aria-label={`Reply to ${author.name}`} onClick={() => onReply(author)}>
            Reply
          </button>
        ) : null}
      </div>
    </li>
  );
}
```

and replace it with:

```tsx
const NO_STUCK: Readonly<Record<string, StuckCardOut>> = {};

interface RowBodyProps {
  message: MessageOut;
  kind: string;
  liveText?: string;
  name: string;
  team: readonly BotOut[];
  stuck: Readonly<Record<string, StuckCardOut>>;
}

// A card when the body is a valid one for its kind; otherwise the text, its links drawn safely.
function RowBody({ message, kind, liveText, name, team, stuck }: RowBodyProps) {
  const created = kind === "bot_created" ? parseCreatedCard(message.body) : null;
  if (created) return <CreatedBotCard card={created} team={team} />;
  const suggestion = kind === "suggestion" ? parseSuggestion(message.body) : null;
  if (suggestion) return <SuggestionCard suggestion={suggestion} team={team} tainted={message.tainted} />;
  const blocked = kind === "stuck" ? parseStuckMessage(message.body) : null;
  if (blocked) {
    return <StuckCard data={blocked} card={stuck[blocked.card_id]} botName={name} tainted={message.tainted} />;
  }
  return <div className="message__body">{renderBody(liveText ?? message.body, message.id)}</div>;
}

export function MessageRow({
  message, runStart, liveText, fallbackName, fallbackAvatar, team, stuck = NO_STUCK, onReply,
}: MessageRowProps) {
  const kind = message.kind ?? "text";
  if (kind === "handoff" || message.role === "activity" || message.role === "system") {
    return <QuietRow message={message} kind={kind} />;
  }
  const isUser = message.role === "user";
  const author = authorOf(message, team);
  const name = isUser ? "You" : author?.name ?? fallbackName;
  const avatar = author?.avatar ?? fallbackAvatar;
  return (
    <li className={`message ${isUser ? "message--user" : "message--bot"}${runStart ? " message--run-start" : ""}`}>
      {!isUser && avatar ? (
        <span className="message__avatar">
          {runStart ? <Avatar avatar={avatar} status="resting" size={32} label={false} perch={false} decorative /> : null}
        </span>
      ) : null}
      <div className="message__content">
        <div className={`message__author${runStart && !isUser ? "" : " sr-only"}`}>{name}</div>
        <RowBody message={message} kind={kind} liveText={liveText} name={name} team={team} stuck={stuck} />
        {onReply && author && kind === "text" && !isUser ? (
          <button type="button" className="message__reply" aria-label={`Reply to ${author.name}`} onClick={() => onReply(author)}>
            Reply
          </button>
        ) : null}
      </div>
    </li>
  );
}
```

In `web/src/components/MessageList.tsx`, make four edits.

Find:

```tsx
import type { AvatarOut, BotOut, MessageOut } from "../api/types";
```

and replace it with:

```tsx
import type { AvatarOut, BotOut, MessageOut, StuckCardOut } from "../api/types";
```

Find:

```tsx
  team?: readonly BotOut[];
  // Rooms pass this so each bot message offers Reply; Chat does not.
```

and replace it with:

```tsx
  team?: readonly BotOut[];
  // Chat passes the Stuck cards it knows (GET /api/stuck merged with live frames), by card id.
  stuck?: Readonly<Record<string, StuckCardOut>>;
  // Rooms pass this so each bot message offers Reply; Chat does not.
```

Find:

```tsx
export function MessageList({ messages, streaming = {}, botName, botAvatar, team = NO_TEAM, onReply }: MessageListProps) {
```

and replace it with:

```tsx
export function MessageList({ messages, streaming = {}, botName, botAvatar, team = NO_TEAM, stuck, onReply }: MessageListProps) {
```

Find:

```tsx
              team={team}
              onReply={onReply}
```

and replace it with:

```tsx
              team={team}
              stuck={stuck}
              onReply={onReply}
```

- [ ] **Step 8: Implement the Chat (`web/src/pages/Chat.tsx`)**

Find:

```tsx
import * as botsApi from "../api/bots";
import * as threadsApi from "../api/threads";
import { describeError } from "../api/client";
import type { BotOut, MessageOut, ThreadOut } from "../api/types";
import { clearAttention } from "../lib/attention";
import { mergeMessages, nextLocalSeq } from "../lib/messages";
import { freshest } from "../lib/team";
```

and replace it with:

```tsx
import * as botsApi from "../api/bots";
import * as stuckApi from "../api/stuck";
import * as threadsApi from "../api/threads";
import { describeError } from "../api/client";
import type { BotOut, MessageOut, StuckCardOut, ThreadOut } from "../api/types";
import { clearAttention } from "../lib/attention";
import { mergeMessages, nextLocalSeq } from "../lib/messages";
import { mergeStuck } from "../lib/stuck";
import { freshest } from "../lib/team";
```

Find:

```tsx
  useEffect(() => load(), [load]);
  return { bot, setBot, threads, thread, messages, setMessages, error, load };
}
```

and replace it with:

```tsx
  useEffect(() => load(), [load]);
  return { bot, setBot, threads, thread, messages, setMessages, error, load };
}

// Your open Stuck cards, loaded once. Live stuck_card frames keep them current (merged with
// mergeStuck). A failed load is said in the dock, and the cards then show only their line.
function useOpenStuck(onError: (message: string) => void): StuckCardOut[] {
  const [cards, setCards] = useState<StuckCardOut[]>([]);
  useEffect(() => {
    let cancelled = false;
    stuckApi.listStuck()
      .then((loaded) => { if (!cancelled) setCards(loaded); })
      .catch((err: unknown) => { if (!cancelled) onError(describeError(err)); });
    return () => { cancelled = true; };
  }, [onError]);
  return cards;
}
```

Find:

```tsx
  const startNewConversation = useNewConversation(botId, setNotice);
  useEffect(() => { if (botId) clearAttention(botId); }, [botId, live.cursor]);
```

and replace it with:

```tsx
  const startNewConversation = useNewConversation(botId, setNotice);
  const openStuck = useOpenStuck(setNotice);
  useEffect(() => { if (botId) clearAttention(botId); }, [botId, live.cursor]);
```

Find:

```tsx
  const all = mergeMessages(data.messages, live.messagesByThread[thread.id] ?? []);
```

and replace it with:

```tsx
  const all = mergeMessages(data.messages, live.messagesByThread[thread.id] ?? []);
  const stuck = mergeStuck(openStuck, live.stuckCards);
```

Find:

```tsx
        <MessageList messages={all} streaming={live.streaming} botName={bot.name} botAvatar={bot.avatar} team={Object.values(live.bots)} />
```

and replace it with:

```tsx
        <MessageList messages={all} streaming={live.streaming} botName={bot.name} botAvatar={bot.avatar}
          team={Object.values(live.bots)} stuck={stuck} />
```

`Chat` grows to 47 lines, which is still under 50.

- [ ] **Step 9: Implement My turn on Home (`web/src/pages/Home.tsx`) and its styles**

Find:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
```

and replace it with:

```tsx
import { useCallback, useEffect, useId, useRef, useState } from "react";
```

Find:

```tsx
import * as botsApi from "../api/bots";
import * as chatsApi from "../api/chats";
import { describeError } from "../api/client";
import type { BotOut, ChatRowOut } from "../api/types";
import type { LiveState } from "../store/live";
import { onTeamChanged } from "../lib/teamChanged";
```

and replace it with:

```tsx
import * as botsApi from "../api/bots";
import * as chatsApi from "../api/chats";
import * as stuckApi from "../api/stuck";
import { describeError } from "../api/client";
import type { BotOut, ChatRowOut, StuckCardOut } from "../api/types";
import type { LiveState } from "../store/live";
import { mergeStuck, openStuckCards, stuckTitle } from "../lib/stuck";
import { onTeamChanged } from "../lib/teamChanged";
```

Find:

```tsx
// Reloads when a message is stored or the team changes (a created or retired
// bot). Only the newest load may answer: an older one that lands last is dropped.
function useHomeData(live: LiveState) {
  const [bots, setBots] = useState<BotOut[] | null>(null);
  const [rows, setRows] = useState<ChatRowOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latestLoad = useRef(0);
  const reload = useCallback(() => {
    const load = ++latestLoad.current;
    setError(null);
    Promise.all([botsApi.listBots(), chatsApi.listChats()])
      .then(([loadedBots, loadedRows]) => {
        if (load === latestLoad.current) { setBots(loadedBots); setRows(loadedRows); }
      })
      .catch((err: unknown) => { if (load === latestLoad.current) setError(describeError(err)); });
  }, []);
  const messages = storedMessageCount(live);
  const team = Object.keys(live.bots).length;
  useEffect(() => reload(), [reload, messages, team]);
  useEffect(() => onTeamChanged(reload), [reload]);
  return { bots, rows, error, reload };
}
```

and replace it with:

```tsx
// Home reloads when a message is stored or the team changes (a created or retired bot).
// useHomeData and useStuckList share this trigger, so either change reloads both.
function useReloadOn(live: LiveState, reload: () => void) {
  const messages = storedMessageCount(live);
  const team = Object.keys(live.bots).length;
  useEffect(() => reload(), [reload, messages, team]);
  useEffect(() => onTeamChanged(reload), [reload]);
}

// Your bots and chats. Only the newest load may answer: an older one that lands last is dropped.
function useHomeData(live: LiveState) {
  const [bots, setBots] = useState<BotOut[] | null>(null);
  const [rows, setRows] = useState<ChatRowOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latestLoad = useRef(0);
  const reload = useCallback(() => {
    const load = ++latestLoad.current;
    setError(null);
    Promise.all([botsApi.listBots(), chatsApi.listChats()])
      .then(([loadedBots, loadedRows]) => {
        if (load === latestLoad.current) { setBots(loadedBots); setRows(loadedRows); }
      })
      .catch((err: unknown) => { if (load === latestLoad.current) setError(describeError(err)); });
  }, []);
  useReloadOn(live, reload);
  return { bots, rows, error, reload };
}

// Your open Stuck cards for My turn, loaded on their own: a failed GET /api/stuck never hides
// the bots and chats, and only My turn says so, with Retry. Same trigger as useHomeData, so a
// new card's chat line reloads it. Only the newest load may answer.
function useStuckList(live: LiveState) {
  const [cards, setCards] = useState<StuckCardOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latestLoad = useRef(0);
  const reload = useCallback(() => {
    const load = ++latestLoad.current;
    setError(null);
    stuckApi.listStuck()
      .then((loaded) => { if (load === latestLoad.current) setCards(loaded); })
      .catch((err: unknown) => { if (load === latestLoad.current) setError(describeError(err)); });
  }, []);
  useReloadOn(live, reload);
  return { cards, error, reload };
}
```

Find:

```tsx
function MainBotHero({ bot }: { bot: BotOut }) {
  return (
    <Link to={`/bots/${bot.id}`} className="main-bot" aria-label={`${bot.name}, your main bot`}>
      <Avatar avatar={bot.avatar} status={bot.status} activity={bot.activity} size={120} perch={false} label={false} decorative star />
      <span className="main-bot__name">{bot.name}</span>
    </Link>
  );
}
```

and add after it:

```tsx

interface MyTurnProps {
  cards: readonly StuckCardOut[];
  bots: Readonly<Record<string, BotOut>>;
  error: string | null;
  onRetry: () => void;
}

// The Stuck cards waiting on you, newest first. Each row opens that bot's chat on the card's thread.
// Shown only while a card is open, or while the list failed to load: then its own ErrorNotice says
// why, with Retry, and the rest of Home is untouched. A card of a bot no longer on the team is left out.
function MyTurn({ cards, bots, error, onRetry }: MyTurnProps) {
  const titleId = useId();
  const shown = cards.filter((card) => bots[card.bot_id]);
  if (shown.length === 0 && !error) return null;
  return (
    <section className="my-turn" aria-labelledby={titleId}>
      <h2 id={titleId} className="my-turn__title">My turn</h2>
      {error ? <ErrorNotice message={error} onRetry={onRetry} /> : null}
      {shown.length > 0 ? (
        <ul className="my-turn__list">
          {shown.map((card) => (
            <li key={card.id}>
              <Link className="my-turn__row" to={`/bots/${card.bot_id}?thread=${encodeURIComponent(card.thread_id)}`}>
                <span className="my-turn__mark" aria-hidden="true">!</span>
                <span className="my-turn__text">
                  {`${bots[card.bot_id].name} · ${stuckTitle(card.host, card.url)}`}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
```

Find:

```tsx
  const { bots, rows, error, reload } = useHomeData(live);
```

and replace it with:

```tsx
  const { bots, rows, error, reload } = useHomeData(live);
  const stuckList = useStuckList(live);
```

Find:

```tsx
  const main = Object.values(byId).find((bot) => bot.is_primary);
```

and replace it with:

```tsx
  const main = Object.values(byId).find((bot) => bot.is_primary);
  const waiting = openStuckCards(mergeStuck(stuckList.cards, live.stuckCards));
```

Find:

```tsx
      {main && !query.trim() ? <MainBotHero bot={main} /> : null}
```

and replace it with:

```tsx
      {main && !query.trim() ? <MainBotHero bot={main} /> : null}
      {!query.trim() ? (
        <MyTurn cards={waiting} bots={byId} error={stuckList.error} onRetry={stuckList.reload} />
      ) : null}
```

The Home-wide `ErrorNotice` (`{error ? … onRetry={reload} …}`) stays as it is: it speaks only for the bots and chats, and its Retry reloads only them. `Home` grows to 29 lines, `MyTurn` is 25 and `useStuckList` 14, all under 50.

In `web/src/styles/home.css`, find:

```css
/* ---- Chat list ------------------------------------------------------- */
```

and replace it with:

```css
/* ---- My turn: the Stuck cards waiting on you (stuck flow) ------------ */

.my-turn {
  margin: 0 16px 12px;
  padding: 10px 12px 8px;
  border: 1px solid var(--coral-edge);
  border-radius: var(--radius-md);
  background: var(--coral-tint);
}

.my-turn__title {
  margin: 0 0 4px;
  color: var(--coral);
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.my-turn__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.my-turn__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: var(--fs-sm);
  text-decoration: none;
}

.my-turn__row:hover {
  background: var(--raised);
}

.my-turn__mark {
  flex: none;
  color: var(--coral);
  font-weight: 700;
}

.my-turn__text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* A failed Stuck list is said inside My turn, so the notice drops its page gutter. */
.my-turn .error-notice {
  margin: 4px 0 6px;
}

/* ---- Chat list ------------------------------------------------------- */
```

- [ ] **Step 10: Implement the notification (`web/src/lib/attention.ts`)**

Find:

```ts
// Bots that finished or asked for you while Roost's tab was hidden (S1.10):
// a highlighted Home row, plus a browser notification when the user allowed them.
```

and replace it with:

```ts
// Bots that finished, asked for you or got Stuck while Roost's tab was hidden (S1.10, stuck flow):
// a highlighted Home row, plus a browser notification when the user allowed them.
```

Find:

```ts
  if (frame.type === "bot_status" && frame.status === "asking_you") {
    const bot = bots[frame.bot_id];
    if (!bot?.notify) return null;
    return { botId: bot.id, title: `${bot.name} needs you`, body: frame.activity ?? "" };
  }
```

and replace it with:

```ts
  if (frame.type === "bot_status" && (frame.status === "asking_you" || frame.status === "stuck")) {
    const bot = bots[frame.bot_id];
    if (!bot?.notify) return null;
    const title = frame.status === "stuck" ? `${bot.name} is stuck` : `${bot.name} needs you`;
    return { botId: bot.id, title, body: frame.activity ?? "" };
  }
```

In `web/src/hooks/useAttention.ts`, find:

```ts
// Mounted once, in Layout: while the tab is hidden, a bot with notifications
// on that finishes a reply or turns Asking you is highlighted and notified.
```

and replace it with:

```ts
// Mounted once, in Layout: while the tab is hidden, a bot with notifications
// on that finishes a reply, turns Asking you or gets Stuck is highlighted and notified.
```

- [ ] **Step 11: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/stuck.test.ts tests/StuckCard.test.tsx tests/live.test.ts tests/MessageList.test.tsx tests/attention.test.ts tests/Home.test.tsx tests/Chat.test.tsx tests/ChatThreads.test.tsx`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm test`
Expected: PASS. This covers every web test, including `Room.test.tsx`, `Profile.test.tsx`, `CreatedBotCard.test.tsx`, `SuggestionCard.test.tsx`, `team.test.ts` and `useLiveStore.test.ts`, which must stay green.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm run build && npm run size`
Expected: `tsc -b` reports no errors, `vite build` succeeds, and `npm run size` prints `entry assets/index-….js: … B gzip (budget 257400 B)` with no "Over the main-bundle budget" line.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vocabulary.py -q`
Expected: PASS. The new copy uses Stuck, Take control and Give it back, and none of the banned strings ("Take the wheel", ">Desk<", " in Talk", …).

- [ ] **Step 12: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add web/src/api/types.ts web/src/api/stuck.ts web/src/lib/stuck.ts web/src/store/live.ts \
  web/src/components/StuckCard.tsx web/src/components/MessageRow.tsx web/src/components/MessageList.tsx \
  web/src/pages/Chat.tsx web/src/pages/Home.tsx web/src/lib/attention.ts web/src/hooks/useAttention.ts \
  web/src/styles/chat.css web/src/styles/home.css \
  web/tests/fixtures.ts web/tests/stuck.test.ts web/tests/StuckCard.test.tsx web/tests/live.test.ts \
  web/tests/MessageList.test.tsx web/tests/attention.test.ts web/tests/Home.test.tsx web/tests/Chat.test.tsx \
  web/tests/ChatThreads.test.tsx
git commit -m "feat: the Stuck card in the chat, My turn on Home and the Stuck notification"
```

---

### Task 9: E2E and the docs

Design §5 (E2E: Stuck card in chat → Take control → Give it back → the bot continues) and R11 (a fake `login` page, not the challenge page): the whole stuck flow, end to end in the browser, against the scripted gateway that `make e2e` starts (`ROOST_MODEL=scripted`, `ROOST_MODEL_SCRIPT=web/e2e/fixtures/team-script.json`, `ROOST_DESK=fake`).
- **The fake sign-in wall.** `FakeDesk` serves `https://login.example/` from Task 2's `FAKE_PAGES`. The first load is `LOGIN_WALL` (a password field on a thin page titled "Sign in · …", which Task 1 detects as `login`). Every later load is `SIGNED_IN`. A `login` block gets neither rung 1's 8-second wait nor its repeat (Task 4), so the card shows at once. The challenge path stays covered by the Task 4 and Task 5 integration tests.
- **A new scripted bot, "Porter".** Nobody else uses the name. The names already taken are Helper, Chief, HiMap SEO, HiMap Social, Scout, Scout Two, Quill, Office and Life admin. Porter's three steps are used in this order:
  1. The first run (your message) calls `open_page`. The page is a sign-in wall, so the run stops after that step and the model is not called again (Task 5).
  2. Take control, then Give it back (`/clear`), queues the continue item, and that run calls `read_page`, which gets `SIGNED_IN`. Give it back releases the hold first (Task 7), so the read is not refused.
  3. The same run then answers "Signed in and done.".
- **Spec order.** Playwright runs the spec files alphabetically on one worker: `computer`, `every-bot`, `main-bot`, `profile`, `records`, `stuck`, `team`. `stuck.spec.ts` uses only Porter's script, so the other specs see no change. At its end Porter's card is closed and Porter is Resting, so `team.spec.ts` sees no My turn section.
- **Scoping.** On a desktop viewport, Home lives in the left `<aside aria-label="Chats pane">` on every route (`web/src/components/Layout.tsx`), and the open chat is the `<main>` (`detailPane`). So every assertion is scoped:
  - card assertions to `detailPane`;
  - My turn assertions to the Chats pane;
  - the chat-row assertions to the "Chats" list inside the Chats pane.
- **A fast pytest mirror.** `tests/test_stuck_e2e_script.py` runs the same path in pytest in under a second. It loads the real `team-script.json`, runs it against the real `FAKE_PAGES`, takes control on the `ControlLock` and gives it back through `StuckService.clear`. A change to the script, the fake pages or the card's words then fails `uv run pytest`, not only the slower `make e2e`.
- **Docs.** The CLAUDE.md Documentation Map gains the design and the plan. The Architecture section gains one short paragraph about the stuck flow. `docs/specs/2026-10-12-roost-design.md` is **not** edited.

**Files:**
- Create:
  - `web/e2e/stuck.spec.ts`
  - `tests/test_stuck_e2e_script.py`
- Modify:
  - `web/e2e/fixtures/team-script.json`: a new `"Porter"` key with three steps.
  - `CLAUDE.md`: two Documentation Map lines and one Architecture paragraph.
- Test: `web/e2e/stuck.spec.ts` and `tests/test_stuck_e2e_script.py`.

**Interfaces:**
- Consumes:
  - **Task 1:** `detect_block(LOGIN_WALL).reason == "login"`, and `detect_block(SIGNED_IN) is None`.
  - **Task 2:** `FakeDesk(bot_id)` serves `FAKE_PAGES` by default, with `FAKE_PAGES["https://login.example/"] == (LOGIN_WALL, SIGNED_IN)`. After `open_page` of a served URL, `read_page` returns that URL's next page (with `status=None`). `FakeDesk.open_page_calls` still records every `open_page`. `roost.desk.fake_pages` exports `LOGIN_URL` and `SIGNED_IN`.
  - **Task 3:**
    - `StuckStore(config)` and `open_for_bot(user_id, bot_id)`;
    - `CardState.CLEARED`, and `StuckCard.reason` / `.host` / `.request`;
    - `stuck_line(card)` starts with `"I'm stuck on login.example: a sign-in page."` (ASCII apostrophe; `REASON_WORDS["login"] == "a sign-in page"`);
    - `stuck_message_body(card)` is JSON with a `"line"` key.
  - **Task 4:** a chat run's `open_page` of a `login` page sets `ToolRunner.block` at once: no wait, no repeat, so `open_page_calls` has one entry. The tool result of a clear page is `wrap_page(page)`, which carries the page text.
  - **Task 5:**
    - `TurnRunner(config, bots, talk, events, desks, model, activity, *, control=..., stuck=...)`;
    - the `kind="stuck"` bot message, and no empty bot bubble for the blocked turn;
    - status `BotStatus.STUCK` while a card is open, and `RESTING` after the continue run;
    - the card's `request` is the run's item bodies (here, the one message text).
  - **Task 6:** `FakeMainBrowser()` from `roost.desk.main_browser`.
  - **Task 7:**
    - `StuckService(store, talk, events, turns, control, main_browser)`;
    - `async clear(user_id, card_id) -> StuckCard | None`, which closes the card, calls `control.give_back(bot_id)`, posts the `kind="card_answer"` line `"I cleared the block on login.example. Read the page again and carry on with: <request>"` and queues the continue item;
    - `POST /api/stuck/{id}/clear` and `GET /api/stuck`.
  - **Task 8: the accessible names the spec relies on** (Task 8's Produces list and its vitest tests pin them):
    - **The open Stuck card** is a `FoldCard`: a `role="group"` named `Stuck on {host}` ("Stuck on login.example"). Its explanation is `data.line`, the server's line verbatim. Its buttons are named exactly "Take control", "Try again", "Use my main Brave" (only when there is an address) and "Give up".
    - **Holding** (after Take control): the card shows "You have control. Clear it in {botName}'s window, then give it back." (ASCII apostrophe) and a "Give it back" button, which calls `/clear`.
    - **The closed card** folds to a `FoldedLine`: a group named, and reading, "Cleared: login.example".
    - **Home's My turn** (inside the Chats pane) is a region named "My turn" (a `<section>` labelled by its `<h2>`), rendered only while a card is open. Each row is a link to `/bots/{bot_id}?thread={thread_id}` named `{bot} · Stuck on {host}` ("Porter · Stuck on login.example").
  - **Existing code:**
    - `web/e2e/helpers.ts`: `signIn`, `createBot`, `say` and `detailPane`;
    - the "Chats" list (`<ul aria-label="Chats">`, `web/src/components/ChatList.tsx`) and its row links (`/^Porter\b/`). A Stuck bot is busy there, so its row shows the status line ("Stuck · …") instead of its preview; once it rests the row shows the latest message preview;
    - the card's Take control calls `POST /api/bots/{bot_id}/control` (`takeControl` in `web/src/api/computer.ts`, `roost/gateway/routes/desk.py`), which holds `app.state.control` and needs no awake computer;
    - `ScriptedTeamModel.from_file(path)` (`roost/llm/scripted_team.py`), which takes JSON `{"Bot": [[{"tool": str, "args": {...}} | {"text": str}], ...]}`;
    - `tests/team_helpers.py`: `RecordingModel`, `Rig`, `make_bot`, `make_rig`, `send` and `wait_idle`;
    - `ControlLock()` with `take(bot_id)` and `held(bot_id)` (`roost/desk/control.py`).
- Produces: the scripted bot name "Porter" (taken from now on for E2E specs), and the CLAUDE.md map entries for the stuck flow. No code interface.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_stuck_e2e_script.py`:

```python
"""The Porter script from the E2E (web/e2e/fixtures/team-script.json) against
the pages FakeDesk serves (design §5, R11): stuck on the sign-in wall, then done
after Take control and Give it back. A fast mirror of web/e2e/stuck.spec.ts, so a
change to the script, the fake pages or the card's words fails here before the E2E runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from roost.bots.models import BotStatus
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.control import ControlLock
from roost.desk.fake_pages import LOGIN_URL, SIGNED_IN
from roost.desk.main_browser import FakeMainBrowser
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.stuck.models import CardState
from roost.stuck.service import StuckService
from roost.stuck.store import StuckStore
from roost.talk.runner import TurnRunner
from team_helpers import RecordingModel, Rig, make_bot, make_rig, send, wait_idle

E2E_SCRIPT = Path(__file__).resolve().parents[1] / "web" / "e2e" / "fixtures" / "team-script.json"
# The words web/e2e/stuck.spec.ts types and waits for.
E2E_REQUEST = "check my orders on https://login.example/"
E2E_CARD_LINE = "I'm stuck on login.example: a sign-in page."
E2E_CONTINUE_LINE = "I cleared the block on login.example."
E2E_REPLY = "Signed in and done."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _e2e_rig(cfg, lock: ControlLock, stuck: StuckStore) -> Rig:
    """The gateway's wiring: the E2E's script, and one control lock and card store shared with StuckService."""
    base = make_rig(cfg, RecordingModel(ScriptedTeamModel.from_file(E2E_SCRIPT)))
    runner = TurnRunner(cfg, base.bots, base.talk, base.events, base.desks, base.model, ActivityBoard(),
                        control=lock, stuck=stuck)
    return Rig(runner=runner, bots=base.bots, talk=base.talk, events=base.events, desks=base.desks, model=base.model)


async def test_the_e2e_script_gets_porter_stuck_on_the_sign_in_page_then_done_after_give_it_back(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Porter")
    lock, stuck = ControlLock(), StuckStore(cfg)
    rig = _e2e_rig(cfg, lock, stuck)
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, E2E_REQUEST)
    await wait_idle(rig.runner, timeout=8)

    card = await stuck.open_for_bot(user_id, bot.id)
    assert card is not None
    assert (card.reason, card.host, card.request) == ("login", "login.example", E2E_REQUEST)
    assert len(rig.model.requests) == 1                          # the run stopped after the open_page step
    assert (await BotStore(cfg).get(user_id, bot.id)).status == BotStatus.STUCK
    [card_message] = [m for m in await rig.talk.list_messages(user_id, thread.id) if m.kind == "stuck"]
    assert json.loads(card_message.body)["line"].startswith(E2E_CARD_LINE)

    lock.take(bot.id)                                            # the card's Take control
    service = StuckService(stuck, rig.talk, rig.events, rig.runner, lock, FakeMainBrowser())
    assert (await service.clear(user_id, card.id)).state == CardState.CLEARED   # Give it back
    assert lock.held(bot.id) is None
    await wait_idle(rig.runner, timeout=8)

    messages = await rig.talk.list_messages(user_id, thread.id)
    [continue_line] = [m for m in messages if m.kind == "card_answer"]
    assert continue_line.role == "user" and continue_line.body.startswith(E2E_CONTINUE_LINE)
    assert [m.body for m in messages if m.role == "bot" and m.kind == "text"] == [E2E_REPLY]
    assert SIGNED_IN.text in [t.text for t in rig.model.requests[-1].turns if t.role == "tool"][-1]
    assert rig.desks.for_bot(bot.id).open_page_calls == [LOGIN_URL]   # read again, never reopened
    assert await stuck.open_for_bot(user_id, bot.id) is None
    assert (await BotStore(cfg).get(user_id, bot.id)).status == BotStatus.RESTING
```

Create `web/e2e/stuck.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { createBot, detailPane, say, signIn } from "./helpers";

// Stuck flow, design §5 and R11, against ROOST_DESK=fake + fixtures/team-script.json ("Porter").
// FakeDesk serves https://login.example/ as a sign-in wall first and the signed-in page after it
// (roost/desk/fake_pages.py). A sign-in wall skips rung 1's 8-second wait, so the card comes at once.
const HOST = "login.example";
const CARD_LINE = `I'm stuck on ${HOST}: a sign-in page.`;
const HOLDING = "You have control. Clear it in Porter's window, then give it back.";
const MY_TURN_ROW = `Porter · Stuck on ${HOST}`;
const REPLY = "Signed in and done.";
const SLOW = { timeout: 20_000 };

test("a bot stuck on a sign-in page: the Stuck card, My turn on Home, then Take control, Give it back and it carries on", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page);
  await createBot(page, "Porter", "Checks my orders on shop sites");
  const detail = detailPane(page);
  const listPane = page.getByRole("complementary", { name: "Chats pane" });
  const porterRow = listPane.getByRole("list", { name: "Chats" }).getByRole("link", { name: /^Porter\b/ });
  await say(page, "Porter", "check my orders on https://login.example/");

  // The card is a FoldCard: a group named after its host that carries the server's line verbatim.
  const card = detail.getByRole("group", { name: `Stuck on ${HOST}` });
  await expect(card).toBeVisible(SLOW);
  await expect(card).toContainText(CARD_LINE);
  for (const name of ["Take control", "Try again", "Use my main Brave", "Give up"]) {
    await expect(card.getByRole("button", { name, exact: true })).toBeVisible();
  }
  // A Stuck bot's row shows its status line ("Stuck · …"), never its preview ("▣ Stuck on login.example").
  await expect(porterRow).toContainText(/Stuck(?! on)/, SLOW);

  // Home lives in the Chats pane on every desktop route. After a reload My turn still lists the card
  // (GET /api/stuck), and its row opens the chat.
  await page.goto("/");
  const myTurn = listPane.getByRole("region", { name: "My turn" });
  await expect(myTurn).toBeVisible(SLOW);
  await myTurn.getByRole("link", { name: MY_TURN_ROW }).click();
  await expect(detail.getByRole("heading", { name: "Porter", exact: true })).toBeVisible();

  // Take control, then Give it back (/clear): the card folds and the continue run reads the page again.
  await card.getByRole("button", { name: "Take control", exact: true }).click();
  await expect(card).toContainText(HOLDING);
  await card.getByRole("button", { name: "Give it back", exact: true }).click();
  await expect(detail.getByRole("group", { name: `Cleared: ${HOST}` })).toBeVisible(SLOW);
  await expect(detail.getByText(REPLY)).toBeVisible(SLOW);
  // Resting again: the row shows the reply as its preview (a Stuck or On it bot shows its status there instead).
  await expect(porterRow).toContainText(REPLY, SLOW);
  await expect(myTurn).toBeHidden(SLOW);
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_e2e_script.py -q`
Expected: FAIL with `AssertionError` at `assert card is not None`. `team-script.json` has no "Porter" key, so `ScriptedTeamModel` falls back to its echo and replies "I heard: check my orders on https://login.example/". No `open_page` runs and no card opens.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run this, as one shell call. It uses the same port rule as `make e2e`: 5173 while the live gateway holds 18800. The Chromium build `make e2e` installed in S1 is reused. If Playwright reports that the browser executable is missing, run `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx playwright install chromium` (the disk guard above has passed), then run this again.

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web && \
port=18800 && if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi && \
npm run build && ROOST_E2E_PORT=$port npx playwright test e2e/stuck.spec.ts
```

Expected: 1 failed. The failure is `Timed out 20000ms waiting for expect(locator).toBeVisible()` on the group named "Stuck on login.example", because Porter only echoes "I heard: check my orders on https://login.example/".

- [ ] **Step 4: Script Porter**

`web/e2e/fixtures/team-script.json`, at the end of the file. Find:

```json
    [{ "text": "Logged 12.50 EUR to food." }]
  ]
}
```

Replace with:

```json
    [{ "text": "Logged 12.50 EUR to food." }]
  ],
  "Porter": [
    [{ "tool": "open_page", "args": { "url": "https://login.example/" } }],
    [{ "tool": "read_page", "args": {} }],
    [{ "text": "Signed in and done." }]
  ]
}
```

Each step matches `roost/llm/scripted_team.py`: `_ToolStep` (`tool`, plus `args` as a dict) or `_TextStep` (`text`), both with `extra="forbid"`. The first step's tool call ends with `TurnDone("tool_use")`. The block stops the run after it, so the model is called only once in the first run. The continue run uses steps 2 and 3.

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_stuck_e2e_script.py tests/test_scripted_team_model.py tests/test_fake_desk.py tests/test_stuck_runs.py -q`
Expected: PASS. `test_scripted_team_model.py` still loads JSON scripts. `test_fake_desk.py` covers the served pages, and `test_stuck_runs.py` (Task 5) covers the run side.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run this, as one shell call:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web && \
port=18800 && if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi && \
ROOST_E2E_PORT=$port npx playwright test e2e/stuck.spec.ts
```

Expected: 1 passed. The build from Step 3 is still current, because only the fixture JSON changed.

If it fails:
- **"resolved to 2 elements" (strict mode).** A query escaped its pane. Scope it to `detail`, `listPane` or the "Chats" list; never loosen it with `.first()`.
- **The My turn region or link, the card's group or its buttons are not found.** Check them against Task 8's names listed under Interfaces. Fix the component, never the expected texts.
- **The reply never comes after Give it back.** The continue run's `read_page` waited on a hold that `/clear` did not release (`StuckService.clear` must call `control.give_back`); `tests/test_stuck_e2e_script.py` fails the same way.

- [ ] **Step 6: The docs**

`CLAUDE.md`, the Documentation Map. Find:

```markdown
- `docs/plans/2026-10-14-roost-s1-simple-like-grok.md` — S1: every bot gets every tool, the main bot from the start and `create_bot`, schema v11 (`bots.notify`), the computer's screenshots and Take control, and the web face as Home · Chat · Profile · Board.
```

Replace with:

```markdown
- `docs/plans/2026-10-14-roost-s1-simple-like-grok.md` — S1: every bot gets every tool, the main bot from the start and `create_bot`, schema v11 (`bots.notify`), the computer's screenshots and Take control, and the web face as Home · Chat · Profile · Board.
- `docs/plans/2026-10-14-roost-stuck-flow-design.md` — the stuck flow (piece A) design: the detector, the Stuck card, Take control / Try again / Give it back, and "Use my main Brave" (open only). Its §6 (R1–R11) overrides the earlier sections.
- `docs/plans/2026-10-14-roost-stuck-flow.md` — the stuck flow plan: schema v12 (`stuck_cards`), `roost/desk/stuck.py`, `roost/stuck/`, `ask_for_help`, the `/api/stuck` routes, the keeper's `main-browser/open`, and My turn on Home.
```

`CLAUDE.md`, the Architecture section, at the end of the "Every bot gets every tool" paragraph. Find:

```markdown
A bot's computer has screenshots and an in-memory control lock (`roost/desk/control.py`).
```

Replace with:

```markdown
A bot's computer has screenshots and an in-memory control lock (`roost/desk/control.py`).

A bot that meets a human check, a sign-in page or a code check stops cleanly (the stuck flow, `docs/plans/2026-10-14-roost-stuck-flow-design.md` §6): the pure detector (`roost/desk/stuck.py`) or the bot's own `ask_for_help` raises a block, and in a run of your own chat messages the run ends with a Stuck card (`roost/stuck/`, schema v12 `stuck_cards`) while the bot shows Stuck; handoffs, rooms and routines get a loud `Blocked:` tool result instead. The card's Give it back / Try again (`POST /api/stuck/{id}/clear`) posts your continue line and queues a `card_answer` item that carries the task on, Give up ends it, and "Use my main Brave" only has the keeper run `/usr/bin/open -a "Brave Browser" <url>` (no shell, no automation, no debug port, no profile access).
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -c "roost-stuck-flow" CLAUDE.md`
Expected: `3` (two map lines and the Architecture paragraph, which is one line).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vocabulary.py -q`
Expected: PASS. The new lines do not use "Take the wheel" or "| Desk |".

- [ ] **Step 7: Full verification**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest -q`
Expected: PASS, the whole suite.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80`
Expected: PASS with `Required test coverage of 80% reached`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm test && npm run build && npm run size`
Expected: every vitest file passes (Task 8's `StuckCard`, `stuck`, attention, live, `MessageList` and Home tests included), the build succeeds, and the size check reports the entry chunk within `bundle-budget.json`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && make e2e`
Expected: every spec passes (`computer`, `every-bot`, `main-bot`, `profile`, `records`, `stuck`, `team`). `make e2e` picks port 5173 when the live gateway holds 18800. It never touches `~/Roost/data`, because the throwaway gateway uses `ROOST_DATA_DIR=$(mktemp -d)`. No real browser of yours is opened: "Use my main Brave" is never pressed, and fake mode's `FakeMainBrowser` only records.

- [ ] **Step 8: Commit**

The stuck-flow design and plan are listed so the new map lines never point at an uncommitted file. Before this plan ran, the design was modified and the plan untracked. `git add` of an unchanged tracked file does nothing.

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/e2e/stuck.spec.ts web/e2e/fixtures/team-script.json tests/test_stuck_e2e_script.py CLAUDE.md \
  docs/plans/2026-10-14-roost-stuck-flow-design.md docs/plans/2026-10-14-roost-stuck-flow.md && \
git commit -m "test: E2E for the stuck flow; docs: the stuck flow in CLAUDE.md"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the six files above is still listed as modified or untracked.

