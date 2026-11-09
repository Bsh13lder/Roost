# Roost Live Control (Take control, Grok-style) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take control opens a **live screen** of the bot's own page inside Roost. You click, double-click, scroll, type and paste straight into it; pop-ups are followed; Give it back can say which account you used, which Roost keeps in **Vault: site logins** and tells the bot. Nothing you type is ever logged, stored, published or shown to the bot.

**Architecture:**
- **CDP plumbing.** `CdpClient` gains `subscribe()`: a bounded, drop-oldest queue of events that ends when the connection ends. A send on a closed socket becomes `CdpClientError`.
- **Input.** `roost/desk/live_input.py` checks every input frame with pydantic (an allow-list of keys, a capped paste, frame-space points) and maps it to the exact `Input.*` CDP calls. A per-socket rate limit drops the excess.
- **The session.** `LiveSession` (`roost/desk/live.py`) screencasts one page of the bot's running browser over that browser's own CDP connection (the keeper's relay takes one client per bot, so it shares the `CdpClient` the bot's tab uses). It acks every frame (about 10 fps), follows pop-ups opened by the bot's page and comes back when they close, follows the address bar, and sends input. `Desk.live_view()` hands it a running browser's page and never starts one; `FakeDesk` hands it `FakeCdp`, a scripted in-memory screencast.
- **The socket.** `WS /api/bots/{id}/live` (`roost/gateway/routes/live.py`) accepts only this Mac, Roost's own origin, a signed-in user, the user's own bot and a held control, and closes with a specific code otherwise. It sends each frame as a JSON header then the JPEG with one frame in flight, and closes with 4000 "Given back." as soon as control is released. An input is sent only while the user still holds control.
- **Secrets.** `read_page` skips every node inside a text box, search box, combo box or spin button, so typed values never reach a bot.
- **Bot windows.** They step out of the way when the bot's tab is created (minimised, or moved far away, per the Task 1 spike). **Show window on Mac** (`POST /api/bots/{id}/window/show`) brings one back.
- **The Vault.** Schema v14 `site_logins` (`roost/vault/`). Give it back takes an optional `account`: the Stuck card's `/clear` puts "I signed in on {host} as {label}." in its continue line; the Computer tab's `DELETE /control` posts it as your message. The bot's prompt names its accounts. The Computer tab lists them, each with Forget.
- **The web.** `LiveScreen` fills the Computer tab while you hold control: the address bar, Back, Reload, Show window on Mac, and Give it back with "Which account did you use?". The Stuck card's Take control opens it.

**Tech Stack:** The S1 and stuck-flow stack, with no new dependency:
- Python 3.12+ (uv; the venv runs 3.14), FastAPI / Starlette 1.7 (`TestClient(app, client=(host, port))` sets the peer), aiosqlite, pydantic 2, `websockets` 17, uvicorn, `cryptography` (`enc:v2` + AAD).
- Vite, React 19 and TypeScript, tested with vitest + Testing Library and Playwright.

**Spec:** `docs/plans/2026-10-15-roost-live-control-design.md` (binding). Background: `docs/specs/2026-10-12-roost-design.md` §5.5 (live frames, input events, secrets out of snapshots), D7, §7.4 vocabulary; the stuck flow (`docs/plans/2026-10-14-roost-stuck-flow-design.md` §6) and S1.8 (`roost/desk/control.py`).

**Design decision — bot windows (L3), set by Task 1:** Not measured yet. Task 1 Step 4 replaces this paragraph with exactly one of the three lines it lists. Task 7 builds the variant that line names (`minimise`, `behind` or `leave`).

**Where the design did not fit the code (decided here):**
- **D1. This Mac in the gateway container.** The always-on gateway runs in Docker (`docker-compose.yml`), so a browser on this Mac reaches it from a Docker network address, never 127.0.0.1. The peer rule is therefore: 127.0.0.1 or ::1; or, in the gateway container (`config.in_container`), any peer, because compose publishes the port on the Mac's 127.0.0.1 alone (pinned by `tests/test_compose.py`). In both cases a request that carries `Forwarded`, `X-Forwarded-For` or `X-Real-IP` is refused: something forwarded it, so it is not this Mac.
- **D2. The host is encrypted too.** CLAUDE.md allows plaintext only for ids, timestamps, status, avatar JSON and template ids. So `site_logins.host` is `enc:v2` (AAD `site_logins:host`) as well as `label`, and the design's "unique on (user_id, bot_id, host)" is kept as unique on `(user_id, bot_id, host_key)`, where `host_key` is HMAC(dek, normalised host), the same way `notes.title_key` works.
- **D3. One queue for target events.** `subscribe(method, session_id)` also takes a tuple of methods that share one queue in arrival order. `LiveSession` needs `targetCreated` and `targetDestroyed` in the browser's own order; with separate queues a pop-up that opens and closes at once could leave the screen on a dead page.
- **D4. Which site an account is for.** It is the Stuck card's host when there is one, else the host of the page the bot's computer shows now (read without starting its browser). With neither, the request is a 400 before anything changes. The web asks "Which account did you use?" only when it knows a site.
- **D5. The Computer tab's message is queued.** "As a user message" is done as `POST /messages` does it: your line goes into the bot's latest chat and is queued as a `message` work item, so the bot acknowledges it.
- **D6. Two close codes the design implies.** 4410 "asleep" (the face offers Open it) and 4503 "The bot's computer stopped answering." (the face offers Retry), plus 4401 "Sign in first." as `/api/events` already does.
- **D7. The spike also checks screenshots.** The Computer tab's 3-second screenshots (S1.8) must keep working for a window set aside, so Task 1 measures `Page.captureScreenshot` too.

## Global Constraints

- **Path guard, first in every task:**
  - `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` must print `/Users/blckit/Desktop/Code_Projects/roost`.
  - `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` must print `night-1`.
  - If either check fails, stop.
- **Where you may edit:**
  - Edit only under `/Users/blckit/Desktop/Code_Projects/roost`.
  - `/Users/blckit/Desktop/Code_Projects/lazyclaw` is never touched. That includes `lazyclaw/data`, its containers and its `make` targets.
  - Never touch the user's running gateway (Docker, `127.0.0.1:18800`) or keeper (launchd, `127.0.0.1:18801`).
- **Clean room (spec §10.3):**
  - Never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`.
  - Do not use browser MCP tools.
  - Only MIT, Apache-2.0, BSD, ISC or MPL-2.0 dependencies. This plan adds none.
- **Ports and Brave:**
  - Every listener binds `127.0.0.1` only (gateway 18800, keeper 18801, egress proxy 18803). The Task 1 spike's throwaway keeper takes a free ephemeral port on 127.0.0.1.
  - **Never use port 9222.** Bot browsers speak CDP over pipes, never a debug port.
  - **Never touch the user's main Brave.** No code in this plan attaches to, drives, reads or opens it. Live control reaches only a bot's own Brave, through that bot's private CDP connection.
- **Tests:**
  - Tests first: red, then green.
  - At least 80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`).
  - Tests never call a real LLM (`ROOST_MODEL=scripted`) and **never launch a real browser** (`ROOST_DESK=fake`; `tests/conftest.py` forces both). The one exception is the Task 1 spike, which is marker `desk`, outside the default run, and run once by hand on the user's Mac.
- **Code rules:**
  - Files at most 800 lines (typically 200–400); functions under 50 lines.
  - Frozen dataclasses; no mutation of shared state (reassign tuples and dicts instead).
  - Pydantic validation at every boundary.
  - Explicit error handling with user-friendly messages.
  - No magic values: they go in `roost/constants.py`, in the new section "Live control", which Task 2 starts at the very end of the file and later tasks extend.
- **Encryption:** every user-content column is `enc:v2` with an AAD from `user_aad(user_id, "<table>:<column>")`. Here: `site_logins.host` and `site_logins.label` (AAD `site_logins:host`, `site_logins:label`). Ids, `host_key`, and timestamps are plaintext.
- **Queries:** every query on user data has `user_id` in its `WHERE`. Another user's bot or site login gives **404**, never the object.
- **Secrets (design L2):** a keystroke, a paste, a frame and an input frame are never logged, stored, audited or published. No log line names a typed value; refused input is dropped, not reported with its text.
- **Vocabulary (§7.4):** Computer, Take control / Give it back, Vault: site logins, Stuck, bot. Never "Take the wheel", ">Desk<" or " in Talk" (`tests/test_vocabulary.py` scans `web/src`).
- **Git:**
  - Commit after each task's green tests. Stage files **by name**, never `git add -A`, `-a` or `.`.
  - Messages are conventional (`feat:`, `fix:`, `test:`, `docs:`), with **no Co-Authored-By or any AI attribution line**.
- **Disk guard:** before `npm install`, `npm run build` or `make e2e`, run `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`. If it shows fewer than 8 GB free, stop and report.
- **Commands:** prefix every command with `cd /Users/blckit/Desktop/Code_Projects/roost &&` (the web ones with `cd /Users/blckit/Desktop/Code_Projects/roost/web &&`).
  - `uv run pytest tests/<file>.py -q` runs one file; `uv run pytest -q` runs the full suite.
  - `npx vitest run tests/<file>` (in `web/`) runs one web test; `npm test` runs them all.
  - `make e2e` runs the Playwright E2E.
- **Another agent may be committing on `night-1`.** Round A of the stuck-flow polish touched `roost/stuck/texts.py`, `roost/stuck/service.py`, `roost/gateway/routes/stuck.py` and `roost/desk/browser.py`. A "find these exact lines" snippet from those files may have moved slightly: adapt it minimally, keep its meaning, and say so in the task's report.

## Review Focus

These are the real-world failures most likely to bite. The test for each is added to the task named.

1. **A keystroke appears in a log, an event or the database.**
   - Expected: what the user types on the live screen, pastes or sends as a refused frame reaches no log line, no event, no audit row and no other row.
   - Tests: Task 6 `test_nothing_typed_reaches_the_logs_the_events_or_the_database`; Task 4 `test_live_session_never_logs_what_was_typed`; Task 3 `test_a_refused_frame_never_carries_what_was_typed`.
2. **A connection that is not from this Mac is accepted.**
   - Expected: a peer that is not 127.0.0.1 or ::1, or any forwarded request, is closed with 4403 "Live control works only on this Mac for now." before anything is shown.
   - Tests: Task 6 `test_a_connection_from_another_machine_is_refused_with_4403`, `test_a_forwarded_connection_is_refused_even_from_this_mac` and `test_only_the_loopback_peer_is_this_mac`.
3. **A pop-up never returns to the bot's page.**
   - Expected: when "Sign in with Google" closes, or closes before it could be shown, the live screen shows the bot's page again.
   - Tests: Task 4 `test_when_the_pop_up_closes_the_screen_returns_to_the_bots_page` and `test_a_pop_up_that_closes_before_it_is_shown_leaves_the_bots_page_on_screen`; Task 6 `test_a_pop_up_is_followed_and_the_screen_comes_back`.
4. **The live screen still accepts input after Give it back.**
   - Expected: once control is released, no input reaches the page, even one already on its way, and the socket closes with 4000.
   - Tests: Task 6 `test_input_after_give_it_back_never_reaches_the_page` and `test_once_control_is_released_no_input_reaches_the_session`; Task 12 (web) `stops sending once the server says it was given back`.
5. **Brave crashes or the keeper restarts while the live screen is open.** (Chosen here.)
   - Expected: the screen says it can't reach the computer and offers Retry. It never sits on a frozen last frame, and the socket never stays open with nothing behind it.
   - Tests: Task 2 `test_a_subscription_ends_when_the_far_end_closes`; Task 6 `test_a_computer_that_stops_answering_closes_the_live_screen_with_4503`; Task 12 (web) `an ended live screen offers Retry, never a frozen last frame`.

---

## Shared Contract (every task uses these exact names)

### Constants (`roost/constants.py`, new section "Live control", at the very end of the file)

```python
# Task 2 — roost/desk/cdp.py
CDP_SUBSCRIPTION_QUEUE_MAX = 64          # a subscribe() queue; when full, the oldest event is dropped

# Task 3 — roost/desk/live_input.py. Modifier bits are CDP's: Alt 1, Ctrl 2, Meta 4, Shift 8.
LIVE_PASTE_MAX_CHARS = 2000              # one paste (Cmd+V)
LIVE_INPUT_MAX_PER_SECOND = 100          # inputs past this in any one window are dropped
LIVE_INPUT_RATE_WINDOW_S = 1.0
LIVE_INPUT_FRAME_MAX_CHARS = 8192        # a raw input frame longer than this is dropped unread
LIVE_WHEEL_MAX_DELTA = 2000.0            # one wheel step, in CSS pixels, either way
LIVE_MAX_CLICKS = 3                      # single, double, triple
LIVE_MODIFIERS_MAX = 15
LIVE_SHORTCUT_MODIFIERS = 6              # Ctrl or Meta: a shortcut, which types no text
LIVE_KEY_CODE_MAX_CHARS = 32
LIVE_NAMED_KEYS = (                      # (key, Windows virtual key code, the text it types)
    ("Enter", 13, "\r"), ("Tab", 9, ""), ("Backspace", 8, ""), ("Delete", 46, ""), ("Escape", 27, ""),
    ("ArrowLeft", 37, ""), ("ArrowUp", 38, ""), ("ArrowRight", 39, ""), ("ArrowDown", 40, ""),
)

# Task 4 — roost/desk/live.py. About 10 fps, at most 1280 px wide.
LIVE_JPEG_QUALITY = 70
LIVE_MAX_WIDTH = 1280
LIVE_MAX_HEIGHT = 1280
LIVE_EVERY_NTH_FRAME = 1
LIVE_MIN_FRAME_INTERVAL_S = 0.1          # a frame is acked no sooner than this after the last ack

# Task 5 — roost/desk/fake_cdp.py
FAKE_SCREENCAST_INTERVAL_S = 0.05        # the fake browser's next frame comes at least this long after an ack
FAKE_SCREEN_WIDTH = 1280
FAKE_SCREEN_HEIGHT = 800

# Task 6 — roost/gateway/live_socket.py, roost/gateway/routes/live.py
LIVE_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
LIVE_FORWARDED_HEADERS = ("forwarded", "x-forwarded-for", "x-real-ip")
LIVE_CLOSE_GIVEN_BACK = 4000
LIVE_CLOSE_UNAUTHENTICATED = 4401
LIVE_CLOSE_REFUSED = 4403
LIVE_CLOSE_NOT_FOUND = 4404
LIVE_CLOSE_NOT_HELD = 4409
LIVE_CLOSE_ASLEEP = 4410
LIVE_CLOSE_UNAVAILABLE = 4503

# Task 7 — roost/desk/browser.py, roost/desk/client.py (the variant Task 1 recorded; see Task 7)
BOT_WINDOW_FAR_AWAY = 100000
BOT_WINDOW_SHOWN_LEFT = 80
BOT_WINDOW_SHOWN_TOP = 60
BOT_WINDOW_ASIDE_STEPS = (MappingProxyType({"windowState": "minimized"}),)   # variant "minimise"
BOT_WINDOW_SHOW_STEPS = (MappingProxyType({"windowState": "normal"}),)       # variant "minimise"

# Task 9 — roost/vault/
SITE_LOGIN_LABEL_MAX_CHARS = 100         # "Which account did you use?"
SITE_LOGIN_LIST_LIMIT = 50               # GET /api/bots/{id}/site-logins
SITE_LOGINS_IN_PROMPT = 10               # the newest rows a bot's prompt names
```

Task 7 adds `from types import MappingProxyType` to the imports at the top of `roost/constants.py`.

### Schema v14 "site logins" (`roost/db/migrations.py`, Task 9; the projects hub is v13)

```sql
CREATE TABLE IF NOT EXISTS site_logins (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    host TEXT NOT NULL,                -- enc:v2, AAD site_logins:host
    host_key TEXT NOT NULL,            -- HMAC(dek, normalised host): the unique key, never the host
    label TEXT NOT NULL,               -- enc:v2, AAD site_logins:label
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
CREATE UNIQUE INDEX IF NOT EXISTS idx_site_logins_one ON site_logins(user_id, bot_id, host_key)
CREATE INDEX IF NOT EXISTS idx_site_logins_bot ON site_logins(user_id, bot_id, updated_at)
```

`tests/fixtures/schema_v13.sql` is frozen first (45 statements), then `tests/test_migrations_v13.py` migrates it.

### Python names

**`roost/desk/cdp.py`** (Task 2):

```python
class CdpSubscription:
    def __init__(self, methods: frozenset[str], session_id: str | None, maxsize: int,
                 on_close: Callable[["CdpSubscription"], None]) -> None: ...
    dropped: int                                     # events dropped because the queue was full
    def wants(self, message: dict[str, Any]) -> bool: ...
    def offer(self, message: dict[str, Any]) -> None: ...   # drop-oldest when full
    def end(self) -> None: ...                       # iteration stops after the queued events
    def close(self) -> None: ...                     # drop the queue, stop, unregister
    def __aiter__(self) -> "CdpSubscription": ...
    async def __anext__(self) -> dict[str, Any]: ...

class CdpChannel(Protocol):                          # CdpClient, or FakeCdp
    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict: ...
    def subscribe(self, method: str | tuple[str, ...], session_id: str | None = None) -> CdpSubscription: ...

CdpClient.subscribe(self, method: str | tuple[str, ...], session_id: str | None = None, *,
                    maxsize: int = CDP_SUBSCRIPTION_QUEUE_MAX) -> CdpSubscription
# send() on a connection that is not open (never connected, closed, or closed by the far end) raises CdpClientError.
```

**`roost/desk/live_input.py`** (Task 3):

```python
NAMED_KEYS: Mapping[str, tuple[int, str]]            # from LIVE_NAMED_KEYS
class MouseInput(BaseModel):  t: Literal["mouse"]; kind: Literal["down", "up", "move"]; x: float; y: float
                              button: Literal["none", "left", "middle", "right"] = "none"; clicks: int = 0; mods: int = 0
class WheelInput(BaseModel):  t: Literal["wheel"]; x: float; y: float; dx: float = 0.0; dy: float = 0.0
class KeyInput(BaseModel):    t: Literal["key"]; kind: Literal["down", "up"]; key: str; code: str = ""; mods: int = 0
class TextInput(BaseModel):   t: Literal["text"]; text: str                     # 1..LIVE_PASTE_MAX_CHARS
class NavInput(BaseModel):    t: Literal["nav"]; action: Literal["back", "reload"]
LiveInputEvent = Union[MouseInput, WheelInput, KeyInput, TextInput, NavInput]
LiveInput = Annotated[LiveInputEvent, Field(discriminator="t")]
def parse_input(raw: str) -> LiveInputEvent | None: ...        # never raises, never logs

@dataclass(frozen=True)
class FrameMeta:
    device_width: float; device_height: float; page_scale: float = 1.0
    offset_top: float = 0.0; scroll_x: float = 0.0; scroll_y: float = 0.0
def frame_meta(raw: Any) -> FrameMeta | None: ...

@dataclass(frozen=True)
class CdpCall:
    method: str
    params: Mapping[str, Any]
def to_css(x: float, y: float, meta: FrameMeta) -> tuple[float, float] | None: ...
def mouse_calls(event: MouseInput, meta: FrameMeta | None) -> tuple[CdpCall, ...]: ...
def wheel_calls(event: WheelInput, meta: FrameMeta | None) -> tuple[CdpCall, ...]: ...
def key_calls(event: KeyInput) -> tuple[CdpCall, ...]: ...
def text_calls(event: TextInput) -> tuple[CdpCall, ...]: ...
def input_calls(event: LiveInputEvent, meta: FrameMeta | None) -> tuple[CdpCall, ...]: ...   # () for NavInput
def back_entry_id(history: Mapping[str, Any]) -> int | None: ...

class InputRateLimit:
    def __init__(self, *, limit: int | None = None, clock: Callable[[], float] = time.monotonic) -> None: ...
    def allow(self) -> bool: ...
```

**`roost/desk/__init__.py`** (Task 4 adds `LiveView`; Task 5 adds `Desk.live_view`; Task 7 adds `Desk.show_window`):

```python
@dataclass(frozen=True)
class LiveView:
    cdp: CdpChannel
    target_id: str

class Desk(Protocol):
    ...
    async def live_view(self) -> LiveView: ...       # never starts a browser: DeskAsleep / DeskUnavailable
    async def show_window(self) -> None: ...         # never starts a browser: DeskAsleep / DeskUnavailable
```

**`roost/desk/live.py`** (Task 4; `bot_page_url` in Task 5):

```python
InputResult = Literal["sent", "dropped", "failed"]
LiveEnd = Literal["stopped", "page_closed", "disconnected"]
FRAME_EVENT = "Page.screencastFrame"
TARGET_EVENTS = ("Target.targetCreated", "Target.targetDestroyed", "Target.targetInfoChanged")

@dataclass(frozen=True)
class LiveFrame:
    meta: FrameMeta
    jpeg: bytes

@dataclass(frozen=True)
class PageInfo:
    url: str
    title: str

class LiveSink(Protocol):
    async def frame(self, frame: LiveFrame) -> None: ...
    async def page(self, info: PageInfo) -> None: ...

class LiveSession:
    def __init__(self, view: LiveView, sink: LiveSink, *, clock: Callable[[], float] = time.monotonic) -> None: ...
    @property
    def shown_target(self) -> str | None: ...
    async def start(self) -> None: ...               # CdpClientError when the page can't be shown
    async def run(self) -> LiveEnd: ...              # after start()
    async def handle(self, event: LiveInputEvent) -> InputResult: ...
    async def stop(self) -> None: ...                # twice is fine; on a dead connection too

async def bot_page_url(desk: Desk) -> str: ...       # "" when asleep or out of reach; never starts a browser
```

**`roost/desk/fake_cdp.py`** (Task 5):

```python
FAKE_PAGE_TARGET = "fake-page"
@dataclass(frozen=True)
class FakeCdpCall:
    method: str
    params: Mapping[str, Any]
    session_id: str | None
class FakeCdp:                                       # a CdpChannel
    def __init__(self, page_url: Callable[[], str], jpeg: bytes) -> None: ...
    calls: tuple[FakeCdpCall, ...]
    def refuse(self, *methods: str) -> None: ...
    def open_pop_up(self, target_id: str, url: str, title: str = "") -> None: ...
    def close_target(self, target_id: str) -> None: ...
    async def disconnect(self) -> None: ...
    def screencasting(self) -> frozenset[str]: ...
```

**`roost/desk/fake.py`** (Task 5, Task 7): `FakeDesk.cdp: FakeCdp`; `async live_view() -> LiveView`; `open_page` and `read_page` wake the fake computer (`browser="running"`), as `KeeperDesk`'s page calls start the real one; `async show_window() -> None` and `windows_shown: int` (Task 7).

**`roost/desk/browser.py`** (Task 5, 7, 8): `DeskBrowserPage(client, *, window_aside: Sequence[Mapping[str, Any]] = ())`; property `cdp -> CdpClient`; `async live_target() -> str`; `async set_window(steps, *, activate: bool = False) -> None`; `_extract_readable_lines` skips every node inside `textbox`, `searchbox`, `combobox` or `spinbutton`.

**`roost/desk/client.py`** (Task 5, 7): `KeeperDesk._view(call)` (the shared viewing path), `async live_view() -> LiveView`, `async show_window() -> None`; `_connect_page` builds `DeskBrowserPage(cdp_client, window_aside=BOT_WINDOW_ASIDE_STEPS)`.

**`roost/desk/control.py`** (Task 6): `ControlLock.wait_released(bot_id: str) -> None` (async): returns once nobody holds the bot's computer, at once when nobody does.

**`roost/gateway/live_socket.py`** (Task 6):

```python
NOT_THIS_MAC_REASON = "Live control works only on this Mac for now."
ORIGIN_REASON = "Origin not allowed."
SIGN_IN_REASON = "Sign in first."
NOT_FOUND_REASON = "Bot not found"
NOT_HELD_REASON = "Take control first."
@dataclass(frozen=True)
class Refusal:
    code: int
    reason: str
def peer_is_this_mac(websocket: WebSocket, config: RoostConfig) -> bool: ...
async def live_refusal(websocket: WebSocket, bot_id: str) -> Refusal | None: ...
def frame_header(meta: FrameMeta) -> dict[str, Any]: ...
class LiveSocketSink:                                # a LiveSink
    def __init__(self, websocket: WebSocket) -> None: ...
    dropped: int
    async def frame(self, frame: LiveFrame) -> None: ...
    async def page(self, info: PageInfo) -> None: ...
    async def notice(self, text: str) -> None: ...
    async def pump(self) -> None: ...                # until cancelled
```

**`roost/gateway/routes/live.py`** (Task 6): `live_router`; `GIVEN_BACK_REASON = "Given back."`, `ASLEEP_REASON = "asleep"`, `UNAVAILABLE_REASON = "The bot's computer stopped answering."`, `INPUT_FAILED_TEXT = "That didn't reach the page. Try again."`; `async def _read_inputs(websocket, bot_id, session, sink, control) -> None`.

**`roost/vault/models.py`** (Task 9):

```python
NO_SITE_TEXT = "Roost can't tell which site that account is for. Give it back without one."
@dataclass(frozen=True)
class SiteLogin:
    id: str; user_id: str; bot_id: str; host: str; label: str; created_at: str; updated_at: str
@dataclass(frozen=True)
class SignIn:
    bot_id: str; host: str; label: str
class SiteLoginOut(BaseModel):                       # no user_id
    id: str; bot_id: str; host: str; label: str; created_at: str; updated_at: str
def site_login_out(login: SiteLogin) -> SiteLoginOut: ...
class NoSite(Exception): ...                         # 400 NO_SITE_TEXT
def clean_label(value: str | None) -> str | None: ...
AccountLabel = Annotated[str | None, Field(max_length=SITE_LOGIN_LABEL_MAX_CHARS), AfterValidator(clean_label)]
class GiveBackIn(BaseModel):                         # extra="forbid"
    account: AccountLabel = None
def normalize_host(host: str) -> str: ...
def signed_in_line(host: str, label: str) -> str: ...   # "I signed in on {host} as {label}."
```

**`roost/vault/store.py`** (Task 9):

```python
def host_key(dek: bytes, host: str) -> str: ...
class SiteLoginStore:
    def __init__(self, config: RoostConfig) -> None: ...
    async def remember(self, user_id: str, sign_in: SignIn) -> SiteLogin: ...   # upsert; ValueError for another user's bot
    async def list_for_bot(self, user_id: str, bot_id: str, limit: int = SITE_LOGIN_LIST_LIMIT) -> tuple[SiteLogin, ...]: ...
    async def forget(self, user_id: str, bot_id: str, login_id: str) -> bool: ...
```

**`roost/vault/service.py`** (Task 11):

```python
class VaultService:
    def __init__(self, store: SiteLoginStore, desks: DeskFactory, talk: TalkStore, events: EventHub,
                 turns: TurnRunner, control: ControlLock) -> None: ...
    async def list_for_bot(self, user_id: str, bot_id: str) -> tuple[SiteLogin, ...]: ...
    async def forget(self, user_id: str, bot_id: str, login_id: str) -> bool: ...
    async def sign_in(self, bot_id: str, account: str, *, known_host: str = "") -> SignIn: ...   # NoSite
    async def remember(self, user_id: str, sign_in: SignIn) -> SiteLogin: ...
    async def give_back(self, user_id: str, bot_id: str, account: str | None) -> None: ...      # NoSite
```

**The prompt line** (Task 10): `build_instructions(..., site_logins: tuple[SiteLogin, ...] = ())` adds, right after the stuck-flow section, `"You are signed in on: github.com (as work email), shop.example (as ana@home)."` (hosts and labels escaped with `_escape_tags`). `RunInputs.vault: SiteLoginStore | None = None`; `TurnRunner(..., vault: SiteLoginStore | None = None)` (default `SiteLoginStore(config)`); `_prepare` reads at most `SITE_LOGINS_IN_PROMPT` rows, newest first.

**The account on Give it back** (Task 11):
- `StuckService(..., main_browser, *, vault: VaultService | None = None)`; `clear(user_id, card_id, how=DEFAULT_CLEAR_HOW, *, account: str | None = None)`. With an account, the line is `f"{signed_in_line(host, label)} {continue_text(card, how)}"`.
- `ClearIn` gains `account: AccountLabel = None`; `NoSite` answers 400 `NO_SITE_TEXT`.
- `DELETE /api/bots/{id}/control` takes an optional `GiveBackIn` body and calls `VaultService.give_back`.

### Wire shapes (the live socket)

- **Server → face, text frames (JSON):**
  - `{"t": "frame", "w": deviceWidth, "h": deviceHeight, "scale": pageScaleFactor, "top": offsetTop, "sx": scrollOffsetX, "sy": scrollOffsetY}`, then **one binary frame**: that frame's JPEG.
  - `{"t": "page", "url": str, "title": str}` whenever the shown page changes or navigates.
  - `{"t": "notice", "text": "That didn't reach the page. Try again."}` when the page refused an input.
- **Face → server, text frames (JSON), each checked by `parse_input`:** `mouse`, `wheel`, `key`, `text`, `nav` exactly as in `live_input.py`. Coordinates are in frame space: `0..w` by `0..h` of the newest header.
- **Close codes:** 4000 "Given back." · 4401 "Sign in first." · 4403 "Live control works only on this Mac for now." / "Origin not allowed." · 4404 "Bot not found" · 4409 "Take control first." · 4410 "asleep" · 4503 "The bot's computer stopped answering.".

### HTTP routes (every route has `CurrentUser`; every mutating route has `RequireOrigin`)

| Route | Task | Result |
|---|---|---|
| `WS /api/bots/{bot_id}/live` | 6 | accept, then frames, or a close code above |
| `POST /api/bots/{bot_id}/window/show` | 7 | 200 `{"shown": true}` · 404 `"Bot not found"` · 409 `"asleep"` · 503 `"desk unavailable"` |
| `GET /api/bots/{bot_id}/site-logins` | 11 | 200 `SiteLoginOut[]`, newest first · 404 |
| `DELETE /api/bots/{bot_id}/site-logins/{login_id}` | 11 | 204 · 404 `"Bot not found"` / `"Site login not found"` |
| `DELETE /api/bots/{bot_id}/control` | 11 | body `{"account": str \| null}` optional · 200 `ControlOut` · 400 `NO_SITE_TEXT` · 404 · 422 |
| `POST /api/stuck/{id}/clear` | 11 | body `{"how": ..., "account": str \| null}` optional · as before, plus 400 `NO_SITE_TEXT` |

### Web names (Tasks 12–13)

- **`web/src/api/live.ts`:** `LIVE_CLOSE` (`givenBack`, `signIn`, `refused`, `notFound`, `notHeld`, `asleep`, `unavailable`); `LiveFrameHeader`, `LivePageFrame`, `LiveNoticeFrame`, `LiveServerFrame`, `LiveButton`, `LiveInputFrame`; `LiveSocket`, `LiveSocketFactory`; `liveUrl(botId)`, `openLiveSocket`, `showWindow(botId)`.
- **`web/src/lib/liveInput.ts`:** `NAMED_KEYS`, `PASTE_MAX_CHARS`, `MAX_CLICKS`, `WHEEL_MAX_DELTA`, `MOVE_INTERVAL_MS`; `modsOf`, `isAllowedKey`, `isPasteShortcut`, `toFrameSpace`, `keyFrame`, `mouseFrame`, `wheelFrame`, `pasteFrame`, `siteOf`.
- **`web/src/hooks/useLiveScreen.ts`:** `LiveStatus` (`"connecting" | "live" | "ended" | "asleep" | "refused" | "unreachable"`), `LiveScreenState`, `statusFor(code)`, `useLiveScreen(botId, connect?) → { state, send, retry, clearNotice }`.
- **`web/src/components/GiveBackForm.tsx`:** `GiveBackForm({ site, botName, onConfirm, onCancel })`, `ACCOUNT_MAX_CHARS`.
- **`web/src/components/profile/LiveScreen.tsx`:** `LiveScreen({ bot, site?, onGiveBack, onEnded, onOpen, connect? })`, `TOO_LONG_TO_PASTE`.
- **`web/src/components/profile/SiteLogins.tsx`:** `SiteLogins({ bot, version })`.
- **`web/src/api/vault.ts`:** `listSiteLogins(botId)`, `forgetSiteLogin(botId, loginId)`. **`web/src/api/types.ts`:** `SiteLoginOut`.
- **`web/src/api/computer.ts`:** `giveBack(botId, account: string | null = null)`. **`web/src/api/stuck.ts`:** `ClearBody`, `clearStuck(cardId, body?: ClearBody)`.
- **`ComputerTab`:** while you hold control the `LiveScreen` replaces the screenshot box; Take control and Show window on Mac otherwise; `SiteLogins` below. Give it back goes through `GiveBackForm`; with an open Stuck card it clears the card with `{ account }`.
- **`StuckCard`:** Take control takes control and opens `/bots/{bot_id}/profile?tab=computer`. Holding: "You have control. Clear it on the live screen, then give it back.", an "Open the live screen" link, and Give it back through `GiveBackForm` (site = the card's host).

### File structure

| File | Task | Responsibility |
|---|---|---|
| `tests/test_live_spike_real.py` (new, marker `desk`) | 1 | the minimise spike, run once by hand |
| `roost/constants.py` | 2 (+3, 4, 5, 6, 7, 9) | the "Live control" section |
| `roost/desk/cdp.py` | 2 | `CdpSubscription`, `CdpChannel`, `CdpClient.subscribe`; a closed socket is `CdpClientError` |
| `tests/test_cdp_live.py` (new) | 2 (+5, 7, 8) | live control's CDP tests, on `tests/test_cdp_client.py`'s fake server and fixtures (that file stays under 800 lines) |
| `roost/desk/live_input.py` (new) | 3 | input models, `parse_input`, `FrameMeta`, the CDP mapping, `InputRateLimit` |
| `roost/desk/__init__.py` | 4 (+5, 7) | `LiveView`; `Desk.live_view`, `Desk.show_window` |
| `roost/desk/live.py` (new) | 4 (+5) | `LiveSession`; `bot_page_url` |
| `roost/desk/fake_cdp.py` (new) | 5 | `FakeCdp`, the scripted screencast |
| `roost/desk/fake.py` | 5 (+7) | `FakeDesk.live_view`, page calls wake it; `show_window` |
| `roost/desk/browser.py` | 5 (+7, 8) | `cdp`, `live_target`; window aside and show; text boxes skipped |
| `roost/desk/client.py` | 5 (+7) | `KeeperDesk._view`, `live_view`; `_connect_page` sets windows aside; `show_window` |
| `roost/desk/control.py` | 6 | `wait_released` |
| `roost/gateway/live_socket.py` (new) | 6 | accept rules, the frame sink |
| `roost/gateway/routes/live.py` (new) | 6 | `WS /api/bots/{id}/live` |
| `roost/gateway/routes/desk.py` | 7 (+11) | `window/show`; `DELETE /control` with an account |
| `roost/gateway/app.py` | 6 (+10, 11) | wiring |
| `roost/db/migrations.py`, `tests/fixtures/schema_v13.sql` (new) | 9 | v14 |
| `roost/vault/{__init__,models,store}.py` (new) | 9 | the Vault's data |
| `roost/talk/instructions.py`, `roost/talk/turn.py`, `roost/talk/runner.py` | 10 | the prompt line |
| `roost/vault/service.py` (new), `roost/gateway/routes/vault.py` (new), `roost/stuck/service.py`, `roost/gateway/routes/stuck.py` | 11 | the account on Give it back, list, Forget |
| `web/src/api/live.ts`, `web/src/lib/liveInput.ts`, `web/src/hooks/useLiveScreen.ts`, `web/src/components/GiveBackForm.tsx`, `web/src/components/profile/LiveScreen.tsx` (all new), `web/src/styles/computer.css` | 12 | the live screen |
| `web/src/api/{computer,stuck,types}.ts`, `web/src/api/vault.ts` (new), `web/src/components/profile/{ComputerTab,SiteLogins}.tsx`, `web/src/components/StuckCard.tsx`, `web/src/styles/computer.css` | 13 | the Computer tab, the Stuck card, the Vault list |
| `web/e2e/stuck.spec.ts`, `web/e2e/computer.spec.ts`, `CLAUDE.md`, `README.md`, `tests/test_docs.py` | 14 | E2E and docs |

---
### Task 1: The spike: does a minimised bot window keep streaming?

Design §2 "Bot windows out of the way", L3, and D7 above. Before any code sets a bot's window aside, measure it once on the user's Mac:
- **What runs:** one throwaway Brave, launched by the real keeper app (`roost.keeper.app.create_app`) served by uvicorn **in this test's process** on a free ephemeral `127.0.0.1` port, with a temporary profile and desks directory. Its egress proxy points at a closed port, so it can reach nothing; the page is a `data:` URL with a spinning box, so it repaints all the time.
- **What it never touches:** the user's running keeper (18801) or gateway (18800), port 9222, the user's main Brave (the throwaway has its own fresh `--user-data-dir`), and Docker (`lifespan="off"` skips the keeper's container reconcile).
- **What it measures**, for 3 s in each state: screencast frames (each acked) and whether `Page.captureScreenshot` answers within 5 s. The states are a normal window, a minimised one, and a normal window moved far away (`left`/`top` 100000).
- **The verdict:** `minimise` if the minimised window still streams at least half as many frames as the normal one and still screenshots; else `behind` if the far-away window does; else `leave` (bot windows stay where Brave puts them).
- This task commits only the spike test and the recorded line in this plan. It is marker `desk`, so the default test run never launches it.

**Files:**
- Create: `tests/test_live_spike_real.py`
- Modify: `docs/plans/2026-10-15-roost-live-control.md` (the "Design decision — bot windows (L3)" paragraph near the top)

**Interfaces:**
- Consumes (existing code): `RoostConfig`, `roost.keeper.app.create_app`, `KeeperClient.start_browser` / `stop_browser`, `roost.desk.client._relay_url`, `CdpClient.connect` / `send` / `wait_event` / `close`, `CdpReplyError`.
- Produces: the recorded verdict, `minimise`, `behind` or `leave`, which Task 7 turns into `BOT_WINDOW_ASIDE_STEPS` and `BOT_WINDOW_SHOW_STEPS`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the spike**

Create `tests/test_live_spike_real.py`:

```python
"""Live control spike (Task 1, design L3): does a minimised bot window keep producing screencast frames?

Marker ``desk``: this launches one real, throwaway Brave through the real keeper app, which uvicorn
serves in this process on a free 127.0.0.1 port, with a temporary profile and desks directory. It
never uses port 18801 or 9222, never the user's running keeper or gateway, and never the user's main
Brave (the throwaway has its own fresh ``--user-data-dir``). The bot browser's proxy points at a
closed port, so the ``data:`` page here is all it can show. ``lifespan="off"`` skips the keeper's
Docker reconcile.

Run it once on the user's Mac, by hand:

    uv run pytest -m desk tests/test_live_spike_real.py -s -q

It prints one ``LIVE-SPIKE {...}`` JSON line. Its only assertion is that a normal window streams
frames; otherwise the measurement means nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from dataclasses import replace
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote

import pytest
import uvicorn

from roost.config import RoostConfig
from roost.desk.cdp import CdpClient, CdpReplyError
from roost.desk.client import KeeperClient, _relay_url
from roost.keeper.app import create_app

pytestmark = pytest.mark.desk

_SECRET = "s" * 32
_BOT_ID = "55555555-5555-4555-8555-555555555555"
_WARMUP_S = 2.0
_WINDOW_S = 3.0
_SETTLE_S = 1.0
_SCREENSHOT_TIMEOUT_S = 5.0
_FAR_AWAY = 100000
_SPINNER = (
    "<style>@keyframes s{to{transform:rotate(360deg)}}"
    "div{width:240px;height:240px;margin:80px;background:linear-gradient(red,blue);"
    "animation:s 1s linear infinite}</style><div></div>"
)
_PAGE_URL = "data:text/html," + quote(_SPINNER)
_SCREENCAST = {"format": "jpeg", "quality": 60, "maxWidth": 1280, "maxHeight": 1280, "everyNthFrame": 1}


def _closed_port() -> int:
    """A 127.0.0.1 port nothing listens on: the throwaway Brave's proxy, so it can reach nothing."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextlib.asynccontextmanager
async def _keeper(config: RoostConfig) -> AsyncIterator[str]:
    """The real keeper app on a free 127.0.0.1 port, in this process."""
    server = uvicorn.Server(uvicorn.Config(
        create_app(config), host="127.0.0.1", port=0, lifespan="off", log_level="warning",
    ))
    serving = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.05)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await serving


async def _count_frames(cdp: CdpClient, session_id: str) -> int:
    """Frames from a fresh screencast within ``_WINDOW_S``, each acked so the next can come. The wait
    for the next frame is armed before the ack, so a fast frame is never missed."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _WINDOW_S
    frames = 0
    waiter = asyncio.ensure_future(
        cdp.wait_event("Page.screencastFrame", session_id=session_id, timeout=_WINDOW_S)
    )
    await cdp.send("Page.startScreencast", _SCREENCAST, session_id=session_id)
    try:
        while (event := await waiter) is not None:
            frames += 1
            left = deadline - loop.time()
            if left <= 0:
                break
            waiter = asyncio.ensure_future(
                cdp.wait_event("Page.screencastFrame", session_id=session_id, timeout=left)
            )
            await cdp.send("Page.screencastFrameAck", {"sessionId": event["params"]["sessionId"]},
                           session_id=session_id)
    finally:
        waiter.cancel()
        await cdp.send("Page.stopScreencast", session_id=session_id)
    return frames


async def _screenshot_ok(cdp: CdpClient, session_id: str) -> bool:
    """Whether the Computer tab's 3-second screenshot (S1.8) would still work in this state."""
    try:
        shot = await asyncio.wait_for(
            cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 60}, session_id=session_id),
            _SCREENSHOT_TIMEOUT_S,
        )
    except (asyncio.TimeoutError, CdpReplyError):
        return False
    return bool(shot.get("result", {}).get("data"))


async def _measure(cdp: CdpClient, session_id: str) -> dict[str, Any]:
    return {"frames": await _count_frames(cdp, session_id), "screenshot": await _screenshot_ok(cdp, session_id)}


async def _in_state(cdp: CdpClient, session_id: str, window_id: int, bounds: dict[str, Any]) -> dict[str, Any]:
    await cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": bounds})
    await asyncio.sleep(_SETTLE_S)
    return await _measure(cdp, session_id)


def _verdict(normal: dict[str, Any], minimised: dict[str, Any], far_away: dict[str, Any]) -> str:
    def streams(state: dict[str, Any]) -> bool:
        return bool(state["screenshot"]) and normal["frames"] > 0 and state["frames"] * 2 >= normal["frames"]

    if streams(minimised):
        return "minimise"
    if streams(far_away):
        return "behind"
    return "leave"


async def _run_spike(cdp: CdpClient) -> dict[str, Any]:
    target = (await cdp.send("Target.createTarget", {"url": _PAGE_URL}))["result"]["targetId"]
    attached = await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True})
    session_id = attached["result"]["sessionId"]
    await cdp.send("Page.enable", session_id=session_id)
    window_id = (await cdp.send("Browser.getWindowForTarget", {"targetId": target}))["result"]["windowId"]
    await asyncio.sleep(_SETTLE_S)
    normal = await _measure(cdp, session_id)
    minimised = await _in_state(cdp, session_id, window_id, {"windowState": "minimized"})
    await cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "normal"}})
    far_away = await _in_state(cdp, session_id, window_id, {"left": _FAR_AWAY, "top": _FAR_AWAY})
    bounds = (await cdp.send("Browser.getWindowBounds", {"windowId": window_id}))["result"]["bounds"]
    return {"normal": normal, "minimised": minimised, "far_away": far_away, "far_away_bounds": bounds,
            "verdict": _verdict(normal, minimised, far_away)}


async def test_does_a_minimised_bot_window_keep_streaming(tmp_path: Path) -> None:
    config = RoostConfig(
        server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET, proxy_port=_closed_port(),
    )
    config.database_dir.mkdir(parents=True, exist_ok=True)
    async with _keeper(config) as keeper_url:
        keeper = KeeperClient(replace(config, keeper_url=keeper_url))
        started = await keeper.start_browser(_BOT_ID)
        await asyncio.sleep(_WARMUP_S)
        cdp = CdpClient(_relay_url(keeper_url, _BOT_ID), started["cdp_token"])
        await cdp.connect()
        try:
            result = await _run_spike(cdp)
        finally:
            await cdp.close()
            await keeper.stop_browser(_BOT_ID)
    print("LIVE-SPIKE " + json.dumps(result, sort_keys=True))
    assert result["normal"]["frames"] > 0, "a normal window must stream, or nothing was measured"
```

- [ ] **Step 3: Check the default run never launches it, then run it once by hand**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_live_spike_real.py -q`
Expected: `1 deselected` and exit status 5 ("no tests ran": marker `desk` is excluded by `addopts`), and no Brave window opens.

Then, on the user's Mac, with someone watching the screen:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest -m desk tests/test_live_spike_real.py -s -q`
Expected: `1 passed`, and one line starting `LIVE-SPIKE {` with `normal`, `minimised`, `far_away`, `far_away_bounds` and `verdict`. A Brave window opens, shows a spinning box, minimises, comes back, moves away, then closes. Whoever watches notes whether that window came to the front when it started.

If it fails with `normal.frames == 0`, stop and report: nothing was measured. If Brave can't start (`failed to start the bot's browser`), check `ROOST_BRAVE_PATH` / `/Applications/Brave Browser.app` and report; do not work around it.

- [ ] **Step 4: Record the result in this plan**

Replace the paragraph that starts `**Design decision — bot windows (L3), set by Task 1:** Not measured yet.` near the top of this file with exactly one of these lines, filling in the date, the numbers from the `LIVE-SPIKE` line, whether the window came to the front on start (`yes`, `no` or `not watched`), and the whole `LIVE-SPIKE {...}` JSON:

- `**Design decision — bot windows (L3), set by Task 1 on <YYYY-MM-DD>:** minimise. A minimised bot window kept streaming (normal <n> frames in 3 s, minimised <m>; screenshots kept working). Came to the front on start: <yes/no/not watched>. LIVE-SPIKE {...}`
- `**Design decision — bot windows (L3), set by Task 1 on <YYYY-MM-DD>:** behind. A minimised window stopped (<m> frames or no screenshot), and a normal window moved far away kept streaming (<f> frames; bounds <far_away_bounds>). Came to the front on start: <yes/no/not watched>. LIVE-SPIKE {...}`
- `**Design decision — bot windows (L3), set by Task 1 on <YYYY-MM-DD>:** leave. Neither a minimised window (<m>) nor a far-away one (<f>) kept streaming, so bot windows stay where Brave puts them. Came to the front on start: <yes/no/not watched>. LIVE-SPIKE {...}`

The word after the colon must be the `verdict` the line printed.

- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add tests/test_live_spike_real.py docs/plans/2026-10-15-roost-live-control.md
git commit -m "test: live control spike: does a minimised bot window keep streaming"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: neither file is listed.

---

### Task 2: CdpClient subscriptions

Design §2 "CDP plumbing". `CdpClient` only has one-shot `wait_event`; live control needs streams:
- `subscribe(method, session_id=None, *, maxsize=CDP_SUBSCRIPTION_QUEUE_MAX)` returns a `CdpSubscription`, an async iterator over every later event named `method` (on `session_id`, or any session when it is None), oldest first.
- `method` may be a tuple of names that share **one** queue in arrival order (D3): `LiveSession` reads `Target.targetCreated` and `Target.targetDestroyed` in the browser's own order.
- The queue is bounded: when full, the **oldest** event is dropped and `dropped` counts it. A slow reader never holds the socket's reader task up.
- `async for` ends when the connection closes, from either end, after the events already queued; `close()` ends it at once, drops the queue and unregisters it. A subscription on a client that isn't connected is already over.
- An event goes to every matching `wait_event` and every matching subscription.
- Review Focus 5: a socket the far end closed ends every subscription, and a later `send` raises `CdpClientError` (it used to raise `websockets.ConnectionClosed`, which `KeeperDesk` already treats the same way).
- `CdpChannel` is the Protocol live control needs (`send`, `subscribe`); `CdpClient` and Task 5's `FakeCdp` both satisfy it.

**Files:**
- Modify: `roost/desk/cdp.py`, `roost/constants.py` (start the "Live control" section at the very end)
- Test: `tests/test_cdp_live.py` (new). It imports `tests/test_cdp_client.py`'s fake server and fixtures, so that file stays under 800 lines.

**Interfaces:**
- Consumes: `CdpClient`, `CdpClientError`, `CdpReplyError` as they are today; `tests/test_cdp_client.py`'s `_FakeCdpServer`, `fake_server` and `connected_client` fixtures, `_IFRAME_DOCUMENT`, `_MAIN_FRAME_SCRIPT`, `_MAIN_FRAME_ID` and `_TOKEN`.
- Produces: `CDP_SUBSCRIPTION_QUEUE_MAX`; `CdpSubscription` (`wants`, `offer`, `end`, `close`, `dropped`, async iteration); `CdpChannel`; `CdpClient.subscribe`; `send` raising `CdpClientError` on a connection that is not open.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_cdp_live.py`:

```python
"""Live control's CDP plumbing, on the same fake CDP server as ``tests/test_cdp_client.py`` (whose server
and fixtures this file imports, so that file stays under 800 lines): subscriptions (Task 2), which page
the live screen shows (Task 5), the bot's window (Task 7), and typed values kept out of ``read_page``
(Task 8). Never a real browser."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from roost.desk.cdp import CdpClient, CdpClientError, CdpSubscription
from test_cdp_client import (  # noqa: F401 — the fixtures are used by name
    _IFRAME_DOCUMENT, _MAIN_FRAME_ID, _MAIN_FRAME_SCRIPT, _TOKEN, _FakeCdpServer, connected_client, fake_server,
)


# -- Task 2: subscriptions --


async def _next(subscription: CdpSubscription, timeout: float = 1.0) -> dict[str, Any]:
    return await asyncio.wait_for(anext(subscription), timeout=timeout)


async def _drain(subscription: CdpSubscription) -> list[dict[str, Any]]:
    return [event async for event in subscription]


async def test_a_subscription_gets_every_event_of_its_method_in_order(connected_client: CdpClient) -> None:
    loads = connected_client.subscribe("Page.loadEventFired", session_id="s1")
    for _ in range(3):
        await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    events = [await _next(loads) for _ in range(3)]
    assert [event["method"] for event in events] == ["Page.loadEventFired"] * 3
    assert {event["sessionId"] for event in events} == {"s1"}


async def test_a_subscription_on_one_session_never_sees_another_sessions_events(connected_client: CdpClient) -> None:
    other = connected_client.subscribe("Page.loadEventFired", session_id="s2")
    any_session = connected_client.subscribe("Page.loadEventFired")
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    assert (await _next(any_session))["sessionId"] == "s1"
    with pytest.raises(asyncio.TimeoutError):
        await _next(other, timeout=0.2)


async def test_several_methods_share_one_queue_in_arrival_order(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    """D3: LiveSession must see a pop-up's creation and its closing in the browser's own order."""
    fake_server._pre_responses = (_IFRAME_DOCUMENT,)
    both = connected_client.subscribe(("Network.responseReceived", "Page.loadEventFired"), session_id="s1")
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    methods = [(await _next(both))["method"] for _ in range(3)]
    assert methods == ["Network.responseReceived", "Network.responseReceived", "Page.loadEventFired"]


async def test_a_full_queue_drops_the_oldest_event(fake_server: _FakeCdpServer, connected_client: CdpClient) -> None:
    fake_server._pre_responses = (_IFRAME_DOCUMENT, _MAIN_FRAME_SCRIPT)
    responses = connected_client.subscribe("Network.responseReceived", session_id="s1", maxsize=2)
    loads = connected_client.subscribe("Page.loadEventFired", session_id="s1")
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    await _next(loads)                                  # every response came before the load event
    kept = [await _next(responses), await _next(responses)]
    assert [event["params"]["type"] for event in kept] == ["Script", "Document"]
    assert kept[1]["params"]["frameId"] == _MAIN_FRAME_ID
    assert responses.dropped == 1


async def test_a_subscription_and_a_wait_both_get_the_same_event(connected_client: CdpClient) -> None:
    loads = connected_client.subscribe("Page.loadEventFired", session_id="s1")
    waiter = asyncio.create_task(connected_client.wait_event("Page.loadEventFired", session_id="s1", timeout=2))
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    assert (await waiter)["method"] == "Page.loadEventFired"
    assert (await _next(loads))["method"] == "Page.loadEventFired"


async def test_a_subscription_ends_when_the_client_closes(connected_client: CdpClient) -> None:
    loads = connected_client.subscribe("Page.loadEventFired")
    reader = asyncio.create_task(_drain(loads))
    await connected_client.close()
    assert await asyncio.wait_for(reader, timeout=1) == []


async def test_a_subscription_ends_when_the_far_end_closes() -> None:
    """Review Focus 5: Brave crashed or the keeper restarted. Every subscription must end, or the live
    screen would sit on its last frame for ever, and a later send is a clean CdpClientError."""
    server = _FakeCdpServer()
    await server.start()
    client = CdpClient(server.url, _TOKEN)
    await client.connect()
    try:
        frames = client.subscribe("Page.screencastFrame")
        reader = asyncio.create_task(_drain(frames))
        await server.stop()
        assert await asyncio.wait_for(reader, timeout=2) == []
        with pytest.raises(CdpClientError):
            await client.send("Page.enable")
        assert await _drain(client.subscribe("Page.screencastFrame")) == []
    finally:
        await client.close()


async def test_closing_a_subscription_stops_it_and_unregisters_it(connected_client: CdpClient) -> None:
    loads = connected_client.subscribe("Page.loadEventFired", session_id="s1")
    reader = asyncio.create_task(_drain(loads))
    loads.close()
    assert await asyncio.wait_for(reader, timeout=1) == []
    await connected_client.send("Page.navigate", {"url": "https://example.com/"}, session_id="s1")
    assert connected_client._subscriptions == ()


async def test_a_subscription_on_a_client_that_never_connected_is_already_over() -> None:
    client = CdpClient("ws://127.0.0.1:1", _TOKEN)
    assert await _drain(client.subscribe("Page.screencastFrame")) == []


async def test_a_subscription_needs_room_for_one_event(connected_client: CdpClient) -> None:
    with pytest.raises(ValueError):
        connected_client.subscribe("Page.screencastFrame", maxsize=0)
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_live.py -q`
Expected: FAIL with one collection error: `ImportError: cannot import name 'CdpSubscription' from 'roost.desk.cdp'`.

- [ ] **Step 4: Start the constants section**

Append this to the very end of `roost/constants.py`:

```python

# ---------------------------------------------------------------------------
# Live control — roost/desk/cdp.py, roost/desk/live_input.py, roost/desk/live.py,
# roost/desk/fake_cdp.py, roost/gateway/live_socket.py, roost/gateway/routes/live.py, roost/vault/
# ---------------------------------------------------------------------------

# Task 2: a CdpClient.subscribe queue holds at most this many events; when full, the oldest is dropped.
CDP_SUBSCRIPTION_QUEUE_MAX = 64
```

- [ ] **Step 5: Implement the subscriptions (`roost/desk/cdp.py`)**

1. The module docstring. Replace these lines:

```python
waiting on that reply's ``id``, or to any ``wait_event()`` call waiting
on that event's ``method``/``sessionId`` (and accepted by that wait's
``predicate``, when it has one).
"""
```

with:

```python
waiting on that reply's ``id``, or to any ``wait_event()`` call waiting
on that event's ``method``/``sessionId`` (and accepted by that wait's
``predicate``, when it has one), and to every ``subscribe()`` stream
that wants it (live control: the screencast and the target events).
"""
```

2. The imports. Replace these lines:

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
```

with:

```python
import asyncio
import contextlib
import itertools
import json
import logging
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

import websockets

from roost.constants import CDP_MAX_MESSAGE_BYTES, CDP_SEND_TIMEOUT_S, CDP_SUBSCRIPTION_QUEUE_MAX
```

3. The subscription and the channel. Replace these lines:

```python
    still actively browsing with just because a view failed once (S1.8
    Fix round 1, finding 1)."""


class CdpClient:
```

with:

```python
    still actively browsing with just because a view failed once (S1.8
    Fix round 1, finding 1)."""


class CdpSubscription:
    """One ``subscribe()`` stream (live control, design §2): every event named in ``methods`` (on
    ``session_id``, or on any session when it is None), in the order the socket delivered them.

    The queue holds at most ``maxsize`` events. When it is full the oldest is dropped (``dropped``
    counts them), so a slow reader sees the newest events and never holds the reader task up.
    ``async for`` ends once the connection closes, after the events already queued, or at once
    when ``close()`` is called."""

    def __init__(self, methods: frozenset[str], session_id: str | None, maxsize: int,
                 on_close: Callable[["CdpSubscription"], None]) -> None:
        self._methods = methods
        self._session_id = session_id
        self._queue: deque[dict[str, Any]] = deque(maxlen=maxsize)
        self._ready = asyncio.Event()
        self._ended = False
        self._on_close = on_close
        self.dropped = 0

    def wants(self, message: dict[str, Any]) -> bool:
        if self._ended or message.get("method") not in self._methods:
            return False
        return self._session_id is None or message.get("sessionId") == self._session_id

    def offer(self, message: dict[str, Any]) -> None:
        """Queue one event; a full queue drops its oldest (``deque(maxlen=...)``)."""
        if self._ended:
            return
        if len(self._queue) == self._queue.maxlen:
            self.dropped += 1
        self._queue.append(message)
        self._ready.set()

    def end(self) -> None:
        """No more events will come: iteration stops once the queued ones are read."""
        self._ended = True
        self._ready.set()

    def close(self) -> None:
        """The reader is done: drop what is queued, stop iterating and stop receiving."""
        self._queue.clear()
        self.end()
        self._on_close(self)

    def __aiter__(self) -> "CdpSubscription":
        return self

    async def __anext__(self) -> dict[str, Any]:
        while not self._queue:
            if self._ended:
                raise StopAsyncIteration
            self._ready.clear()
            await self._ready.wait()
        return self._queue.popleft()


class CdpChannel(Protocol):
    """What live control needs of a CDP connection: ``CdpClient``, or ``FakeCdp`` in fake mode."""

    async def send(self, method: str, params: dict[str, Any] | None = None,
                   session_id: str | None = None) -> dict: ...

    def subscribe(self, method: str | tuple[str, ...], session_id: str | None = None) -> CdpSubscription: ...


class CdpClient:
```

4. The client's state. Replace these lines:

```python
        self._event_waiters: list[
            tuple[str, str | None, EventPredicate | None, asyncio.Future[dict[str, Any]]]
        ] = []
```

with:

```python
        self._event_waiters: list[
            tuple[str, str | None, EventPredicate | None, asyncio.Future[dict[str, Any]]]
        ] = []
        # Live control: every open subscribe() stream, a tuple that is replaced, never changed.
        self._subscriptions: tuple[CdpSubscription, ...] = ()
        # True from connect() until the socket closes, from either end.
        self._open = False
```

5. `connect` and `close`. Replace these lines:

```python
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        self._fail_all_pending(CdpClientError("connection closed"))
```

with:

```python
        self._reader_task = asyncio.create_task(self._read_loop())
        self._open = True

    async def close(self) -> None:
        self._open = False
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
        self._fail_all_pending(CdpClientError("connection closed"))
        self._end_subscriptions()
```

6. `send` on a connection that is not open. Replace these lines:

```python
        Both are ``CdpReplyError`` rather than the base ``CdpClientError``
        -- the socket is still fine, only this one command wasn't
        answered usefully (S1.8 Fix round 1, finding 1).
        """
        if self._ws is None:
            raise CdpClientError("not connected")
```

with:

```python
        Both are ``CdpReplyError`` rather than the base ``CdpClientError``
        -- the socket is still fine, only this one command wasn't
        answered usefully (S1.8 Fix round 1, finding 1). A connection that
        is not open is the base ``CdpClientError`` (live control).
        """
        if self._ws is None or not self._open:
            raise CdpClientError("not connected")
```

Then replace these lines:

```python
        try:
            await self._ws.send(json.dumps(payload))
            try:
```

with:

```python
        try:
            await self._write(payload)
            try:
```

7. `subscribe`. Replace these lines:

```python
        finally:
            with contextlib.suppress(ValueError):
                self._event_waiters.remove(waiter)
```

with:

```python
        finally:
            with contextlib.suppress(ValueError):
                self._event_waiters.remove(waiter)

    def subscribe(self, method: str | tuple[str, ...], session_id: str | None = None, *,
                  maxsize: int = CDP_SUBSCRIPTION_QUEUE_MAX) -> CdpSubscription:
        """Every later event named ``method`` (one name, or a tuple of names that share one queue
        in arrival order), on ``session_id`` or on any session when it is None. Live control's
        screencast frames and target events use it; ``wait_event`` still serves one-shot waits, and
        an event goes to both. On a client that is not connected the subscription is already over."""
        if maxsize < 1:
            raise ValueError("a CDP subscription needs room for at least one event")
        methods = frozenset((method,) if isinstance(method, str) else method)
        subscription = CdpSubscription(methods, session_id, maxsize, self._unsubscribe)
        if not self._open:
            subscription.end()
            return subscription
        self._subscriptions = (*self._subscriptions, subscription)
        return subscription
```

8. The reader ends every subscription when the socket closes. Replace these lines:

```python
        except websockets.ConnectionClosed:
            pass
        finally:
            self._fail_all_pending(CdpClientError("connection closed"))
```

with:

```python
        except websockets.ConnectionClosed:
            pass
        finally:
            self._open = False
            self._fail_all_pending(CdpClientError("connection closed"))
            self._end_subscriptions()
```

9. Routing. Replace these lines:

```python
            if _accepts(predicate, message):
                future.set_result(message)
```

with:

```python
            if _accepts(predicate, message):
                future.set_result(message)
        for subscription in self._subscriptions:
            if subscription.wants(message):
                subscription.offer(message)
```

10. Writing, unsubscribing and ending. Replace these lines:

```python
    def _fail_all_pending(self, exc: Exception) -> None:
        pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(exc)
```

with:

```python
    def _fail_all_pending(self, exc: Exception) -> None:
        pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(exc)

    async def _write(self, payload: dict[str, Any]) -> None:
        """Send one frame. A socket that closed under it is a dead connection: ``CdpClientError``,
        never a raw ``websockets`` exception (live control, Review Focus 5)."""
        assert self._ws is not None
        try:
            await self._ws.send(json.dumps(payload))
        except websockets.ConnectionClosed as exc:
            raise CdpClientError("connection closed") from exc

    def _unsubscribe(self, subscription: CdpSubscription) -> None:
        self._subscriptions = tuple(s for s in self._subscriptions if s is not subscription)

    def _end_subscriptions(self) -> None:
        """The socket is gone: every stream ends after what it already queued (Review Focus 5)."""
        subscriptions, self._subscriptions = self._subscriptions, ()
        for subscription in subscriptions:
            subscription.end()
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_live.py tests/test_cdp_client.py tests/test_keeper_client.py tests/test_desk_api.py tests/test_computer_api.py -q`
Expected: PASS. `test_keeper_client.py` covers `KeeperDesk`'s reconnect path, which now sees `CdpClientError` where it used to see `websockets.ConnectionClosed`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_live.py tests/test_cdp_client.py --cov=roost.desk.cdp --cov-report=term-missing -q`
Expected: PASS, and `roost/desk/cdp.py` at least 95%: only the Protocol's `...` lines may be reported missed.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/desk/cdp.py roost/constants.py tests/test_cdp_live.py
git commit -m "feat: CDP subscriptions: bounded, drop-oldest event streams that end with the connection"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the three files is listed.

---

### Task 3: Live input: checking, mapping and the rate limit

Design §2 "Input" and "How input reaches the page", L2:
- **Frames.** Each input is a JSON text frame: `mouse`, `wheel`, `key`, `text` (a paste) or `nav` (Back, Reload). `parse_input` checks it with pydantic (`extra="forbid"`, a discriminator on `t`) and returns the input, or `None` for anything else. It never raises and never logs: a pydantic error carries the frame's own text, which is what the user typed (Review Focus 1). A raw frame over `LIVE_INPUT_FRAME_MAX_CHARS` is dropped unread.
- **Keys** are an allow-list: the named keys in `LIVE_NAMED_KEYS` (Enter, Tab, Backspace, Delete, Escape, the four arrows) and any one printable character. Shift, Meta, F-keys and the rest are refused. A paste is 1 to `LIVE_PASTE_MAX_CHARS` characters.
- **Coordinates** come in frame space, the screencast frame's device box (`FrameMeta`, from `Page.screencastFrame`'s metadata). `to_css` maps a point to the page's CSS pixels: `x / page_scale`, `(y - offset_top) / page_scale`. A point outside the frame, or in browser UI above the page, is dropped.
- **The CDP calls.** A press or release is `Input.dispatchMouseEvent` (`mousePressed` / `mouseReleased`, its button and click count); a move carries no button and no click; a wheel is `mouseWheel`. A key down that types (a named key with text, or a character) is `keyDown` with `text`. A key down that does not type (Tab, Backspace, Delete, Escape, an arrow, or any key with Ctrl or Meta) is `rawKeyDown`. A key up is `keyUp`. A paste is `Input.insertText`. `nav` is left to `LiveSession` (Task 4): Back needs the page's history first, and `back_entry_id` picks the entry.
- **The rate limit.** `InputRateLimit` allows `LIVE_INPUT_MAX_PER_SECOND` inputs in any `LIVE_INPUT_RATE_WINDOW_S`, and the rest are dropped. It reads the constant when it is built, so a test can patch it.

**Files:**
- Create: `roost/desk/live_input.py`, `tests/test_live_input.py`
- Modify: `roost/constants.py` (append the input constants to the "Live control" section)

**Interfaces:**
- Consumes: Task 2's "Live control" section in `roost/constants.py`.
- Produces: everything listed for `roost/desk/live_input.py` in the Shared Contract, and the constants `LIVE_PASTE_MAX_CHARS`, `LIVE_INPUT_MAX_PER_SECOND`, `LIVE_INPUT_RATE_WINDOW_S`, `LIVE_INPUT_FRAME_MAX_CHARS`, `LIVE_WHEEL_MAX_DELTA`, `LIVE_MAX_CLICKS`, `LIVE_MODIFIERS_MAX`, `LIVE_SHORTCUT_MODIFIERS`, `LIVE_KEY_CODE_MAX_CHARS` and `LIVE_NAMED_KEYS`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_live_input.py`:

```python
"""Live control's input (Task 3; design §2): the allow-list, frame space to CSS pixels, the exact CDP
calls each input becomes, and the rate limit. Pure functions: no browser, no socket."""

from __future__ import annotations

import json
import logging

import pytest

import roost.desk.live_input as live_input
from roost.constants import LIVE_INPUT_FRAME_MAX_CHARS, LIVE_INPUT_MAX_PER_SECOND, LIVE_NAMED_KEYS, LIVE_PASTE_MAX_CHARS
from roost.desk.live_input import (
    CdpCall, FrameMeta, InputRateLimit, KeyInput, MouseInput, NavInput, TextInput, WheelInput, back_entry_id,
    frame_meta, input_calls, parse_input, to_css,
)

META = FrameMeta(device_width=1280, device_height=800)
ZOOMED = FrameMeta(device_width=1280, device_height=800, page_scale=2.0, offset_top=40)
SECRET = "hunter2-correct-horse"


def _parse(**frame: object) -> object:
    return parse_input(json.dumps(frame))


def _only(calls: tuple[CdpCall, ...]) -> tuple[str, dict]:
    [call] = calls
    return call.method, dict(call.params)


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


# -- parse_input: only exactly an allowed input gets through --


@pytest.mark.parametrize("key", [name for name, _code, _text in LIVE_NAMED_KEYS])
def test_every_named_key_is_allowed(key):
    assert _parse(t="key", kind="down", key=key, code=key) == KeyInput(t="key", kind="down", key=key, code=key)


@pytest.mark.parametrize("key", ["a", "Z", "7", "@", " ", "é", "€"])
def test_any_one_printable_character_is_allowed(key):
    assert _parse(t="key", kind="up", key=key) == KeyInput(t="key", kind="up", key=key)


@pytest.mark.parametrize("key", ["F5", "Meta", "Shift", "Control", "Home", "\x00", "\n", "ab", "", " "])
def test_any_other_key_is_refused(key):
    assert _parse(t="key", kind="down", key=key) is None


def test_a_mouse_frame_parses_with_its_defaults():
    assert _parse(t="mouse", kind="move", x=1, y=2) == MouseInput(t="mouse", kind="move", x=1, y=2)


def test_a_paste_of_the_limit_is_allowed():
    text = "x" * LIVE_PASTE_MAX_CHARS
    assert _parse(t="text", text=text) == TextInput(t="text", text=text)


@pytest.mark.parametrize("frame", [
    {"t": "mouse", "kind": "down", "x": 1, "y": 1, "button": "back"},
    {"t": "mouse", "kind": "down", "x": 1, "y": 1, "clicks": 4},
    {"t": "mouse", "kind": "down", "x": 1, "y": 1, "mods": 16},
    {"t": "mouse", "kind": "drag", "x": 1, "y": 1},
    {"t": "mouse", "kind": "down", "x": "NaN", "y": 1},
    {"t": "wheel", "x": 1, "y": 1, "dy": 1e9},
    {"t": "key", "kind": "down", "key": "a", "code": "Key A"},
    {"t": "text", "text": ""},
    {"t": "text", "text": "x" * (LIVE_PASTE_MAX_CHARS + 1)},
    {"t": "nav", "action": "forward"},
    {"t": "mouse", "kind": "down", "x": 1, "y": 1, "extra": True},
    {"t": "exec", "command": "ls"},
    {"kind": "down"},
])
def test_a_frame_that_is_not_exactly_an_allowed_input_is_dropped(frame):
    assert parse_input(json.dumps(frame)) is None


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null", '{"t": "text"', "x" * (LIVE_INPUT_FRAME_MAX_CHARS + 1)])
def test_garbage_is_dropped(raw):
    assert parse_input(raw) is None


def test_a_refused_frame_never_carries_what_was_typed(caplog):
    """Review Focus 1: a refused frame is None, never an error or a log line holding the text."""
    caplog.set_level(logging.DEBUG)
    refused = (
        {"t": "key", "kind": "down", "key": SECRET},
        {"t": "text", "text": SECRET * 200},
        {"t": "text", "text": SECRET, "x": 1},
    )
    for frame in refused:
        assert parse_input(json.dumps(frame)) is None
    assert SECRET not in caplog.text


# -- frame space to CSS pixels --


def test_a_frame_point_maps_to_css_pixels():
    assert to_css(640, 400, META) == (640, 400)
    assert to_css(640, 440, ZOOMED) == (320, 200)


@pytest.mark.parametrize("point", [(-1, 10), (10, -1), (1281, 10), (10, 801)])
def test_a_point_outside_the_frame_is_dropped(point):
    assert to_css(*point, META) is None


def test_a_point_in_the_browser_ui_above_the_page_is_dropped():
    assert to_css(10, 39, ZOOMED) is None


# -- the CDP calls --


@pytest.mark.parametrize(("kind", "cdp_type"), [("down", "mousePressed"), ("up", "mouseReleased")])
@pytest.mark.parametrize("button", ["left", "middle", "right"])
@pytest.mark.parametrize("clicks", [1, 2, 3])
def test_a_press_or_release_becomes_one_mouse_event(kind, cdp_type, button, clicks):
    event = MouseInput(t="mouse", kind=kind, x=100, y=50, button=button, clicks=clicks, mods=8)
    assert _only(input_calls(event, META)) == ("Input.dispatchMouseEvent", {
        "type": cdp_type, "x": 100, "y": 50, "button": button, "clickCount": clicks, "modifiers": 8,
    })


def test_a_move_carries_no_button_and_no_click():
    event = MouseInput(t="mouse", kind="move", x=640, y=440, button="left", clicks=2)
    assert _only(input_calls(event, ZOOMED)) == ("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": 320, "y": 200, "button": "none", "clickCount": 0, "modifiers": 0,
    })


def test_mouse_input_before_any_frame_or_outside_it_is_dropped():
    press = MouseInput(t="mouse", kind="down", x=100, y=50, button="left", clicks=1)
    assert input_calls(press, None) == ()
    assert input_calls(MouseInput(t="mouse", kind="down", x=5000, y=50, button="left", clicks=1), META) == ()
    assert input_calls(WheelInput(t="wheel", x=5000, y=50, dy=120), META) == ()


def test_a_wheel_becomes_a_mouse_wheel_event():
    assert _only(input_calls(WheelInput(t="wheel", x=10, y=20, dx=0, dy=120), META)) == (
        "Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 10, "y": 20, "deltaX": 0, "deltaY": 120})


@pytest.mark.parametrize(("key", "vk", "text"), LIVE_NAMED_KEYS)
def test_every_named_key_presses_with_its_code(key, vk, text):
    common = {"key": key, "code": key, "windowsVirtualKeyCode": vk, "modifiers": 0}
    down = _only(input_calls(KeyInput(t="key", kind="down", key=key, code=key), META))
    expected = {"type": "keyDown", **common, "text": text, "unmodifiedText": text} if text else {"type": "rawKeyDown", **common}
    assert down == ("Input.dispatchKeyEvent", expected)
    up = _only(input_calls(KeyInput(t="key", kind="up", key=key, code=key), META))
    assert up == ("Input.dispatchKeyEvent", {"type": "keyUp", **common})


@pytest.mark.parametrize(("key", "vk"), [("a", 65), ("Z", 90), ("7", 55), ("@", 0), ("é", 0)])
def test_a_character_types_itself(key, vk):
    down = _only(input_calls(KeyInput(t="key", kind="down", key=key, mods=8), META))
    assert down == ("Input.dispatchKeyEvent", {
        "type": "keyDown", "key": key, "code": "", "windowsVirtualKeyCode": vk, "modifiers": 8,
        "text": key, "unmodifiedText": key,
    })


@pytest.mark.parametrize("mods", [2, 4, 6])
def test_a_shortcut_types_no_text(mods):
    down = _only(input_calls(KeyInput(t="key", kind="down", key="a", code="KeyA", mods=mods), META))
    assert down == ("Input.dispatchKeyEvent", {
        "type": "rawKeyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": mods,
    })


def test_a_paste_inserts_its_text_with_no_frame_needed():
    assert _only(input_calls(TextInput(t="text", text="ana@example.com"), None)) == (
        "Input.insertText", {"text": "ana@example.com"})


def test_back_and_reload_are_left_to_the_session():
    assert input_calls(NavInput(t="nav", action="reload"), META) == ()


def test_back_is_the_entry_before_the_current_one():
    assert back_entry_id({"currentIndex": 2, "entries": [{"id": 3}, {"id": 5}, {"id": 9}]}) == 5


@pytest.mark.parametrize("history", [
    {"currentIndex": 0, "entries": [{"id": 3}]},
    {"currentIndex": 3, "entries": [{"id": 3}]},
    {},
    {"currentIndex": 1, "entries": [{"url": "https://example.com/"}, {"id": 4}]},
])
def test_there_is_no_back_on_the_first_page_or_in_a_broken_history(history):
    assert back_entry_id(history) is None


# -- frame metadata --


def test_frame_metadata_is_read_from_cdp():
    raw = {"deviceWidth": 1280, "deviceHeight": 800, "pageScaleFactor": 1, "offsetTop": 0,
           "scrollOffsetX": 0, "scrollOffsetY": 120, "timestamp": 1.5}
    assert frame_meta(raw) == FrameMeta(1280, 800, 1.0, 0.0, 0.0, 120.0)


@pytest.mark.parametrize("raw", [None, {}, "x", {"deviceWidth": 0, "deviceHeight": 800},
                                 {"deviceWidth": 1280, "deviceHeight": 800, "pageScaleFactor": 0}])
def test_unusable_frame_metadata_is_none(raw):
    assert frame_meta(raw) is None


# -- the rate limit --


def test_inputs_over_the_limit_in_one_second_are_dropped():
    clock = _Clock()
    limit = InputRateLimit(limit=3, clock=clock)
    assert [limit.allow() for _ in range(5)] == [True, True, True, False, False]
    clock.now += 0.5
    assert limit.allow() is False
    clock.now += 0.51
    assert limit.allow() is True


def test_the_default_limit_is_the_constant_and_a_test_can_patch_it(monkeypatch):
    clock = _Clock()
    default = InputRateLimit(clock=clock)
    assert sum(default.allow() for _ in range(LIVE_INPUT_MAX_PER_SECOND + 5)) == LIVE_INPUT_MAX_PER_SECOND
    monkeypatch.setattr(live_input, "LIVE_INPUT_MAX_PER_SECOND", 2)
    patched = InputRateLimit(clock=clock)
    assert sum(patched.allow() for _ in range(5)) == 2
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_live_input.py -q`
Expected: FAIL with one collection error: `ImportError: cannot import name 'LIVE_INPUT_FRAME_MAX_CHARS' from 'roost.constants'`.

- [ ] **Step 4: Add the input constants**

Append this to the very end of `roost/constants.py`:

```python

# Task 3 — roost/desk/live_input.py. Modifier bits are CDP's: Alt 1, Ctrl 2, Meta 4, Shift 8.
LIVE_PASTE_MAX_CHARS = 2000              # one paste (Cmd+V)
LIVE_INPUT_MAX_PER_SECOND = 100          # inputs past this in any one window are dropped
LIVE_INPUT_RATE_WINDOW_S = 1.0
LIVE_INPUT_FRAME_MAX_CHARS = 8192        # a raw input frame longer than this is dropped unread
LIVE_WHEEL_MAX_DELTA = 2000.0            # one wheel step, in CSS pixels, either way
LIVE_MAX_CLICKS = 3                      # single, double, triple
LIVE_MODIFIERS_MAX = 15
LIVE_SHORTCUT_MODIFIERS = 6              # Ctrl or Meta: a shortcut, which types no text
LIVE_KEY_CODE_MAX_CHARS = 32
LIVE_NAMED_KEYS = (                      # (key, Windows virtual key code, the text it types)
    ("Enter", 13, "\r"), ("Tab", 9, ""), ("Backspace", 8, ""), ("Delete", 46, ""), ("Escape", 27, ""),
    ("ArrowLeft", 37, ""), ("ArrowUp", 38, ""), ("ArrowRight", 39, ""), ("ArrowDown", 40, ""),
)
```

- [ ] **Step 5: Implement `roost/desk/live_input.py`**

Create `roost/desk/live_input.py`:

```python
"""Live control's input (design §2): what the user's live screen may send, checked with pydantic,
and the exact CDP calls each input becomes.

Every input frame is JSON text: ``mouse``, ``wheel``, ``key``, ``text`` (a paste) or ``nav`` (Back,
Reload). ``parse_input`` returns the checked input, or ``None`` for anything else. It never raises
and never logs: a pydantic error carries the frame's own text, which is what the user typed.

Coordinates come in frame space, the screencast frame's device box (``FrameMeta``). ``to_css`` maps
them to the page's CSS pixels; a point outside the frame is dropped. Keys are an allow-list: the
named keys in ``LIVE_NAMED_KEYS`` and any one printable character.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Any, Callable, Literal, Mapping, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from roost.constants import (
    LIVE_INPUT_FRAME_MAX_CHARS, LIVE_INPUT_MAX_PER_SECOND, LIVE_INPUT_RATE_WINDOW_S, LIVE_KEY_CODE_MAX_CHARS,
    LIVE_MAX_CLICKS, LIVE_MODIFIERS_MAX, LIVE_NAMED_KEYS, LIVE_PASTE_MAX_CHARS, LIVE_SHORTCUT_MODIFIERS,
    LIVE_WHEEL_MAX_DELTA,
)

# key -> (Windows virtual key code, the text the key types)
NAMED_KEYS: Mapping[str, tuple[int, str]] = MappingProxyType(
    {key: (code, text) for key, code, text in LIVE_NAMED_KEYS}
)
_MOUSE_EVENT_TYPES: Mapping[str, str] = MappingProxyType(
    {"down": "mousePressed", "up": "mouseReleased", "move": "mouseMoved"}
)

Coordinate = Annotated[float, Field(allow_inf_nan=False)]
WheelDelta = Annotated[float, Field(ge=-LIVE_WHEEL_MAX_DELTA, le=LIVE_WHEEL_MAX_DELTA, allow_inf_nan=False)]
Modifiers = Annotated[int, Field(ge=0, le=LIVE_MODIFIERS_MAX)]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MouseInput(_Input):
    t: Literal["mouse"]
    kind: Literal["down", "up", "move"]
    x: Coordinate
    y: Coordinate
    button: Literal["none", "left", "middle", "right"] = "none"
    clicks: int = Field(default=0, ge=0, le=LIVE_MAX_CLICKS)
    mods: Modifiers = 0


class WheelInput(_Input):
    t: Literal["wheel"]
    x: Coordinate
    y: Coordinate
    dx: WheelDelta = 0.0
    dy: WheelDelta = 0.0


class KeyInput(_Input):
    t: Literal["key"]
    kind: Literal["down", "up"]
    key: str
    code: str = Field(default="", max_length=LIVE_KEY_CODE_MAX_CHARS, pattern=r"^[A-Za-z0-9]*$")
    mods: Modifiers = 0

    @field_validator("key")
    @classmethod
    def _allowed_key(cls, key: str) -> str:
        """A named key, or one printable character. The error never names the key."""
        if key in NAMED_KEYS or (len(key) == 1 and key.isprintable()):
            return key
        raise ValueError("not a key live control sends")


class TextInput(_Input):
    t: Literal["text"]
    text: str = Field(min_length=1, max_length=LIVE_PASTE_MAX_CHARS)


class NavInput(_Input):
    t: Literal["nav"]
    action: Literal["back", "reload"]


LiveInputEvent = Union[MouseInput, WheelInput, KeyInput, TextInput, NavInput]
LiveInput = Annotated[LiveInputEvent, Field(discriminator="t")]
_LIVE_INPUT: TypeAdapter[LiveInputEvent] = TypeAdapter(LiveInput)


def parse_input(raw: str) -> LiveInputEvent | None:
    """One input frame, checked, or None. The ``ValidationError`` is dropped on purpose: its text
    would carry what the user typed (Review Focus 1)."""
    if not raw or len(raw) > LIVE_INPUT_FRAME_MAX_CHARS:
        return None
    try:
        return _LIVE_INPUT.validate_json(raw)
    except ValidationError:
        return None


@dataclass(frozen=True)
class FrameMeta:
    """A screencast frame's metadata (CDP ``Page.ScreencastFrameMetadata``): the page's device box in
    DIP, its zoom, the height of browser UI drawn above the page (0 on a desktop window) and the
    scroll position."""

    device_width: float
    device_height: float
    page_scale: float = 1.0
    offset_top: float = 0.0
    scroll_x: float = 0.0
    scroll_y: float = 0.0


class _Metadata(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    device_width: float = Field(alias="deviceWidth", gt=0, allow_inf_nan=False)
    device_height: float = Field(alias="deviceHeight", gt=0, allow_inf_nan=False)
    page_scale: float = Field(default=1.0, alias="pageScaleFactor", gt=0, allow_inf_nan=False)
    offset_top: float = Field(default=0.0, alias="offsetTop", ge=0, allow_inf_nan=False)
    scroll_x: float = Field(default=0.0, alias="scrollOffsetX", allow_inf_nan=False)
    scroll_y: float = Field(default=0.0, alias="scrollOffsetY", allow_inf_nan=False)


def frame_meta(raw: Any) -> FrameMeta | None:
    """``Page.screencastFrame``'s metadata, or None when it has no usable size or zoom."""
    try:
        meta = _Metadata.model_validate(raw)
    except ValidationError:
        return None
    return FrameMeta(meta.device_width, meta.device_height, meta.page_scale, meta.offset_top,
                     meta.scroll_x, meta.scroll_y)


@dataclass(frozen=True)
class CdpCall:
    method: str
    params: Mapping[str, Any]


def _call(method: str, **params: Any) -> CdpCall:
    return CdpCall(method, MappingProxyType(params))


def to_css(x: float, y: float, meta: FrameMeta) -> tuple[float, float] | None:
    """A frame-space point in the page's CSS pixels, or None when it falls outside the frame."""
    if not (0 <= x <= meta.device_width and meta.offset_top <= y <= meta.device_height):
        return None
    return x / meta.page_scale, (y - meta.offset_top) / meta.page_scale


def mouse_calls(event: MouseInput, meta: FrameMeta | None) -> tuple[CdpCall, ...]:
    point = to_css(event.x, event.y, meta) if meta is not None else None
    if point is None:
        return ()
    moving = event.kind == "move"
    return (_call(
        "Input.dispatchMouseEvent", type=_MOUSE_EVENT_TYPES[event.kind], x=point[0], y=point[1],
        button="none" if moving else event.button, clickCount=0 if moving else event.clicks,
        modifiers=event.mods,
    ),)


def wheel_calls(event: WheelInput, meta: FrameMeta | None) -> tuple[CdpCall, ...]:
    point = to_css(event.x, event.y, meta) if meta is not None else None
    if point is None:
        return ()
    return (_call("Input.dispatchMouseEvent", type="mouseWheel", x=point[0], y=point[1],
                  deltaX=event.dx, deltaY=event.dy),)


def _virtual_key(key: str) -> tuple[int, str]:
    """(Windows virtual key code, text) for an allowed key: a letter or digit has its own code, any
    other character 0."""
    named = NAMED_KEYS.get(key)
    if named is not None:
        return named
    return (ord(key.upper()) if key.isascii() and key.isalnum() else 0), key


def key_calls(event: KeyInput) -> tuple[CdpCall, ...]:
    code, text = _virtual_key(event.key)
    common = {"key": event.key, "code": event.code, "windowsVirtualKeyCode": code, "modifiers": event.mods}
    if event.kind == "up":
        return (_call("Input.dispatchKeyEvent", type="keyUp", **common),)
    if text and not (event.mods & LIVE_SHORTCUT_MODIFIERS):
        return (_call("Input.dispatchKeyEvent", type="keyDown", text=text, unmodifiedText=text, **common),)
    return (_call("Input.dispatchKeyEvent", type="rawKeyDown", **common),)


def text_calls(event: TextInput) -> tuple[CdpCall, ...]:
    return (_call("Input.insertText", text=event.text),)


def input_calls(event: LiveInputEvent, meta: FrameMeta | None) -> tuple[CdpCall, ...]:
    """The CDP calls one input becomes, in order. ``()`` drops it (no frame yet, or outside it).
    ``NavInput`` is ``LiveSession``'s: Back needs the page's history first."""
    if isinstance(event, MouseInput):
        return mouse_calls(event, meta)
    if isinstance(event, WheelInput):
        return wheel_calls(event, meta)
    if isinstance(event, KeyInput):
        return key_calls(event)
    if isinstance(event, TextInput):
        return text_calls(event)
    return ()


def back_entry_id(history: Mapping[str, Any]) -> int | None:
    """``Page.getNavigationHistory``'s result: the id of the entry one step back, or None on the
    first page or in a history that can't be read."""
    index, entries = history.get("currentIndex"), history.get("entries")
    if not isinstance(index, int) or not isinstance(entries, list) or not 0 < index < len(entries):
        return None
    entry = entries[index - 1]
    entry_id = entry.get("id") if isinstance(entry, dict) else None
    return entry_id if isinstance(entry_id, int) else None


class InputRateLimit:
    """At most ``LIVE_INPUT_MAX_PER_SECOND`` inputs in any ``LIVE_INPUT_RATE_WINDOW_S``; the rest are
    dropped (design §2). One per live socket. The kept times are a tuple that is replaced, never
    changed. ``limit=None`` reads the constant when the limit is built, so a test can patch it."""

    def __init__(self, *, limit: int | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = LIVE_INPUT_MAX_PER_SECOND if limit is None else limit
        self._clock = clock
        self._times: tuple[float, ...] = ()

    def allow(self) -> bool:
        now = self._clock()
        recent = tuple(t for t in self._times if now - t < LIVE_INPUT_RATE_WINDOW_S)
        if len(recent) >= self._limit:
            self._times = recent
            return False
        self._times = (*recent, now)
        return True
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_live_input.py --cov=roost.desk.live_input --cov-report=term-missing -q`
Expected: PASS, with `roost/desk/live_input.py` at 100%.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/desk/live_input.py roost/constants.py tests/test_live_input.py
git commit -m "feat: live control input: an allow-list of keys, frame space to CSS pixels, exact CDP calls and a rate limit"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the three files is listed.

---

### Task 4: The live session: screencast, acks, pop-ups and input

Design §2 "Frames", "Which page is shown", "How input reaches the page" and "Ending", L4:
- **`LiveView`** (`roost/desk/__init__.py`) is what a desk hands live control: the CDP connection to the bot's running browser (`CdpChannel`) and the bot's own page on it (`target_id`). Task 5 makes the desks hand one out.
- **`LiveSession(view, sink)`** shows one page of that browser. It shares the bot's own `CdpClient`, because the keeper's relay takes one client per bot, but it works on CDP sessions of its own, attached to the page it shows.
- **`start()`** subscribes first (so nothing is missed), turns `Target.setDiscoverTargets` on, and shows the bot's page: `Target.attachToTarget` (flatten), `Page.enable`, `Page.startScreencast {format: "jpeg", quality: LIVE_JPEG_QUALITY, maxWidth: LIVE_MAX_WIDTH, maxHeight: LIVE_MAX_HEIGHT, everyNthFrame: 1}`, then `Target.getTargetInfo` for the address bar.
- **`run()`** pumps two subscriptions until the end:
  - `Page.screencastFrame`. A frame of the shown page goes to the sink with its metadata (`LiveFrame`); a frame of a page no longer shown is dropped. Every frame is then acked with `Page.screencastFrameAck`, no sooner than `LIVE_MIN_FRAME_INTERVAL_S` after the last ack (about 10 fps). Frames are never written anywhere.
  - The three target events, in one queue in the browser's order (D3):
    - A new `page` whose `openerId` is the bot's page, while the bot's page is on screen, is shown at once. If it can't be attached (it closed already), the bot's page is shown again (Review Focus 3).
    - When the shown pop-up is destroyed, the bot's page comes back (Review Focus 3).
    - When the bot's own page is destroyed, the session ends `"page_closed"`.
    - `Target.targetInfoChanged` for the shown page goes to the sink as `PageInfo` (the address bar).
  - `run()` returns `"disconnected"` when the connection ends (Review Focus 5), `"page_closed"`, or `"stopped"`.
- **`handle(event)`** sends one checked input to the shown page on this session's CDP session. It returns `"sent"`, `"dropped"` (nothing on screen yet, or a point outside the frame), or `"failed"` (the page refused it; the route tells the user). Back reads `Page.getNavigationHistory` and goes to `back_entry_id`; Reload is `Page.reload`. Nothing here logs an input or anything about one (Review Focus 1).
- **`stop()`** closes the subscriptions, stops the screencast, detaches, and turns discovery off. It is safe to call twice, and on a connection that is already gone.
- A CDP error while following a page (`CdpReplyError`) is a warning naming the event, never the input. A dead connection (`CdpClientError`) ends the pump, and with it `run()`.

**Files:**
- Create: `roost/desk/live.py`, `tests/test_live_session.py`
- Modify: `roost/desk/__init__.py` (`LiveView`), `roost/constants.py` (append the screencast constants)

**Interfaces:**
- Consumes:
  - Task 2: `CdpChannel`, `CdpSubscription`, `CdpClient.subscribe`, `CdpClientError`, `CdpReplyError`.
  - Task 3: `FrameMeta`, `frame_meta`, `LiveInputEvent`, `NavInput`, `input_calls`, `back_entry_id`.
  - `tests/team_helpers.until`.
- Produces: `LiveView(cdp, target_id)`; from `roost.desk.live`: `LiveSession` (`start`, `run`, `handle`, `stop`, `shown_target`), `LiveFrame`, `PageInfo`, `LiveSink`, `InputResult`, `LiveEnd`, `FRAME_EVENT`, `TARGET_EVENTS`; the constants `LIVE_JPEG_QUALITY`, `LIVE_MAX_WIDTH`, `LIVE_MAX_HEIGHT`, `LIVE_EVERY_NTH_FRAME`, `LIVE_MIN_FRAME_INTERVAL_S`. `LIVE_MIN_FRAME_INTERVAL_S` is imported by name, so tests patch `roost.desk.live.LIVE_MIN_FRAME_INTERVAL_S`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_live_session.py`:

```python
"""``LiveSession`` (live control, Task 4; design §2): the screencast, the acks, pop-ups and input,
against a fake CDP WebSocket server through the real ``CdpClient``. Never a real browser.

``_ScreencastServer`` plays a bot's browser: each screencast sends ``frames`` frames for its page,
the first when it starts and each next one when the last is acked, as a real browser does."""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import pytest
import websockets

import roost.desk.live as live_module
from roost.constants import LIVE_EVERY_NTH_FRAME, LIVE_JPEG_QUALITY, LIVE_MAX_HEIGHT, LIVE_MAX_WIDTH
from roost.desk import LiveView
from roost.desk.cdp import CdpClient
from roost.desk.live import LiveFrame, LiveSession, PageInfo
from roost.desk.live_input import FrameMeta, KeyInput, MouseInput, NavInput, TextInput
from team_helpers import until

_BOT = "bot-page"
_POP_UP = "pop-up"
_OTHER_TAB = "other-tab"
_BOT_URL = "https://shop.example/login"
_POP_UP_URL = "https://accounts.example/signin"
_META = {"deviceWidth": 1280, "deviceHeight": 800, "pageScaleFactor": 1, "offsetTop": 0,
         "scrollOffsetX": 0, "scrollOffsetY": 0, "timestamp": 1.0}
_SECRET = "hunter2-correct-horse"
_ANSWERED = frozenset({
    "Target.setDiscoverTargets", "Target.detachFromTarget", "Page.enable", "Page.startScreencast",
    "Page.stopScreencast", "Page.screencastFrameAck", "Page.reload", "Page.navigateToHistoryEntry",
    "Input.dispatchMouseEvent", "Input.dispatchKeyEvent", "Input.insertText",
})


def _jpeg(target_id: str, n: int) -> bytes:
    return f"jpeg {target_id} {n}".encode()


class _ScreencastServer:
    """Plays a bot's browser for live control. ``gone`` holds targets that can't be attached any more;
    ``refused`` holds methods answered with a CDP error. Every message received is kept, in order."""

    def __init__(self, frames: int = 3) -> None:
        self.received: list[dict[str, Any]] = []
        self.targets: dict[str, dict[str, str]] = {_BOT: {"url": _BOT_URL, "title": "Sign in"}}
        self.gone: set[str] = set()
        self.refused: set[str] = set()
        self.history: dict[str, Any] = {
            "currentIndex": 1, "entries": [{"id": 7, "url": "https://shop.example/"}, {"id": 8, "url": _BOT_URL}],
        }
        self._frames = frames
        self._target_of: dict[str, str] = {}
        self._sent: dict[str, int] = {}
        self._numbers = itertools.count(1)
        self._sessions = itertools.count(1)
        self._connection: Any = None
        self._server: Any = None

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle, "127.0.0.1", 0)

    async def stop(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        server.close()
        await server.wait_closed()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self._server.sockets[0].getsockname()[1]}"

    def methods(self) -> list[str]:
        return [message["method"] for message in self.received]

    async def push(self, method: str, params: dict[str, Any], session_id: str | None = None) -> None:
        event: dict[str, Any] = {"method": method, "params": params}
        if session_id is not None:
            event["sessionId"] = session_id
        await self._connection.send(json.dumps(event))

    async def _handle(self, connection: Any) -> None:
        self._connection = connection
        async for raw in connection:
            message = json.loads(raw)
            self.received.append(message)
            await self._answer(connection, message)

    async def _answer(self, connection: Any, message: dict[str, Any]) -> None:
        method, params, session = message["method"], message.get("params") or {}, message.get("sessionId")
        result = None if method in self.refused else self._result(method, params)
        if result is None:
            reply = {"id": message["id"], "error": {"message": f"refused {method}"}}
        else:
            reply = {"id": message["id"], "result": result}
        await connection.send(json.dumps(reply))
        if result is not None and method in ("Page.startScreencast", "Page.screencastFrameAck"):
            await self._next_frame(connection, session)

    def _result(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if method == "Target.attachToTarget":
            target_id = params.get("targetId")
            if target_id in self.gone or target_id not in self.targets:
                return None
            session = f"live-{next(self._sessions)}"
            self._target_of[session] = target_id
            return {"sessionId": session}
        if method == "Target.getTargetInfo":
            target_id = params.get("targetId")
            return {"targetInfo": {"targetId": target_id, "type": "page", **self.targets.get(target_id, {})}}
        if method == "Page.getNavigationHistory":
            return self.history
        return {} if method in _ANSWERED else None

    async def _next_frame(self, connection: Any, session: str | None) -> None:
        target_id = self._target_of.get(session or "")
        sent = self._sent.get(session or "", 0)
        if target_id is None or target_id in self.gone or sent >= self._frames:
            return
        self._sent[session] = sent + 1
        data = base64.b64encode(_jpeg(target_id, sent + 1)).decode()
        await connection.send(json.dumps({"method": "Page.screencastFrame", "sessionId": session, "params": {
            "data": data, "metadata": _META, "sessionId": next(self._numbers)}}))


class _Sink:
    def __init__(self) -> None:
        self.frames: list[LiveFrame] = []
        self.pages: list[PageInfo] = []

    async def frame(self, frame: LiveFrame) -> None:
        self.frames.append(frame)

    async def page(self, info: PageInfo) -> None:
        self.pages.append(info)

    def from_target(self, target_id: str) -> list[LiveFrame]:
        return [frame for frame in self.frames if frame.jpeg.split(b" ")[1] == target_id.encode()]


@pytest.fixture(autouse=True)
def _no_frame_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_module, "LIVE_MIN_FRAME_INTERVAL_S", 0.0)


@pytest.fixture
async def server():
    fake = _ScreencastServer()
    await fake.start()
    try:
        yield fake
    finally:
        await fake.stop()


@pytest.fixture
async def cdp(server: _ScreencastServer):
    client = CdpClient(server.url, "token")
    await client.connect()
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def sink() -> _Sink:
    return _Sink()


def _session(cdp: CdpClient, sink: _Sink) -> LiveSession:
    return LiveSession(LiveView(cdp=cdp, target_id=_BOT), sink)


@asynccontextmanager
async def _live(cdp: CdpClient, sink: _Sink) -> AsyncIterator[tuple[LiveSession, "asyncio.Task[str]"]]:
    session = _session(cdp, sink)
    await session.start()
    running = asyncio.create_task(session.run())
    try:
        yield session, running
    finally:
        await session.stop()
        await asyncio.wait_for(running, timeout=2)


async def _bot_frames_acked(server: _ScreencastServer, sink: _Sink) -> None:
    await until(lambda: len(sink.frames) >= 3 and server.methods().count("Page.screencastFrameAck") >= 3)


async def _open_pop_up(server: _ScreencastServer, sink: _Sink) -> None:
    await _bot_frames_acked(server, sink)
    server.targets[_POP_UP] = {"url": _POP_UP_URL, "title": "Sign in with Example"}
    await server.push("Target.targetCreated", {"targetInfo": {
        "targetId": _POP_UP, "type": "page", "openerId": _BOT, "url": _POP_UP_URL, "title": "Sign in with Example"}})
    await until(lambda: len(sink.from_target(_POP_UP)) == 3)


def _attached(server: _ScreencastServer) -> list[str]:
    return [m["params"]["targetId"] for m in server.received if m["method"] == "Target.attachToTarget"]


# -- the screencast --


async def test_start_shows_the_bots_page_with_the_exact_screencast(server, cdp, sink):
    async with _live(cdp, sink) as (session, _running):
        await until(lambda: len(sink.frames) == 3)
        assert session.shown_target == _BOT
    assert server.methods()[:5] == [
        "Target.setDiscoverTargets", "Target.attachToTarget", "Page.enable", "Page.startScreencast",
        "Target.getTargetInfo",
    ]
    assert server.received[0]["params"] == {"discover": True}
    assert server.received[1]["params"] == {"targetId": _BOT, "flatten": True}
    start = server.received[3]
    assert start["params"] == {"format": "jpeg", "quality": LIVE_JPEG_QUALITY, "maxWidth": LIVE_MAX_WIDTH,
                               "maxHeight": LIVE_MAX_HEIGHT, "everyNthFrame": LIVE_EVERY_NTH_FRAME}
    assert start["sessionId"] == "live-1"
    assert sink.pages[0] == PageInfo(url=_BOT_URL, title="Sign in")


async def test_every_frame_goes_out_with_its_metadata_then_is_acked(server, cdp, sink):
    async with _live(cdp, sink):
        await _bot_frames_acked(server, sink)
    assert [frame.jpeg for frame in sink.frames] == [_jpeg(_BOT, n) for n in (1, 2, 3)]
    assert {frame.meta for frame in sink.frames} == {FrameMeta(1280, 800)}
    acks = [m for m in server.received if m["method"] == "Page.screencastFrameAck"]
    assert [ack["params"]["sessionId"] for ack in acks] == [1, 2, 3]
    assert {ack["sessionId"] for ack in acks} == {"live-1"}


async def test_frames_are_acked_about_ten_a_second(server, cdp, sink, monkeypatch):
    monkeypatch.setattr(live_module, "LIVE_MIN_FRAME_INTERVAL_S", 0.05)
    loop = asyncio.get_running_loop()
    started = loop.time()
    async with _live(cdp, sink):
        await until(lambda: server.methods().count("Page.screencastFrameAck") == 3)
        assert loop.time() - started >= 0.1          # three acks, two waits between them


async def test_a_frame_of_a_page_no_longer_shown_is_acked_but_never_forwarded(server, cdp, sink):
    async with _live(cdp, sink):
        await _bot_frames_acked(server, sink)
        data = base64.b64encode(_jpeg("old", 1)).decode()
        await server.push("Page.screencastFrame", {"data": data, "metadata": _META, "sessionId": 99},
                          session_id="live-old")
        await until(lambda: any(m["params"].get("sessionId") == 99 for m in server.received
                                if m["method"] == "Page.screencastFrameAck"))
    assert len(sink.frames) == 3


# -- pop-ups (Review Focus 3) --


async def test_a_pop_up_opened_by_the_bots_page_is_shown_at_once(server, cdp, sink):
    async with _live(cdp, sink) as (session, _running):
        await _open_pop_up(server, sink)
        assert session.shown_target == _POP_UP
    after = server.received[server.methods().index("Page.stopScreencast"):]
    assert [m["method"] for m in after][:3] == ["Page.stopScreencast", "Target.detachFromTarget", "Target.attachToTarget"]
    assert after[0]["sessionId"] == "live-1"
    assert after[1]["params"] == {"sessionId": "live-1"}
    assert after[2]["params"] == {"targetId": _POP_UP, "flatten": True}
    assert PageInfo(url=_POP_UP_URL, title="Sign in with Example") in sink.pages


async def test_when_the_pop_up_closes_the_screen_returns_to_the_bots_page(server, cdp, sink):
    """Review Focus 3: "Sign in with Google" closes itself once you are signed in. The live screen
    must come back to the bot's page, never stay on a page that is gone."""
    async with _live(cdp, sink) as (session, _running):
        await _open_pop_up(server, sink)
        server.gone.add(_POP_UP)
        await server.push("Target.targetDestroyed", {"targetId": _POP_UP})
        await until(lambda: session.shown_target == _BOT and len(sink.from_target(_BOT)) == 6)
    assert _attached(server) == [_BOT, _POP_UP, _BOT]
    assert sink.pages[-1] == PageInfo(url=_BOT_URL, title="Sign in")


async def test_a_pop_up_that_closes_before_it_is_shown_leaves_the_bots_page_on_screen(server, cdp, sink):
    """Review Focus 3: the pop-up is gone before it can be attached. The bot's page comes back at once."""
    async with _live(cdp, sink) as (session, _running):
        await _bot_frames_acked(server, sink)
        server.gone.add(_POP_UP)
        await server.push("Target.targetCreated", {"targetInfo": {"targetId": _POP_UP, "type": "page", "openerId": _BOT}})
        await until(lambda: len(sink.from_target(_BOT)) == 6)
        assert session.shown_target == _BOT
    assert _attached(server) == [_BOT, _POP_UP, _BOT]


@pytest.mark.parametrize("info", [
    {"targetId": _OTHER_TAB, "type": "page", "openerId": "someone-else"},
    {"targetId": _OTHER_TAB, "type": "page"},
    {"targetId": "worker", "type": "service_worker", "openerId": _BOT},
])
async def test_a_target_the_bots_page_did_not_open_is_never_shown(server, cdp, sink, info):
    async with _live(cdp, sink) as (session, _running):
        await _bot_frames_acked(server, sink)
        server.targets[info["targetId"]] = {"url": "https://other.example/", "title": "Other"}
        await server.push("Target.targetCreated", {"targetInfo": info})
        await server.push("Target.targetInfoChanged", {"targetInfo": {
            "targetId": _BOT, "url": _BOT_URL + "?step=2", "title": "Step 2"}})
        await until(lambda: sink.pages[-1].title == "Step 2")   # the target queue got past the creation
        assert session.shown_target == _BOT
    assert _attached(server) == [_BOT]


async def test_the_address_bar_follows_the_shown_page_only(server, cdp, sink):
    async with _live(cdp, sink):
        await _bot_frames_acked(server, sink)
        await server.push("Target.targetInfoChanged", {"targetInfo": {
            "targetId": _OTHER_TAB, "url": "https://other.example/", "title": "Other"}})
        await server.push("Target.targetInfoChanged", {"targetInfo": {
            "targetId": _BOT, "url": "https://shop.example/orders", "title": "Your orders"}})
        await until(lambda: sink.pages[-1].title == "Your orders")
    assert [page.title for page in sink.pages] == ["Sign in", "Your orders"]


# -- input --


async def test_input_becomes_the_exact_cdp_calls_on_the_shown_page(server, cdp, sink):
    async with _live(cdp, sink) as (session, _running):
        await _bot_frames_acked(server, sink)
        assert await session.handle(MouseInput(t="mouse", kind="down", x=100, y=50, button="left", clicks=1)) == "sent"
        assert await session.handle(KeyInput(t="key", kind="down", key="a", code="KeyA")) == "sent"
        assert await session.handle(TextInput(t="text", text="ana@example.com")) == "sent"
    sent = [(m["method"], m["params"], m["sessionId"]) for m in server.received if m["method"].startswith("Input.")]
    assert sent == [
        ("Input.dispatchMouseEvent",
         {"type": "mousePressed", "x": 100, "y": 50, "button": "left", "clickCount": 1, "modifiers": 0}, "live-1"),
        ("Input.dispatchKeyEvent",
         {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 0,
          "text": "a", "unmodifiedText": "a"}, "live-1"),
        ("Input.insertText", {"text": "ana@example.com"}, "live-1"),
    ]


async def test_a_point_outside_the_frame_is_dropped(server, cdp, sink):
    async with _live(cdp, sink) as (session, _running):
        await _bot_frames_acked(server, sink)
        outside = MouseInput(t="mouse", kind="down", x=5000, y=50, button="left", clicks=1)
        assert await session.handle(outside) == "dropped"
    assert "Input.dispatchMouseEvent" not in server.methods()


async def test_input_before_anything_is_on_screen_is_dropped(cdp, sink):
    assert await _session(cdp, sink).handle(TextInput(t="text", text="early")) == "dropped"


async def test_back_goes_one_entry_back_and_reload_reloads(server, cdp, sink):
    async with _live(cdp, sink) as (session, _running):
        await _bot_frames_acked(server, sink)
        assert await session.handle(NavInput(t="nav", action="back")) == "sent"
        assert await session.handle(NavInput(t="nav", action="reload")) == "sent"
    navigation = [(m["method"], m["params"]) for m in server.received
                  if m["method"] in ("Page.getNavigationHistory", "Page.navigateToHistoryEntry", "Page.reload")]
    assert navigation == [("Page.getNavigationHistory", {}), ("Page.navigateToHistoryEntry", {"entryId": 7}),
                          ("Page.reload", {})]


async def test_back_on_the_first_page_does_nothing(server, cdp, sink):
    server.history = {"currentIndex": 0, "entries": [{"id": 7, "url": _BOT_URL}]}
    async with _live(cdp, sink) as (session, _running):
        await _bot_frames_acked(server, sink)
        assert await session.handle(NavInput(t="nav", action="back")) == "dropped"
    assert "Page.navigateToHistoryEntry" not in server.methods()


async def test_a_refused_input_is_failed_and_never_raised(server, cdp, sink):
    server.refused.add("Input.insertText")
    async with _live(cdp, sink) as (session, _running):
        await _bot_frames_acked(server, sink)
        assert await session.handle(TextInput(t="text", text="ana@example.com")) == "failed"


async def test_live_session_never_logs_what_was_typed(server, cdp, sink, caplog):
    """Review Focus 1, in the session: sent, refused or dropped, typed text never reaches a log."""
    caplog.set_level(logging.DEBUG)
    server.refused.add("Input.insertText")
    async with _live(cdp, sink) as (session, _running):
        await _bot_frames_acked(server, sink)
        await session.handle(KeyInput(t="key", kind="down", key="h", code="KeyH"))
        await session.handle(TextInput(t="text", text=_SECRET))
        await session.handle(MouseInput(t="mouse", kind="down", x=-5, y=1, button="left", clicks=1))
    assert _SECRET not in caplog.text
    assert "KeyH" not in caplog.text


# -- the end --


async def test_stop_ends_the_screencast_and_switches_discovery_off(server, cdp, sink):
    session = _session(cdp, sink)
    await session.start()
    running = asyncio.create_task(session.run())
    await _bot_frames_acked(server, sink)
    await session.stop()
    assert await asyncio.wait_for(running, timeout=2) == "stopped"
    assert server.methods()[-3:] == ["Page.stopScreencast", "Target.detachFromTarget", "Target.setDiscoverTargets"]
    assert server.received[-1]["params"] == {"discover": False}
    await session.stop()                               # twice is fine
    assert server.methods().count("Target.setDiscoverTargets") == 2


async def test_the_session_ends_when_the_connection_closes(server, cdp, sink):
    """Review Focus 5: Brave crashed or the keeper restarted."""
    session = _session(cdp, sink)
    await session.start()
    running = asyncio.create_task(session.run())
    await _bot_frames_acked(server, sink)
    await server.stop()
    assert await asyncio.wait_for(running, timeout=2) == "disconnected"
    await session.stop()                               # on a dead connection, still clean


async def test_closing_the_bots_page_ends_the_session(server, cdp, sink):
    session = _session(cdp, sink)
    await session.start()
    running = asyncio.create_task(session.run())
    await _bot_frames_acked(server, sink)
    await server.push("Target.targetDestroyed", {"targetId": _BOT})
    assert await asyncio.wait_for(running, timeout=2) == "page_closed"
    await session.stop()


async def test_a_page_that_cannot_be_shown_fails_start(server, cdp, sink):
    server.gone.add(_BOT)
    with pytest.raises(Exception) as failed:
        await _session(cdp, sink).start()
    assert type(failed.value).__name__ == "CdpReplyError"


# -- what goes wrong on the way --


async def test_a_frame_that_is_not_a_jpeg_is_acked_but_never_forwarded(server, cdp, sink):
    async with _live(cdp, sink):
        await _bot_frames_acked(server, sink)
        await server.push("Page.screencastFrame", {"data": "", "metadata": _META, "sessionId": 97}, session_id="live-1")
        await server.push("Page.screencastFrame", {"data": "not base64!", "metadata": _META, "sessionId": 98},
                          session_id="live-1")
        unnumbered = base64.b64encode(_jpeg(_BOT, 9)).decode()
        await server.push("Page.screencastFrame", {"data": unnumbered, "metadata": _META}, session_id="live-1")
        await until(lambda: len(sink.frames) == 4)
    acked = [m["params"]["sessionId"] for m in server.received if m["method"] == "Page.screencastFrameAck"]
    assert acked == [1, 2, 3, 97, 98]                  # a frame with no number can't be acked
    assert sink.frames[-1].jpeg == _jpeg(_BOT, 9)


async def test_a_refused_ack_is_a_warning_and_the_screen_stays_up(server, cdp, sink, caplog):
    server.refused.add("Page.screencastFrameAck")
    caplog.set_level(logging.DEBUG, logger=live_module.logger.name)
    async with _live(cdp, sink) as (_session_, running):
        await until(lambda: any("could not follow Page.screencastFrame" in r.getMessage() for r in caplog.records))
        assert not running.done()
        data = base64.b64encode(_jpeg("old", 1)).decode()
        await server.push("Page.screencastFrame", {"data": data, "metadata": _META, "sessionId": 99},
                          session_id="live-old")
        await until(lambda: any("no longer shown" in r.getMessage() for r in caplog.records))
    assert len(sink.frames) == 1


async def test_a_second_pop_up_while_one_is_shown_is_left_alone(server, cdp, sink):
    async with _live(cdp, sink) as (session, _running):
        await _open_pop_up(server, sink)
        server.targets["second"] = {"url": "https://other.example/", "title": "Second"}
        await server.push("Target.targetCreated", {"targetInfo": {"targetId": "second", "type": "page", "openerId": _BOT}})
        await server.push("Target.targetInfoChanged", {"targetInfo": {
            "targetId": _POP_UP, "url": _POP_UP_URL + "#step-2", "title": "Step 2"}})
        await until(lambda: sink.pages[-1].title == "Step 2")
        assert session.shown_target == _POP_UP
    assert _attached(server) == [_BOT, _POP_UP]


async def test_stopping_a_page_that_is_already_gone_still_ends_cleanly(server, cdp, sink):
    server.refused.update({"Page.stopScreencast", "Target.detachFromTarget"})
    session = _session(cdp, sink)
    await session.start()
    running = asyncio.create_task(session.run())
    await _bot_frames_acked(server, sink)
    await session.stop()
    assert await asyncio.wait_for(running, timeout=2) == "stopped"
    assert server.received[-1]["params"] == {"discover": False}
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_live_session.py -q`
Expected: FAIL with one collection error: `ImportError: cannot import name 'LIVE_EVERY_NTH_FRAME' from 'roost.constants'`.

- [ ] **Step 4: Add the screencast constants and `LiveView`**

Append this to the very end of `roost/constants.py`:

```python

# Task 4 — roost/desk/live.py. About 10 fps, at most 1280 px wide.
LIVE_JPEG_QUALITY = 70
LIVE_MAX_WIDTH = 1280
LIVE_MAX_HEIGHT = 1280
LIVE_EVERY_NTH_FRAME = 1
LIVE_MIN_FRAME_INTERVAL_S = 0.1          # a frame is acked no sooner than this after the last ack
```

In `roost/desk/__init__.py`, replace these lines:

```python
from dataclasses import dataclass
from typing import Literal, Protocol

from roost.config import RoostConfig
```

with:

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from roost.config import RoostConfig

if TYPE_CHECKING:
    from roost.desk.cdp import CdpChannel
```

Then replace these lines:

```python
class DeskAsleep(RuntimeError):
    """The bot's browser is closed. A screenshot never starts it (S1.8): the
    Computer tab says "<bot>'s computer is asleep · Open it" instead."""
```

with:

```python
class DeskAsleep(RuntimeError):
    """The bot's browser is closed. A screenshot never starts it (S1.8): the
    Computer tab says "<bot>'s computer is asleep · Open it" instead."""


@dataclass(frozen=True)
class LiveView:
    """Live control (design §2): the CDP connection to a bot's running browser, and the bot's own
    page on it. ``Desk.live_view`` hands one out, and never starts a browser to do it."""

    cdp: CdpChannel
    target_id: str
```

- [ ] **Step 5: Implement `roost/desk/live.py`**

Create `roost/desk/live.py`:

```python
"""Live control (design §2, L4): the user's live screen of one page of a bot's running browser.

``LiveSession`` works through that browser's own private CDP connection: the same ``CdpClient``
the bot's tab uses (the keeper's relay takes one client per bot), or ``FakeCdp`` in fake mode.
There is no VNC, no screen sharing and no DevTools frontend.

- **Frames.** On a CDP session of its own on the shown page it sends ``Page.startScreencast``.
  Each ``Page.screencastFrame`` of that page goes to the sink with its metadata, then is acked, no
  sooner than ``LIVE_MIN_FRAME_INTERVAL_S`` after the last ack (about 10 fps). A frame of a page no
  longer shown is acked and dropped. Frames are never written anywhere.
- **Pop-ups.** ``Target.setDiscoverTargets`` is on only while a session runs. A new ``page`` whose
  opener is the bot's page is shown at once; when it closes, or can't be shown, the bot's page comes
  back. The target events share one queue, so their order is the browser's.
- **The address bar.** ``Target.targetInfoChanged`` for the shown page goes to the sink.
- **Input.** ``handle`` sends one checked input (``roost.desk.live_input``) to the shown page.
  Nothing here logs an input, or anything about one.
- It never opens a tab and never starts a browser: ``Desk.live_view`` hands it a running one.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Literal, Mapping, Protocol

from roost.constants import (
    LIVE_EVERY_NTH_FRAME, LIVE_JPEG_QUALITY, LIVE_MAX_HEIGHT, LIVE_MAX_WIDTH, LIVE_MIN_FRAME_INTERVAL_S,
)
from roost.desk import LiveView
from roost.desk.cdp import CdpChannel, CdpClientError, CdpReplyError, CdpSubscription
from roost.desk.live_input import (
    FrameMeta, LiveInputEvent, NavInput, back_entry_id, frame_meta, input_calls,
)

logger = logging.getLogger(__name__)

InputResult = Literal["sent", "dropped", "failed"]
LiveEnd = Literal["stopped", "page_closed", "disconnected"]

FRAME_EVENT = "Page.screencastFrame"
TARGET_EVENTS = ("Target.targetCreated", "Target.targetDestroyed", "Target.targetInfoChanged")
_SCREENCAST: Mapping[str, Any] = MappingProxyType({
    "format": "jpeg", "quality": LIVE_JPEG_QUALITY, "maxWidth": LIVE_MAX_WIDTH, "maxHeight": LIVE_MAX_HEIGHT,
    "everyNthFrame": LIVE_EVERY_NTH_FRAME,
})


@dataclass(frozen=True)
class LiveFrame:
    meta: FrameMeta
    jpeg: bytes


@dataclass(frozen=True)
class PageInfo:
    url: str
    title: str


class LiveSink(Protocol):
    """Where a session's output goes: the gateway's socket (``LiveSocketSink``), or a test's recorder."""

    async def frame(self, frame: LiveFrame) -> None: ...

    async def page(self, info: PageInfo) -> None: ...


def _page_info(info: Any) -> PageInfo:
    found = info if isinstance(info, dict) else {}
    return PageInfo(url=str(found.get("url") or ""), title=str(found.get("title") or ""))


def _jpeg(data: Any) -> bytes | None:
    if not isinstance(data, str) or not data:
        return None
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


class LiveSession:
    def __init__(self, view: LiveView, sink: LiveSink, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._cdp: CdpChannel = view.cdp
        self._bot_target = view.target_id
        self._sink = sink
        self._clock = clock
        self._shown: str | None = None          # the target on screen
        self._session: str | None = None        # this session's own CDP session on it
        self._meta: FrameMeta | None = None     # the newest frame's metadata, for mapping input
        self._last_ack: float | None = None
        self._subscriptions: tuple[CdpSubscription, ...] = ()
        self._switch = asyncio.Lock()
        self._end: LiveEnd = "disconnected"     # until stop() or the bot's page closing says otherwise
        self._stopped = False

    @property
    def shown_target(self) -> str | None:
        return self._shown

    async def start(self) -> None:
        """Subscribe first, so nothing is missed, then show the bot's page. Raises ``CdpClientError``
        (or its ``CdpReplyError``) when the browser can't be reached or the page can't be shown."""
        self._subscriptions = (self._cdp.subscribe(FRAME_EVENT), self._cdp.subscribe(TARGET_EVENTS))
        await self._cdp.send("Target.setDiscoverTargets", {"discover": True})
        await self._show(self._bot_target)

    async def run(self) -> LiveEnd:
        """After ``start``: until the connection ends ("disconnected"), the bot's page closes
        ("page_closed") or ``stop`` runs ("stopped")."""
        frames, targets = self._subscriptions
        pumps = (asyncio.create_task(self._pump(frames, self._on_frame)),
                 asyncio.create_task(self._pump(targets, self._on_target)))
        try:
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
        return self._end

    async def handle(self, event: LiveInputEvent) -> InputResult:
        """Send one checked input to the shown page. "dropped": nothing on screen yet, or a point
        outside the frame. "failed": the page refused it, or the connection is gone (the caller tells
        the user). Never logged: an input is what the user typed."""
        session = self._session
        if session is None:
            return "dropped"
        try:
            if isinstance(event, NavInput):
                return await self._navigate(session, event)
            return await self._send_input(session, event)
        except CdpClientError:
            return "failed"

    async def stop(self) -> None:
        """End the session: the subscriptions, the screencast and target discovery. Safe to call
        twice, and on a connection that is already gone."""
        if self._stopped:
            return
        self._stopped = True
        self._finish("stopped")
        try:
            async with self._switch:
                await self._leave()
            await self._cdp.send("Target.setDiscoverTargets", {"discover": False})
        except CdpClientError as exc:
            logger.debug("Live control ended on a connection that was already gone (%s)", type(exc).__name__)

    async def _pump(self, subscription: CdpSubscription,
                    handle: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Handle each event in turn. A refused command (``CdpReplyError``: the page went away
        mid-way) is a warning; a dead connection ends the pump, and with it ``run``."""
        async for event in subscription:
            try:
                await handle(event)
            except CdpReplyError as exc:
                logger.warning("Live control could not follow %s: %s", event.get("method"), exc)
            except CdpClientError:
                return

    async def _on_frame(self, event: dict[str, Any]) -> None:
        session = event.get("sessionId")
        params = event.get("params") or {}
        meta, jpeg = frame_meta(params.get("metadata")), _jpeg(params.get("data"))
        if session is not None and session == self._session and meta is not None and jpeg is not None:
            self._meta = meta
            await self._sink.frame(LiveFrame(meta, jpeg))
        await self._ack(session, params.get("sessionId"))

    async def _ack(self, session: str | None, frame_number: Any) -> None:
        """Ack one frame, so the browser sends the next, about every ``LIVE_MIN_FRAME_INTERVAL_S``.
        A page no longer shown may be gone already: refusing that ack is expected."""
        if session is None or not isinstance(frame_number, int):
            return
        if self._last_ack is not None:
            wait = self._last_ack + LIVE_MIN_FRAME_INTERVAL_S - self._clock()
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_ack = self._clock()
        try:
            await self._cdp.send("Page.screencastFrameAck", {"sessionId": frame_number}, session_id=session)
        except CdpReplyError:
            if session == self._session:
                raise
            logger.debug("Live control: a frame of a page no longer shown could not be acked")

    async def _on_target(self, event: dict[str, Any]) -> None:
        params = event.get("params") or {}
        method = event.get("method")
        if method == "Target.targetCreated":
            await self._on_created(params.get("targetInfo") or {})
        elif method == "Target.targetDestroyed":
            await self._on_destroyed(params.get("targetId"))
        else:
            info = params.get("targetInfo") or {}
            if info.get("targetId") == self._shown:
                await self._sink.page(_page_info(info))

    async def _on_created(self, info: dict[str, Any]) -> None:
        """A pop-up or new tab opened by the bot's page, while the bot's page is on screen, is shown."""
        target_id = info.get("targetId")
        if info.get("type") != "page" or info.get("openerId") != self._bot_target or not isinstance(target_id, str):
            return
        if self._shown != self._bot_target:
            return
        try:
            await self._show(target_id)
        except CdpReplyError:
            # Review Focus 3: it closed before it could be shown, so the bot's page comes back.
            await self._show(self._bot_target)

    async def _on_destroyed(self, target_id: Any) -> None:
        if target_id == self._bot_target:
            self._finish("page_closed")
        elif target_id is not None and target_id == self._shown:
            await self._show(self._bot_target)   # Review Focus 3: the pop-up closed

    async def _show(self, target_id: str) -> None:
        """Move the screencast to ``target_id``. The old page's screencast stops first."""
        async with self._switch:
            await self._leave()
            attached = await self._cdp.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
            session = attached.get("result", {}).get("sessionId")
            if not isinstance(session, str):
                raise CdpReplyError("Target.attachToTarget gave no session for the page to show")
            self._shown, self._session = target_id, session
            await self._cdp.send("Page.enable", session_id=session)
            await self._cdp.send("Page.startScreencast", dict(_SCREENCAST), session_id=session)
            info = await self._cdp.send("Target.getTargetInfo", {"targetId": target_id})
        await self._sink.page(_page_info(info.get("result", {}).get("targetInfo")))

    async def _leave(self) -> None:
        """Stop showing the current page. It may be gone already, so a refusal here is expected."""
        session, self._session, self._meta = self._session, None, None
        if session is None:
            return
        await self._quietly("Page.stopScreencast", None, session)
        await self._quietly("Target.detachFromTarget", {"sessionId": session}, None)

    async def _quietly(self, method: str, params: dict[str, Any] | None, session_id: str | None) -> None:
        try:
            await self._cdp.send(method, params, session_id=session_id)
        except CdpReplyError:
            logger.debug("Live control: %s refused for a page already gone", method)

    async def _send_input(self, session: str, event: LiveInputEvent) -> InputResult:
        calls = input_calls(event, self._meta)
        for call in calls:
            await self._cdp.send(call.method, dict(call.params), session_id=session)
        return "sent" if calls else "dropped"

    async def _navigate(self, session: str, event: NavInput) -> InputResult:
        if event.action == "reload":
            await self._cdp.send("Page.reload", {}, session_id=session)
            return "sent"
        history = await self._cdp.send("Page.getNavigationHistory", session_id=session)
        entry_id = back_entry_id(history.get("result", {}))
        if entry_id is None:
            return "dropped"
        await self._cdp.send("Page.navigateToHistoryEntry", {"entryId": entry_id}, session_id=session)
        return "sent"

    def _finish(self, end: LiveEnd) -> None:
        if self._end == "disconnected":
            self._end = end
        for subscription in self._subscriptions:
            subscription.close()
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_live_session.py tests/test_live_input.py tests/test_cdp_client.py --cov=roost.desk.live --cov-report=term-missing -q`
Expected: PASS, and `roost/desk/live.py` at least 95%. Only the pump's "a dead connection mid-event" return and `_show`'s "no session in the reply" guard may be reported missed.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/desk/live.py roost/desk/__init__.py roost/constants.py tests/test_live_session.py
git commit -m "feat: the live session: a screencast of the bot's page, acked, following pop-ups, with checked input"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the four files is listed.

---

### Task 5: The desk seam: `live_view` on the real and the fake desk, and FakeCdp

Design §2 "Ending" and §3 "E2E (… the fake desk needs a scripted screencast; the plan defines it)":
- **`Desk.live_view() -> LiveView`.** It never starts a browser and never opens a tab. A closed browser is `DeskAsleep` (the face's "asleep · Open it"), and an unreachable keeper or a CDP error is `DeskUnavailable`.
- **`KeeperDesk.live_view`** shares the S1.8 viewing path with `screenshot`: the bot's page if one is connected, else `/browser/attach` (409 → `DeskAsleep`), never `/browser/start`. That path moves into `KeeperDesk._view(call)`, and `screenshot` keeps its exact behaviour through it. The view's target is `DeskBrowserPage.live_target()`: the bot's own tab while it is open, else the page the browser shows. The view's `cdp` is the page's own `CdpClient`.
- **`FakeDesk.live_view`** hands out its one `FakeCdp` and the target `FAKE_PAGE_TARGET`, or `DeskAsleep` while its browser is stopped.
  - `FakeDesk.open_page` and `read_page` now wake the fake computer, as `KeeperDesk`'s page calls start the real browser (`_ensure_page`). So after a bot opened a page, the E2E's live screen shows it.
  - The fake page's address is the last URL the bot opened (`about:blank` before any).
- **`FakeCdp`** is an in-memory `CdpChannel` that answers exactly what `LiveSession` and the window code send. Its scripted screencast sends one `Page.screencastFrame` (`FAKE_JPEG`, a `FAKE_SCREEN_WIDTH` × `FAKE_SCREEN_HEIGHT` page) when a screencast starts, then the next one at least `FAKE_SCREENCAST_INTERVAL_S` after each ack, until it stops.
  - It records every call in `calls` (a tuple that is replaced, never changed) so tests can assert the exact CDP calls an input became. The record lives in memory only, for that test; nothing logs or stores it.
  - Test controls: `refuse(*methods)`, `open_pop_up`, `close_target`, `disconnect()` (Brave crashed: every subscription ends, every later call fails) and `screencasting()`.
- **`bot_page_url(desk)`** (`roost/desk/live.py`, used by the Vault in Task 11) reads the address of the bot's page without starting anything. It answers `""` when the computer is asleep or out of reach; out of reach is a warning.

**Files:**
- Create: `roost/desk/fake_cdp.py`, `tests/test_fake_cdp.py`
- Modify:
  - `roost/desk/__init__.py` (`Desk.live_view`)
  - `roost/desk/browser.py` (`cdp`, `live_target`; round A touched this file, see Global Constraints)
  - `roost/desk/client.py` (`_live_view_of`, `KeeperDesk._view`, `screenshot` through it, `live_view`)
  - `roost/desk/fake.py` (`cdp`, `live_view`, page calls wake it)
  - `roost/desk/live.py` (`bot_page_url`)
  - `roost/constants.py` (append the fake screencast constants)
- Test: `tests/test_fake_cdp.py` (new); `tests/test_fake_desk.py`, `tests/test_keeper_client.py` and `tests/test_cdp_live.py` (imports, and tests appended); `tests/test_cdp_client.py` (the fake server lists the tabs the bot created)

**Interfaces:**
- Consumes: Task 2 `CdpSubscription`, `CdpChannel`, `CdpClientError`, `CdpReplyError`; Task 4 `LiveView`, `LiveSession`, `LiveFrame`, `PageInfo`; existing `FAKE_JPEG`, `DeskAsleep`, `DeskUnavailable`, `KeeperDesk._attach_page`, `_DeadConnectionError`.
- Produces:
  - `Desk.live_view`, `KeeperDesk.live_view`, `KeeperDesk._view(call)`, `FakeDesk.live_view`, `FakeDesk.cdp`.
  - `DeskBrowserPage.cdp` and `DeskBrowserPage.live_target()`.
  - `roost.desk.fake_cdp`: `FakeCdp`, `FakeCdpCall`, `FAKE_PAGE_TARGET`.
  - `roost.desk.live.bot_page_url(desk) -> str`.
  - The constants `FAKE_SCREENCAST_INTERVAL_S`, `FAKE_SCREEN_WIDTH` and `FAKE_SCREEN_HEIGHT`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_fake_cdp.py`:

```python
"""``FakeCdp`` (live control, Task 5): the fake browser's live control. Its scripted screencast, its
targets and pop-ups, its record of calls, and a ``LiveSession`` running on it end to end."""

from __future__ import annotations

import asyncio
import base64

import pytest

from roost.constants import FAKE_SCREEN_HEIGHT, FAKE_SCREEN_WIDTH, FAKE_SCREENCAST_INTERVAL_S
from roost.desk import LiveView
from roost.desk.cdp import CdpClientError, CdpReplyError, CdpSubscription
from roost.desk.fake import FAKE_JPEG
from roost.desk.fake_cdp import FAKE_PAGE_TARGET, FakeCdp
from roost.desk.live import LiveFrame, LiveSession, PageInfo
from team_helpers import until

_LOGIN = "https://login.example/"


def _fake(url: str = _LOGIN) -> FakeCdp:
    return FakeCdp(lambda: url, FAKE_JPEG)


async def _next(subscription: CdpSubscription, timeout: float = 1.0) -> dict:
    return await asyncio.wait_for(anext(subscription), timeout=timeout)


async def _screencast(cdp: FakeCdp, target_id: str = FAKE_PAGE_TARGET) -> str:
    attached = await cdp.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
    session = attached["result"]["sessionId"]
    await cdp.send("Page.startScreencast", {"format": "jpeg"}, session_id=session)
    return session


class _Sink:
    def __init__(self) -> None:
        self.frames: list[LiveFrame] = []
        self.pages: list[PageInfo] = []

    async def frame(self, frame: LiveFrame) -> None:
        self.frames.append(frame)

    async def page(self, info: PageInfo) -> None:
        self.pages.append(info)


async def test_a_screencast_sends_a_frame_then_one_after_each_ack():
    cdp = _fake()
    frames = cdp.subscribe("Page.screencastFrame")
    session = await _screencast(cdp)
    first = await _next(frames)
    assert first["sessionId"] == session
    assert base64.b64decode(first["params"]["data"]) == FAKE_JPEG
    assert (first["params"]["metadata"]["deviceWidth"], first["params"]["metadata"]["deviceHeight"]) == (
        FAKE_SCREEN_WIDTH, FAKE_SCREEN_HEIGHT)
    with pytest.raises(asyncio.TimeoutError):
        await _next(frames, timeout=FAKE_SCREENCAST_INTERVAL_S * 4)   # nothing more until it is acked
    await cdp.send("Page.screencastFrameAck", {"sessionId": first["params"]["sessionId"]}, session_id=session)
    second = await _next(frames)
    assert second["params"]["sessionId"] == first["params"]["sessionId"] + 1
    assert cdp.screencasting() == frozenset({session})
    await cdp.send("Page.stopScreencast", session_id=session)
    assert cdp.screencasting() == frozenset()


async def test_the_bots_page_shows_the_last_address_it_opened():
    shown = {"url": "about:blank"}
    cdp = FakeCdp(lambda: shown["url"], FAKE_JPEG)
    info = await cdp.send("Target.getTargetInfo", {"targetId": FAKE_PAGE_TARGET})
    assert info["result"]["targetInfo"]["url"] == "about:blank"
    shown["url"] = _LOGIN
    targets = await cdp.send("Target.getTargets")
    assert targets["result"]["targetInfos"] == [
        {"targetId": FAKE_PAGE_TARGET, "type": "page", "url": _LOGIN, "title": "Fake Page"}]


async def test_a_target_or_session_that_does_not_exist_is_refused():
    cdp = _fake()
    with pytest.raises(CdpReplyError):
        await cdp.send("Target.attachToTarget", {"targetId": "nope", "flatten": True})
    with pytest.raises(CdpReplyError):
        await cdp.send("Target.getTargetInfo", {"targetId": "nope"})
    with pytest.raises(CdpReplyError):
        await cdp.send("Page.startScreencast", {}, session_id="no-such-session")


async def test_every_call_is_recorded_in_a_new_tuple():
    cdp = _fake()
    before = cdp.calls
    await cdp.send("Input.insertText", {"text": "ana@example.com"}, session_id="s1")
    assert before == ()
    [call] = cdp.calls
    assert (call.method, dict(call.params), call.session_id) == ("Input.insertText", {"text": "ana@example.com"}, "s1")


async def test_a_refused_method_answers_a_cdp_error_and_is_still_recorded():
    cdp = _fake()
    cdp.refuse("Input.insertText")
    with pytest.raises(CdpReplyError):
        await cdp.send("Input.insertText", {"text": "x"}, session_id="s1")
    assert [call.method for call in cdp.calls] == ["Input.insertText"]


async def test_a_method_the_fake_browser_does_not_know_is_refused():
    with pytest.raises(CdpReplyError):
        await _fake().send("Runtime.evaluate", {"expression": "1"})


async def test_a_pop_up_opens_and_closes_with_target_events():
    cdp = _fake()
    targets = cdp.subscribe(("Target.targetCreated", "Target.targetDestroyed"))
    cdp.open_pop_up("pop-up", "https://accounts.example/", "Sign in")
    created = await _next(targets)
    assert created["params"]["targetInfo"] == {
        "targetId": "pop-up", "type": "page", "url": "https://accounts.example/", "title": "Sign in",
        "openerId": FAKE_PAGE_TARGET}
    session = await _screencast(cdp, "pop-up")
    assert cdp.screencasting() == frozenset({session})
    cdp.close_target("pop-up")
    assert (await _next(targets))["params"] == {"targetId": "pop-up"}
    assert cdp.screencasting() == frozenset()
    with pytest.raises(CdpReplyError):
        await cdp.send("Target.attachToTarget", {"targetId": "pop-up", "flatten": True})


async def test_disconnect_ends_every_subscription_and_every_later_call():
    """Review Focus 5 in the fake: Brave crashed or the keeper restarted."""
    cdp = _fake()
    frames = cdp.subscribe("Page.screencastFrame")
    await _screencast(cdp)
    await _next(frames)
    await cdp.disconnect()
    assert [event async for event in frames] == []
    assert cdp.screencasting() == frozenset()
    with pytest.raises(CdpClientError):
        await cdp.send("Page.enable")
    assert [event async for event in cdp.subscribe("Page.screencastFrame")] == []


async def test_a_live_session_runs_on_the_fake_browser():
    cdp = _fake()
    sink = _Sink()
    session = LiveSession(LiveView(cdp=cdp, target_id=FAKE_PAGE_TARGET), sink)
    await session.start()
    running = asyncio.create_task(session.run())
    await until(lambda: len(sink.frames) >= 2)
    await session.stop()
    assert await asyncio.wait_for(running, timeout=2) == "stopped"
    assert cdp.screencasting() == frozenset()
    assert sink.pages[0] == PageInfo(url=_LOGIN, title="Fake Page")
    assert sink.frames[0].jpeg == FAKE_JPEG
```

In `tests/test_fake_desk.py`, replace these import lines:

```python
from roost.desk import DeskStatus, DeskUnavailable, ExecResult, PageText
from roost.desk.fake import FakeDesk
```

with:

```python
from roost.desk import DeskAsleep, DeskStatus, DeskUnavailable, ExecResult, PageText
from roost.desk.fake import FakeDesk
from roost.desk.fake_cdp import FAKE_PAGE_TARGET
from roost.desk.live import bot_page_url
```

Then append this to the end of `tests/test_fake_desk.py`:

```python


# -- Live control (Task 5): the fake computer's live view --


async def test_the_live_view_of_a_sleeping_computer_is_asleep_and_never_starts_it():
    desk = FakeDesk(_BOT_ID)
    with pytest.raises(DeskAsleep):
        await desk.live_view()
    assert (await desk.status()).browser == "stopped"


async def test_the_live_view_is_the_fake_browsers_own_page():
    desk = FakeDesk(_BOT_ID)
    await desk.start_browser()
    view = await desk.live_view()
    assert (view.cdp, view.target_id) == (desk.cdp, FAKE_PAGE_TARGET)
    assert await desk.live_view() == view


async def test_opening_a_page_wakes_the_computer_as_the_real_one_does():
    desk = FakeDesk(_BOT_ID)
    await desk.open_page("https://login.example/")
    assert (await desk.status()).browser == "running"
    info = await (await desk.live_view()).cdp.send("Target.getTargetInfo", {"targetId": FAKE_PAGE_TARGET})
    assert info["result"]["targetInfo"]["url"] == "https://login.example/"


async def test_reading_a_page_wakes_it_too():
    desk = FakeDesk(_BOT_ID)
    await desk.read_page()
    assert (await desk.status()).browser == "running"


async def test_an_unavailable_desk_has_no_live_view():
    desk = FakeDesk(_BOT_ID, force_unavailable=True)
    with pytest.raises(DeskUnavailable):
        await desk.live_view()


async def test_the_bots_page_address_is_read_without_starting_anything():
    desk = FakeDesk(_BOT_ID)
    assert await bot_page_url(desk) == ""                     # asleep
    assert (await desk.status()).browser == "stopped"
    await desk.open_page("https://shop.example/orders")
    assert await bot_page_url(desk) == "https://shop.example/orders"
    desk.force_unavailable = True
    assert await bot_page_url(desk) == ""                     # out of reach
```

In `tests/test_keeper_client.py`, replace this import line:

```python
from roost.desk import DeskStatus, DeskUnavailable, ExecResult, PageText
```

with:

```python
from roost.desk import DeskAsleep, DeskStatus, DeskUnavailable, ExecResult, PageText
```

Then append this to the end of `tests/test_keeper_client.py`:

```python


# -- Live control (Task 5): the live view never starts the browser --


class _LivePage:
    """A connected page for live control: its connection and its own tab's target, or ``error``."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.cdp = object()
        self.closed = False
        self._error = error

    async def live_target(self) -> str:
        if self._error is not None:
            raise self._error
        return "target-7"

    async def close(self) -> None:
        self.closed = True


def _attaching_desk(config: RoostConfig, page: _LivePage, seen: list[tuple[str, str]],
                    status: int = 200) -> KeeperDesk:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if status == 409:
            return httpx.Response(409, json={"detail": "asleep"})
        return httpx.Response(200, json={"browser": "running", "cdp_token": "tok"})

    async def connect(url: str, token: str):
        return page

    return KeeperDesk(config, _BOT_ID, transport=httpx.MockTransport(handler), connect_page=connect)


async def test_the_live_view_is_the_running_browsers_page_and_never_starts_it(config: RoostConfig) -> None:
    seen: list[tuple[str, str]] = []
    page = _LivePage()
    view = await _attaching_desk(config, page, seen).live_view()
    assert (view.cdp, view.target_id) == (page.cdp, "target-7")
    assert seen == [("POST", _ATTACH)]


async def test_the_live_view_of_a_sleeping_computer_is_asleep(config: RoostConfig) -> None:
    seen: list[tuple[str, str]] = []
    with pytest.raises(DeskAsleep):
        await _attaching_desk(config, _LivePage(), seen, status=409).live_view()
    assert seen == [("POST", _ATTACH)]


async def test_a_reply_error_in_the_live_view_keeps_the_bots_page(config: RoostConfig) -> None:
    page = _LivePage(error=CdpReplyError("CDP error replying to 'Target.getTargets': refused"))
    with pytest.raises(DeskUnavailable):
        await _attaching_desk(config, page, []).live_view()
    assert page.closed is False


async def test_a_dead_connection_in_the_live_view_drops_the_page(config: RoostConfig) -> None:
    page = _LivePage(error=CdpClientError("connection closed"))
    with pytest.raises(DeskUnavailable):
        await _attaching_desk(config, page, []).live_view()
    assert page.closed is True


async def test_the_live_view_of_a_retired_desk_is_unavailable(config: RoostConfig) -> None:
    desk = _attaching_desk(config, _LivePage(), [])
    desk._retired = True
    with pytest.raises(DeskUnavailable):
        await desk.live_view()
```

In `tests/test_cdp_client.py`, make the fake server list the tabs the bot created. Replace these lines:

```python
        self._target_ids = itertools.count(1)
        self._server: websockets.server.Server | None = None
```

with:

```python
        self._target_ids = itertools.count(1)
        self._created: list[str] = []          # live control (Task 5): the tabs Target.createTarget made
        self._server: websockets.server.Server | None = None
```

Then replace these lines:

```python
        if method == "Target.createTarget":
            return {"targetId": f"target-{next(self._target_ids)}"}
```

with:

```python
        if method == "Target.createTarget":
            target_id = f"target-{next(self._target_ids)}"
            self._created.append(target_id)
            return {"targetId": target_id}
```

Then replace these lines:

```python
        if method == "Target.getTargets":
            infos = [{"targetId": "target-0", "type": "page", "url": "https://example.com/"}] if self._open_pages else []
            return {"targetInfos": infos}
```

with:

```python
        if method == "Target.getTargets":
            infos = [{"targetId": "target-0", "type": "page", "url": "https://example.com/"}] if self._open_pages else []
            created = [{"targetId": target_id, "type": "page", "url": "about:blank"} for target_id in self._created]
            return {"targetInfos": infos + created}
```

In `tests/test_cdp_live.py`, replace this import line:

```python
from roost.desk.cdp import CdpClient, CdpClientError, CdpSubscription
```

with:

```python
from roost.desk import DeskAsleep
from roost.desk.browser import DeskBrowserPage
from roost.desk.cdp import CdpClient, CdpClientError, CdpSubscription
```

Then append this to the end of `tests/test_cdp_live.py`:

```python


# -- Task 5: which page the live screen shows --


async def test_live_control_shows_the_bots_own_tab_when_it_has_one(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    page = DeskBrowserPage(connected_client)
    await page.open_page("https://example.com/")           # the bot's own tab is target-1
    fake_server.received.clear()
    assert await page.live_target() == "target-1"
    assert [m["method"] for m in fake_server.received] == ["Target.getTargets"]
    assert page.cdp is connected_client


async def test_live_control_shows_the_open_page_when_the_bot_has_no_tab_yet(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    assert await DeskBrowserPage(connected_client).live_target() == "target-0"
    assert "Target.createTarget" not in [m["method"] for m in fake_server.received]


async def test_live_control_of_a_browser_with_no_page_is_asleep() -> None:
    server = _FakeCdpServer(open_pages=False)
    await server.start()
    client = CdpClient(server.url, _TOKEN)
    await client.connect()
    try:
        with pytest.raises(DeskAsleep):
            await DeskBrowserPage(client).live_target()
        assert "Target.createTarget" not in [m["method"] for m in server.received]
    finally:
        await client.close()
        await server.stop()
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_fake_cdp.py tests/test_fake_desk.py tests/test_keeper_client.py tests/test_cdp_live.py -q`
Expected: FAIL.
- `tests/test_fake_cdp.py`: `ImportError: cannot import name 'FAKE_SCREEN_HEIGHT' from 'roost.constants'`.
- `tests/test_fake_desk.py`: `ModuleNotFoundError: No module named 'roost.desk.fake_cdp'`.
- `tests/test_keeper_client.py`: the five new tests fail with `AttributeError: 'KeeperDesk' object has no attribute 'live_view'`.
- `tests/test_cdp_live.py`: the three new tests fail with `AttributeError: 'DeskBrowserPage' object has no attribute 'live_target'`.

- [ ] **Step 4: Add the fake screencast constants**

Append this to the very end of `roost/constants.py`:

```python

# Task 5 — roost/desk/fake_cdp.py: the fake browser's scripted screencast (tests and the E2E).
FAKE_SCREENCAST_INTERVAL_S = 0.05        # the next frame comes at least this long after an ack
FAKE_SCREEN_WIDTH = 1280
FAKE_SCREEN_HEIGHT = 800
```

- [ ] **Step 5: `Desk.live_view` and the bot's page (`roost/desk/__init__.py`, `roost/desk/browser.py`)**

In `roost/desk/__init__.py`, replace these lines:

```python
    async def retire(self) -> None: ...
    async def screenshot(self) -> bytes: ...
```

with:

```python
    async def retire(self) -> None: ...
    async def screenshot(self) -> bytes: ...
    async def live_view(self) -> LiveView: ...
```

In `roost/desk/browser.py`, replace these lines:

```python
        page instead of failing against the same dead client forever
        (Fix round 1, finding 4)."""
        await self._client.close()
```

with:

```python
        page instead of failing against the same dead client forever
        (Fix round 1, finding 4)."""
        await self._client.close()

    @property
    def cdp(self) -> CdpClient:
        """The connection under this page. Live control shares it: the keeper's relay takes one client per bot."""
        return self._client

    async def live_target(self) -> str:
        """The bot's own page, for live control and its window: its own tab while that is open, else
        the page the browser shows. Never opens a tab: with no page open, ``DeskAsleep``."""
        targets = await self._client.send("Target.getTargets")
        pages = [info.get("targetId") for info in targets.get("result", {}).get("targetInfos", [])
                 if info.get("type") == "page" and isinstance(info.get("targetId"), str)]
        if self._target_id is not None and self._target_id in pages:
            return self._target_id
        if not pages:
            raise DeskAsleep("the bot's browser has no open page")
        return pages[0]
```

- [ ] **Step 6: `KeeperDesk.live_view` (`roost/desk/client.py`)**

1. Imports. Replace this line:

```python
from roost.desk import DeskAsleep, DeskStatus, DeskUnavailable, ExecResult, PageText, build_shell_argv
```

with:

```python
from roost.desk import DeskAsleep, DeskStatus, DeskUnavailable, ExecResult, LiveView, PageText, build_shell_argv
```

2. The view of a page. Replace these lines:

```python
    return f"{base}/desks/{bot_id}/cdp"


class KeeperClient:
```

with:

```python
    return f"{base}/desks/{bot_id}/cdp"


async def _live_view_of(page: DeskBrowserPage) -> LiveView:
    """Live control: the page's own connection and the bot's page on it (never a new tab)."""
    return LiveView(cdp=page.cdp, target_id=await page.live_target())


class KeeperClient:
```

3. `screenshot` through `_view`, and `live_view`. Replace these lines:

```python
        ``self._page`` at all (S1.8 Fix round 1, finding 1)."""
        if self._retired:
            raise DeskUnavailable(f"desk for bot {self._bot_id} has been retired")
        page = self._page or await self._attach_page()
        try:
            return await page.capture_screenshot()
        except CdpReplyError as exc:
            raise DeskUnavailable(f"desk CDP connection for bot {self._bot_id} is unavailable: {exc}") from exc
        except _DeadConnectionError as exc:
            await page.close()
            if self._page is page:
                self._page = None
            raise DeskUnavailable(f"desk CDP connection for bot {self._bot_id} is unavailable: {exc}") from exc
```

with:

```python
        ``self._page`` at all (S1.8 Fix round 1, finding 1)."""
        return await self._view(lambda page: page.capture_screenshot())

    async def live_view(self) -> LiveView:
        """Live control (design §2): the running browser's connection and the bot's page on it. Like a
        screenshot it never starts the browser (``DeskAsleep``) and never opens a tab."""
        return await self._view(_live_view_of)

    async def _view(self, call: Callable[[DeskBrowserPage], Awaitable[T]]) -> T:
        """Run a viewing call (a screenshot, the live view, the window) on the bot's page: the one it
        has, else one attached to the running browser, never one that starts it. A ``CdpReplyError``
        keeps the page (only this call failed); a dead connection drops it. Both are ``DeskUnavailable``."""
        if self._retired:
            raise DeskUnavailable(f"desk for bot {self._bot_id} has been retired")
        page = self._page or await self._attach_page()
        try:
            return await call(page)
        except CdpReplyError as exc:
            raise DeskUnavailable(f"desk CDP connection for bot {self._bot_id} is unavailable: {exc}") from exc
        except _DeadConnectionError as exc:
            await page.close()
            if self._page is page:
                self._page = None
            raise DeskUnavailable(f"desk CDP connection for bot {self._bot_id} is unavailable: {exc}") from exc
```

- [ ] **Step 7: `FakeCdp` (`roost/desk/fake_cdp.py`)**

Create `roost/desk/fake_cdp.py`:

```python
"""``FakeCdp`` — the fake browser's live control (live control, Task 5): an in-memory ``CdpChannel``
that ``FakeDesk.live_view`` hands out in every test and in the E2E (``ROOST_DESK=fake``).

It answers exactly the CDP calls ``LiveSession`` and the bot-window code send, and streams a scripted
screencast: one ``Page.screencastFrame`` (the desk's JPEG, a ``FAKE_SCREEN_WIDTH`` x
``FAKE_SCREEN_HEIGHT`` page) when a screencast starts, then the next one at least
``FAKE_SCREENCAST_INTERVAL_S`` after each ack, until it stops.

Every call is recorded in ``calls`` (a tuple that is replaced, never changed), so a test can assert
the exact CDP calls an input became. The record lives in memory only, for that test; nothing here
logs or stores it. Tests drive the rest: ``refuse`` makes methods answer a CDP error, ``open_pop_up``
and ``close_target`` play a page's pop-up, and ``disconnect`` plays Brave crashing.
"""

from __future__ import annotations

import asyncio
import base64
import itertools
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from roost.constants import (
    CDP_SUBSCRIPTION_QUEUE_MAX, FAKE_SCREEN_HEIGHT, FAKE_SCREEN_WIDTH, FAKE_SCREENCAST_INTERVAL_S,
)
from roost.desk.cdp import CdpClientError, CdpReplyError, CdpSubscription

FAKE_PAGE_TARGET = "fake-page"
_FAKE_TITLE = "Fake Page"
_WINDOW_ID = 1
_FRAME_METADATA: Mapping[str, Any] = MappingProxyType({
    "deviceWidth": FAKE_SCREEN_WIDTH, "deviceHeight": FAKE_SCREEN_HEIGHT, "pageScaleFactor": 1,
    "offsetTop": 0, "scrollOffsetX": 0, "scrollOffsetY": 0,
})
# The calls FakeCdp answers with an empty result.
_PLAIN = frozenset({
    "Target.setDiscoverTargets", "Target.activateTarget", "Page.enable", "Page.reload",
    "Page.navigateToHistoryEntry", "Page.screencastFrameAck", "Input.dispatchMouseEvent",
    "Input.dispatchKeyEvent", "Input.insertText", "Browser.setWindowBounds",
})


@dataclass(frozen=True)
class FakeCdpCall:
    method: str
    params: Mapping[str, Any]
    session_id: str | None


@dataclass(frozen=True)
class _FakeTarget:
    target_id: str
    url: str
    title: str
    opener_id: str | None = None

    def info(self) -> dict[str, Any]:
        found = {"targetId": self.target_id, "type": "page", "url": self.url, "title": self.title}
        return found if self.opener_id is None else {**found, "openerId": self.opener_id}


class FakeCdp:
    def __init__(self, page_url: Callable[[], str], jpeg: bytes) -> None:
        self.calls: tuple[FakeCdpCall, ...] = ()
        self._page_url = page_url
        self._jpeg = base64.b64encode(jpeg).decode()
        self._pop_ups: dict[str, _FakeTarget] = {}
        self._sessions: dict[str, str] = {}                     # CDP session -> target
        self._screencasts: dict[str, "asyncio.Task[None]"] = {}
        self._acks: dict[str, asyncio.Event] = {}
        self._subscriptions: tuple[CdpSubscription, ...] = ()
        self._refused: frozenset[str] = frozenset()
        self._numbers = itertools.count(1)
        self._frames = itertools.count(1)
        self._connected = True

    def subscribe(self, method: str | tuple[str, ...], session_id: str | None = None) -> CdpSubscription:
        methods = frozenset((method,) if isinstance(method, str) else method)
        subscription = CdpSubscription(methods, session_id, CDP_SUBSCRIPTION_QUEUE_MAX, self._unsubscribe)
        if not self._connected:
            subscription.end()
            return subscription
        self._subscriptions = (*self._subscriptions, subscription)
        return subscription

    async def send(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict:
        if not self._connected:
            raise CdpClientError("connection closed")
        given = dict(params or {})
        self.calls = (*self.calls, FakeCdpCall(method, MappingProxyType(given), session_id))
        if method in self._refused:
            raise CdpReplyError(f"CDP error replying to {method!r}: refused by the fake browser")
        return {"result": self._answer(method, given, session_id)}

    def refuse(self, *methods: str) -> None:
        """From now on, ``methods`` answer a CDP error, as a page that went away does."""
        self._refused = self._refused | frozenset(methods)

    def open_pop_up(self, target_id: str, url: str, title: str = "") -> None:
        """The bot's page opens a pop-up (``window.open``), as "Sign in with Google" does."""
        target = _FakeTarget(target_id, url, title, opener_id=FAKE_PAGE_TARGET)
        self._pop_ups = {**self._pop_ups, target_id: target}
        self._emit({"method": "Target.targetCreated", "params": {"targetInfo": target.info()}})

    def close_target(self, target_id: str) -> None:
        """A pop-up closes: its screencasts stop and ``Target.targetDestroyed`` goes out."""
        self._pop_ups = {key: value for key, value in self._pop_ups.items() if key != target_id}
        for session_id, session_target in tuple(self._sessions.items()):
            if session_target == target_id:
                self._stop_screencast(session_id)
        self._emit({"method": "Target.targetDestroyed", "params": {"targetId": target_id}})

    async def disconnect(self) -> None:
        """Brave crashed or the keeper restarted: every subscription ends and every later call fails."""
        self._connected = False
        for session_id in tuple(self._screencasts):
            self._stop_screencast(session_id)
        subscriptions, self._subscriptions = self._subscriptions, ()
        for subscription in subscriptions:
            subscription.end()

    def screencasting(self) -> frozenset[str]:
        """The CDP sessions with a screencast running now."""
        return frozenset(self._screencasts)

    def _answer(self, method: str, params: dict[str, Any], session_id: str | None) -> dict[str, Any]:
        if method in _PLAIN:
            if method == "Page.screencastFrameAck" and session_id is not None:
                self._acked(session_id)
            return {}
        if method == "Target.getTargets":
            return {"targetInfos": [target.info() for target in self._targets().values()]}
        if method == "Target.getTargetInfo":
            return {"targetInfo": self._target(params.get("targetId")).info()}
        if method == "Target.attachToTarget":
            return {"sessionId": self._attach(self._target(params.get("targetId")).target_id)}
        if method in ("Target.detachFromTarget", "Page.stopScreencast"):
            self._stop_screencast(params.get("sessionId", session_id))
            return {}
        if method == "Page.startScreencast":
            self._start_screencast(self._session_target(session_id), session_id or "")
            return {}
        if method == "Page.getNavigationHistory":
            return {"currentIndex": 0, "entries": [{"id": 1, "url": self._page_url(), "title": _FAKE_TITLE}]}
        if method == "Browser.getWindowForTarget":
            self._target(params.get("targetId"))
            return {"windowId": _WINDOW_ID, "bounds": {"windowState": "normal"}}
        raise CdpReplyError(f"CDP error replying to {method!r}: the fake browser does not answer it")

    def _targets(self) -> dict[str, _FakeTarget]:
        return {FAKE_PAGE_TARGET: _FakeTarget(FAKE_PAGE_TARGET, self._page_url(), _FAKE_TITLE), **self._pop_ups}

    def _target(self, target_id: Any) -> _FakeTarget:
        target = self._targets().get(target_id)
        if target is None:
            raise CdpReplyError("CDP error replying to a target call: No target with given id found")
        return target

    def _attach(self, target_id: str) -> str:
        session_id = f"fake-session-{next(self._numbers)}"
        self._sessions = {**self._sessions, session_id: target_id}
        return session_id

    def _session_target(self, session_id: str | None) -> str:
        target_id = self._sessions.get(session_id or "")
        if target_id is None or target_id not in self._targets():
            raise CdpReplyError("CDP error replying to Page.startScreencast: Session with given id not found")
        return target_id

    def _start_screencast(self, target_id: str, session_id: str) -> None:
        self._stop_screencast(session_id)
        ack = asyncio.Event()
        task = asyncio.get_running_loop().create_task(self._screencast(session_id, ack))
        self._acks = {**self._acks, session_id: ack}
        self._screencasts = {**self._screencasts, session_id: task}

    def _stop_screencast(self, session_id: str | None) -> None:
        task = self._screencasts.get(session_id or "")
        self._screencasts = {key: value for key, value in self._screencasts.items() if key != session_id}
        self._acks = {key: value for key, value in self._acks.items() if key != session_id}
        if task is not None:
            task.cancel()

    def _acked(self, session_id: str) -> None:
        ack = self._acks.get(session_id)
        if ack is not None:
            ack.set()

    async def _screencast(self, session_id: str, ack: asyncio.Event) -> None:
        """One frame now, then one after each ack, no faster than ``FAKE_SCREENCAST_INTERVAL_S``."""
        while True:
            ack.clear()
            self._emit({"method": "Page.screencastFrame", "sessionId": session_id, "params": {
                "data": self._jpeg, "metadata": dict(_FRAME_METADATA), "sessionId": next(self._frames)}})
            await ack.wait()
            await asyncio.sleep(FAKE_SCREENCAST_INTERVAL_S)

    def _emit(self, event: dict[str, Any]) -> None:
        for subscription in self._subscriptions:
            if subscription.wants(event):
                subscription.offer(event)

    def _unsubscribe(self, subscription: CdpSubscription) -> None:
        self._subscriptions = tuple(s for s in self._subscriptions if s is not subscription)
```

- [ ] **Step 8: `FakeDesk.live_view` (`roost/desk/fake.py`)**

1. Imports. Replace these lines:

```python
from roost.constants import EXEC_TIMEOUT_S
from roost.desk import DeskAsleep, DeskStatus, DeskUnavailable, ExecResult, PageText, build_shell_argv
from roost.desk.fake_pages import FAKE_PAGES
from roost.desk.url_policy import check_url
```

with:

```python
from roost.constants import EXEC_TIMEOUT_S
from roost.desk import DeskAsleep, DeskStatus, DeskUnavailable, ExecResult, LiveView, PageText, build_shell_argv
from roost.desk.fake_cdp import FAKE_PAGE_TARGET, FakeCdp
from roost.desk.fake_pages import FAKE_PAGES
from roost.desk.url_policy import check_url
```

2. The class docstring. Replace these lines:

```python
    ``ROOST_DESK=fake`` gateway (the E2E) can show a sign-in wall. Every
    other URL gets the plain "Fake Page", exactly as before.
    """
```

with:

```python
    ``ROOST_DESK=fake`` gateway (the E2E) can show a sign-in wall. Every
    other URL gets the plain "Fake Page", exactly as before.

    Live control (Task 5): ``live_view`` hands out ``cdp``, this desk's one
    ``FakeCdp``, whose page shows the last URL the bot opened. A page call
    wakes the fake computer, as ``KeeperDesk``'s page calls start the real
    browser, so the live screen can show what the bot was doing.
    """
```

3. The fake browser. Replace these lines:

```python
        self._pages: dict[str, tuple[PageText, ...]] = _scripts(FAKE_PAGES if pages is None else pages)
        self._page_reads: dict[str, int] = {}
```

with:

```python
        self._pages: dict[str, tuple[PageText, ...]] = _scripts(FAKE_PAGES if pages is None else pages)
        self._page_reads: dict[str, int] = {}
        self.cdp = FakeCdp(self._live_page_url, FAKE_JPEG)
```

4. Page calls wake it. Replace these lines:

```python
    async def open_page(self, url: str) -> PageText:
        self._require_available()
        checked_url = check_url(url)
```

with:

```python
    async def open_page(self, url: str) -> PageText:
        self._require_available()
        self._browser = "running"      # a page call starts the real browser too (KeeperDesk._ensure_page)
        checked_url = check_url(url)
```

Then replace these lines:

```python
    async def read_page(self) -> PageText:
        self._require_available()
        if not self.open_page_calls:
```

with:

```python
    async def read_page(self) -> PageText:
        self._require_available()
        self._browser = "running"
        if not self.open_page_calls:
```

5. The live view. Replace these lines:

```python
    async def screenshot(self) -> bytes:
        self._require_available()
        if self._browser != "running":
            raise DeskAsleep(f"the browser of bot {self.bot_id} is closed")
        return FAKE_JPEG
```

with:

```python
    async def screenshot(self) -> bytes:
        self._require_available()
        if self._browser != "running":
            raise DeskAsleep(f"the browser of bot {self.bot_id} is closed")
        return FAKE_JPEG

    async def live_view(self) -> LiveView:
        """Live control: the fake browser's own page. Like the real one, it never starts a closed browser."""
        self._require_available()
        if self._browser != "running":
            raise DeskAsleep(f"the browser of bot {self.bot_id} is closed")
        return LiveView(cdp=self.cdp, target_id=FAKE_PAGE_TARGET)

    def _live_page_url(self) -> str:
        """What the fake browser shows: the last page the bot opened."""
        return self.open_page_calls[-1] if self.open_page_calls else "about:blank"
```

- [ ] **Step 9: `bot_page_url` (`roost/desk/live.py`)**

Replace this line:

```python
from roost.desk import LiveView
```

with:

```python
from roost.desk import Desk, DeskAsleep, DeskUnavailable, LiveView
```

Then append this to the end of `roost/desk/live.py`:

```python


async def bot_page_url(desk: Desk) -> str:
    """The address the bot's own page shows now (the Vault's site, Task 11), or "" when its computer is
    asleep or out of reach. Never starts a browser and never opens a tab."""
    try:
        view = await desk.live_view()
        info = await view.cdp.send("Target.getTargetInfo", {"targetId": view.target_id})
    except DeskAsleep:
        return ""
    except (DeskUnavailable, CdpClientError) as exc:
        logger.warning("Could not read the address of the bot's page (%s)", type(exc).__name__)
        return ""
    return str(info.get("result", {}).get("targetInfo", {}).get("url") or "")
```

- [ ] **Step 10: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_fake_cdp.py tests/test_fake_desk.py tests/test_keeper_client.py tests/test_cdp_client.py tests/test_cdp_live.py tests/test_live_session.py tests/test_computer_api.py tests/test_desk_api.py tests/test_stuck_api.py -q`
Expected: PASS. `test_computer_api.py` still finds a sleeping computer asleep: a screenshot is not a page call, so it wakes nothing.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_fake_cdp.py tests/test_fake_desk.py tests/test_keeper_client.py tests/test_cdp_live.py --cov=roost.desk.fake_cdp --cov=roost.desk.fake --cov=roost.desk.client --cov=roost.desk.live --cov-report=term-missing -q`
Expected: PASS. `roost/desk/fake_cdp.py` and `roost/desk/fake.py` at least 95%.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/desk/__init__.py roost/desk/browser.py roost/desk/client.py roost/desk/fake.py \
  roost/desk/fake_cdp.py roost/desk/live.py roost/constants.py tests/test_fake_cdp.py tests/test_fake_desk.py \
  tests/test_keeper_client.py tests/test_cdp_client.py tests/test_cdp_live.py
git commit -m "feat: the desks hand out a live view without starting a browser; FakeCdp streams a scripted screencast"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the twelve files is listed.

---

### Task 6: The live socket: accept rules, frames out, input in, and the close on Give it back

Design §2 "The live connection", L1, L2, and D1, D6 above:
- **`WS /api/bots/{bot_id}/live`** accepts first, then closes with a specific code (Ruling 9, as `/api/events` does), so the face always gets a real close frame with a reason it can show. It checks, in this order:
  1. this Mac: 4403 "Live control works only on this Mac for now." (D1);
  2. Roost's own origin: 4403 "Origin not allowed.";
  3. signed in: 4401 "Sign in first.";
  4. the user's own bot: 4404 "Bot not found";
  5. control held: 4409 "Take control first.".
- **Then the desk.** `desks.for_bot(id).live_view()`. A closed browser closes with 4410 "asleep"; an unreachable one, or a page that can't be shown, closes with 4503 "The bot's computer stopped answering.".
- **While it runs, four things race:**
  - the session's frames and target events (`LiveSession.run`);
  - the frame sender (`LiveSocketSink.pump`): each frame goes out as a JSON header then its JPEG, with one frame in flight;
  - the user's inputs: checked (`parse_input`), rate-limited (`InputRateLimit`), and sent **only while the user still holds control**, so nothing typed after Give it back reaches the page (Review Focus 4). A refused input sends `{"t": "notice", "text": "That didn't reach the page. Try again."}`;
  - the control lock's release (`ControlLock.wait_released`).
- **The first to finish ends it.** The session then stops (screencast off, discovery off), and the socket closes:
  - 4000 "Given back." when control was released: Give it back, Give up, a Stuck card's clear, Retire this bot;
  - 4410 when the bot's page closed;
  - 4503 when the connection died (Review Focus 5);
  - nothing when the user closed the live screen themselves.
- **No input is ever logged, audited or published.** The route logs only a bot id and an error's type name.

**Files:**
- Create: `roost/gateway/live_socket.py`, `roost/gateway/routes/live.py`, `tests/test_live_socket.py`, `tests/test_live_api.py`
- Modify:
  - `roost/desk/control.py` (`wait_released`)
  - `roost/gateway/app.py` (the router)
  - `roost/constants.py` (append the socket constants)
- Test: `tests/test_control_lock.py` (tests appended)

**Interfaces:**
- Consumes:
  - Task 3: `parse_input`, `InputRateLimit`, `FrameMeta`.
  - Task 4: `LiveSession`, `LiveFrame`, `PageInfo`.
  - Task 5: `Desk.live_view`, and `FakeDesk.cdp` (`calls`, `refuse`, `open_pop_up`, `close_target`, `disconnect`, `screencasting`).
  - Existing: `ControlLock`, `get_session_user`, `SESSION_COOKIE_NAME`, `ensure_initialized`, `RoostConfig.allowed_origins` / `in_container`, `DeskAsleep`, `DeskUnavailable`, `CdpClientError`; `tests/team_helpers.make_bot` / `until`.
- Produces:
  - `ControlLock.wait_released`.
  - From `roost.gateway.live_socket`: `Refusal`, `peer_is_this_mac`, `live_refusal`, `frame_header`, `LiveSocketSink`, and the reason texts.
  - From `roost.gateway.routes.live`: `live_router`, `GIVEN_BACK_REASON`, `ASLEEP_REASON`, `UNAVAILABLE_REASON`, `INPUT_FAILED_TEXT`, `_read_inputs`.
  - The constants `LIVE_LOOPBACK_HOSTS`, `LIVE_FORWARDED_HEADERS` and `LIVE_CLOSE_*`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Append this to the end of `tests/test_control_lock.py`:

```python


# -- Live control (Task 6): the live screen closes as soon as control is released --


async def test_wait_released_returns_at_once_when_nobody_holds_the_computer():
    await asyncio.wait_for(ControlLock().wait_released("b1"), timeout=0.5)


async def test_wait_released_waits_for_the_give_back():
    lock = ControlLock()
    lock.take("b1")
    waiting = asyncio.create_task(lock.wait_released("b1"))
    await asyncio.sleep(0.01)
    assert not waiting.done()
    lock.give_back("b1")
    await asyncio.wait_for(waiting, timeout=0.5)


async def test_retiring_the_bot_ends_the_wait_too():
    lock = ControlLock()
    lock.take("b1")
    waiting = asyncio.create_task(lock.wait_released("b1"))
    await asyncio.sleep(0.01)
    lock.forget("b1")
    await asyncio.wait_for(waiting, timeout=0.5)


async def test_wait_released_only_listens_to_its_own_bot():
    lock = ControlLock()
    lock.take("b1")
    lock.take("b2")
    waiting = asyncio.create_task(lock.wait_released("b1"))
    lock.give_back("b2")
    await asyncio.sleep(0.01)
    assert not waiting.done()
    lock.give_back("b1")
    await asyncio.wait_for(waiting, timeout=0.5)
```

Create `tests/test_live_socket.py`:

```python
"""The live screen's socket side (live control, Task 6): who counts as this Mac, the frame sink's one
frame in flight, and the input reader that stops at Give it back. Unit tests on small fakes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from starlette.datastructures import Address, Headers

from roost.config import load_config
from roost.desk.control import ControlLock
from roost.desk.live import LiveFrame, PageInfo
from roost.desk.live_input import FrameMeta, TextInput
from roost.gateway.live_socket import LiveSocketSink, frame_header, peer_is_this_mac
from roost.gateway.routes.live import INPUT_FAILED_TEXT, _read_inputs
from team_helpers import until

SECRET = "hunter2-correct-horse"
META = FrameMeta(1280, 800)


def _peer(host: str | None, headers: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(headers=Headers(headers=headers or {}),
                           client=None if host is None else Address(host, 50000))


@pytest.fixture
def config():
    return load_config()


# -- this Mac (L1, D1) --


@pytest.mark.parametrize(("host", "this_mac"), [
    ("127.0.0.1", True), ("::1", True), ("192.168.1.20", False), ("10.0.0.5", False),
    ("127.0.0.2", False), ("testclient", False),
])
def test_only_the_loopback_peer_is_this_mac(config, host, this_mac):
    """Review Focus 2."""
    assert peer_is_this_mac(_peer(host), config) is this_mac


def test_no_peer_at_all_is_not_this_mac(config):
    assert peer_is_this_mac(_peer(None), config) is False


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Forwarded", "X-Real-IP"])
def test_a_forwarded_request_is_never_this_mac(config, header):
    forwarded = _peer("127.0.0.1", {header: "203.0.113.7"})
    assert peer_is_this_mac(forwarded, config) is False
    assert peer_is_this_mac(forwarded, replace(config, in_container=True)) is False


def test_in_the_gateway_container_the_published_port_is_this_mac(config):
    """D1: compose publishes the gateway on the Mac's 127.0.0.1 alone, so every peer the container sees
    came from this Mac."""
    assert peer_is_this_mac(_peer("192.168.65.1"), replace(config, in_container=True)) is True


# -- the frame sink: one frame in flight --


class _SlowSocket:
    """Records what is sent; ``send_bytes`` waits for ``release`` (a socket that has fallen behind)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []
        self.release = asyncio.Event()

    async def send_json(self, payload: dict) -> None:
        self.sent.append(("json", payload))

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(("bytes", data))
        await self.release.wait()


def _jpegs(socket: _SlowSocket) -> list[object]:
    return [data for kind, data in socket.sent if kind == "bytes"]


async def test_each_frame_goes_out_as_its_header_then_its_jpeg():
    socket = _SlowSocket()
    socket.release.set()
    sink = LiveSocketSink(socket)
    pump = asyncio.create_task(sink.pump())
    await sink.frame(LiveFrame(META, b"one"))
    await until(lambda: len(socket.sent) == 2)
    pump.cancel()
    assert socket.sent == [("json", frame_header(META)), ("bytes", b"one")]
    assert frame_header(META) == {"t": "frame", "w": 1280, "h": 800, "scale": 1, "top": 0, "sx": 0, "sy": 0}


async def test_a_frame_that_comes_while_one_is_going_out_replaces_the_one_waiting():
    socket = _SlowSocket()
    sink = LiveSocketSink(socket)
    pump = asyncio.create_task(sink.pump())
    await sink.frame(LiveFrame(META, b"one"))
    await until(lambda: _jpegs(socket) == [b"one"])          # "one" is going out, and stuck
    await sink.frame(LiveFrame(META, b"two"))
    await sink.frame(LiveFrame(META, b"three"))
    socket.release.set()
    await until(lambda: b"three" in _jpegs(socket))
    pump.cancel()
    assert _jpegs(socket) == [b"one", b"three"]
    assert sink.dropped == 1


async def test_page_changes_and_notices_go_out_as_json():
    socket = _SlowSocket()
    sink = LiveSocketSink(socket)
    await sink.page(PageInfo(url="https://login.example/", title="Sign in"))
    await sink.notice(INPUT_FAILED_TEXT)
    assert socket.sent == [
        ("json", {"t": "page", "url": "https://login.example/", "title": "Sign in"}),
        ("json", {"t": "notice", "text": "That didn't reach the page. Try again."}),
    ]


# -- the input reader --


class _Inputs:
    """A socket that delivers ``messages``, then the user's disconnect."""

    def __init__(self, messages: list[dict]) -> None:
        self._messages = [*messages, {"type": "websocket.disconnect", "code": 1000}]

    async def receive(self) -> dict:
        message, self._messages = self._messages[0], self._messages[1:]
        return message


def _text(frame: object) -> dict:
    return {"type": "websocket.receive", "text": frame if isinstance(frame, str) else json.dumps(frame)}


class _Session:
    def __init__(self, result: str = "sent") -> None:
        self.handled: list[object] = []
        self._result = result

    async def handle(self, event: object) -> str:
        self.handled.append(event)
        return self._result


class _Notices:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def notice(self, text: str) -> None:
        self.sent.append(text)


def _held(bot_id: str = "b1") -> ControlLock:
    lock = ControlLock()
    lock.take(bot_id)
    return lock


async def test_while_held_checked_inputs_reach_the_session_in_order():
    session = _Session()
    messages = [_text({"t": "text", "text": "one"}), _text("not json"), _text({"t": "text", "text": "two"})]
    await _read_inputs(_Inputs(messages), "b1", session, _Notices(), _held())
    assert session.handled == [TextInput(t="text", text="one"), TextInput(t="text", text="two")]


async def test_once_control_is_released_no_input_reaches_the_session():
    """Review Focus 4: an input already on its way when Give it back lands is never sent."""
    lock = _held()
    lock.give_back("b1")
    session = _Session()
    await _read_inputs(_Inputs([_text({"t": "text", "text": SECRET})]), "b1", session, _Notices(), lock)
    assert session.handled == []


async def test_an_input_the_page_refuses_is_told_to_the_user():
    notices = _Notices()
    await _read_inputs(_Inputs([_text({"t": "text", "text": "x"})]), "b1", _Session("failed"), notices, _held())
    assert notices.sent == [INPUT_FAILED_TEXT]


async def test_binary_from_the_face_is_never_input():
    session = _Session()
    binary = {"type": "websocket.receive", "bytes": json.dumps({"t": "text", "text": "x"}).encode()}
    await _read_inputs(_Inputs([binary]), "b1", session, _Notices(), _held())
    assert session.handled == []
```

Create `tests/test_live_api.py`:

```python
"""``WS /api/bots/{bot_id}/live`` (live control, Task 6; design §2) against the real gateway in fake
mode: the accept rules and their close codes, frames and input through ``FakeDesk``'s ``FakeCdp``,
the close on Give it back, and that nothing typed is ever logged, published or stored.

Every test uses ``with TestClient(app, client=...) as c:`` so the lifespan runs and every request and
socket share one event loop: the give-back request must wake the socket's wait on that loop.
``client=`` sets the peer address the route sees (Starlette's default, "testclient", is not this Mac).
Leaving a ``websocket_connect`` block cancels the route, so a test that ends a session itself
(``_leave``) waits for the session to stop before it leaves the block."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Callable, Iterator

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import roost.desk.live as live_module
import roost.desk.live_input as live_input_module
from roost.config import load_config
from roost.constants import LIVE_JPEG_QUALITY, LIVE_MAX_HEIGHT, LIVE_MAX_WIDTH
from roost.db.connection import get_db_path
from roost.desk.fake import FAKE_JPEG
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}
HERE = ("127.0.0.1", 50000)
HERE_V6 = ("::1", 50000)
LAN = ("192.168.1.20", 50000)
DOCKER_HOST = ("192.168.65.1", 50000)
PASSWORD = "pw-123456"
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}
SECRET = "hunter2-correct-horse"
NOT_THIS_MAC = (4403, "Live control works only on this Mac for now.")
GIVEN_BACK = (4000, "Given back.")
UNAVAILABLE = (4503, "The bot's computer stopped answering.")
ROWS = ("events", "audit", "messages", "work_items")
LIVE_LOGGERS = ("roost.desk.live", "roost.gateway.live_socket", "roost.gateway.routes.live")


@pytest.fixture(autouse=True)
def _frames_without_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_module, "LIVE_MIN_FRAME_INTERVAL_S", 0.0)


@contextmanager
def _gateway(peer: tuple[str, int] = HERE, *, in_container: bool = False) -> Iterator[TestClient]:
    config = replace(load_config(), in_container=in_container)
    with TestClient(create_app(config), client=peer) as client:
        registered = client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD}, headers=O)
        assert registered.status_code == 201
        yield client


def _bot(c: TestClient, *, running: bool = True, held: bool = True) -> str:
    created = c.post("/api/bots", json={"name": "Helper", "job": "helps", "instructions": "", "avatar": AVATAR},
                     headers=O)
    bot_id = created.json()["id"]
    if running:
        c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    if held:
        c.post(f"/api/bots/{bot_id}/control", headers=O)
    return bot_id


def _live(c: TestClient, bot_id: str, headers: dict[str, str] | None = None):
    return c.websocket_connect(f"/api/bots/{bot_id}/live", headers={**O, **(headers or {})})


def _refused(c: TestClient, bot_id: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    with pytest.raises(WebSocketDisconnect) as closed:
        with _live(c, bot_id, headers) as ws:
            ws.receive_text()
    return closed.value.code, closed.value.reason


def _until_closed(ws: Any) -> tuple[int, str]:
    for _ in range(5000):
        message = ws.receive()
        if message["type"] == "websocket.close":
            return message.get("code", 1000), message.get("reason") or ""
    raise AssertionError("the live screen was never closed")


def _next_text(ws: Any, kind: str) -> dict[str, Any]:
    """The next JSON frame of ``kind`` ("frame", "page" or "notice"). JPEGs and other frames are skipped."""
    for _ in range(5000):
        message = ws.receive()
        if message["type"] == "websocket.close":
            raise AssertionError(f"closed with {message.get('code')} {message.get('reason')!r} before a {kind}")
        text = message.get("text")
        if text is not None and json.loads(text)["t"] == kind:
            return json.loads(text)
    raise AssertionError(f"no {kind} frame came")


def _first_frame(ws: Any) -> tuple[dict[str, Any], bytes]:
    header = _next_text(ws, "frame")
    return header, ws.receive()["bytes"]


def _wait(predicate: Callable[[], bool], timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting")
        time.sleep(0.01)


def _cdp(c: TestClient, bot_id: str) -> Any:
    return c.app.state.desks.for_bot(bot_id).cdp


def _sent(c: TestClient, bot_id: str, method: str) -> list[dict[str, Any]]:
    return [dict(call.params) for call in _cdp(c, bot_id).calls if call.method == method]


def _stopped(c: TestClient, bot_id: str) -> bool:
    """The session stopped: discovery is off as often as it was turned on, and no screencast runs."""
    turns = _sent(c, bot_id, "Target.setDiscoverTargets")
    return turns.count({"discover": False}) == turns.count({"discover": True}) > 0 and not _cdp(c, bot_id).screencasting()


def _leave(c: TestClient, bot_id: str, ws: Any) -> None:
    """The user closes the live screen; the session stops before the test leaves the block."""
    ws.close(1000)
    _wait(lambda: _stopped(c, bot_id))


def _row_counts(c: TestClient) -> dict[str, int]:
    con = sqlite3.connect(get_db_path(c.app.state.config))
    try:
        return {table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ROWS}
    finally:
        con.close()


def test_the_gateway_wires_the_live_route():
    assert create_app().url_path_for("live_ws", bot_id="bot-1") == "/api/bots/bot-1/live"


# -- frames and input --


def test_the_live_screen_streams_frames_each_with_its_metadata_first():
    with _gateway() as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            header, jpeg = _first_frame(ws)
            assert header == {"t": "frame", "w": 1280, "h": 800, "scale": 1, "top": 0, "sx": 0, "sy": 0}
            assert jpeg == FAKE_JPEG
            _wait(lambda: len(_sent(c, bot_id, "Page.screencastFrameAck")) >= 1)
            _leave(c, bot_id, ws)
        assert _sent(c, bot_id, "Page.startScreencast") == [{
            "format": "jpeg", "quality": LIVE_JPEG_QUALITY, "maxWidth": LIVE_MAX_WIDTH,
            "maxHeight": LIVE_MAX_HEIGHT, "everyNthFrame": 1}]
        assert c.get(f"/api/bots/{bot_id}/control").json()["held"] is True     # closing the screen keeps control


def test_the_address_bar_shows_the_bots_page():
    with _gateway() as c:
        bot_id = _bot(c)
        c.portal.call(c.app.state.desks.for_bot(bot_id).open_page, "https://login.example/")
        with _live(c, bot_id) as ws:
            assert _next_text(ws, "page") == {"t": "page", "url": "https://login.example/", "title": "Fake Page"}
            _leave(c, bot_id, ws)


def test_clicks_and_typing_become_the_exact_cdp_calls():
    with _gateway() as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            ws.send_json({"t": "mouse", "kind": "down", "x": 640, "y": 400, "button": "left", "clicks": 1, "mods": 0})
            ws.send_json({"t": "key", "kind": "down", "key": "a", "code": "KeyA", "mods": 0})
            ws.send_json({"t": "text", "text": "ana@example.com"})
            ws.send_json({"t": "nav", "action": "reload"})
            _wait(lambda: len(_sent(c, bot_id, "Page.reload")) == 1)
            _leave(c, bot_id, ws)
        assert _sent(c, bot_id, "Input.dispatchMouseEvent") == [
            {"type": "mousePressed", "x": 640, "y": 400, "button": "left", "clickCount": 1, "modifiers": 0}]
        assert _sent(c, bot_id, "Input.dispatchKeyEvent") == [
            {"type": "keyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 0,
             "text": "a", "unmodifiedText": "a"}]
        assert _sent(c, bot_id, "Input.insertText") == [{"text": "ana@example.com"}]


def test_an_input_the_page_refuses_tells_the_user():
    with _gateway() as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            _cdp(c, bot_id).refuse("Input.insertText")
            ws.send_json({"t": "text", "text": "ana@example.com"})
            assert _next_text(ws, "notice") == {"t": "notice", "text": "That didn't reach the page. Try again."}
            _leave(c, bot_id, ws)


def test_inputs_over_the_rate_limit_are_dropped(monkeypatch):
    monkeypatch.setattr(live_input_module, "LIVE_INPUT_MAX_PER_SECOND", 3)
    with _gateway() as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            for n in range(6):
                ws.send_json({"t": "text", "text": f"paste {n}"})
            _wait(lambda: len(_sent(c, bot_id, "Input.insertText")) == 3)
            time.sleep(0.2)                                    # the other three would have landed by now
            assert _sent(c, bot_id, "Input.insertText") == [{"text": f"paste {n}"} for n in range(3)]
            _leave(c, bot_id, ws)


def test_a_pop_up_is_followed_and_the_screen_comes_back():
    """Review Focus 3, end to end through the socket."""
    with _gateway() as c:
        bot_id = _bot(c)
        cdp = _cdp(c, bot_id)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            c.portal.call(cdp.open_pop_up, "pop-up", "https://accounts.example/signin", "Sign in")
            assert _next_text(ws, "page")["url"] == "https://accounts.example/signin"
            c.portal.call(cdp.close_target, "pop-up")
            assert _next_text(ws, "page")["url"] == "about:blank"
            _leave(c, bot_id, ws)


# -- the end --


def test_give_it_back_closes_the_live_screen_with_4000_and_stops_the_screencast():
    with _gateway() as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            assert c.delete(f"/api/bots/{bot_id}/control", headers=O).json() == {"held": False, "since": None}
            assert _until_closed(ws) == GIVEN_BACK
        assert _stopped(c, bot_id)


def test_input_after_give_it_back_never_reaches_the_page():
    """Review Focus 4: once the computer is given back, nothing typed on a live screen that is still
    closing may reach the bot's page."""
    with _gateway() as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            c.delete(f"/api/bots/{bot_id}/control", headers=O)
            ws.send_json({"t": "text", "text": SECRET})
            ws.send_json({"t": "key", "kind": "down", "key": "x", "code": "KeyX", "mods": 0})
            assert _until_closed(ws) == GIVEN_BACK
        assert _sent(c, bot_id, "Input.insertText") == []
        assert _sent(c, bot_id, "Input.dispatchKeyEvent") == []


def test_retiring_the_bot_closes_its_live_screen():
    with _gateway() as c:
        bot_id = _bot(c)
        cdp = _cdp(c, bot_id)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            assert c.delete(f"/api/bots/{bot_id}", headers=O).status_code < 300
            assert _until_closed(ws) == GIVEN_BACK
        assert cdp.screencasting() == frozenset()


def test_a_computer_that_stops_answering_closes_the_live_screen_with_4503():
    """Review Focus 5: Brave crashed or the keeper restarted. The live screen must say so (the face
    offers Retry), never sit on its last frame."""
    with _gateway() as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            c.portal.call(_cdp(c, bot_id).disconnect)
            assert _until_closed(ws) == UNAVAILABLE


# -- who may connect --


def test_a_connection_from_another_machine_is_refused_with_4403():
    """Review Focus 2 (L1): live control works only on this Mac for now."""
    with _gateway(LAN) as c:
        bot_id = _bot(c)
        assert _refused(c, bot_id) == NOT_THIS_MAC
        assert _cdp(c, bot_id).calls == ()


@pytest.mark.parametrize("header", [{"X-Forwarded-For": "203.0.113.7"}, {"Forwarded": "for=203.0.113.7"},
                                    {"X-Real-IP": "203.0.113.7"}])
def test_a_forwarded_connection_is_refused_even_from_this_mac(header):
    """Review Focus 2: something forwarded it, so it is not this Mac."""
    with _gateway(HERE) as c:
        bot_id = _bot(c)
        assert _refused(c, bot_id, header) == NOT_THIS_MAC


def test_ipv6_loopback_is_this_mac_too():
    with _gateway(HERE_V6) as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            assert _first_frame(ws)[1] == FAKE_JPEG
            _leave(c, bot_id, ws)


def test_the_gateway_container_counts_its_published_port_as_this_mac():
    """D1: the always-on gateway runs in Docker and sees this Mac's browser from a Docker address."""
    with _gateway(DOCKER_HOST, in_container=True) as c:
        bot_id = _bot(c)
        with _live(c, bot_id) as ws:
            assert _first_frame(ws)[1] == FAKE_JPEG
            _leave(c, bot_id, ws)


def test_a_foreign_origin_is_refused_with_4403():
    with _gateway() as c:
        assert _refused(c, _bot(c), BAD_O) == (4403, "Origin not allowed.")


def test_without_a_session_it_is_4401():
    with _gateway() as c:
        bot_id = _bot(c)
        c.cookies.clear()
        assert _refused(c, bot_id) == (4401, "Sign in first.")


def test_an_unknown_bot_or_another_users_bot_is_4404():
    with _gateway() as c:
        config = c.app.state.config
        bob = c.portal.call(register_user, config, "bob", PASSWORD)
        bobs_bot = c.portal.call(make_bot, config, bob.id, "Helper")
        c.portal.call(c.app.state.control.take, bobs_bot.id)
        assert _refused(c, bobs_bot.id) == (4404, "Bot not found")
        assert _refused(c, "not-a-bot") == (4404, "Bot not found")


def test_without_control_it_is_4409_take_control_first():
    with _gateway() as c:
        assert _refused(c, _bot(c, held=False)) == (4409, "Take control first.")


def test_a_sleeping_computer_closes_with_asleep():
    with _gateway() as c:
        bot_id = _bot(c, running=False)
        assert _refused(c, bot_id) == (4410, "asleep")
        assert c.get(f"/api/bots/{bot_id}/desk").json()["browser"] == "stopped"   # never started


def test_an_unreachable_computer_closes_with_4503():
    with _gateway() as c:
        bot_id = _bot(c)
        c.app.state.desks.for_bot(bot_id).force_unavailable = True
        assert _refused(c, bot_id) == UNAVAILABLE


# -- secrets (L2) --


def test_nothing_typed_reaches_the_logs_the_events_or_the_database(caplog):
    """Review Focus 1: keys, a paste, refused frames and an input the page refused reach no log line,
    no event, no audit row and no other row."""
    caplog.set_level(logging.DEBUG)
    with _gateway() as c:
        bot_id = _bot(c)
        user_id = c.get("/api/auth/me").json()["id"]
        before = _row_counts(c)
        with _live(c, bot_id) as ws:
            _first_frame(ws)
            for char in SECRET:
                ws.send_json({"t": "key", "kind": "down", "key": char, "code": "", "mods": 0})
                ws.send_json({"t": "key", "kind": "up", "key": char, "code": "", "mods": 0})
            ws.send_json({"t": "text", "text": SECRET})
            ws.send_json({"t": "key", "kind": "down", "key": SECRET})                   # refused: not a key
            ws.send_json({"t": "text", "text": SECRET, "smuggled": True})               # refused: an extra field
            ws.send_text(SECRET)                                                        # refused: not JSON
            _wait(lambda: len(_sent(c, bot_id, "Input.insertText")) == 1)
            _cdp(c, bot_id).refuse("Input.insertText")
            ws.send_json({"t": "text", "text": SECRET})                                 # refused by the page
            _next_text(ws, "notice")
            c.delete(f"/api/bots/{bot_id}/control", headers=O)
            assert _until_closed(ws) == GIVEN_BACK
        after = _row_counts(c)
        frames = c.portal.call(c.app.state.events.since, user_id, 0)
    assert after == before
    assert SECRET not in caplog.text
    assert SECRET not in json.dumps(frames)
    assert [r for r in caplog.records if r.levelno >= logging.WARNING and r.name.startswith(LIVE_LOGGERS)] == []
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_control_lock.py tests/test_live_socket.py tests/test_live_api.py -q`
Expected: FAIL.
- `tests/test_control_lock.py`: the four new tests fail with `AttributeError: 'ControlLock' object has no attribute 'wait_released'`.
- `tests/test_live_socket.py`: a collection error, `ModuleNotFoundError: No module named 'roost.gateway.live_socket'`.
- `tests/test_live_api.py`: `test_the_gateway_wires_the_live_route` fails with `starlette.routing.NoMatchFound`, and every socket test fails (Starlette refuses the handshake for a path with no WebSocket route), because `/api/bots/{bot_id}/live` does not exist yet.

- [ ] **Step 4: Add the socket constants**

Append this to the very end of `roost/constants.py`:

```python

# Task 6 — roost/gateway/live_socket.py, roost/gateway/routes/live.py: who may connect, and the close codes.
LIVE_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
LIVE_FORWARDED_HEADERS = ("forwarded", "x-forwarded-for", "x-real-ip")
LIVE_CLOSE_GIVEN_BACK = 4000
LIVE_CLOSE_UNAUTHENTICATED = 4401
LIVE_CLOSE_REFUSED = 4403
LIVE_CLOSE_NOT_FOUND = 4404
LIVE_CLOSE_NOT_HELD = 4409
LIVE_CLOSE_ASLEEP = 4410
LIVE_CLOSE_UNAVAILABLE = 4503
```

- [ ] **Step 5: `ControlLock.wait_released` (`roost/desk/control.py`)**

Replace these lines:

```python
    def forget(self, bot_id: str) -> None:
        """The bot was retired: a hold on its computer means nothing any more."""
        self.give_back(bot_id)
        self._taken = {k: v for k, v in self._taken.items() if k != bot_id}
```

with:

```python
    def forget(self, bot_id: str) -> None:
        """The bot was retired: a hold on its computer means nothing any more."""
        self.give_back(bot_id)
        self._taken = {k: v for k, v in self._taken.items() if k != bot_id}

    async def wait_released(self, bot_id: str) -> None:
        """Live control: returns once the person no longer holds ``bot_id``'s computer, and at once when
        nobody does. Any release ends the wait: Give it back, Give up, a Stuck card's clear, retiring."""
        event = self._released.get(bot_id)
        if bot_id not in self._holds or event is None:
            return
        await event.wait()
```

- [ ] **Step 6: The socket side (`roost/gateway/live_socket.py`)**

Create `roost/gateway/live_socket.py`:

```python
"""The live screen's socket side (live control, Task 6; design §2, L1, L2, D1).

- ``live_refusal`` checks one ``/api/bots/{id}/live`` connection against design §2's accept rules, in
  this order, and gives the close code and reason of the first one it breaks, or ``None``: this Mac
  (4403), Roost's own origin (4403), signed in (4401), the user's own bot (4404), control held (4409).
- ``peer_is_this_mac``: the peer is 127.0.0.1 or ::1, and nothing forwarded the request. Inside the
  gateway container every peer is this Mac's own loopback, because compose publishes the port on the
  Mac's 127.0.0.1 alone (``docker-compose.yml``, pinned by ``tests/test_compose.py``), so there the
  peer address is not checked (D1). A forwarded request is refused either way.
- ``LiveSocketSink`` sends what a ``LiveSession`` produces: a frame as a JSON header then its JPEG,
  with one frame in flight (a frame that comes while the last one is still going out replaces the one
  waiting), and page changes and notices as JSON. It never writes a frame anywhere else.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

from roost.config import RoostConfig
from roost.constants import (
    LIVE_CLOSE_NOT_FOUND, LIVE_CLOSE_NOT_HELD, LIVE_CLOSE_REFUSED, LIVE_CLOSE_UNAUTHENTICATED,
    LIVE_FORWARDED_HEADERS, LIVE_LOOPBACK_HOSTS,
)
from roost.db.connection import ensure_initialized
from roost.desk.live import LiveFrame, PageInfo
from roost.desk.live_input import FrameMeta
from roost.gateway.auth import SESSION_COOKIE_NAME, get_session_user

NOT_THIS_MAC_REASON = "Live control works only on this Mac for now."
ORIGIN_REASON = "Origin not allowed."
SIGN_IN_REASON = "Sign in first."
NOT_FOUND_REASON = "Bot not found"
NOT_HELD_REASON = "Take control first."


@dataclass(frozen=True)
class Refusal:
    """A close code, and the reason the face shows for it."""

    code: int
    reason: str


def peer_is_this_mac(websocket: WebSocket, config: RoostConfig) -> bool:
    """L1 and D1: a loopback peer, or any peer of the gateway container; never a forwarded request."""
    if any(websocket.headers.get(name) is not None for name in LIVE_FORWARDED_HEADERS):
        return False
    if config.in_container:
        return True
    client = websocket.client
    return client is not None and client.host in LIVE_LOOPBACK_HOSTS


async def live_refusal(websocket: WebSocket, bot_id: str) -> Refusal | None:
    """The first accept rule this connection breaks, or ``None`` when it may see the bot's page."""
    state = websocket.app.state
    config: RoostConfig = state.config
    if not peer_is_this_mac(websocket, config):
        return Refusal(LIVE_CLOSE_REFUSED, NOT_THIS_MAC_REASON)
    if websocket.headers.get("origin") not in config.allowed_origins:
        return Refusal(LIVE_CLOSE_REFUSED, ORIGIN_REASON)
    await ensure_initialized(config)
    session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    user = await get_session_user(config, session_id) if session_id else None
    if user is None:
        return Refusal(LIVE_CLOSE_UNAUTHENTICATED, SIGN_IN_REASON)
    if await state.bots.get(user.id, bot_id) is None:
        return Refusal(LIVE_CLOSE_NOT_FOUND, NOT_FOUND_REASON)
    if state.control.held(bot_id) is None:
        return Refusal(LIVE_CLOSE_NOT_HELD, NOT_HELD_REASON)
    return None


def frame_header(meta: FrameMeta) -> dict[str, Any]:
    """The small JSON text frame that goes just before each JPEG (design §2)."""
    return {"t": "frame", "w": meta.device_width, "h": meta.device_height, "scale": meta.page_scale,
            "top": meta.offset_top, "sx": meta.scroll_x, "sy": meta.scroll_y}


class LiveSocketSink:
    """A ``LiveSink`` on the user's socket. ``frame`` never waits on the socket: the newest frame waits
    in one slot and ``pump`` sends it, so a slow socket gets the newest frame next, not a backlog
    (``dropped`` counts the frames it skipped). Everything that goes out shares one lock, so a page or
    notice frame never lands between a frame's header and its JPEG."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._waiting: LiveFrame | None = None
        self._ready = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self.dropped = 0

    async def frame(self, frame: LiveFrame) -> None:
        if self._waiting is not None:
            self.dropped += 1
        self._waiting = frame
        self._ready.set()

    async def page(self, info: PageInfo) -> None:
        await self._send_json({"t": "page", "url": info.url, "title": info.title})

    async def notice(self, text: str) -> None:
        await self._send_json({"t": "notice", "text": text})

    async def pump(self) -> None:
        """Send the newest waiting frame, one at a time, until cancelled."""
        while True:
            await self._ready.wait()
            self._ready.clear()
            frame, self._waiting = self._waiting, None
            if frame is None:
                continue
            async with self._send_lock:
                await self._websocket.send_json(frame_header(frame.meta))
                await self._websocket.send_bytes(frame.jpeg)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._websocket.send_json(payload)
```

- [ ] **Step 7: The route (`roost/gateway/routes/live.py`)**

Create `roost/gateway/routes/live.py`:

```python
"""Live control over a WebSocket — ``WS /api/bots/{bot_id}/live`` (Task 6; design §2).

Accept first, then close with a specific code (Ruling 9, as ``/api/events`` does), so the face always
gets a real close frame with a reason it can show:

- 4403 "Live control works only on this Mac for now." or "Origin not allowed."
- 4401 "Sign in first."
- 4404 "Bot not found": not the user's bot.
- 4409 "Take control first.": the user doesn't hold the bot's computer.
- 4410 "asleep": the bot's browser is closed, and the face offers Open it.
- 4503 "The bot's computer stopped answering.": the keeper or Brave can't be reached, or went away.
- 4000 "Given back.": control was released (Give it back, Give up, a Stuck card's clear, Retire this bot).

While it runs, four things race: the session's frames and target events, the frame sender, the
user's inputs, and the control lock's release. The first to finish ends the session, which then
stops (screencast off, discovery off). An input is sent only while the user still holds control, so
nothing typed after Give it back reaches the page. No input is ever logged, audited or published.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from roost.constants import LIVE_CLOSE_ASLEEP, LIVE_CLOSE_GIVEN_BACK, LIVE_CLOSE_UNAVAILABLE
from roost.desk import DeskAsleep, DeskUnavailable
from roost.desk.cdp import CdpClientError
from roost.desk.control import ControlLock
from roost.desk.live import LiveEnd, LiveSession
from roost.desk.live_input import InputRateLimit, parse_input
from roost.gateway.live_socket import LiveSocketSink, Refusal, live_refusal

logger = logging.getLogger(__name__)

live_router = APIRouter(tags=["live"])

GIVEN_BACK_REASON = "Given back."
ASLEEP_REASON = "asleep"
UNAVAILABLE_REASON = "The bot's computer stopped answering."
INPUT_FAILED_TEXT = "That didn't reach the page. Try again."
_GIVEN_BACK = Refusal(LIVE_CLOSE_GIVEN_BACK, GIVEN_BACK_REASON)
_ASLEEP = Refusal(LIVE_CLOSE_ASLEEP, ASLEEP_REASON)
_UNAVAILABLE = Refusal(LIVE_CLOSE_UNAVAILABLE, UNAVAILABLE_REASON)


@live_router.websocket("/api/bots/{bot_id}/live")
async def live_ws(websocket: WebSocket, bot_id: str) -> None:
    await websocket.accept()
    ending = await live_refusal(websocket, bot_id)
    if ending is None:
        ending = await _serve(websocket, bot_id)
    if ending is not None:
        # The user's side may have gone in the meantime; then there is no one left to tell.
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=ending.code, reason=ending.reason)


async def _serve(websocket: WebSocket, bot_id: str) -> Refusal | None:
    """Show the bot's page until the first of: given back, the user leaves, the computer goes away."""
    state = websocket.app.state
    try:
        view = await state.desks.for_bot(bot_id).live_view()
    except DeskAsleep:
        return _ASLEEP
    except DeskUnavailable:
        logger.warning("Live control: the computer of bot %s can't be reached", bot_id)
        return _UNAVAILABLE
    sink = LiveSocketSink(websocket)
    session = LiveSession(view, sink)
    try:
        await session.start()
        return await _until_the_end(websocket, bot_id, session, sink, state.control)
    except CdpClientError as exc:
        logger.warning("Live control: the page of bot %s could not be shown (%s)", bot_id, type(exc).__name__)
        return _UNAVAILABLE
    finally:
        await session.stop()


async def _until_the_end(websocket: WebSocket, bot_id: str, session: LiveSession, sink: LiveSocketSink,
                         control: ControlLock) -> Refusal | None:
    released = asyncio.create_task(control.wait_released(bot_id))
    showing = asyncio.create_task(session.run())
    sending = asyncio.create_task(sink.pump())
    reading = asyncio.create_task(_read_inputs(websocket, bot_id, session, sink, control))
    tasks = (released, showing, sending, reading)
    try:
        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if released in done:
        return _GIVEN_BACK
    if showing in done:
        return _session_ending(showing, bot_id)
    return None   # the user closed the live screen, or it could not be written to


def _session_ending(showing: "asyncio.Task[LiveEnd]", bot_id: str) -> Refusal:
    error = showing.exception()
    if error is not None:
        logger.error("Live control for bot %s ended on an error", bot_id, exc_info=error)
        return _UNAVAILABLE
    return _ASLEEP if showing.result() == "page_closed" else _UNAVAILABLE


async def _read_inputs(websocket: WebSocket, bot_id: str, session: LiveSession, sink: LiveSocketSink,
                       control: ControlLock) -> None:
    """The user's inputs, one at a time: checked, rate-limited, and sent only while the user still holds
    control. Returns when the user leaves, or when control was released (Review Focus 4)."""
    limit = InputRateLimit()
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        event = parse_input(message.get("text") or "")
        if event is None or not limit.allow():
            continue
        if control.held(bot_id) is None:
            return
        if await session.handle(event) == "failed":
            await sink.notice(INPUT_FAILED_TEXT)
```

- [ ] **Step 8: Wire the router (`roost/gateway/app.py`)**

Replace this line:

```python
from roost.gateway.routes.health import health_router
```

with:

```python
from roost.gateway.routes.health import health_router
from roost.gateway.routes.live import live_router
```

Then replace this line:

```python
    app.include_router(stuck_router)
```

with:

```python
    app.include_router(stuck_router)
    app.include_router(live_router)
```

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_control_lock.py tests/test_live_socket.py tests/test_live_api.py tests/test_events_ws.py tests/test_computer_api.py -q`
Expected: PASS. `test_events_ws.py` is the other WebSocket route and must not change.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_live_socket.py tests/test_live_api.py --cov=roost.gateway.live_socket --cov=roost.gateway.routes.live --cov-report=term-missing -q`
Expected: PASS, both modules at least 90%.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/desk/control.py roost/gateway/live_socket.py roost/gateway/routes/live.py roost/gateway/app.py \
  roost/constants.py tests/test_control_lock.py tests/test_live_socket.py tests/test_live_api.py
git commit -m "feat: the live screen's socket: this Mac only, frames out, checked input in, closed on Give it back"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the eight files is listed.

---

### Task 7: Bot windows out of the way, and Show window on Mac

Design §2 "Bot windows out of the way (L3)", and the Task 1 spike's recorded line:
- **Set aside on start.** When a bot's own tab is created (`DeskBrowserPage._ensure_session`, the first page call after the keeper starts or reattaches Brave), the bot's window steps aside. That is `Browser.getWindowForTarget`, then one `Browser.setWindowBounds` per step of `BOT_WINDOW_ASIDE_STEPS`. A window that can't be moved is only a warning: the bot's page still opens. `_connect_page`, the real page builder, passes the steps in. Pages built in tests pass none, so every existing call-sequence test is unchanged.
- **Show window on Mac** (`POST /api/bots/{id}/window/show`) restores the window (`BOT_WINDOW_SHOW_STEPS`) and brings the bot's page to the front (`Target.activateTarget`). Like a screenshot, it never starts a browser and never opens a tab: a closed browser is 409 "asleep".
- **The variant comes from Task 1's recorded line.** Write the constants for the word it recorded:
  - `minimise`: aside `({"windowState": "minimized"},)`, show `({"windowState": "normal"},)`.
  - `behind`: aside `({"left": BOT_WINDOW_FAR_AWAY, "top": BOT_WINDOW_FAR_AWAY},)`, show `({"windowState": "normal"}, {"left": BOT_WINDOW_SHOWN_LEFT, "top": BOT_WINDOW_SHOWN_TOP})`.
  - `leave`: aside `()`, show `({"windowState": "normal"},)`.
- **The tests read the constants**, so they pass for whichever variant was recorded. The tests of `DeskBrowserPage` itself use their own explicit steps.

**Files:**
- Modify:
  - `roost/constants.py` (the `MappingProxyType` import, and the window constants appended)
  - `roost/desk/__init__.py` (`Desk.show_window`)
  - `roost/desk/browser.py` (`window_aside`, `_set_aside`, `set_window`, `_apply_window`; round A touched this file)
  - `roost/desk/client.py` (`_connect_page` passes the aside steps; `KeeperDesk.show_window`)
  - `roost/desk/fake.py` (`show_window`, `windows_shown`)
  - `roost/gateway/routes/desk.py` (the route)
- Test: `tests/test_cdp_client.py` (the fake server answers window calls); `tests/test_cdp_live.py`, `tests/test_keeper_client.py`, `tests/test_fake_desk.py` and `tests/test_computer_api.py` (imports where needed, and tests appended)

**Interfaces:**
- Consumes:
  - Task 1's recorded variant.
  - Task 5: `DeskBrowserPage.live_target`, `KeeperDesk._view`, `FakeDesk` waking on page calls.
  - Existing: `_owned_bot_or_404`, `_unavailable`, `desk_router`, `RequireOrigin`, `CurrentUser`.
- Produces:
  - `BOT_WINDOW_FAR_AWAY`, `BOT_WINDOW_SHOWN_LEFT`, `BOT_WINDOW_SHOWN_TOP`, `BOT_WINDOW_ASIDE_STEPS`, `BOT_WINDOW_SHOW_STEPS`.
  - `DeskBrowserPage(client, *, window_aside=())` and `DeskBrowserPage.set_window(steps, *, activate=False)`.
  - `Desk.show_window`, `KeeperDesk.show_window`, `FakeDesk.show_window` and `FakeDesk.windows_shown`.
  - `POST /api/bots/{bot_id}/window/show`.

- [ ] **Step 1: Path guard, and read the recorded variant**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `grep -n "^\*\*Design decision — bot windows (L3), set by Task 1" /Users/blckit/Desktop/Code_Projects/roost/docs/plans/2026-10-15-roost-live-control.md`
Expected: one line that reads `... set by Task 1 on <date>:** minimise.`, `behind.` or `leave.`. If it still says `Not measured yet`, stop: Task 1 comes first.

- [ ] **Step 2: Write the failing tests**

In `tests/test_cdp_client.py`, make the fake server answer the window calls. Replace these lines:

```python
        self._dom_error = dom_error
```

with:

```python
        self._dom_error = dom_error
        self._no_window = False          # live control (Task 7): Browser.getWindowForTarget answers an error
```

Then replace these lines:

```python
        if method.startswith("DOM.") and not self._dom_error:
            return self._dom_result(method, params)
        return None
```

with:

```python
        if method.startswith("DOM.") and not self._dom_error:
            return self._dom_result(method, params)
        if method == "Browser.getWindowForTarget" and not self._no_window:
            return {"windowId": 3, "bounds": {"windowState": "normal"}}
        if method in ("Browser.setWindowBounds", "Target.activateTarget"):
            return {}
        return None
```

In `tests/test_cdp_live.py`, replace these import lines:

```python
import asyncio
from typing import Any
```

with:

```python
import asyncio
import logging
from typing import Any
```

Then replace these lines:

```python
from roost.desk import DeskAsleep
from roost.desk.browser import DeskBrowserPage
from roost.desk.cdp import CdpClient, CdpClientError, CdpSubscription
```

with:

```python
import roost.desk.browser as browser_module
from roost.desk import DeskAsleep
from roost.desk.browser import DeskBrowserPage
from roost.desk.cdp import CdpClient, CdpClientError, CdpReplyError, CdpSubscription
```

Then append this to the end of `tests/test_cdp_live.py`:

```python


# -- Task 7: the bot's window steps aside, and Show window on Mac --

_ASIDE = ({"windowState": "minimized"},)
_SHOW = ({"windowState": "normal"}, {"left": 80, "top": 60})


def _window_calls(fake_server: _FakeCdpServer) -> list[tuple[str, dict[str, Any]]]:
    return [(m["method"], m["params"]) for m in fake_server.received
            if m["method"].startswith("Browser.") or m["method"] == "Target.activateTarget"]


async def test_the_bots_window_steps_aside_once_its_tab_exists(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    page = DeskBrowserPage(connected_client, window_aside=_ASIDE)
    await page.open_page("https://example.com/")
    await page.open_page("https://example.com/")                # the tab exists now: no second move
    assert _window_calls(fake_server) == [
        ("Browser.getWindowForTarget", {"targetId": "target-1"}),
        ("Browser.setWindowBounds", {"windowId": 3, "bounds": {"windowState": "minimized"}}),
    ]
    methods = [m["method"] for m in fake_server.received]
    assert methods.index("Browser.setWindowBounds") < methods.index("Page.navigate")


async def test_a_page_with_no_aside_steps_leaves_the_window_alone(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    await DeskBrowserPage(connected_client).open_page("https://example.com/")
    assert _window_calls(fake_server) == []


async def test_a_window_that_cannot_be_moved_is_a_warning_and_the_page_still_opens(
    fake_server: _FakeCdpServer, connected_client: CdpClient, caplog: pytest.LogCaptureFixture
) -> None:
    fake_server._no_window = True
    with caplog.at_level(logging.WARNING, logger=browser_module.logger.name):
        result = await DeskBrowserPage(connected_client, window_aside=_ASIDE).open_page("https://example.com/")
    assert result.title == "Example Page"
    assert any("set aside" in record.getMessage() for record in caplog.records)


async def test_show_window_restores_it_and_brings_the_page_to_the_front(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    await DeskBrowserPage(connected_client).set_window(_SHOW, activate=True)
    assert [(m["method"], m["params"]) for m in fake_server.received] == [
        ("Target.getTargets", {}),
        ("Browser.getWindowForTarget", {"targetId": "target-0"}),
        ("Browser.setWindowBounds", {"windowId": 3, "bounds": {"windowState": "normal"}}),
        ("Browser.setWindowBounds", {"windowId": 3, "bounds": {"left": 80, "top": 60}}),
        ("Target.activateTarget", {"targetId": "target-0"}),
    ]


async def test_showing_the_window_of_a_browser_with_no_page_is_asleep() -> None:
    server = _FakeCdpServer(open_pages=False)
    await server.start()
    client = CdpClient(server.url, _TOKEN)
    await client.connect()
    try:
        with pytest.raises(DeskAsleep):
            await DeskBrowserPage(client).set_window(_SHOW, activate=True)
        assert "Target.createTarget" not in [m["method"] for m in server.received]
    finally:
        await client.close()
        await server.stop()


async def test_a_window_the_browser_cannot_find_is_a_cdp_reply_error(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._no_window = True
    with pytest.raises(CdpReplyError):
        await DeskBrowserPage(connected_client).set_window(_SHOW)
```

In `tests/test_keeper_client.py`, replace these import lines:

```python
from roost.config import RoostConfig
from roost.constants import EXEC_TIMEOUT_S, KEEPER_RETIRE_REQUEST_TIMEOUT_S
```

with:

```python
import roost.desk.client as client_module
from roost.config import RoostConfig
from roost.constants import (
    BOT_WINDOW_ASIDE_STEPS, BOT_WINDOW_SHOW_STEPS, EXEC_TIMEOUT_S, KEEPER_RETIRE_REQUEST_TIMEOUT_S,
)
```

Then append this to the end of `tests/test_keeper_client.py`:

```python


# -- Live control (Task 7): bot windows --


class _WindowPage(_LivePage):
    """A connected page that records each window change."""

    def __init__(self) -> None:
        super().__init__()
        self.windows: list[tuple[object, bool]] = []

    async def set_window(self, steps, *, activate: bool = False) -> None:
        self.windows.append((steps, activate))


async def test_show_window_restores_the_running_browsers_window_and_never_starts_it(config: RoostConfig) -> None:
    seen: list[tuple[str, str]] = []
    page = _WindowPage()
    await _attaching_desk(config, page, seen).show_window()
    assert page.windows == [(BOT_WINDOW_SHOW_STEPS, True)]
    assert seen == [("POST", _ATTACH)]


async def test_show_window_of_a_sleeping_computer_is_asleep(config: RoostConfig) -> None:
    seen: list[tuple[str, str]] = []
    with pytest.raises(DeskAsleep):
        await _attaching_desk(config, _WindowPage(), seen, status=409).show_window()
    assert seen == [("POST", _ATTACH)]


async def test_the_real_page_builder_sets_the_bots_window_aside(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Unconnected:
        def __init__(self, relay_url: str, token: str) -> None:
            self.relay_url = relay_url

        async def connect(self) -> None:
            return None

    monkeypatch.setattr(client_module, "CdpClient", _Unconnected)
    page = await _connect_page("ws://127.0.0.1:1/desks/x/cdp", "token")
    assert page._window_aside == tuple(BOT_WINDOW_ASIDE_STEPS)
```

Append this to the end of `tests/test_fake_desk.py`:

```python


# -- Live control (Task 7): Show window on Mac --


async def test_show_window_of_a_sleeping_fake_computer_is_asleep():
    desk = FakeDesk(_BOT_ID)
    with pytest.raises(DeskAsleep):
        await desk.show_window()
    assert desk.windows_shown == 0


async def test_show_window_is_counted_while_the_computer_runs():
    desk = FakeDesk(_BOT_ID)
    await desk.start_browser()
    await desk.show_window()
    assert desk.windows_shown == 1


async def test_show_window_of_an_unavailable_desk_is_unavailable():
    with pytest.raises(DeskUnavailable):
        await FakeDesk(_BOT_ID, force_unavailable=True).show_window()
```

Append this to the end of `tests/test_computer_api.py`:

```python


# -- Live control (Task 7): Show window on Mac --


def test_show_window_brings_the_bots_window_up():
    c, bot_id = _client_and_bot()
    c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    r = c.post(f"/api/bots/{bot_id}/window/show", headers=O)
    assert (r.status_code, r.json()) == (200, {"shown": True})
    assert c.app.state.desks.for_bot(bot_id).windows_shown == 1


def test_show_window_of_a_sleeping_computer_is_409_and_never_starts_it():
    c, bot_id = _client_and_bot()
    r = c.post(f"/api/bots/{bot_id}/window/show", headers=O)
    assert (r.status_code, r.json()) == (409, {"detail": "asleep"})
    assert c.get(f"/api/bots/{bot_id}/desk").json()["browser"] == "stopped"


def test_show_window_of_an_unreachable_computer_is_503():
    c, bot_id = _client_and_bot()
    c.app.state.desks.for_bot(bot_id).force_unavailable = True
    r = c.post(f"/api/bots/{bot_id}/window/show", headers=O)
    assert (r.status_code, r.json()) == (503, {"detail": "desk unavailable"})


def test_show_window_needs_an_origin_and_an_owned_bot():
    c, bot_id = _client_and_bot()
    assert c.post(f"/api/bots/{bot_id}/window/show").status_code == 403
    assert c.post("/api/bots/not-a-bot/window/show", headers=O).status_code == 404
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_live.py tests/test_keeper_client.py tests/test_fake_desk.py tests/test_computer_api.py -q`
Expected: FAIL.
- `tests/test_keeper_client.py`: a collection error, `ImportError: cannot import name 'BOT_WINDOW_ASIDE_STEPS' from 'roost.constants'`.
- `tests/test_cdp_live.py`: the new tests fail with `TypeError: DeskBrowserPage.__init__() got an unexpected keyword argument 'window_aside'` and `AttributeError: ... 'set_window'`.
- `tests/test_fake_desk.py`: `AttributeError: 'FakeDesk' object has no attribute 'show_window'`.
- `tests/test_computer_api.py`: the route tests get 404 or 405.

- [ ] **Step 4: Add the window constants**

In `roost/constants.py`, replace these import lines:

```python
from decimal import Decimal
from pathlib import Path
```

with:

```python
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
```

Then append this to the very end of `roost/constants.py`, for the variant `minimise`:

```python

# Task 7 — roost/desk/browser.py, roost/desk/client.py: bot windows out of the way (design L3). Each step
# is one Browser.setWindowBounds "bounds". The variant is the one the Task 1 spike recorded in
# docs/plans/2026-10-15-roost-live-control.md ("Design decision — bot windows (L3)").
BOT_WINDOW_FAR_AWAY = 100000            # a window moved here is pushed to the screen's far corner
BOT_WINDOW_SHOWN_LEFT = 80
BOT_WINDOW_SHOWN_TOP = 60
BOT_WINDOW_ASIDE_STEPS = (MappingProxyType({"windowState": "minimized"}),)
BOT_WINDOW_SHOW_STEPS = (MappingProxyType({"windowState": "normal"}),)
```

If the recorded variant is `behind`, write these two lines instead of the last two:

```python
BOT_WINDOW_ASIDE_STEPS = (MappingProxyType({"left": BOT_WINDOW_FAR_AWAY, "top": BOT_WINDOW_FAR_AWAY}),)
BOT_WINDOW_SHOW_STEPS = (
    MappingProxyType({"windowState": "normal"}),
    MappingProxyType({"left": BOT_WINDOW_SHOWN_LEFT, "top": BOT_WINDOW_SHOWN_TOP}),
)
```

If it is `leave`, write these two lines instead:

```python
BOT_WINDOW_ASIDE_STEPS: tuple = ()
BOT_WINDOW_SHOW_STEPS = (MappingProxyType({"windowState": "normal"}),)
```

- [ ] **Step 5: The window on the page (`roost/desk/browser.py`)**

1. Imports. Replace these lines:

```python
from dataclasses import replace
from typing import Any
```

with:

```python
from dataclasses import replace
from typing import Any, Mapping, Sequence
```

2. The aside steps. Replace these lines:

```python
    def __init__(self, client: CdpClient) -> None:
        self._client = client
```

with:

```python
    def __init__(self, client: CdpClient, *, window_aside: Sequence[Mapping[str, Any]] = ()) -> None:
        self._client = client
        # Live control (L3): the Browser.setWindowBounds steps that put the bot's window out of the way
        # once its tab exists. The real page builder (client._connect_page) passes BOT_WINDOW_ASIDE_STEPS.
        self._window_aside = tuple(window_aside)
```

3. Set aside once the tab exists. Replace these lines:

```python
        tree = await self._client.send("Page.getFrameTree", session_id=session_id)

        self._target_id = target_id
```

with:

```python
        tree = await self._client.send("Page.getFrameTree", session_id=session_id)
        await self._set_aside(target_id)

        self._target_id = target_id
```

4. The window calls. Replace these lines:

```python
    async def live_target(self) -> str:
```

with:

```python
    async def set_window(self, steps: Sequence[Mapping[str, Any]], *, activate: bool = False) -> None:
        """Show window on Mac (L3): change the bot's window by ``steps``, then, with ``activate``, bring
        its page to the front. Never opens a tab: with no page open, ``DeskAsleep``."""
        target_id = await self.live_target()
        await self._apply_window(target_id, steps)
        if activate:
            await self._client.send("Target.activateTarget", {"targetId": target_id})

    async def _set_aside(self, target_id: str) -> None:
        """The bot's window steps out of the way once its tab exists. A window that can't be moved is
        only a warning: the bot's page still opens."""
        if not self._window_aside:
            return
        try:
            await self._apply_window(target_id, self._window_aside)
        except CdpReplyError as exc:
            logger.warning("The bot's window could not be set aside: %s", exc)

    async def _apply_window(self, target_id: str, steps: Sequence[Mapping[str, Any]]) -> None:
        if not steps:
            return
        window = await self._client.send("Browser.getWindowForTarget", {"targetId": target_id})
        window_id = window.get("result", {}).get("windowId")
        if not isinstance(window_id, int):
            raise CdpReplyError("Browser.getWindowForTarget gave no window for the bot's page")
        for bounds in steps:
            await self._client.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": dict(bounds)})

    async def live_target(self) -> str:
```

- [ ] **Step 6: The desks (`roost/desk/__init__.py`, `roost/desk/client.py`, `roost/desk/fake.py`)**

In `roost/desk/__init__.py`, replace these lines:

```python
    async def screenshot(self) -> bytes: ...
    async def live_view(self) -> LiveView: ...
```

with:

```python
    async def screenshot(self) -> bytes: ...
    async def live_view(self) -> LiveView: ...
    async def show_window(self) -> None: ...
```

In `roost/desk/client.py`:

1. Imports. Replace this line:

```python
from roost.constants import EXEC_TIMEOUT_S, KEEPER_EXEC_REQUEST_TIMEOUT_S, KEEPER_RETIRE_REQUEST_TIMEOUT_S
```

with:

```python
from roost.constants import (
    BOT_WINDOW_ASIDE_STEPS, BOT_WINDOW_SHOW_STEPS, EXEC_TIMEOUT_S, KEEPER_EXEC_REQUEST_TIMEOUT_S,
    KEEPER_RETIRE_REQUEST_TIMEOUT_S,
)
```

2. The real page builder. Replace this line:

```python
    return DeskBrowserPage(cdp_client)
```

with:

```python
    return DeskBrowserPage(cdp_client, window_aside=BOT_WINDOW_ASIDE_STEPS)
```

3. `show_window`. Replace these lines:

```python
    async def live_view(self) -> LiveView:
```

with:

```python
    async def show_window(self) -> None:
        """Show window on Mac (L3): restore the bot's window and bring its page to the front. Like a
        screenshot it never starts the browser (``DeskAsleep``) and never opens a tab."""
        await self._view(lambda page: page.set_window(BOT_WINDOW_SHOW_STEPS, activate=True))

    async def live_view(self) -> LiveView:
```

In `roost/desk/fake.py`:

1. Replace these lines:

```python
        self.cdp = FakeCdp(self._live_page_url, FAKE_JPEG)
```

with:

```python
        self.cdp = FakeCdp(self._live_page_url, FAKE_JPEG)
        self.windows_shown = 0
```

2. Replace these lines:

```python
    def _live_page_url(self) -> str:
```

with:

```python
    async def show_window(self) -> None:
        """Show window on Mac: counted, since the fake browser has no window. Never starts it."""
        self._require_available()
        if self._browser != "running":
            raise DeskAsleep(f"the browser of bot {self.bot_id} is closed")
        self.windows_shown = self.windows_shown + 1

    def _live_page_url(self) -> str:
```

- [ ] **Step 7: The route (`roost/gateway/routes/desk.py`)**

Replace these lines:

```python
@desk_router.get("/api/bots/{bot_id}/control")
async def get_control(bot_id: str, request: Request, user: CurrentUser):
```

with:

```python
@desk_router.post("/api/bots/{bot_id}/window/show", dependencies=[RequireOrigin])
async def show_window(bot_id: str, request: Request, user: CurrentUser):
    """Show window on Mac (live control, L3): the bot's own window, restored and in front. Never starts a browser."""
    await _owned_bot_or_404(request, user, bot_id)
    try:
        await request.app.state.desks.for_bot(bot_id).show_window()
    except DeskAsleep:
        raise HTTPException(status_code=409, detail="asleep")
    except DeskUnavailable:
        raise _unavailable()
    return {"shown": True}


@desk_router.get("/api/bots/{bot_id}/control")
async def get_control(bot_id: str, request: Request, user: CurrentUser):
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_client.py tests/test_cdp_live.py tests/test_keeper_client.py tests/test_fake_desk.py tests/test_computer_api.py tests/test_desk_api.py tests/test_live_api.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/constants.py roost/desk/__init__.py roost/desk/browser.py roost/desk/client.py roost/desk/fake.py \
  roost/gateway/routes/desk.py tests/test_cdp_client.py tests/test_cdp_live.py tests/test_keeper_client.py \
  tests/test_fake_desk.py tests/test_computer_api.py
git commit -m "feat: bot windows step out of the way, and Show window on Mac brings one back"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the eleven files is listed.

---

### Task 8: Typed values never reach the bot's `read_page`

Design §2 "Secrets": the model's `read_page` text is built from the accessibility tree's readable roles, which exclude text boxes. But Chromium also exposes a box's value as a `StaticText` (and `InlineTextBox`) **inside** the box, and `StaticText` is a readable role. So after the user types into a sign-in form on the live screen, the bot's next `read_page` would contain the email and the password.
- **The fix.** `_extract_readable_lines` skips every node inside a `textbox`, `searchbox`, `combobox` or `spinbutton`, at any depth.
- **"Inside" is found both ways Chromium reports it**, through a node's `parentId` and through its parent's `childIds`. The walk up is cycle-safe.
- **What stays.** Labels and text outside the boxes ("Email", "Password", the heading, the button) are kept, so the bot still sees what the page is.
- **The test** uses a realistic tree: a sign-in form after the user typed an email and a password, plus a search box, a spin button and a combo box, each holding a value as a child `StaticText`.

**Files:**
- Modify: `roost/desk/browser.py` (`_FIELD_ROLES`, `_node_id`, `_role`, `_parents`, `_inside_fields`, `_has_ancestor_in`, `_extract_readable_lines`; round A touched this file)
- Test: `tests/test_cdp_client.py` (the fake server's tree can be swapped); `tests/test_cdp_live.py` (an import, and tests appended)

**Interfaces:**
- Consumes: `_build_page_text`, `_extract_readable_lines`, `_READABLE_ROLES`, `DeskBrowserPage.read_page` as they are today; `_FakeCdpServer`.
- Produces: `read_page` text that never contains a value typed into a box. No public name changes.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

In `tests/test_cdp_client.py`, let a test swap the fake server's accessibility tree. Replace these lines:

```python
        self._oversized_ax_tree = oversized_ax_tree
```

with:

```python
        self._oversized_ax_tree = oversized_ax_tree
        self._ax_nodes: list[dict[str, Any]] = _AX_NODES     # live control (Task 8): a test may swap the tree
```

Then replace this line:

```python
            return {"nodes": _OVERSIZED_AX_NODES if self._oversized_ax_tree else _AX_NODES}
```

with:

```python
            return {"nodes": _OVERSIZED_AX_NODES if self._oversized_ax_tree else self._ax_nodes}
```

In `tests/test_cdp_live.py`, replace this import line:

```python
from roost.desk.browser import DeskBrowserPage
```

with:

```python
from roost.desk.browser import DeskBrowserPage, _build_page_text
```

Then append this to the end of `tests/test_cdp_live.py`:

```python


# -- Task 8: what the user typed never reaches the bot --

_TYPED_EMAIL = "ana.private@example.com"
_TYPED_PASSWORD = "hunter2-correct-horse"
_TYPED_SEARCH = "my bank statement"
_TYPED_CODE = "804512"
_TYPED_COUNTRY = "Liechtenstein"


def _ax(node_id: str, role: str, name: str = "", *, parent: str | None = None,
        children: tuple[str, ...] = (), value: str | None = None) -> dict[str, Any]:
    """One node as Accessibility.getFullAXTree reports it."""
    node: dict[str, Any] = {"nodeId": node_id, "ignored": False, "role": {"type": "role", "value": role},
                            "name": {"type": "computedString", "value": name}, "childIds": list(children)}
    if parent is not None:
        node["parentId"] = parent
    if value is not None:
        node["value"] = {"type": "string", "value": value}
    return node


# A sign-in form after the user typed into it on the live screen. Chromium shows each box's value
# again as a StaticText (and an InlineTextBox) inside the box. Node 7 is linked to its parent only by
# the parent's childIds, and node 10 only by its own parentId: both ways must be followed.
_TYPED_FORM_AX_NODES = [
    _ax("1", "RootWebArea", "Sign in", children=("2", "3", "4", "8", "11", "12", "16", "19", "22", "23")),
    _ax("2", "heading", "Sign in to Shop", parent="1"),
    _ax("3", "StaticText", "Email", parent="1"),
    _ax("4", "textbox", "Email", parent="1", children=("5",), value=_TYPED_EMAIL),
    _ax("5", "generic", parent="4", children=("6",)),
    _ax("6", "StaticText", _TYPED_EMAIL, parent="5", children=("7",)),
    {"nodeId": "7", "role": {"value": "InlineTextBox"}, "name": {"value": _TYPED_EMAIL}},
    _ax("8", "textbox", "Password", parent="1", children=("9",), value="•••••••••••••••••••••"),
    _ax("9", "generic", parent="8"),
    _ax("10", "StaticText", _TYPED_PASSWORD, parent="9"),
    _ax("11", "StaticText", "Password", parent="1"),
    _ax("12", "searchbox", "Search orders", parent="1", children=("13",), value=_TYPED_SEARCH),
    _ax("13", "generic", parent="12", children=("14",)),
    _ax("14", "StaticText", _TYPED_SEARCH, parent="13", children=("15",)),
    _ax("15", "InlineTextBox", _TYPED_SEARCH, parent="14"),
    _ax("16", "spinbutton", "Code", parent="1", children=("17",), value=_TYPED_CODE),
    _ax("17", "StaticText", _TYPED_CODE, parent="16"),
    _ax("19", "combobox", "Country", parent="1", children=("20",), value=_TYPED_COUNTRY),
    _ax("20", "StaticText", _TYPED_COUNTRY, parent="19"),
    _ax("22", "button", "Continue", parent="1"),
    _ax("23", "paragraph", "Forgot your password?", parent="1"),
]
_TYPED = (_TYPED_EMAIL, _TYPED_PASSWORD, _TYPED_SEARCH, _TYPED_CODE, _TYPED_COUNTRY)


def test_the_page_text_never_includes_what_was_typed_into_a_box() -> None:
    text, truncated = _build_page_text(_TYPED_FORM_AX_NODES)
    assert [typed for typed in _TYPED if typed in text] == []
    assert text == "Sign in to Shop\nEmail\nPassword\nContinue\nForgot your password?"
    assert truncated is False


async def test_a_typed_email_and_password_never_reach_read_page(
    fake_server: _FakeCdpServer, connected_client: CdpClient
) -> None:
    fake_server._ax_nodes = _TYPED_FORM_AX_NODES
    page = await DeskBrowserPage(connected_client).read_page()
    assert _TYPED_EMAIL not in page.text and _TYPED_PASSWORD not in page.text
    assert "Sign in to Shop" in page.text


def test_text_after_a_box_is_still_read() -> None:
    nodes = [
        _ax("1", "RootWebArea", children=("2", "4")),
        _ax("2", "textbox", "Note", parent="1", children=("3",)),
        _ax("3", "StaticText", "typed note", parent="2"),
        _ax("4", "paragraph", "Saved.", parent="1"),
    ]
    assert _build_page_text(nodes) == ("Saved.", False)


def test_a_tree_whose_parents_loop_never_hangs() -> None:
    nodes = [
        _ax("1", "paragraph", "One", parent="2"),
        _ax("2", "paragraph", "Two", parent="1"),
        _ax("3", "textbox", "Search"),                         # a box, so the walk up runs
    ]
    assert _build_page_text(nodes) == ("One\nTwo", False)
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_live.py -q -k "typed or after_a_box or loop"`
Expected: FAIL. `test_the_page_text_never_includes_what_was_typed_into_a_box` lists the five typed values, and `test_a_typed_email_and_password_never_reach_read_page` finds the email in the text. `test_text_after_a_box_is_still_read` fails (the text holds "typed note"). `test_a_tree_whose_parents_loop_never_hangs` already passes.

- [ ] **Step 4: Skip everything inside a box (`roost/desk/browser.py`)**

1. The roles. Replace these lines:

```python
_READABLE_ROLES = frozenset({"heading", "link", "StaticText", "paragraph", "listitem", "cell", "button"})
```

with:

```python
_READABLE_ROLES = frozenset({"heading", "link", "StaticText", "paragraph", "listitem", "cell", "button"})

# Live control (design §2 "Secrets"): what the user types into a box must never reach the bot. Chromium
# shows a box's value again as text inside it (a StaticText child), so every node inside one is skipped.
_FIELD_ROLES = frozenset({"textbox", "searchbox", "combobox", "spinbutton"})
```

2. The walk. Replace these lines:

```python
def _extract_readable_lines(nodes: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for node in nodes:
        if node.get("ignored"):
            continue
        role = (node.get("role") or {}).get("value")
        if role not in _READABLE_ROLES:
            continue
```

with:

```python
def _node_id(node: dict[str, Any]) -> str | None:
    found = node.get("nodeId")
    return None if found is None else str(found)


def _role(node: dict[str, Any]) -> str | None:
    return (node.get("role") or {}).get("value")


def _parents(nodes: list[dict[str, Any]]) -> dict[str, str]:
    """Each node's parent, from its own ``parentId`` and from its parent's ``childIds`` (Chromium sends both)."""
    parents: dict[str, str] = {}
    for node in nodes:
        node_id = _node_id(node)
        if node_id is None:
            continue
        for child in node.get("childIds") or ():
            parents.setdefault(str(child), node_id)
        if node.get("parentId") is not None:
            parents[node_id] = str(node["parentId"])
    return parents


def _has_ancestor_in(node_id: str, parents: dict[str, str], fields: frozenset[str]) -> bool:
    """Whether a box is above ``node_id``. A loop in the parents (a broken tree) ends the walk."""
    seen: set[str] = set()
    current = parents.get(node_id)
    while current is not None and current not in seen:
        if current in fields:
            return True
        seen.add(current)
        current = parents.get(current)
    return False


def _inside_fields(nodes: list[dict[str, Any]]) -> frozenset[str]:
    """Every node inside a text box, search box, combo box or spin button, at any depth."""
    fields = frozenset(node_id for node in nodes
                       if (node_id := _node_id(node)) is not None and _role(node) in _FIELD_ROLES)
    if not fields:
        return frozenset()
    parents = _parents(nodes)
    return frozenset(node_id for node_id in parents if _has_ancestor_in(node_id, parents, fields))


def _extract_readable_lines(nodes: list[dict[str, Any]]) -> list[str]:
    hidden = _inside_fields(nodes)
    lines: list[str] = []
    for node in nodes:
        if node.get("ignored") or _node_id(node) in hidden:
            continue
        role = _role(node)
        if role not in _READABLE_ROLES:
            continue
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_cdp_client.py tests/test_cdp_live.py tests/test_stuck_detector.py tests/test_fake_desk.py -q`
Expected: PASS. Every earlier page-text test (`_AX_NODES` has no node ids) reads the same as before.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/desk/browser.py tests/test_cdp_client.py tests/test_cdp_live.py
git commit -m "fix: read_page skips everything inside a text box, so typed values never reach a bot"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the three files is listed.

---

### Task 9: Vault: site logins — schema v14, models and store

Design §2 "Vault: site logins", L2, and D2 above:
- **Schema v14** adds `site_logins`, one row per bot and site. `host` and `label` are `enc:v2` (AAD `site_logins:host`, `site_logins:label`). `host_key` = HMAC(dek, normalised host) is the unique key, so one site has one row without the host ever being stored in plaintext (D2). A bot's rows go with it (`ON DELETE CASCADE`). There is no password column, and none is ever added.
- **`SiteLoginStore`:**
  - `remember` upserts: a new label for the same site replaces the old one and keeps `created_at`. The insert only yields a row for one of the user's own bots, so another user's bot is a `ValueError` and nothing is written.
  - `list_for_bot` gives the bot's rows newest first, at most `limit`.
  - `forget` deletes one row of the user's bot.
  - Every query has `user_id` in its `WHERE`.
- **`roost/vault/models.py`:**
  - The dataclasses and `SiteLoginOut`.
  - `NoSite`, and its user-facing text.
  - `clean_label`: runs of white space become one space, empty means none, and a control character is refused, so a label can never break the bot's prompt line.
  - `AccountLabel`: the pydantic type every route uses for the optional `account`, at most `SITE_LOGIN_LABEL_MAX_CHARS`.
  - `GiveBackIn`, `normalize_host`, and `signed_in_line` ("I signed in on {host} as {label}.").
- **The fixture first.** `tests/fixtures/schema_v13.sql` is frozen **before** `migrations.py` changes, the way the projects hub froze v12.

**Files:**
- Create:
  - `tests/fixtures/schema_v13.sql` (generated in Step 2a, before `migrations.py` changes)
  - `tests/test_migrations_v13.py`, `tests/test_site_login_store.py`
  - `roost/vault/__init__.py`, `roost/vault/models.py`, `roost/vault/store.py`
- Modify: `roost/db/migrations.py` (`_SITE_LOGINS`, `Migration(14, "site logins", ...)`), `roost/constants.py` (append the Vault constants)

**Interfaces:**
- Consumes:
  - `encrypt`, `decrypt_field`, `user_aad` (`roost/crypto/encryption.py`), `get_user_dek`, `db_session`, `RoostConfig`.
  - `tests/test_migrations_v12.py`'s `_ROWS` and `_EXPECTED`, and `tests/test_migrations_v8.py`'s `_NOW`; `team_helpers.make_bot`.
- Produces:
  - Schema v14.
  - From `roost.vault.models`: `SiteLogin`, `SignIn`, `SiteLoginOut`, `site_login_out`, `NoSite`, `NO_SITE_TEXT`, `clean_label`, `AccountLabel`, `GiveBackIn`, `normalize_host`, `signed_in_line`.
  - From `roost.vault.store`: `SiteLoginStore` (`remember`, `list_for_bot`, `forget`) and `host_key`.
  - The constants `SITE_LOGIN_LABEL_MAX_CHARS`, `SITE_LOGIN_LIST_LIMIT` and `SITE_LOGINS_IN_PROMPT`.

- [ ] **Step 1: Path guard, and check the schema is still v13**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test ! -e tests/fixtures/schema_v13.sql && grep -n "Migration(1[34]," roost/db/migrations.py`
Expected: one line, `    Migration(13, "projects hub", (`. If `schema_v13.sql` exists or `Migration(14,` shows up, stop: this task already ran, or another one took v14.

- [ ] **Step 2: Freeze schema v13, then write the failing tests**

**2a. Freeze schema v13.** This must run **before** `roost/db/migrations.py` changes. The script builds a throwaway database in `$TMPDIR`, never in `~/Roost/data`:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && uv run python - <<'PY'
import asyncio, sqlite3, tempfile
from pathlib import Path
import aiosqlite
from roost.db.migrations import apply_migrations, latest_version

assert latest_version() == 13, f"expected schema v13 before live control, got {latest_version()}"

async def build(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(Path("roost/db/schema.sql").read_text())
        await db.commit()
        await apply_migrations(db)

path = Path(tempfile.mkdtemp(prefix="roost-v13-")) / "v13.db"
asyncio.run(build(path))
con = sqlite3.connect(path)
rows = con.execute(
    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
).fetchall()
con.close()
header = ("-- Roost schema version 13, frozen by live-control Task 9 (schema.sql + migrations 1-13).\n"
          "-- The live ~/Roost/data/roost.db runs this schema at the start of live control. Never edit.\n\n")
Path("tests/fixtures/schema_v13.sql").write_text(header + ";\n\n".join(r[0] for r in rows) + ";\n")
print("tables/indexes:", len(rows))
PY
grep -c "CREATE" tests/fixtures/schema_v13.sql        # 45
grep -c "site_logins" tests/fixtures/schema_v13.sql   # 0
grep -c "topup_id" tests/fixtures/schema_v13.sql      # 1
```

Expected: the script prints `tables/indexes: 45`, and the three greps print `45`, `0` and `1`. The file starts with exactly these lines:

```sql
-- Roost schema version 13, frozen by live-control Task 9 (schema.sql + migrations 1-13).
-- The live ~/Roost/data/roost.db runs this schema at the start of live control. Never edit.

CREATE TABLE users (
```

**2b. The migration test from v13, with rows.**

Create `tests/test_migrations_v13.py`:

```python
"""Migrating from the schema the live gateway runs at the start of live control (version 13).

``tests/fixtures/schema_v13.sql`` was frozen by live-control Task 9. Rows go in every table the user's
account uses today (the v12 test's rows, which carry a Stuck card). v14 only adds Vault: site logins."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from roost.config import load_config
from roost.db.connection import get_db_path, init_db
from roost.db.migrations import latest_version
from test_migrations_v12 import _EXPECTED, _ROWS
from test_migrations_v8 import _NOW

_V13_SCHEMA = Path(__file__).parent / "fixtures" / "schema_v13.sql"
_SITE_LOGIN_COLUMNS = {"id", "user_id", "bot_id", "host", "host_key", "label", "created_at", "updated_at"}
_NEW_INDEXES = {"idx_site_logins_one", "idx_site_logins_bot"}
_SITE_LOGIN = ("INSERT INTO site_logins (id, user_id, bot_id, host, host_key, label, created_at, updated_at) "
               f"VALUES (?, 'u1', 'b2', 'enc:h', 'hk1', 'enc:l', '{_NOW}', '{_NOW}')")


def _query(db_path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _version(db_path: Path) -> int:
    return _query(db_path, "PRAGMA user_version")[0][0]


def _counts(db_path: Path) -> dict[str, int]:
    return {table: _query(db_path, f"SELECT COUNT(*) FROM {table}")[0][0] for table in _EXPECTED}


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


@pytest.fixture
def seeded_v13():
    cfg = load_config()
    db_path = get_db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_V13_SCHEMA.read_text())
        con.execute("PRAGMA user_version = 13")
        for statement in _ROWS:
            con.execute(statement)
        con.commit()
    finally:
        con.close()
    return cfg, db_path


async def test_v13_database_migrates_to_latest_and_keeps_every_row(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    assert latest_version() >= 14
    assert _version(db_path) == latest_version()
    assert _counts(db_path) == _EXPECTED


async def test_v13_database_gains_site_logins_and_its_indexes(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    assert {row[1] for row in _query(db_path, "PRAGMA table_info(site_logins)")} == _SITE_LOGIN_COLUMNS
    indexes = {row[0] for row in _query(db_path, "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert _NEW_INDEXES <= indexes
    assert _query(db_path, "SELECT COUNT(*) FROM site_logins") == [(0,)]


async def test_one_bot_has_one_row_per_site(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute(_SITE_LOGIN, ("s1",))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(_SITE_LOGIN, ("s2",))
    finally:
        con.close()


async def test_a_bots_site_logins_go_with_it(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    con = _connect(db_path)
    try:
        con.execute(_SITE_LOGIN, ("s1",))
        con.execute("DELETE FROM bots WHERE id = 'b2'")
        assert con.execute("SELECT COUNT(*) FROM site_logins").fetchone() == (0,)
    finally:
        con.close()


async def test_migrating_v13_twice_is_a_no_op_and_backs_up_once(seeded_v13):
    cfg, db_path = seeded_v13
    await init_db(cfg)
    await init_db(cfg)
    assert _counts(db_path) == _EXPECTED
    [backup] = sorted(db_path.parent.glob(f"roost.db.pre-v{latest_version()}-*.bak"))
    assert _version(backup) == 13
```

**2c. The store and models test.**

Create `tests/test_site_login_store.py`:

```python
"""``SiteLoginStore`` and the Vault's models (live control, Task 9; schema v14): one encrypted row per
bot and site, the newest first, and an account label that is tidied and capped."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import SITE_LOGIN_LABEL_MAX_CHARS
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.vault.models import GiveBackIn, SignIn, SiteLoginOut, clean_label, signed_in_line, site_login_out
from roost.vault.store import SiteLoginStore
from team_helpers import make_bot

PASSWORD = "pw-123456"


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def alice(cfg):
    return await register_user(cfg, "alice", PASSWORD)


@pytest.fixture
async def helper(cfg, alice):
    return await make_bot(cfg, alice.id, "Helper")


async def _raw(cfg) -> list[dict]:
    async with db_session(cfg) as db:
        return [dict(row) for row in await (await db.execute("SELECT * FROM site_logins")).fetchall()]


async def test_a_site_login_is_kept_and_listed(cfg, alice, helper):
    store = SiteLoginStore(cfg)
    kept = await store.remember(alice.id, SignIn(bot_id=helper.id, host="github.com", label="work email"))
    assert (kept.user_id, kept.bot_id, kept.host, kept.label) == (alice.id, helper.id, "github.com", "work email")
    assert await store.list_for_bot(alice.id, helper.id) == (kept,)


async def test_the_site_and_the_account_are_encrypted_at_rest(cfg, alice, helper):
    await SiteLoginStore(cfg).remember(alice.id, SignIn(helper.id, "github.com", "work email"))
    [row] = await _raw(cfg)
    assert row["host"].startswith("enc:v2") and row["label"].startswith("enc:v2")
    assert len(row["host_key"]) == 64 and "github" not in row["host_key"]
    assert "github" not in str(row) and "work email" not in str(row)


async def test_a_new_account_for_the_same_site_replaces_the_old_one(cfg, alice, helper):
    store = SiteLoginStore(cfg)
    first = await store.remember(alice.id, SignIn(helper.id, "github.com", "work email"))
    second = await store.remember(alice.id, SignIn(helper.id, "GitHub.com.", "personal"))
    assert (second.id, second.created_at, second.host, second.label) == (first.id, first.created_at, "github.com", "personal")
    assert second.updated_at >= first.updated_at
    assert len(await _raw(cfg)) == 1


async def test_each_bot_keeps_its_own_and_the_newest_comes_first(cfg, alice, helper):
    scout = await make_bot(cfg, alice.id, "Scout")
    store = SiteLoginStore(cfg)
    await store.remember(alice.id, SignIn(helper.id, "github.com", "work email"))
    await store.remember(alice.id, SignIn(helper.id, "shop.example", "ana@home"))
    await store.remember(alice.id, SignIn(scout.id, "github.com", "scout account"))
    assert [login.host for login in await store.list_for_bot(alice.id, helper.id)] == ["shop.example", "github.com"]
    assert [login.label for login in await store.list_for_bot(alice.id, scout.id)] == ["scout account"]
    assert [login.host for login in await store.list_for_bot(alice.id, helper.id, limit=1)] == ["shop.example"]


async def test_another_users_bot_gets_no_row_and_reads_as_none(cfg, alice, helper):
    bob = await register_user(cfg, "bob", PASSWORD)
    store = SiteLoginStore(cfg)
    with pytest.raises(ValueError):
        await store.remember(bob.id, SignIn(helper.id, "github.com", "bob's account"))
    await store.remember(alice.id, SignIn(helper.id, "github.com", "work email"))
    assert await store.list_for_bot(bob.id, helper.id) == ()
    assert len(await _raw(cfg)) == 1


async def test_forget_removes_only_your_own_row(cfg, alice, helper):
    bob = await register_user(cfg, "bob", PASSWORD)
    store = SiteLoginStore(cfg)
    kept = await store.remember(alice.id, SignIn(helper.id, "github.com", "work email"))
    assert await store.forget(bob.id, helper.id, kept.id) is False
    assert await store.forget(alice.id, "another-bot", kept.id) is False
    assert await store.forget(alice.id, helper.id, kept.id) is True
    assert await store.forget(alice.id, helper.id, kept.id) is False
    assert await store.list_for_bot(alice.id, helper.id) == ()


async def test_retiring_a_bot_removes_its_site_logins(cfg, alice, helper):
    await SiteLoginStore(cfg).remember(alice.id, SignIn(helper.id, "github.com", "work email"))
    assert await BotStore(cfg).delete(alice.id, helper.id) is True
    assert await _raw(cfg) == []


@pytest.mark.parametrize("sign_in", [SignIn("b", "", "work email"), SignIn("b", " . ", "work email"),
                                     SignIn("b", "github.com", "")])
async def test_a_site_login_needs_a_site_and_an_account(cfg, alice, sign_in):
    with pytest.raises(ValueError):
        await SiteLoginStore(cfg).remember(alice.id, sign_in)


async def test_the_wire_shape_has_no_user_id(cfg, alice, helper):
    kept = await SiteLoginStore(cfg).remember(alice.id, SignIn(helper.id, "github.com", "work email"))
    assert site_login_out(kept) == SiteLoginOut(id=kept.id, bot_id=helper.id, host="github.com", label="work email",
                                                created_at=kept.created_at, updated_at=kept.updated_at)
    assert "user_id" not in SiteLoginOut.model_fields


# -- the account label --


@pytest.mark.parametrize(("given", "kept"), [
    ("work email", "work email"), ("  work \t email \n", "work email"), ("ana@example.com", "ana@example.com"),
    ("", None), ("   ", None), (None, None),
])
def test_an_account_label_is_tidied(given, kept):
    assert clean_label(given) == kept


def test_an_account_label_never_holds_a_control_character():
    with pytest.raises(ValueError):
        clean_label("work\x00email")
    with pytest.raises(ValidationError):
        GiveBackIn(account="work\x1bemail")


def test_an_account_label_has_a_limit_and_nothing_else_comes_with_it():
    assert GiveBackIn(account="x" * SITE_LOGIN_LABEL_MAX_CHARS).account == "x" * SITE_LOGIN_LABEL_MAX_CHARS
    assert GiveBackIn().account is None
    with pytest.raises(ValidationError):
        GiveBackIn(account="x" * (SITE_LOGIN_LABEL_MAX_CHARS + 1))
    with pytest.raises(ValidationError):
        GiveBackIn.model_validate({"account": "work email", "password": "hunter2"})


def test_the_bot_is_told_the_account_in_the_users_own_words():
    assert signed_in_line("github.com", "work email") == "I signed in on github.com as work email."
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations_v13.py tests/test_site_login_store.py -q`
Expected: FAIL.
- `tests/test_migrations_v13.py`: `assert latest_version() >= 14` fails (it is 13), and the `site_logins` tests fail with `sqlite3.OperationalError: no such table: site_logins`.
- `tests/test_site_login_store.py`: a collection error, `ImportError: cannot import name 'SITE_LOGIN_LABEL_MAX_CHARS' from 'roost.constants'`.

- [ ] **Step 4: Add the Vault constants**

Append this to the very end of `roost/constants.py`:

```python

# Tasks 9–11 — roost/vault/: Vault: site logins.
SITE_LOGIN_LABEL_MAX_CHARS = 100        # "Which account did you use?"
SITE_LOGIN_LIST_LIMIT = 50              # GET /api/bots/{id}/site-logins
SITE_LOGINS_IN_PROMPT = 10              # the newest rows a bot's prompt names
```

- [ ] **Step 5: Schema v14 (`roost/db/migrations.py`)**

Replace these lines:

```python
    answer_item_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
)"""
```

with:

```python
    answer_item_id TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
)"""

# Live control: Vault: site logins. One row per (user, bot, site): which account the user said they used
# when they gave the bot's computer back. host and label are enc:v2 under site_logins:<column>; host_key
# is HMAC(dek, normalised host), so a site has one row without the host ever being stored in plaintext.
# Passwords are never stored. A bot's rows go with it (CASCADE).
_SITE_LOGINS = """
CREATE TABLE IF NOT EXISTS site_logins (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    host TEXT NOT NULL,                -- enc:v2, AAD site_logins:host
    host_key TEXT NOT NULL,            -- HMAC(dek, normalised host): the unique key, never the host
    label TEXT NOT NULL,               -- enc:v2, AAD site_logins:label
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""
```

Then replace these lines:

```python
        "CREATE INDEX IF NOT EXISTS idx_documents_user_project ON documents(user_id, project_id)",
    )),
)
```

with:

```python
        "CREATE INDEX IF NOT EXISTS idx_documents_user_project ON documents(user_id, project_id)",
    )),
    Migration(14, "site logins", (
        _SITE_LOGINS,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_site_logins_one ON site_logins(user_id, bot_id, host_key)",
        "CREATE INDEX IF NOT EXISTS idx_site_logins_bot ON site_logins(user_id, bot_id, updated_at)",
    )),
)
```

- [ ] **Step 6: The models (`roost/vault/__init__.py`, `roost/vault/models.py`)**

Create `roost/vault/__init__.py`:

```python
"""Vault: site logins (live control): which account the user used on a site, kept per bot."""
```

Create `roost/vault/models.py`:

```python
"""Vault: site logins (live control, design §2, L2): which account the user says they used on a site,
kept per bot so the bot remembers who it is signed in as. Only that label is kept, never a password
or anything else typed on the live screen.

The label is written by the user, so it is trusted text. It is the only thing the user typed that a
bot ever gets: in its prompt line (``roost/talk/instructions.py``) and in "I signed in on {host} as
{label}." (``signed_in_line``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from roost.constants import SITE_LOGIN_LABEL_MAX_CHARS

NO_SITE_TEXT = "Roost can't tell which site that account is for. Give it back without one."


@dataclass(frozen=True)
class SiteLogin:
    id: str
    user_id: str
    bot_id: str
    host: str
    label: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SignIn:
    """One "I used this account on this site", before it is kept."""

    bot_id: str
    host: str
    label: str


class SiteLoginOut(BaseModel):
    """The wire shape: ``GET /api/bots/{id}/site-logins``. No ``user_id``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    bot_id: str
    host: str
    label: str
    created_at: str
    updated_at: str


def site_login_out(login: SiteLogin) -> SiteLoginOut:
    return SiteLoginOut(id=login.id, bot_id=login.bot_id, host=login.host, label=login.label,
                        created_at=login.created_at, updated_at=login.updated_at)


class NoSite(Exception):
    """An account was given, but no site is known to keep it for: the Stuck card has no address and the
    bot's page shows none (D4). The routes answer 400 ``NO_SITE_TEXT``, and nothing changes."""


def clean_label(value: str | None) -> str | None:
    """The account label as kept: runs of white space become one space, and empty means none. A control
    character is refused, so a label can never break the bot's prompt line."""
    if value is None:
        return None
    if any(not character.isprintable() and not character.isspace() for character in value):
        raise ValueError("an account name can't hold control characters")
    cleaned = " ".join(value.split())
    return cleaned or None


# The optional "Which account did you use?" on every Give it back.
AccountLabel = Annotated[str | None, Field(max_length=SITE_LOGIN_LABEL_MAX_CHARS), AfterValidator(clean_label)]


class GiveBackIn(BaseModel):
    """``DELETE /api/bots/{id}/control``'s optional body: which account the user used, if they say."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account: AccountLabel = None


def normalize_host(host: str) -> str:
    return host.strip().rstrip(".").strip().casefold()


def signed_in_line(host: str, label: str) -> str:
    """What the bot is told when the user names the account: the user's own words."""
    return f"I signed in on {host} as {label}."
```

- [ ] **Step 7: The store (`roost/vault/store.py`)**

Create `roost/vault/store.py`:

```python
"""``SiteLoginStore`` — Vault: site logins (live control, Task 9; schema v14).

``host`` and ``label`` are user content, ``enc:v2`` under ``site_logins:<column>``. ``host_key`` is
HMAC(dek, normalised host): the unique index ``(user_id, bot_id, host_key)`` keeps one row per bot and
site without the host ever being stored in plaintext (D2). Every query has ``user_id`` in its
``WHERE``, and a row is only ever written for one of the user's own bots, so another user's bot or row
reads as none. ``remember`` upserts: a new label for the same site replaces the old one and keeps
``created_at``."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

import aiosqlite

from roost.config import RoostConfig
from roost.constants import SITE_LOGIN_LIST_LIMIT
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.db.connection import db_session
from roost.vault.models import SignIn, SiteLogin, normalize_host

_COLUMNS = "id, user_id, bot_id, host, label, created_at, updated_at"
# One row per bot and site. The SELECT yields a row only for one of the user's own bots.
_UPSERT = (
    "INSERT INTO site_logins (id, user_id, bot_id, host, host_key, label, created_at, updated_at) "
    "SELECT ?, ?, ?, ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM bots WHERE id = ? AND user_id = ?) "
    "ON CONFLICT(user_id, bot_id, host_key) DO UPDATE SET "
    "host = excluded.host, label = excluded.label, updated_at = excluded.updated_at "
    f"RETURNING {_COLUMNS}"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aad(user_id: str, column: str) -> bytes:
    return user_aad(user_id, f"site_logins:{column}")


def host_key(dek: bytes, host: str) -> str:
    return hmac.new(dek, normalize_host(host).encode("utf-8"), hashlib.sha256).hexdigest()


def _row_to_login(row: aiosqlite.Row, dek: bytes) -> SiteLogin:
    user_id = row["user_id"]
    return SiteLogin(
        id=row["id"], user_id=user_id, bot_id=row["bot_id"],
        host=decrypt_field(row["host"], dek, _aad(user_id, "host"), fallback="") or "",
        label=decrypt_field(row["label"], dek, _aad(user_id, "label"), fallback="") or "",
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class SiteLoginStore:
    def __init__(self, config: RoostConfig) -> None:
        self._config = config

    async def remember(self, user_id: str, sign_in: SignIn) -> SiteLogin:
        """Keep ``sign_in`` for its bot and site, replacing that site's old label. ``ValueError`` when
        the site or the label is empty, or the bot is not the user's (nothing is written)."""
        host = normalize_host(sign_in.host)
        if not host or not sign_in.label:
            raise ValueError("A site login needs a site and an account name.")
        dek = await get_user_dek(self._config, user_id)
        now = _now_iso()
        params = (
            str(uuid4()), user_id, sign_in.bot_id, encrypt(host, dek, _aad(user_id, "host")), host_key(dek, host),
            encrypt(sign_in.label, dek, _aad(user_id, "label")), now, now, sign_in.bot_id, user_id,
        )
        async with db_session(self._config) as db:
            rows = await (await db.execute(_UPSERT, params)).fetchall()
            await db.commit()
        if not rows:
            raise ValueError("That bot is not one of yours.")
        return _row_to_login(rows[0], dek)

    async def list_for_bot(self, user_id: str, bot_id: str,
                           limit: int = SITE_LOGIN_LIST_LIMIT) -> tuple[SiteLogin, ...]:
        """The bot's site logins, newest first."""
        async with db_session(self._config) as db:
            rows = await (await db.execute(
                f"SELECT {_COLUMNS} FROM site_logins WHERE user_id = ? AND bot_id = ? "
                "ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (user_id, bot_id, limit),
            )).fetchall()
        return await self._logins(user_id, rows)

    async def forget(self, user_id: str, bot_id: str, login_id: str) -> bool:
        """Forget one of the bot's rows. False when it is not the user's bot's row."""
        async with db_session(self._config) as db:
            cursor = await db.execute(
                "DELETE FROM site_logins WHERE id = ? AND user_id = ? AND bot_id = ?", (login_id, user_id, bot_id),
            )
            await db.commit()
        return cursor.rowcount > 0

    async def _logins(self, user_id: str, rows: Sequence[aiosqlite.Row]) -> tuple[SiteLogin, ...]:
        if not rows:
            return ()
        dek = await get_user_dek(self._config, user_id)
        return tuple(_row_to_login(row, dek) for row in rows)
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_migrations_v13.py tests/test_site_login_store.py tests/test_migrations_v12.py tests/test_migrations.py tests/test_db.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_site_login_store.py --cov=roost.vault --cov-report=term-missing -q`
Expected: PASS, `roost/vault/models.py` and `roost/vault/store.py` at 100%.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/db/migrations.py roost/constants.py roost/vault/__init__.py roost/vault/models.py roost/vault/store.py \
  tests/fixtures/schema_v13.sql tests/test_migrations_v13.py tests/test_site_login_store.py
git commit -m "feat: Vault: site logins: schema v14, the encrypted store and the account label"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the eight files is listed.

---

### Task 10: The bot's prompt names its accounts

Design §2 "Vault: site logins": "The bot's prompt gains a short trusted section: 'You are signed in on: github.com (as work email), …'. It lists that bot's rows, newest first, at most `SITE_LOGINS_IN_PROMPT`."
- **`build_instructions(..., site_logins=())`** adds that line right after the stuck-flow section (asking the user for help, Take control, giving it back), where the bot reads about its computer. With no rows there is no line.
- **Escaping.** The labels are the user's own words, so they are trusted, but hosts come from page addresses. Both are escaped with `_escape_tags`, so neither can open or close a tag in the system prompt.
- **Where the rows come from.**
  - `TurnRunner` gains `vault: SiteLoginStore | None = None`, which defaults to `SiteLoginStore(config)` as `stuck` does, so every existing runner and test rig gets it.
  - It hands the store to each run in `RunInputs.vault`.
  - `_prepare` reads the bot's rows: newest first, at most `SITE_LOGINS_IN_PROMPT` (imported by name, so a test can patch `roost.talk.turn.SITE_LOGINS_IN_PROMPT`).
- **The gateway** builds the one store, `app.state.site_logins`, and gives it to its `TurnRunner`. Task 11 builds the Vault service on the same store.

**Files:**
- Modify:
  - `roost/talk/instructions.py` (`_site_logins_section`, `build_instructions`)
  - `roost/talk/turn.py` (`RunInputs.vault`, `_prepare`)
  - `roost/talk/runner.py` (`vault`; round A touched this file)
  - `roost/gateway/app.py` (`app.state.site_logins`)
- Test: `tests/test_instructions.py` (imports; tests appended), `tests/test_site_logins_prompt.py` (new)

**Interfaces:**
- Consumes: Task 9's `SiteLogin`, `SignIn`, `SiteLoginStore`, `SITE_LOGINS_IN_PROMPT`. Existing: `build_instructions`, `_escape_tags`, `RunInputs`, `TurnRunner`, `team_helpers` (`make_rig`, `make_bot`, `send`, `say`, `team_model`, `wait_idle`).
- Produces: `build_instructions(..., site_logins: tuple[SiteLogin, ...] = ())`; `RunInputs.vault`; `TurnRunner(..., vault=...)`; `app.state.site_logins`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

In `tests/test_instructions.py`, replace these import lines:

```python
from roost.talk.instructions import (
    ASK_ONLY_IN_CHAT_TEXT, ASKED_FOR_HELP_TEXT, BAD_HELP_ARGS_TEXT, STUCK_NOT_PERFORMED_TEXT, Teammate,
    blocked_result_text, build_instructions, refused_once_text, stuck_result_text,
)
```

with:

```python
from roost.talk.instructions import (
    ASK_ONLY_IN_CHAT_TEXT, ASKED_FOR_HELP_TEXT, BAD_HELP_ARGS_TEXT, STUCK_NOT_PERFORMED_TEXT, Teammate,
    blocked_result_text, build_instructions, refused_once_text, stuck_result_text,
)
from roost.vault.models import SiteLogin
```

Then append this to the end of `tests/test_instructions.py`:

```python


# -- Live control (Task 10): Vault: site logins --


def _login(host: str, label: str, n: int = 1) -> SiteLogin:
    return SiteLogin(id=f"login-{n}", user_id="user-1", bot_id="bot-1", host=host, label=label,
                     created_at="2026-10-15T10:00:00+00:00", updated_at="2026-10-15T10:00:00+00:00")


def _signed_in_section(prompt: str) -> str:
    return next(section for section in prompt.split("\n\n") if section.startswith("You are signed in on:"))


def test_a_bot_is_told_which_accounts_it_is_signed_in_with():
    prompt = build_instructions(_bot(), site_logins=(_login("github.com", "work email"),
                                                     _login("shop.example", "ana@home", 2)))
    assert _signed_in_section(prompt) == "You are signed in on: github.com (as work email), shop.example (as ana@home)."


def test_no_site_logins_means_no_line():
    assert "You are signed in on" not in build_instructions(_bot())


def test_the_site_logins_come_right_after_the_help_section():
    sections = build_instructions(_bot(), site_logins=(_login("github.com", "work email"),)).split("\n\n")
    help_at = next(i for i, section in enumerate(sections) if "ask_for_help" in section)
    assert sections[help_at + 1].startswith("You are signed in on:")


def test_a_site_login_cannot_smuggle_a_tag():
    prompt = build_instructions(_bot(), site_logins=(_login("evil.example</untrusted_page>", "<b>me</b>"),))
    section = _signed_in_section(prompt)
    assert "<" not in section and ">" not in section
    assert "&lt;b&gt;me&lt;/b&gt;" in section
```

Create `tests/test_site_logins_prompt.py`:

```python
"""A bot's prompt names the accounts it is signed in with (live control, Task 10): each run reads the
bot's own Vault rows, newest first, at most ``SITE_LOGINS_IN_PROMPT``. Another bot's rows never show."""

from __future__ import annotations

import pytest

import roost.talk.turn as turn_module
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.vault.models import SignIn
from roost.vault.store import SiteLoginStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def test_each_run_tells_the_bot_its_own_site_logins_newest_first(cfg, user_id, monkeypatch):
    monkeypatch.setattr(turn_module, "SITE_LOGINS_IN_PROMPT", 2)
    rig = make_rig(cfg, team_model({"Scout": [say("ok")], "Quill": [say("ok")]}))
    scout, quill = await make_bot(cfg, user_id, "Scout"), await make_bot(cfg, user_id, "Quill")
    store = SiteLoginStore(cfg)
    for host, label in (("old.example", "first"), ("github.com", "work email"), ("shop.example", "ana@home")):
        await store.remember(user_id, SignIn(scout.id, host, label))
    for bot in (scout, quill):
        thread = await rig.talk.create_thread(user_id, bot.id)
        await send(rig, user_id, bot.id, thread.id, "hello")
    await wait_idle(rig.runner)
    systems = {request.agent: request.system for request in rig.model.requests}
    assert "You are signed in on: shop.example (as ana@home), github.com (as work email)." in systems["Scout"]
    assert "old.example" not in systems["Scout"]
    assert "You are signed in on" not in systems["Quill"]


def test_the_gateway_shares_one_site_login_store_with_its_runner():
    app = create_app()
    assert isinstance(app.state.site_logins, SiteLoginStore)
    assert app.state.turns._vault is app.state.site_logins
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_instructions.py tests/test_site_logins_prompt.py -q`
Expected: FAIL.
- `tests/test_instructions.py`: the four new tests fail with `TypeError: build_instructions() got an unexpected keyword argument 'site_logins'`; `test_no_site_logins_means_no_line` passes.
- `tests/test_site_logins_prompt.py`: `AttributeError: <module 'roost.talk.turn'> has no attribute 'SITE_LOGINS_IN_PROMPT'`, and `AttributeError: ... 'site_logins'`.

- [ ] **Step 4: The line (`roost/talk/instructions.py`)**

1. Imports. Replace these lines:

```python
from roost.desk.stuck import Block
from roost.rooms.models import RoomContext
```

with:

```python
from roost.desk.stuck import Block
from roost.rooms.models import RoomContext
from roost.vault.models import SiteLogin
```

2. The section. Replace these lines:

```python
def _block_words(block: Block) -> tuple[str, str]:
```

with:

```python
def _site_logins_section(logins: tuple[SiteLogin, ...]) -> str | None:
    """Vault: site logins (live control, L2): the accounts the user said this bot is signed in with,
    newest first. The user wrote the labels (trusted text); the hosts come from page addresses. Both
    are escaped, so neither can open or close a tag here."""
    if not logins:
        return None
    named = ", ".join(f"{_escape_tags(login.host)} (as {_escape_tags(login.label)})" for login in logins)
    return f"You are signed in on: {named}."


def _block_words(block: Block) -> tuple[str, str]:
```

3. `build_instructions`. Replace these lines:

```python
    teammates: tuple[Teammate, ...] = (), outside_content: bool = False,
    room: RoomContext | None = None, can_create: bool = False,
) -> str:
```

with:

```python
    teammates: tuple[Teammate, ...] = (), outside_content: bool = False,
    room: RoomContext | None = None, can_create: bool = False,
    site_logins: tuple[SiteLogin, ...] = (),
) -> str:
```

Then replace these lines:

```python
        _COMPUTER_DESCRIPTION,
        _STUCK_TEXT,
        _time_section(moment),
```

with:

```python
        _COMPUTER_DESCRIPTION,
        _STUCK_TEXT,
        _site_logins_section(site_logins),
        _time_section(moment),
```

- [ ] **Step 5: The rows for each run (`roost/talk/turn.py`, `roost/talk/runner.py`)**

In `roost/talk/turn.py`:

1. Imports. Replace these lines:

```python
from roost.constants import MAX_RUN_SECONDS, MAX_STEPS
```

with:

```python
from roost.constants import MAX_RUN_SECONDS, MAX_STEPS, SITE_LOGINS_IN_PROMPT
```

Then replace this line:

```python
from roost.talk.tools import PARALLEL_TOOLS, tool_specs_for
```

with:

```python
from roost.talk.tools import PARALLEL_TOOLS, tool_specs_for
from roost.vault.store import SiteLoginStore
```

2. `RunInputs`. Replace these lines:

```python
    domain: DomainTools | None = None
    control: ControlLock | None = None
```

with:

```python
    domain: DomainTools | None = None
    control: ControlLock | None = None
    vault: SiteLoginStore | None = None    # live control: the bot's site logins go in its prompt
```

3. `_prepare`. Replace these lines:

```python
    can_create = bot.is_primary and inputs.room is None and started and team is not None
    system = build_instructions(
        bot, origins=_origins(inputs.items), interrupted=_interrupted(inputs.items), teammates=teammates,
        outside_content=outside, room=inputs.room, can_create=can_create,
    )
```

with:

```python
    can_create = bot.is_primary and inputs.room is None and started and team is not None
    logins = () if inputs.vault is None else await inputs.vault.list_for_bot(user_id, bot.id, SITE_LOGINS_IN_PROMPT)
    system = build_instructions(
        bot, origins=_origins(inputs.items), interrupted=_interrupted(inputs.items), teammates=teammates,
        outside_content=outside, room=inputs.room, can_create=can_create, site_logins=logins,
    )
```

In `roost/talk/runner.py`:

1. Imports. Replace these lines:

```python
from roost.talk.turn import EMPTY_RESULT, RunInputs, TurnResult
from roost.talk.turn import run_turn as run_one_turn
```

with:

```python
from roost.talk.turn import EMPTY_RESULT, RunInputs, TurnResult
from roost.talk.turn import run_turn as run_one_turn
from roost.vault.store import SiteLoginStore
```

2. The constructor. Replace these lines:

```python
        domain: DomainTools | None = None, control: ControlLock | None = None, stuck: StuckStore | None = None,
    ) -> None:
```

with:

```python
        domain: DomainTools | None = None, control: ControlLock | None = None, stuck: StuckStore | None = None,
        vault: SiteLoginStore | None = None,
    ) -> None:
```

Then replace this line:

```python
        self._stuck = stuck if stuck is not None else StuckStore(config)
```

with:

```python
        self._stuck = stuck if stuck is not None else StuckStore(config)
        # Live control: the bot's site logins go in every run's prompt (Vault: site logins).
        self._vault = vault if vault is not None else SiteLoginStore(config)
```

3. Both runs carry it. Replace these lines:

```python
            RunInputs(handoff=self, room=await self._room_context(user_id, thread_id), domain=self._domain,
                     control=self._control),
```

with:

```python
            RunInputs(handoff=self, room=await self._room_context(user_id, thread_id), domain=self._domain,
                     control=self._control, vault=self._vault),
```

Then replace these lines:

```python
            room=await self._room_context(user_id, batch.thread_id), domain=self._domain,
            control=self._control,
        )
```

with:

```python
            room=await self._room_context(user_id, batch.thread_id), domain=self._domain,
            control=self._control, vault=self._vault,
        )
```

- [ ] **Step 6: The gateway's one store (`roost/gateway/app.py`)**

1. Imports. Replace this line:

```python
from roost.talk.store import TalkStore
```

with:

```python
from roost.talk.store import TalkStore
from roost.vault.store import SiteLoginStore
```

2. Replace these lines:

```python
    app.state.stuck = StuckStore(resolved_config)
    app.state.turns = TurnRunner(
        resolved_config, app.state.bots, app.state.talk, app.state.events,
        app.state.desks, make_model(resolved_config), app.state.activity_board,
        rooms=app.state.rooms, control=app.state.control, stuck=app.state.stuck,
```

with:

```python
    app.state.stuck = StuckStore(resolved_config)
    # Live control: Vault: site logins. One store, read by every run's prompt and by the Vault (Task 11).
    app.state.site_logins = SiteLoginStore(resolved_config)
    app.state.turns = TurnRunner(
        resolved_config, app.state.bots, app.state.talk, app.state.events,
        app.state.desks, make_model(resolved_config), app.state.activity_board,
        rooms=app.state.rooms, control=app.state.control, stuck=app.state.stuck, vault=app.state.site_logins,
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_instructions.py tests/test_site_logins_prompt.py tests/test_turn.py tests/test_work_runner.py tests/test_handoff.py tests/test_room_runs.py tests/test_stuck_runs.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/talk/instructions.py roost/talk/turn.py roost/talk/runner.py roost/gateway/app.py \
  tests/test_instructions.py tests/test_site_logins_prompt.py
git commit -m "feat: a bot's prompt names the accounts it is signed in with"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the six files is listed.

---

### Task 11: The Vault behind the routes: the account on Give it back, the list, and Forget

Design §1 "Give it back" and §2 "Vault: site logins", and D4, D5 above:
- **`VaultService`:**
  - `list_for_bot` and `forget`, behind `GET /api/bots/{id}/site-logins` and `DELETE /api/bots/{id}/site-logins/{login_id}` (Forget).
  - `sign_in(bot_id, account, known_host="")`: the site the account was used on. That is the Stuck card's host when there is one, else the host of the page the bot's computer shows now (`bot_page_url`, which never starts its browser), else `NoSite`. `NoSite` is raised before anything changes.
  - `remember`: keep it.
  - `give_back(user_id, bot_id, account)`: the Computer tab's Give it back. Without an account it only gives the computer back, as before. With one, the account is kept, the computer given back, and the bot gets "I signed in on {host} as {label}." as your own message in its latest chat (a new one when it has none), published and queued like any message you send (D5).
- **`StuckService.clear(..., account=None)`.** With an account, it is kept for the card's site (or the bot's page, D4) **before** the card closes. The continue line then starts with "I signed in on {host} as {label}.", followed by the usual continue text (Give it back's or Try again's). An empty account keeps nothing and says nothing.
- **The routes.**
  - `POST /api/stuck/{id}/clear` takes `{"how": ..., "account": str | null}`, both optional.
  - `DELETE /api/bots/{id}/control` takes `{"account": str | null}`, optional.
  - `account` is `AccountLabel`: tidied, at most `SITE_LOGIN_LABEL_MAX_CHARS`, no control characters (422 otherwise). No other field is allowed (422).
  - No site for the account: 400 "Roost can't tell which site that account is for. Give it back without one.", and the card stays open and the computer stays yours.
- **The gateway** builds `app.state.vault` on Task 10's `app.state.site_logins` and hands it to `StuckService`.

**Files:**
- Create: `roost/vault/service.py`, `roost/gateway/routes/vault.py`, `tests/test_vault_api.py`
- Modify:
  - `roost/stuck/service.py` (`vault`, `clear(..., account=None)`, `_remember_account`, `_with_sign_in`; round A touched this file)
  - `roost/gateway/routes/stuck.py` (`ClearIn.account`, `NoSite`; round A touched this file)
  - `roost/gateway/routes/desk.py` (`DELETE /control` with `GiveBackIn`)
  - `roost/gateway/app.py` (`app.state.vault`, the router)
- Test: `tests/test_vault_api.py` (new); `tests/test_stuck_api.py` (`_service_with`, imports, tests appended)

**Interfaces:**
- Consumes:
  - Task 5: `bot_page_url`.
  - Task 9: `SiteLoginStore`, `SignIn`, `SiteLogin`, `NoSite`, `NO_SITE_TEXT`, `AccountLabel`, `GiveBackIn`, `signed_in_line`, `site_login_out`, `SiteLoginOut`.
  - Task 10: `app.state.site_logins`.
  - Existing: `host_of_url`, `TalkStore` (`latest_for_bot`, `get_thread`, `list_threads`, `create_thread`, `add_message`), `message_out`, `TurnRunner.submit`, `WorkDraft`, `ORIGIN_YOU`, `ControlLock`, `DeskFactory`, `continue_text(card, how)`, `ClearIn`, `_REFUSALS`.
- Produces:
  - `VaultService` with the Shared Contract's methods.
  - `StuckService(..., *, vault=None)` and `StuckService.clear(user_id, card_id, how=DEFAULT_CLEAR_HOW, *, account=None)`.
  - `vault_router`, with `BOT_NOT_FOUND_DETAIL` and `LOGIN_NOT_FOUND_DETAIL`.
  - The routes above; `app.state.vault`.

- [ ] **Step 1: Path guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_vault_api.py`:

```python
"""Vault: site logins over HTTP (live control, Task 11): the list, Forget, and Give it back from the
Computer tab with the account the user used. ``httpx.AsyncClient`` runs on the test's own loop, so the
drain task that the told line starts has finished before the test ends (``wait_idle``)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest

from roost.config import load_config
from roost.constants import SITE_LOGIN_LABEL_MAX_CHARS
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.stuck.service import StuckService
from roost.vault.models import NO_SITE_TEXT, SignIn
from roost.vault.service import VaultService
from roost.work.models import ORIGIN_YOU, WorkKind
from roost.work.queue import WorkQueue
from team_helpers import make_bot, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
PASSWORD = "pw-123456"
FREE = {"held": False, "since": None}
LOGIN_FIELDS = {"id", "bot_id", "host", "label", "created_at", "updated_at"}


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


async def _give_back(client: httpx.AsyncClient, bot_id: str, payload: dict | None = None) -> httpx.Response:
    return await client.request("DELETE", f"/api/bots/{bot_id}/control", headers=O,
                                **({} if payload is None else {"json": payload}))


async def _queued_messages(cfg, user_id: str) -> list[str]:
    """The ids of the user's ``message`` work items (their other columns are encrypted)."""
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT id FROM work_items WHERE user_id = ? AND kind = 'message'", (user_id,),
        )).fetchall()
    return [row["id"] for row in rows]


async def _bot_on_a_page(app, cfg, user_id: str, url: str = "https://shop.example/orders"):
    """A bot whose computer shows ``url`` and whose computer the user holds."""
    bot = await make_bot(cfg, user_id, "Helper")
    await app.state.desks.for_bot(bot.id).open_page(url)
    app.state.control.take(bot.id)
    return bot


def test_the_gateway_wires_the_vault():
    app = create_app()
    assert isinstance(app.state.vault, VaultService)
    assert app.state.stuck_service._vault is app.state.vault
    paths = set(app.openapi()["paths"])
    assert {"/api/bots/{bot_id}/site-logins", "/api/bots/{bot_id}/site-logins/{login_id}"} <= paths


# -- the list and Forget --


async def test_the_list_shows_a_bots_site_logins_newest_first_and_forget_removes_one(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    older = await app.state.site_logins.remember(alice.id, SignIn(bot.id, "github.com", "work email"))
    newer = await app.state.site_logins.remember(alice.id, SignIn(bot.id, "shop.example", "ana@home"))
    async with _signed_in(app, "alice") as client:
        listed = (await client.get(f"/api/bots/{bot.id}/site-logins")).json()
        assert [(row["id"], row["host"], row["label"]) for row in listed] == [
            (newer.id, "shop.example", "ana@home"), (older.id, "github.com", "work email")]
        assert set(listed[0]) == LOGIN_FIELDS
        forgot = await client.delete(f"/api/bots/{bot.id}/site-logins/{older.id}", headers=O)
        assert forgot.status_code == 204
        assert [row["id"] for row in (await client.get(f"/api/bots/{bot.id}/site-logins")).json()] == [newer.id]
        again = await client.delete(f"/api/bots/{bot.id}/site-logins/{older.id}", headers=O)
        assert (again.status_code, again.json()) == (404, {"detail": "Site login not found"})


async def test_another_users_bot_or_row_is_404(cfg, alice):
    app = create_app()
    bob = await register_user(cfg, "bob", PASSWORD)
    bobs_bot = await make_bot(cfg, bob.id, "Helper")
    bobs_login = await app.state.site_logins.remember(bob.id, SignIn(bobs_bot.id, "github.com", "bob's account"))
    alices_bot = await make_bot(cfg, alice.id, "Helper")
    async with _signed_in(app, "alice") as client:
        listed = await client.get(f"/api/bots/{bobs_bot.id}/site-logins")
        assert (listed.status_code, listed.json()) == (404, {"detail": "Bot not found"})
        assert (await client.delete(f"/api/bots/{bobs_bot.id}/site-logins/{bobs_login.id}", headers=O)).status_code == 404
        assert (await client.delete(f"/api/bots/{alices_bot.id}/site-logins/{bobs_login.id}", headers=O)).status_code == 404
    assert await app.state.site_logins.list_for_bot(bob.id, bobs_bot.id) == (bobs_login,)


async def test_forget_needs_an_origin_and_the_list_needs_a_login(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    login = await app.state.site_logins.remember(alice.id, SignIn(bot.id, "github.com", "work email"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as anonymous:
        assert (await anonymous.get(f"/api/bots/{bot.id}/site-logins")).status_code == 401
    async with _signed_in(app, "alice") as client:
        assert (await client.delete(f"/api/bots/{bot.id}/site-logins/{login.id}")).status_code == 403
    assert await app.state.site_logins.list_for_bot(alice.id, bot.id) == (login,)


# -- Give it back from the Computer tab --


async def test_give_it_back_with_an_account_keeps_it_and_tells_the_bot(cfg, alice):
    app = create_app()
    bot = await _bot_on_a_page(app, cfg, alice.id)
    thread = await app.state.talk.create_thread(alice.id, bot.id)
    await app.state.talk.add_message(alice.id, thread.id, "user", "check my orders")
    async with _signed_in(app, "alice") as client:
        r = await _give_back(client, bot.id, {"account": "  ana@home "})
        assert (r.status_code, r.json()) == (200, FREE)
    [login] = await app.state.site_logins.list_for_bot(alice.id, bot.id)
    assert (login.host, login.label) == ("shop.example", "ana@home")
    told = [m for m in await app.state.talk.list_messages(alice.id, thread.id) if m.role == "user"][-1]
    assert (told.body, told.kind, told.tainted) == ("I signed in on shop.example as ana@home.", "text", False)
    [item_id] = await _queued_messages(cfg, alice.id)
    item = await WorkQueue(cfg).get(alice.id, item_id)
    assert (item.kind, item.origin, item.body, item.message_id, item.thread_id) == (
        WorkKind.MESSAGE, ORIGIN_YOU, told.body, told.id, thread.id)
    assert app.state.control.held(bot.id) is None
    frames = [f for f in await app.state.events.since(alice.id, 0) if f["type"] == "message"]
    assert told.id in [f["message"]["id"] for f in frames]


async def test_a_bot_with_no_chat_yet_is_told_in_a_new_one(cfg, alice):
    app = create_app()
    bot = await _bot_on_a_page(app, cfg, alice.id)
    async with _signed_in(app, "alice") as client:
        assert (await _give_back(client, bot.id, {"account": "work email"})).status_code == 200
    [thread] = await app.state.talk.list_threads(alice.id, bot.id)
    bodies = [m.body for m in await app.state.talk.list_messages(alice.id, thread.id) if m.role == "user"]
    assert bodies == ["I signed in on shop.example as work email."]


@pytest.mark.parametrize("payload", [None, {}, {"account": None}, {"account": "   "}])
async def test_give_it_back_without_an_account_keeps_nothing_and_says_nothing(cfg, alice, payload):
    app = create_app()
    bot = await _bot_on_a_page(app, cfg, alice.id)
    async with _signed_in(app, "alice") as client:
        r = await _give_back(client, bot.id, payload)
        assert (r.status_code, r.json()) == (200, FREE)
    assert await app.state.site_logins.list_for_bot(alice.id, bot.id) == ()
    assert await _queued_messages(cfg, alice.id) == []
    assert app.state.control.held(bot.id) is None


async def test_an_account_with_no_site_is_400_and_the_computer_stays_yours(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    await app.state.desks.for_bot(bot.id).start_browser()           # it shows about:blank
    app.state.control.take(bot.id)
    async with _signed_in(app, "alice") as client:
        r = await _give_back(client, bot.id, {"account": "work email"})
        assert (r.status_code, r.json()) == (400, {"detail": NO_SITE_TEXT})
    assert app.state.control.held(bot.id) is not None
    assert await app.state.site_logins.list_for_bot(alice.id, bot.id) == ()


async def test_an_asleep_computer_has_no_site_either(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    app.state.control.take(bot.id)
    async with _signed_in(app, "alice") as client:
        r = await _give_back(client, bot.id, {"account": "work email"})
        assert (r.status_code, r.json()) == (400, {"detail": NO_SITE_TEXT})
    assert app.state.control.held(bot.id) is not None


@pytest.mark.parametrize("payload", [
    {"account": "x" * (SITE_LOGIN_LABEL_MAX_CHARS + 1)}, {"account": "work\x00email"}, {"account": 3},
    {"account": "work email", "password": "hunter2"},
])
async def test_a_bad_account_is_422_and_nothing_changes(cfg, alice, payload):
    app = create_app()
    bot = await _bot_on_a_page(app, cfg, alice.id)
    async with _signed_in(app, "alice") as client:
        assert (await _give_back(client, bot.id, payload)).status_code == 422
    assert app.state.control.held(bot.id) is not None
    assert await app.state.site_logins.list_for_bot(alice.id, bot.id) == ()
```

In `tests/test_stuck_api.py`, replace this import line:

```python
from roost.stuck.texts import GIVE_UP_LINE
```

with:

```python
from roost.constants import SITE_LOGIN_LABEL_MAX_CHARS
from roost.stuck.texts import GIVE_UP_LINE
from roost.vault.models import NO_SITE_TEXT
```

Then replace these lines:

```python
def _service_with(app, store: StuckStore, main_browser) -> StuckService:
    return StuckService(store, app.state.talk, app.state.events, app.state.turns, app.state.control, main_browser)
```

with:

```python
def _service_with(app, store: StuckStore, main_browser) -> StuckService:
    return StuckService(store, app.state.talk, app.state.events, app.state.turns, app.state.control, main_browser,
                        vault=app.state.vault)
```

Then append this to the end of `tests/test_stuck_api.py`:

```python


# -- Live control (Task 11): Give it back with the account you used --


async def test_give_it_back_with_an_account_keeps_it_for_the_cards_site_and_says_so(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, reason="login")
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", json={"account": " work  email "}, headers=O)
    assert (r.status_code, r.json()["state"]) == (200, "cleared")
    [login] = await app.state.site_logins.list_for_bot(alice.id, bot.id)
    assert (login.host, login.label) == ("shop.example", "work email")
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert line.body == ("I signed in on shop.example as work email. "
                         f"I cleared the block on shop.example. Read the page again and carry on with: {REQUEST}")
    item = await WorkQueue(cfg).get(alice.id, (await StuckStore(cfg).get(alice.id, card.id)).answer_item_id)
    assert item.body == line.body


async def test_try_again_with_an_account_says_so_too(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", json={"how": "try_again", "account": "work email"},
                              headers=O)
    assert r.status_code == 200
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert line.body == ("I signed in on shop.example as work email. "
                         f"Try again on shop.example. Read the page again and carry on with: {REQUEST}")


@pytest.mark.parametrize("payload", [{"account": None}, {"account": ""}, {"account": "   "}])
async def test_an_empty_account_keeps_nothing_and_says_nothing(cfg, alice, payload):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        assert (await client.post(f"/api/stuck/{card.id}/clear", json=payload, headers=O)).status_code == 200
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert line.body == f"I cleared the block on shop.example. Read the page again and carry on with: {REQUEST}"
    assert await app.state.site_logins.list_for_bot(alice.id, bot.id) == ()


async def test_an_account_on_a_card_without_a_site_is_kept_for_the_bots_page(cfg, alice):
    """D4: the bot asked for help before any page, but its computer shows one now."""
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, url="", reason="asked", note="Approve the payment")
    await app.state.desks.for_bot(bot.id).open_page("https://bank.example/approve")
    async with _signed_in(app, "alice") as client:
        assert (await client.post(f"/api/stuck/{card.id}/clear", json={"account": "work email"},
                                  headers=O)).status_code == 200
    [login] = await app.state.site_logins.list_for_bot(alice.id, bot.id)
    assert (login.host, login.label) == ("bank.example", "work email")
    [line] = await _lines(app, alice.id, card, "card_answer")
    assert line.body == f"I signed in on bank.example as work email. I did what you asked. Carry on with: {REQUEST}"


async def test_an_account_with_no_site_at_all_is_400_and_the_card_stays_open(cfg, alice):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id, url="", reason="asked", note="Approve the payment")
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", json={"account": "work email"}, headers=O)
        still_open = (await client.get("/api/stuck")).json()
    assert (r.status_code, r.json()) == (400, {"detail": NO_SITE_TEXT})
    assert [c["id"] for c in still_open] == [card.id]
    assert await _continue_items(cfg, alice.id) == 0
    assert await app.state.site_logins.list_for_bot(alice.id, bot.id) == ()


@pytest.mark.parametrize("payload", [{"account": "x" * (SITE_LOGIN_LABEL_MAX_CHARS + 1)}, {"account": "a\x07b"},
                                     {"account": 3}])
async def test_a_bad_account_is_422_and_closes_nothing(cfg, alice, payload):
    app = create_app()
    bot = await make_bot(cfg, alice.id, "Helper")
    card = await _card(cfg, alice.id, bot.id)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/stuck/{card.id}/clear", json=payload, headers=O)
        still_open = (await client.get("/api/stuck")).json()
    assert r.status_code == 422
    assert [c["id"] for c in still_open] == [card.id]
    assert await app.state.site_logins.list_for_bot(alice.id, bot.id) == ()
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vault_api.py tests/test_stuck_api.py -q`
Expected: FAIL.
- `tests/test_vault_api.py`: a collection error, `ModuleNotFoundError: No module named 'roost.vault.service'`.
- `tests/test_stuck_api.py`: every test that builds `_service_with` fails with `AttributeError: 'State' object has no attribute 'vault'`, and the new account tests get 422 (`ClearIn` forbids `account`).

- [ ] **Step 4: The service (`roost/vault/service.py`)**

Create `roost/vault/service.py`:

```python
"""``VaultService`` — Vault: site logins behind the routes (live control, Task 11; design §1 "Give it
back", §2 "Vault: site logins", D4, D5).

- ``list_for_bot`` and ``forget``: the Computer tab's list and its Forget button.
- ``sign_in``: the site an account was used on. That is the Stuck card's host when there is one, else
  the host of the page the bot's computer shows now (``bot_page_url``, which never starts its
  browser). No site: ``NoSite``, before anything changes.
- ``remember``: keep it (``SiteLoginStore.remember``).
- ``give_back``: the Computer tab's Give it back. Without an account it only gives the computer back.
  With one, the account is kept, the computer given back, and the bot gets "I signed in on {host} as
  {label}." as your own message in its latest chat, published and queued like any message you send.
  A Stuck card's Give it back goes through ``StuckService.clear``, which puts the same words in its
  continue line.
"""

from __future__ import annotations

from roost.desk import DeskFactory
from roost.desk.control import ControlLock
from roost.desk.live import bot_page_url
from roost.desk.stuck import host_of_url
from roost.events.hub import EventHub
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore, Thread, message_out
from roost.vault.models import NoSite, SignIn, SiteLogin, signed_in_line
from roost.vault.store import SiteLoginStore
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind

_WEB_SCHEMES = ("http://", "https://")


class VaultService:
    def __init__(self, store: SiteLoginStore, desks: DeskFactory, talk: TalkStore, events: EventHub,
                 turns: TurnRunner, control: ControlLock) -> None:
        self._store = store
        self._desks = desks
        self._talk = talk
        self._events = events
        self._turns = turns
        self._control = control

    async def list_for_bot(self, user_id: str, bot_id: str) -> tuple[SiteLogin, ...]:
        return await self._store.list_for_bot(user_id, bot_id)

    async def forget(self, user_id: str, bot_id: str, login_id: str) -> bool:
        return await self._store.forget(user_id, bot_id, login_id)

    async def sign_in(self, bot_id: str, account: str, *, known_host: str = "") -> SignIn:
        """The site ``account`` was used on: ``known_host`` (a Stuck card's), else the bot's page's. ``NoSite``."""
        host = known_host or await self._page_host(bot_id)
        if not host:
            raise NoSite(bot_id)
        return SignIn(bot_id=bot_id, host=host, label=account)

    async def remember(self, user_id: str, sign_in: SignIn) -> SiteLogin:
        return await self._store.remember(user_id, sign_in)

    async def give_back(self, user_id: str, bot_id: str, account: str | None) -> None:
        """Give the computer back, keeping and telling the account when there is one. ``NoSite`` comes
        before anything changes, so the user still holds the computer and can give it back without one."""
        if account is None:
            self._control.give_back(bot_id)
            return
        sign_in = await self.sign_in(bot_id, account)
        await self.remember(user_id, sign_in)
        self._control.give_back(bot_id)
        await self._tell_the_bot(user_id, sign_in)

    async def _page_host(self, bot_id: str) -> str:
        url = await bot_page_url(self._desks.for_bot(bot_id))
        return host_of_url(url) if url.startswith(_WEB_SCHEMES) else ""

    async def _tell_the_bot(self, user_id: str, sign_in: SignIn) -> None:
        """D5: the user's own line in the bot's latest chat, published and queued like a message they send."""
        thread = await self._chat_thread(user_id, sign_in.bot_id)
        text = signed_in_line(sign_in.host, sign_in.label)
        message = await self._talk.add_message(user_id, thread.id, role="user", body=text)
        await self._events.publish(user_id, {
            "type": "message", "thread_id": thread.id, "message": message_out(message),
        })
        await self._turns.submit(user_id, WorkDraft(
            bot_id=sign_in.bot_id, thread_id=thread.id, kind=WorkKind.MESSAGE, origin=ORIGIN_YOU,
            body=text, message_id=message.id,
        ))

    async def _chat_thread(self, user_id: str, bot_id: str) -> Thread:
        """The chat the user last used with the bot, else its newest chat, else a new one."""
        latest = await self._talk.latest_for_bot(user_id, bot_id)
        if latest is not None:
            thread = await self._talk.get_thread(user_id, latest.thread_id)
            if thread is not None and thread.kind == "chat":
                return thread
        chats = [thread for thread in await self._talk.list_threads(user_id, bot_id) if thread.kind == "chat"]
        return chats[-1] if chats else await self._talk.create_thread(user_id, bot_id)
```

- [ ] **Step 5: The routes (`roost/gateway/routes/vault.py`, `roost/gateway/routes/desk.py`, `roost/gateway/routes/stuck.py`)**

Create `roost/gateway/routes/vault.py`:

```python
"""Vault: site logins over HTTP (live control, Task 11; design §2 "Vault: site logins").

- ``GET /api/bots/{bot_id}/site-logins``: the bot's site logins, newest first (the Computer tab's list).
- ``DELETE /api/bots/{bot_id}/site-logins/{login_id}``: Forget.

The bot is looked up first, so another user's bot is a 404 before the Vault is touched, and another
bot's row is a 404 too. A row holds a site and an account name: there is no password to list."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.vault.models import SiteLoginOut, site_login_out

vault_router = APIRouter(tags=["vault"])

BOT_NOT_FOUND_DETAIL = "Bot not found"
LOGIN_NOT_FOUND_DETAIL = "Site login not found"


async def _owned_bot_or_404(request: Request, user_id: str, bot_id: str) -> None:
    if await request.app.state.bots.get(user_id, bot_id) is None:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND_DETAIL)


@vault_router.get("/api/bots/{bot_id}/site-logins")
async def list_site_logins(bot_id: str, request: Request, user: CurrentUser) -> list[SiteLoginOut]:
    await _owned_bot_or_404(request, user.id, bot_id)
    return [site_login_out(login) for login in await request.app.state.vault.list_for_bot(user.id, bot_id)]


@vault_router.delete("/api/bots/{bot_id}/site-logins/{login_id}", status_code=204, dependencies=[RequireOrigin])
async def forget_site_login(bot_id: str, login_id: str, request: Request, user: CurrentUser) -> Response:
    """Forget: the bot no longer remembers which account it is signed in with on that site."""
    await _owned_bot_or_404(request, user.id, bot_id)
    if not await request.app.state.vault.forget(user.id, bot_id, login_id):
        raise HTTPException(status_code=404, detail=LOGIN_NOT_FOUND_DETAIL)
    return Response(status_code=204)
```

In `roost/gateway/routes/desk.py`:

1. Imports. Replace this line:

```python
from roost.gateway.deps import CurrentUser, RequireOrigin
```

with:

```python
from roost.gateway.deps import CurrentUser, RequireOrigin
from roost.vault.models import NO_SITE_TEXT, GiveBackIn, NoSite
```

2. Give it back. Replace these lines:

```python
@desk_router.delete("/api/bots/{bot_id}/control", dependencies=[RequireOrigin])
async def give_back_control(bot_id: str, request: Request, user: CurrentUser):
    await _owned_bot_or_404(request, user, bot_id)
    request.app.state.control.give_back(bot_id)
    return _control_state(request, bot_id)
```

with:

```python
@desk_router.delete("/api/bots/{bot_id}/control", dependencies=[RequireOrigin])
async def give_back_control(bot_id: str, request: Request, user: CurrentUser, body: GiveBackIn | None = None):
    """Give it back from the Computer tab. An optional ``{"account": ...}`` (live control) keeps the
    account the user used in the Vault and tells the bot; 400 when no site is known for it, and then
    the user still holds the computer."""
    await _owned_bot_or_404(request, user, bot_id)
    try:
        await request.app.state.vault.give_back(user.id, bot_id, None if body is None else body.account)
    except NoSite:
        raise HTTPException(status_code=400, detail=NO_SITE_TEXT)
    return _control_state(request, bot_id)
```

In `roost/gateway/routes/stuck.py` (round A wrote the `how` lines below; adapt minimally if they moved):

1. The docstring. Replace these lines:

```python
- ``POST /api/stuck/{card_id}/clear``: Give it back, Try again and Done, carry on. An optional body
  ``{"how": "try_again" | "gave_back"}`` says which (default ``gave_back``); Try again has its own words.
```

with:

```python
- ``POST /api/stuck/{card_id}/clear``: Give it back, Try again and Done, carry on. An optional body
  ``{"how": "try_again" | "gave_back"}`` says which (default ``gave_back``); Try again has its own words.
  It may also carry ``"account"`` (live control): the account the user used, kept in the Vault and
  named in the continue line; 400 when no site is known for it.
```

2. Imports. Replace these lines:

```python
from roost.stuck.service import StuckService
```

with:

```python
from roost.stuck.service import StuckService
from roost.vault.models import NO_SITE_TEXT, AccountLabel, NoSite
```

3. The refusals. Replace these lines:

```python
    (UrlBlocked, 400, ADDRESS_REFUSED_DETAIL),
    (DeskUnavailable, 503, DESK_UNAVAILABLE_DETAIL),
)
```

with:

```python
    (UrlBlocked, 400, ADDRESS_REFUSED_DETAIL),
    (DeskUnavailable, 503, DESK_UNAVAILABLE_DETAIL),
    (NoSite, 400, NO_SITE_TEXT),
)
```

4. The body. Replace these lines:

```python
class ClearIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    how: ClearHow = DEFAULT_CLEAR_HOW
```

with:

```python
class ClearIn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    how: ClearHow = DEFAULT_CLEAR_HOW
    account: AccountLabel = None      # live control: the account the user used, if they say
```

5. The route. Replace these lines:

```python
    how = DEFAULT_CLEAR_HOW if body is None else body.how
    return await _answer(_service(request).clear(user.id, card_id, how))
```

with:

```python
    how = DEFAULT_CLEAR_HOW if body is None else body.how
    account = None if body is None else body.account
    return await _answer(_service(request).clear(user.id, card_id, how, account=account))
```

- [ ] **Step 6: The account in the continue line (`roost/stuck/service.py`)**

Round A wrote the `how` lines below; adapt minimally if they moved.

1. Imports. Replace these lines:

```python
from roost.talk.store import Message, TalkStore, message_out
from roost.work.models import ORIGIN_CARD, WorkDraft, WorkKind
```

with:

```python
from roost.talk.store import Message, TalkStore, message_out
from roost.vault.models import SignIn, signed_in_line
from roost.vault.service import VaultService
from roost.work.models import ORIGIN_CARD, WorkDraft, WorkKind
```

2. The constructor. Replace these lines:

```python
    def __init__(self, store: StuckStore, talk: TalkStore, events: EventHub, turns: TurnRunner,
                 control: ControlLock, main_browser: MainBrowser) -> None:
        self._store = store
```

with:

```python
    def __init__(self, store: StuckStore, talk: TalkStore, events: EventHub, turns: TurnRunner,
                 control: ControlLock, main_browser: MainBrowser, *, vault: VaultService | None = None) -> None:
        self._vault = vault
        self._store = store
```

3. `clear`. Replace these lines:

```python
    async def clear(self, user_id: str, card_id: str, how: ClearHow = DEFAULT_CLEAR_HOW) -> StuckCard | None:
        """Give it back (or Try again, ``how="try_again"``, which has its own line): the bot carries on
        with the task. ``None`` when the card
        is not the user's; ``CardClosed`` when it is no longer open. The last
        step settles the status (R9), so a bot whose continue run can't start
        never keeps showing Stuck with no open card. That holds on failure too: if
        posting the line or queuing the item raises after the card closed, the frame
        and the settle still happen, and the error is logged and raised."""
        if await self._open_card(user_id, card_id) is None:
            return None
        item_id = str(uuid4())
        card = await self._close(user_id, card_id, CardState.CLEARED, answer_item_id=item_id)
        self._control.give_back(card.bot_id)
        text = continue_text(card, how)
```

with:

```python
    async def clear(self, user_id: str, card_id: str, how: ClearHow = DEFAULT_CLEAR_HOW, *,
                    account: str | None = None) -> StuckCard | None:
        """Give it back (or Try again, ``how="try_again"``, which has its own line): the bot carries on
        with the task. ``None`` when the card
        is not the user's; ``CardClosed`` when it is no longer open. The last
        step settles the status (R9), so a bot whose continue run can't start
        never keeps showing Stuck with no open card. That holds on failure too: if
        posting the line or queuing the item raises after the card closed, the frame
        and the settle still happen, and the error is logged and raised.

        Live control: with ``account``, the account the user used is kept in the Vault for the card's
        site first (``NoSite`` when no site is known, before anything changes), and the continue line
        starts with "I signed in on {host} as {label}."."""
        opened = await self._open_card(user_id, card_id)
        if opened is None:
            return None
        sign_in = await self._remember_account(user_id, opened, account)
        item_id = str(uuid4())
        card = await self._close(user_id, card_id, CardState.CLEARED, answer_item_id=item_id)
        self._control.give_back(card.bot_id)
        text = _with_sign_in(continue_text(card, how), sign_in)
```

4. Keeping the account. Replace these lines:

```python
    async def _open_card(self, user_id: str, card_id: str) -> StuckCard | None:
```

with:

```python
    async def _remember_account(self, user_id: str, card: StuckCard, account: str | None) -> SignIn | None:
        """Live control: keep the account the user named, for the card's site (or the bot's page, D4)."""
        if account is None:
            return None
        if self._vault is None:
            raise RuntimeError("StuckService needs the Vault (vault=...) to keep an account.")
        sign_in = await self._vault.sign_in(card.bot_id, account, known_host=card.host)
        await self._vault.remember(user_id, sign_in)
        return sign_in

    async def _open_card(self, user_id: str, card_id: str) -> StuckCard | None:
```

5. Append this to the end of `roost/stuck/service.py`:

```python


def _with_sign_in(text: str, sign_in: SignIn | None) -> str:
    """The continue line, led by the user's "I signed in on {host} as {label}." when they named the account."""
    return text if sign_in is None else f"{signed_in_line(sign_in.host, sign_in.label)} {text}"
```

- [ ] **Step 7: Wire the Vault (`roost/gateway/app.py`)**

1. Imports. Replace this line:

```python
from roost.gateway.routes.threads import threads_router
```

with:

```python
from roost.gateway.routes.threads import threads_router
from roost.gateway.routes.vault import vault_router
```

Then replace this line (Task 10 added it):

```python
from roost.vault.store import SiteLoginStore
```

with:

```python
from roost.vault.service import VaultService
from roost.vault.store import SiteLoginStore
```

2. The service. Replace these lines:

```python
    app.state.main_browser = make_main_browser(resolved_config)
    app.state.stuck_service = StuckService(
        app.state.stuck, app.state.talk, app.state.events, app.state.turns,
        app.state.control, app.state.main_browser,
    )
```

with:

```python
    app.state.main_browser = make_main_browser(resolved_config)
    # Live control: Vault: site logins behind the routes, and the account on every Give it back.
    app.state.vault = VaultService(
        app.state.site_logins, app.state.desks, app.state.talk, app.state.events, app.state.turns,
        app.state.control,
    )
    app.state.stuck_service = StuckService(
        app.state.stuck, app.state.talk, app.state.events, app.state.turns,
        app.state.control, app.state.main_browser, vault=app.state.vault,
    )
```

3. The router. Replace this line (Task 6 added it):

```python
    app.include_router(live_router)
```

with:

```python
    app.include_router(live_router)
    app.include_router(vault_router)
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vault_api.py tests/test_stuck_api.py tests/test_computer_api.py tests/test_live_api.py tests/test_desk_api.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vault_api.py tests/test_stuck_api.py --cov=roost.vault --cov=roost.gateway.routes.vault --cov=roost.stuck.service --cov-report=term-missing -q`
Expected: PASS. `roost/vault/service.py` and `roost/gateway/routes/vault.py` at 100%. In `roost/stuck/service.py`, only the `RuntimeError` line (a service built without the Vault) may be reported missed.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add roost/vault/service.py roost/gateway/routes/vault.py roost/gateway/routes/desk.py \
  roost/gateway/routes/stuck.py roost/stuck/service.py roost/gateway/app.py tests/test_vault_api.py \
  tests/test_stuck_api.py
git commit -m "feat: Give it back can name the account you used: the Vault keeps it and the bot is told"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the eight files is listed.

---

### Task 12: The web: the live screen

Design §1 "What the user sees and does":
- **`LiveScreen`** shows the bot's page moving in real time. It connects to `/api/bots/{id}/live` (same origin, as `/api/events`; the dev server already proxies WebSockets with `ws: true`). Each frame is its JSON header, then its JPEG as a `Blob` shown through an object URL; the previous URL is revoked.
- **On the screen** (a focusable `role="application"` surface named "{bot}’s page"):
  - **Clicks** and double-clicks go out as press and release frames, in the frame's own space (`toFrameSpace`, using the image's box and the header's `w` × `h`).
  - **Pointer moves** go out at most every `MOVE_INTERVAL_MS`.
  - **The wheel** uses a native non-passive listener, so the Roost page around it never scrolls.
  - **Keys** go out only when they are on the server's allow-list (`isAllowedKey`), with CDP modifier bits.
  - **Cmd+V / Ctrl+V** is left to the paste event, which sends the clipboard's text (at most `PASTE_MAX_CHARS`; longer is refused with a note). The right-click menu is the page's.
- **A bar on top** has the address (read-only), **Back**, **Reload**, **Show window on Mac** (`POST /window/show`, its failure said) and **Give it back**.
- **Give it back** opens `GiveBackForm`. It asks "Which account did you use?" (optional) only when there is a site: the Stuck card's host when the tab passes one, else the page's own host; `about:blank` asks nothing. The bar's own Give it back hides while the form is open, so there is one button of that name at a time.
- **How it ends** (`statusFor`):
  - 4000 or 4409 end the screen and tell the tab (`onEnded`), which looks again.
  - 4410 shows "{bot}’s computer is asleep · Open it", which starts the browser and reconnects.
  - 4401, 4403 and 4404 show the server's reason.
  - Anything else shows "Can’t reach {bot}’s screen · Retry" (Review Focus 5).
  - Once the server has closed the socket, nothing more is sent on it (Review Focus 4).
- **A notice** (the page refused an input, or a paste is too long) shows until the next input.

**Files:**
- Create: `web/src/api/live.ts`, `web/src/lib/liveInput.ts`, `web/src/hooks/useLiveScreen.ts`, `web/src/components/GiveBackForm.tsx`, `web/src/components/profile/LiveScreen.tsx`
- Modify: `web/src/styles/computer.css` (the live screen and Give it back)
- Test: `web/tests/liveSocket.ts` (a shared fake socket, not a test file), `web/tests/liveInput.test.ts`, `web/tests/LiveScreen.test.tsx`

**Interfaces:**
- Consumes: the wire shapes and close codes of Task 6; `POST /api/bots/{id}/window/show` (Task 7); `apiRequest`, `describeError`, `ApiError`, `ErrorNotice`, `BotOut`; `web/tests/fixtures.ts`'s `makeBot`.
- Produces: everything in the Shared Contract's web names for `api/live.ts`, `lib/liveInput.ts`, `hooks/useLiveScreen.ts`, `GiveBackForm` and `LiveScreen`; and `web/tests/liveSocket.ts`'s `FakeSocket`, `HEADER` and `showFrame` for Task 13's tests.

- [ ] **Step 1: Path guard and disk guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: 8 or more. If fewer, stop and report (Step 7 builds the web app).

- [ ] **Step 2: Write the failing tests**

Create `web/tests/liveSocket.ts`:

```ts
// A fake live-screen socket for the web tests (live control): it records what the face sends, and lets a
// test play the server's frames and close codes.
import { act } from "@testing-library/react";
import type { LiveSocket } from "../src/api/live";

export class FakeSocket implements LiveSocket {
  readonly url: string;
  binaryType = "";
  readyState = 1;
  onmessage: LiveSocket["onmessage"] = null;
  onclose: LiveSocket["onclose"] = null;
  sent: unknown[] = [];
  closed = false;

  constructor(url: string) {
    this.url = url;
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(): void {
    this.closed = true;
  }

  text(frame: object): void {
    act(() => { this.onmessage?.({ data: JSON.stringify(frame) }); });
  }

  image(): void {
    act(() => { this.onmessage?.({ data: new Blob(["jpeg"], { type: "image/jpeg" }) }); });
  }

  end(code: number, reason = ""): void {
    this.readyState = 3;
    act(() => { this.onclose?.({ code, reason }); });
  }
}

export const HEADER = { t: "frame", w: 1280, h: 800, scale: 1, top: 0, sx: 0, sy: 0 } as const;

// The screen once its first frame is in, on a page at ``url``.
export function showFrame(socket: FakeSocket, url = "https://shop.example/login"): void {
  socket.text({ t: "page", url, title: "Sign in" });
  socket.text(HEADER);
  socket.image();
}
```

Create `web/tests/liveInput.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  isAllowedKey, keyFrame, MAX_CLICKS, modsOf, mouseFrame, NAMED_KEYS, pasteFrame, PASTE_MAX_CHARS, siteOf,
  toFrameSpace, wheelFrame, WHEEL_MAX_DELTA,
} from "../src/lib/liveInput";
import type { LiveFrameHeader } from "../src/api/live";

const FRAME: LiveFrameHeader = { t: "frame", w: 1280, h: 800, scale: 1, top: 0, sx: 0, sy: 0 };
const BOX = { left: 10, top: 20, width: 640, height: 400 };
const NO_MODS = { altKey: false, ctrlKey: false, metaKey: false, shiftKey: false };

describe("liveInput", () => {
  it("maps a point on the shown image into the frame's own space", () => {
    expect(toFrameSpace(330, 220, BOX, FRAME)).toEqual({ x: 640, y: 400 });
    expect(toFrameSpace(10, 20, BOX, FRAME)).toEqual({ x: 0, y: 0 });
  });

  it("drops a point outside the image, or an image with no size", () => {
    expect(toFrameSpace(5, 220, BOX, FRAME)).toBeNull();
    expect(toFrameSpace(330, 621, BOX, FRAME)).toBeNull();
    expect(toFrameSpace(330, 220, { ...BOX, width: 0 }, FRAME)).toBeNull();
  });

  it("sends the server's named keys and any one printable character, and nothing else", () => {
    for (const key of NAMED_KEYS) expect(isAllowedKey(key)).toBe(true);
    for (const key of ["a", "Z", "7", "@", " ", "é", "€"]) expect(isAllowedKey(key)).toBe(true);
    for (const key of ["Shift", "Meta", "F5", "Home", "Dead", "Process", "\n", " ", ""]) {
      expect(isAllowedKey(key)).toBe(false);
    }
  });

  it("builds a key frame with CDP's modifier bits, and drops a code it can't send", () => {
    expect(keyFrame("down", { key: "A", code: "KeyA", ...NO_MODS, shiftKey: true }))
      .toEqual({ t: "key", kind: "down", key: "A", code: "KeyA", mods: 8 });
    expect(modsOf({ altKey: true, ctrlKey: true, metaKey: true, shiftKey: true })).toBe(15);
    expect(keyFrame("up", { key: "x", code: "weird code!", ...NO_MODS }))
      .toEqual({ t: "key", kind: "up", key: "x", code: "", mods: 0 });
  });

  it("leaves Cmd+V and Ctrl+V to the paste, and refuses keys the server won't take", () => {
    expect(keyFrame("down", { key: "v", code: "KeyV", ...NO_MODS, metaKey: true })).toBeNull();
    expect(keyFrame("down", { key: "V", code: "KeyV", ...NO_MODS, ctrlKey: true })).toBeNull();
    expect(keyFrame("down", { key: "Shift", code: "ShiftLeft", ...NO_MODS, shiftKey: true })).toBeNull();
  });

  it("builds mouse frames: a move carries no button, a click its count", () => {
    expect(mouseFrame("down", { x: 1, y: 2 }, 0, 2, 0))
      .toEqual({ t: "mouse", kind: "down", x: 1, y: 2, button: "left", clicks: 2, mods: 0 });
    expect(mouseFrame("up", { x: 1, y: 2 }, 2, 9, 4))
      .toEqual({ t: "mouse", kind: "up", x: 1, y: 2, button: "right", clicks: MAX_CLICKS, mods: 4 });
    expect(mouseFrame("move", { x: 1, y: 2 }, 0, 0, 0))
      .toEqual({ t: "mouse", kind: "move", x: 1, y: 2, button: "none", clicks: 0, mods: 0 });
  });

  it("clamps a wheel step to what the server takes", () => {
    expect(wheelFrame({ x: 1, y: 2 }, 0, 120)).toEqual({ t: "wheel", x: 1, y: 2, dx: 0, dy: 120 });
    expect(wheelFrame({ x: 1, y: 2 }, -9999, 9999))
      .toEqual({ t: "wheel", x: 1, y: 2, dx: -WHEEL_MAX_DELTA, dy: WHEEL_MAX_DELTA });
  });

  it("pastes text up to the server's limit", () => {
    expect(pasteFrame("ana@example.com")).toEqual({ t: "text", text: "ana@example.com" });
    expect(pasteFrame("x".repeat(PASTE_MAX_CHARS))).not.toBeNull();
    expect(pasteFrame("x".repeat(PASTE_MAX_CHARS + 1))).toBeNull();
    expect(pasteFrame("")).toBeNull();
  });

  it("knows a web page's site, and nothing else's", () => {
    expect(siteOf("https://Login.Example/orders?x=1")).toBe("login.example");
    for (const url of ["about:blank", "data:text/html,x", "", undefined, "not a url"]) expect(siteOf(url)).toBe("");
  });
});
```

Create `web/tests/LiveScreen.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LiveScreen, TOO_LONG_TO_PASTE } from "../src/components/profile/LiveScreen";
import { ApiError } from "../src/api/client";
import { MOVE_INTERVAL_MS } from "../src/lib/liveInput";
import { makeBot } from "./fixtures";
import { FakeSocket, showFrame } from "./liveSocket";

const live = { showWindow: vi.fn() };
vi.mock("../src/api/live", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/api/live")>()),
  showWindow: (id: string) => live.showWindow(id),
}));

const BOT = makeBot({ id: "bot-1", name: "Scout" });
const NO_SITE = "Roost can't tell which site that account is for. Give it back without one.";
const props = { onGiveBack: vi.fn(), onEnded: vi.fn(), onOpen: vi.fn() };
let sockets: FakeSocket[] = [];
let frames = 0;
const connect = (url: string) => {
  const socket = new FakeSocket(url);
  sockets.push(socket);
  return socket;
};
const last = () => sockets[sockets.length - 1];
const surface = () => screen.getByRole("application", { name: "Scout’s page" });
const renderScreen = (site?: string) => render(<LiveScreen bot={BOT} site={site} {...props} connect={connect} />);

beforeEach(() => {
  sockets = [];
  frames = 0;
  URL.createObjectURL = vi.fn(() => `blob:frame-${(frames += 1)}`);
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue(
    { left: 0, top: 0, width: 640, height: 400, right: 640, bottom: 400, x: 0, y: 0, toJSON: () => ({}) } as DOMRect,
  );
  props.onGiveBack.mockResolvedValue(undefined);
  props.onOpen.mockResolvedValue(undefined);
  live.showWindow.mockResolvedValue({ shown: true });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  [...Object.values(props), ...Object.values(live)].forEach((mock) => mock.mockReset());
});

describe("LiveScreen", () => {
  it("connects to the bot's live screen and shows each frame as it comes", () => {
    renderScreen();
    expect(last().url).toMatch(/^ws:\/\/[^/]+\/api\/bots\/bot-1\/live$/);
    expect(last().binaryType).toBe("blob");
    expect(screen.getByText("Connecting to Scout’s screen…")).toBeInTheDocument();
    showFrame(last());
    expect(screen.getByRole("img", { name: "Scout’s live screen" })).toHaveAttribute("src", "blob:frame-1");
    expect(screen.getByRole("textbox", { name: "Address" })).toHaveValue("https://shop.example/login");
    last().text({ t: "frame", w: 1280, h: 800, scale: 1, top: 0, sx: 0, sy: 0 });
    last().image();
    expect(screen.getByRole("img", { name: "Scout’s live screen" })).toHaveAttribute("src", "blob:frame-2");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:frame-1");
  });

  it("a click goes out as a press and a release in the frame's own space", () => {
    renderScreen();
    showFrame(last());
    fireEvent.mouseDown(surface(), { clientX: 320, clientY: 100, button: 0, detail: 1 });
    fireEvent.mouseUp(surface(), { clientX: 320, clientY: 100, button: 0, detail: 1 });
    expect(last().sent).toEqual([
      { t: "mouse", kind: "down", x: 640, y: 200, button: "left", clicks: 1, mods: 0 },
      { t: "mouse", kind: "up", x: 640, y: 200, button: "left", clicks: 1, mods: 0 },
    ]);
  });

  it("pointer moves go out at most every MOVE_INTERVAL_MS", () => {
    const now = vi.spyOn(Date, "now").mockReturnValue(1000);
    renderScreen();
    showFrame(last());
    fireEvent.mouseMove(surface(), { clientX: 10, clientY: 10 });
    fireEvent.mouseMove(surface(), { clientX: 20, clientY: 20 });
    now.mockReturnValue(1000 + MOVE_INTERVAL_MS);
    fireEvent.mouseMove(surface(), { clientX: 30, clientY: 30 });
    expect(last().sent).toEqual([
      { t: "mouse", kind: "move", x: 20, y: 20, button: "none", clicks: 0, mods: 0 },
      { t: "mouse", kind: "move", x: 60, y: 60, button: "none", clicks: 0, mods: 0 },
    ]);
  });

  it("typing sends the keys the server takes, and nothing else", () => {
    renderScreen();
    showFrame(last());
    fireEvent.keyDown(surface(), { key: "a", code: "KeyA" });
    fireEvent.keyUp(surface(), { key: "a", code: "KeyA" });
    fireEvent.keyDown(surface(), { key: "Enter", code: "Enter" });
    fireEvent.keyDown(surface(), { key: "F5", code: "F5" });
    fireEvent.keyDown(surface(), { key: "Shift", code: "ShiftLeft", shiftKey: true });
    fireEvent.keyDown(surface(), { key: "v", code: "KeyV", metaKey: true });
    expect(last().sent).toEqual([
      { t: "key", kind: "down", key: "a", code: "KeyA", mods: 0 },
      { t: "key", kind: "up", key: "a", code: "KeyA", mods: 0 },
      { t: "key", kind: "down", key: "Enter", code: "Enter", mods: 0 },
    ]);
  });

  it("Cmd+V pastes the clipboard's text, and a paste that is too long is refused with a note", () => {
    renderScreen();
    showFrame(last());
    fireEvent.paste(surface(), { clipboardData: { getData: () => "ana@example.com" } });
    fireEvent.paste(surface(), { clipboardData: { getData: () => "x".repeat(2001) } });
    expect(last().sent).toEqual([{ t: "text", text: "ana@example.com" }]);
    expect(screen.getByRole("status")).toHaveTextContent(TOO_LONG_TO_PASTE);
  });

  it("the wheel scrolls the bot's page, never the Roost page around it", () => {
    renderScreen();
    showFrame(last());
    const wheel = new WheelEvent("wheel", { clientX: 320, clientY: 100, deltaY: 120, bubbles: true, cancelable: true });
    act(() => { surface().dispatchEvent(wheel); });
    expect(wheel.defaultPrevented).toBe(true);
    expect(last().sent).toEqual([{ t: "wheel", x: 640, y: 200, dx: 0, dy: 120 }]);
  });

  it("Back, Reload and Show window on Mac", async () => {
    renderScreen();
    showFrame(last());
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    await userEvent.click(screen.getByRole("button", { name: "Reload" }));
    await userEvent.click(screen.getByRole("button", { name: "Show window on Mac" }));
    expect(last().sent).toEqual([{ t: "nav", action: "back" }, { t: "nav", action: "reload" }]);
    expect(live.showWindow).toHaveBeenCalledWith("bot-1");
  });

  it("a failed Show window on Mac says why", async () => {
    live.showWindow.mockRejectedValue(new ApiError(409, "asleep"));
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Show window on Mac" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("asleep");
  });

  it("Give it back asks which account you used on the page's site, then gives the computer back", async () => {
    renderScreen();
    showFrame(last());
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    const field = screen.getByLabelText("Which account did you use?");
    expect(field).toHaveAttribute("placeholder", "On shop.example, for example work email");
    await userEvent.type(field, "  work email ");
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(props.onGiveBack).toHaveBeenCalledWith("work email");
  });

  it("an empty account gives it back with none, and Cancel keeps control", async () => {
    renderScreen();
    showFrame(last());
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Give it back" })).not.toBeInTheDocument();
    expect(props.onGiveBack).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(props.onGiveBack).toHaveBeenCalledWith(null);
  });

  it("a page with no site asks for no account, and a Stuck card's site wins over the page's", async () => {
    renderScreen();
    showFrame(last(), "about:blank");
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(screen.queryByLabelText("Which account did you use?")).not.toBeInTheDocument();
    cleanup();
    renderScreen("login.example");
    showFrame(last(), "https://accounts.example/");
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(screen.getByLabelText("Which account did you use?"))
      .toHaveAttribute("placeholder", "On login.example, for example work email");
  });

  it("a give-back that fails says why and keeps the form", async () => {
    props.onGiveBack.mockRejectedValue(new ApiError(400, NO_SITE));
    renderScreen();
    showFrame(last());
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    await userEvent.type(screen.getByLabelText("Which account did you use?"), "work email");
    await userEvent.click(screen.getByRole("button", { name: "Give it back" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(NO_SITE);
    expect(screen.getByRole("form", { name: "Give it back" })).toBeInTheDocument();
  });

  it("stops sending once the server says it was given back, and tells the tab", async () => {
    // Review Focus 4, in the face: a socket the server closed is never written to again.
    renderScreen();
    showFrame(last());
    last().end(4000, "Given back.");
    expect(props.onEnded).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(last().sent).toEqual([]);
    expect(screen.queryByRole("application")).not.toBeInTheDocument();
  });

  it("a refused live screen says why", () => {
    renderScreen();
    last().end(4403, "Live control works only on this Mac for now.");
    expect(screen.getByText("Live control works only on this Mac for now.")).toBeInTheDocument();
    expect(props.onEnded).not.toHaveBeenCalled();
  });

  it("an asleep computer offers Open it, then connects again", async () => {
    renderScreen();
    last().end(4410, "asleep");
    expect(screen.getByText(/Scout’s computer is asleep/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open it" }));
    expect(props.onOpen).toHaveBeenCalled();
    expect(sockets).toHaveLength(2);
  });

  it("an ended live screen offers Retry, never a frozen last frame", async () => {
    // Review Focus 5, in the face: Brave crashed or the keeper restarted.
    renderScreen();
    showFrame(last());
    last().end(4503, "The bot's computer stopped answering.");
    expect(screen.queryByRole("img", { name: "Scout’s live screen" })).not.toBeInTheDocument();
    expect(screen.getByText(/Can’t reach Scout’s screen/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(sockets).toHaveLength(2);
  });

  it("a notice from the server shows until the next input", () => {
    renderScreen();
    showFrame(last());
    last().text({ t: "notice", text: "That didn't reach the page. Try again." });
    expect(screen.getByRole("status")).toHaveTextContent("That didn't reach the page. Try again.");
    fireEvent.keyDown(surface(), { key: "a", code: "KeyA" });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("leaving closes the socket and frees the frame", () => {
    const view = renderScreen();
    showFrame(last());
    const socket = last();
    view.unmount();
    expect(socket.closed).toBe(true);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:frame-1");
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/liveInput.test.ts tests/LiveScreen.test.tsx`
Expected: FAIL: both files fail to import (`Failed to resolve import "../src/lib/liveInput"` and `"../src/components/profile/LiveScreen"`).

- [ ] **Step 4: The socket's API (`web/src/api/live.ts`)**

Create `web/src/api/live.ts`:

```ts
// web/src/api/live.ts — live control (design §2): the live screen's socket, its frames, and Show window on Mac.
import { apiRequest } from "./client";

// The codes the server closes a live screen with (roost/constants.py LIVE_CLOSE_*).
export const LIVE_CLOSE = {
  givenBack: 4000, signIn: 4401, refused: 4403, notFound: 4404, notHeld: 4409, asleep: 4410, unavailable: 4503,
} as const;

// Server to face. A "frame" header always comes just before its JPEG (a binary frame).
export interface LiveFrameHeader { t: "frame"; w: number; h: number; scale: number; top: number; sx: number; sy: number }
export interface LivePageFrame { t: "page"; url: string; title: string }
export interface LiveNoticeFrame { t: "notice"; text: string }
export type LiveServerFrame = LiveFrameHeader | LivePageFrame | LiveNoticeFrame;

// Face to server: exactly what roost/desk/live_input.py accepts. Points are in the frame's own space (w × h).
export type LiveButton = "none" | "left" | "middle" | "right";
export type LiveInputFrame =
  | { t: "mouse"; kind: "down" | "up" | "move"; x: number; y: number; button: LiveButton; clicks: number; mods: number }
  | { t: "wheel"; x: number; y: number; dx: number; dy: number }
  | { t: "key"; kind: "down" | "up"; key: string; code: string; mods: number }
  | { t: "text"; text: string }
  | { t: "nav"; action: "back" | "reload" };

// The slice of a browser WebSocket the live screen uses, so tests can hand it a fake.
export interface LiveSocket {
  binaryType: string;
  readonly readyState: number;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number; reason: string }) => void) | null;
  send(data: string): void;
  close(): void;
}
export type LiveSocketFactory = (url: string) => LiveSocket;

// Same origin, as /api/events: the dev server proxies it (ws: true), and the gateway serves it in production.
export function liveUrl(botId: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/bots/${encodeURIComponent(botId)}/live`;
}

export const openLiveSocket: LiveSocketFactory = (url) => new WebSocket(url) as unknown as LiveSocket;

export const showWindow = (botId: string) =>
  apiRequest<{ shown: boolean }>("POST", `/api/bots/${encodeURIComponent(botId)}/window/show`);
```

- [ ] **Step 5: What the screen sends (`web/src/lib/liveInput.ts`)**

Create `web/src/lib/liveInput.ts`:

```ts
// web/src/lib/liveInput.ts — what the live screen sends for a pointer, a wheel, a key or a paste (live
// control, design §2). Pure functions. The server checks every frame again, and drops what it doesn't allow.
import type { LiveButton, LiveFrameHeader, LiveInputFrame } from "../api/live";

// The server's own lists and limits (roost/constants.py LIVE_NAMED_KEYS, LIVE_PASTE_MAX_CHARS,
// LIVE_MAX_CLICKS, LIVE_WHEEL_MAX_DELTA).
export const NAMED_KEYS: ReadonlySet<string> = new Set([
  "Enter", "Tab", "Backspace", "Delete", "Escape", "ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown",
]);
export const PASTE_MAX_CHARS = 2000;
export const MAX_CLICKS = 3;
export const WHEEL_MAX_DELTA = 2000;
// A pointer move goes out at most this often (the server takes 100 inputs a second).
export const MOVE_INTERVAL_MS = 50;

const KEY_CODE = /^[A-Za-z0-9]{0,32}$/;
// One printable character: not a control, format or separator character (a plain space is allowed apart).
const PRINTABLE = /^[^\p{C}\p{Z}]$/u;
const BUTTONS: readonly LiveButton[] = ["left", "middle", "right"];

export interface Modifiers { altKey: boolean; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean }
export interface Box { left: number; top: number; width: number; height: number }
export interface FramePoint { x: number; y: number }

// CDP's modifier bits: Alt 1, Ctrl 2, Meta 4, Shift 8.
export function modsOf(event: Modifiers): number {
  return (event.altKey ? 1 : 0) | (event.ctrlKey ? 2 : 0) | (event.metaKey ? 4 : 0) | (event.shiftKey ? 8 : 0);
}

export function isAllowedKey(key: string): boolean {
  return NAMED_KEYS.has(key) || key === " " || PRINTABLE.test(key);
}

// Cmd+V or Ctrl+V: the paste event sends the clipboard's text instead of the key.
export function isPasteShortcut(event: { key: string } & Modifiers): boolean {
  return (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "v";
}

// A point on the shown image, in the frame's own space (its w × h); null outside the image.
export function toFrameSpace(clientX: number, clientY: number, box: Box, frame: LiveFrameHeader): FramePoint | null {
  if (box.width <= 0 || box.height <= 0) return null;
  const x = ((clientX - box.left) / box.width) * frame.w;
  const y = ((clientY - box.top) / box.height) * frame.h;
  if (x < 0 || y < 0 || x > frame.w || y > frame.h) return null;
  return { x, y };
}

export function keyFrame(kind: "down" | "up", event: { key: string; code: string } & Modifiers): LiveInputFrame | null {
  if (!isAllowedKey(event.key) || isPasteShortcut(event)) return null;
  return { t: "key", kind, key: event.key, code: KEY_CODE.test(event.code) ? event.code : "", mods: modsOf(event) };
}

export function mouseFrame(kind: "down" | "up" | "move", point: FramePoint, button: number, detail: number,
  mods: number): LiveInputFrame {
  const moving = kind === "move";
  return {
    t: "mouse", kind, x: point.x, y: point.y,
    button: moving ? "none" : (BUTTONS[button] ?? "left"),
    clicks: moving ? 0 : Math.min(Math.max(detail, 1), MAX_CLICKS),
    mods,
  };
}

const clampWheel = (delta: number) => Math.max(-WHEEL_MAX_DELTA, Math.min(WHEEL_MAX_DELTA, delta));

export function wheelFrame(point: FramePoint, dx: number, dy: number): LiveInputFrame {
  return { t: "wheel", x: point.x, y: point.y, dx: clampWheel(dx), dy: clampWheel(dy) };
}

// A paste's text, or null when it is empty or longer than the server takes.
export function pasteFrame(text: string): LiveInputFrame | null {
  if (!text || text.length > PASTE_MAX_CHARS) return null;
  return { t: "text", text };
}

// The site a page is on, for "Which account did you use?": its host for a web page, else "".
export function siteOf(url: string | undefined): string {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.hostname : "";
  } catch {
    return ""; // not an address at all: no site to name
  }
}
```

- [ ] **Step 6: The socket's state, the form and the screen**

Create `web/src/hooks/useLiveScreen.ts`:

```ts
// web/src/hooks/useLiveScreen.ts — one live screen's socket (live control, design §2). It connects to
// /api/bots/{id}/live, shows each frame as it comes (the JSON header first, then the JPEG), follows the
// page's address and the server's notices, and says how the screen ended. retry() opens a new socket.
// Once the server has closed the socket, nothing more is ever sent on it.
import { useCallback, useEffect, useRef, useState } from "react";
import { LIVE_CLOSE, liveUrl, openLiveSocket } from "../api/live";
import type { LiveFrameHeader, LiveInputFrame, LiveServerFrame, LiveSocket, LiveSocketFactory } from "../api/live";

export type LiveStatus = "connecting" | "live" | "ended" | "asleep" | "refused" | "unreachable";

export interface LiveScreenState {
  status: LiveStatus;
  image: string | null;
  frame: LiveFrameHeader | null;
  page: { url: string; title: string } | null;
  notice: string | null;
  reason: string;
}

const CONNECTING: LiveScreenState = { status: "connecting", image: null, frame: null, page: null, notice: null, reason: "" };
const SOCKET_OPEN = 1;
const REFUSED: ReadonlySet<number> = new Set([LIVE_CLOSE.refused, LIVE_CLOSE.signIn, LIVE_CLOSE.notFound]);

// How a close code ends the screen: given back or no longer held ends it; asleep offers Open it; a refusal
// shows its reason; anything else (the computer stopped answering, the network) offers Retry.
export function statusFor(code: number): LiveStatus {
  if (code === LIVE_CLOSE.givenBack || code === LIVE_CLOSE.notHeld) return "ended";
  if (code === LIVE_CLOSE.asleep) return "asleep";
  if (REFUSED.has(code)) return "refused";
  return "unreachable";
}

function parseFrame(data: string): LiveServerFrame | null {
  try {
    const frame: unknown = JSON.parse(data);
    return typeof frame === "object" && frame !== null && "t" in frame ? (frame as LiveServerFrame) : null;
  } catch {
    console.warn("live screen: a frame that is not JSON was skipped");
    return null;
  }
}

function withText(state: LiveScreenState, frame: LiveServerFrame): LiveScreenState {
  if (frame.t === "page") return { ...state, page: { url: frame.url, title: frame.title } };
  if (frame.t === "notice") return { ...state, notice: frame.text };
  return state;
}

export function useLiveScreen(botId: string, connect: LiveSocketFactory = openLiveSocket) {
  const [state, setState] = useState<LiveScreenState>(CONNECTING);
  const [attempt, setAttempt] = useState(0);
  const socketRef = useRef<LiveSocket | null>(null);
  useEffect(() => {
    let image: string | null = null;
    let header: LiveFrameHeader | null = null;
    let open = true;
    setState(CONNECTING);
    const socket = connect(liveUrl(botId));
    socket.binaryType = "blob";
    socketRef.current = socket;
    socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        const frame = parseFrame(event.data);
        if (frame?.t === "frame") header = frame;
        else if (frame) setState((current) => withText(current, frame));
        return;
      }
      if (!(event.data instanceof Blob) || !header) return;
      const shown = header;
      const previous = image;
      const next = URL.createObjectURL(event.data);
      image = next;
      setState((current) => ({ ...current, status: "live", image: next, frame: shown }));
      if (previous) URL.revokeObjectURL(previous);
    };
    socket.onclose = (event) => {
      open = false;
      socketRef.current = null;
      setState((current) => ({ ...current, status: statusFor(event.code), reason: event.reason }));
    };
    return () => {
      socket.onmessage = null;
      socket.onclose = null;
      socketRef.current = null;
      if (open) socket.close();
      if (image) URL.revokeObjectURL(image);
    };
  }, [botId, connect, attempt]);
  const send = useCallback((frame: LiveInputFrame) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === SOCKET_OPEN) socket.send(JSON.stringify(frame));
  }, []);
  const clearNotice = useCallback(
    () => setState((current) => (current.notice ? { ...current, notice: null } : current)), [],
  );
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { state, send, retry, clearNotice };
}
```

Create `web/src/components/GiveBackForm.tsx`:

```tsx
// web/src/components/GiveBackForm.tsx — Give it back, with the optional "Which account did you use?"
// (live control, design §1). Roost keeps only that name, in the bot's Vault: site logins, never a
// password. With no site to name (about:blank, a card with no address) it asks nothing.
import { useId, useState, type FormEvent } from "react";

export const ACCOUNT_MAX_CHARS = 100; // roost/constants.py SITE_LOGIN_LABEL_MAX_CHARS

export interface GiveBackFormProps {
  site: string;
  botName: string;
  // Gives the computer back. It handles its own errors and resolves either way.
  onConfirm: (account: string | null) => Promise<void>;
  onCancel: () => void;
}

export function GiveBackForm({ site, botName, onConfirm, onCancel }: GiveBackFormProps) {
  const [account, setAccount] = useState("");
  const [busy, setBusy] = useState(false);
  const fieldId = useId();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    try {
      await onConfirm(account.trim() || null);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="give-back" aria-label="Give it back" onSubmit={(event) => void submit(event)}>
      {site ? (
        <div className="give-back__field">
          <label className="give-back__label" htmlFor={fieldId}>Which account did you use?</label>
          <input id={fieldId} className="give-back__input" value={account} maxLength={ACCOUNT_MAX_CHARS}
            placeholder={`On ${site}, for example work email`} aria-describedby={`${fieldId}-hint`}
            onChange={(event) => setAccount(event.target.value)} />
          <p id={`${fieldId}-hint`} className="give-back__hint">
            Optional. {botName} remembers it; your password is never kept.
          </p>
        </div>
      ) : null}
      <div className="give-back__actions">
        <button type="submit" className="btn btn--danger btn--small" disabled={busy}>Give it back</button>
        <button type="button" className="btn btn--quiet btn--small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
```

Create `web/src/components/profile/LiveScreen.tsx`:

```tsx
// web/src/components/profile/LiveScreen.tsx — the live screen (live control, design §1). The bot's page
// moves in real time and fills the Computer view; you click, double-click, scroll, type and paste into it.
// A bar on top shows the page's address, Back, Reload, Show window on Mac and Give it back. The server
// follows pop-ups. What you type goes to that page and nowhere else.
import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent, type MouseEvent, type RefObject } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { GiveBackForm } from "../GiveBackForm";
import { describeError } from "../../api/client";
import * as liveApi from "../../api/live";
import type { LiveInputFrame, LiveSocketFactory } from "../../api/live";
import type { BotOut } from "../../api/types";
import { useLiveScreen, type LiveScreenState } from "../../hooks/useLiveScreen";
import {
  keyFrame, modsOf, MOVE_INTERVAL_MS, mouseFrame, pasteFrame, PASTE_MAX_CHARS, siteOf, toFrameSpace, wheelFrame,
} from "../../lib/liveInput";

export const TOO_LONG_TO_PASTE = `That’s too long to paste here (at most ${PASTE_MAX_CHARS} characters).`;

export interface LiveScreenProps {
  bot: BotOut;
  // The Stuck card's site when the bot is stuck: the account is kept for it. Else the page's own site.
  site?: string;
  // Gives the computer back; it throws, so the form can say why it failed.
  onGiveBack: (account: string | null) => Promise<void>;
  // The server ended the screen (given back elsewhere, or control no longer held): look again.
  onEnded: () => void;
  // Open it: start the bot's browser. The screen then connects again.
  onOpen: () => Promise<void>;
  connect?: LiveSocketFactory;
}

interface LiveInputHandlers {
  surface: RefObject<HTMLDivElement | null>;
  image: RefObject<HTMLImageElement | null>;
  onMouseDown: (event: MouseEvent) => void;
  onMouseUp: (event: MouseEvent) => void;
  onMouseMove: (event: MouseEvent) => void;
  onKeyDown: (event: KeyboardEvent) => void;
  onKeyUp: (event: KeyboardEvent) => void;
  onPaste: (event: ClipboardEvent) => void;
}

// The surface's handlers: every pointer, key and paste on it becomes a checked frame for the server.
function useLiveInput(state: LiveScreenState, send: (frame: LiveInputFrame) => void,
  onNotice: (text: string) => void): LiveInputHandlers {
  const surface = useRef<HTMLDivElement | null>(null);
  const image = useRef<HTMLImageElement | null>(null);
  const lastMove = useRef(0);
  const at = (clientX: number, clientY: number) => {
    const box = image.current?.getBoundingClientRect();
    return state.frame && box ? toFrameSpace(clientX, clientY, box, state.frame) : null;
  };
  // React's wheel listener is passive, so the Roost page would scroll too: a native one that can stop it.
  // It is bound again after every render, so it always sees the newest frame.
  useEffect(() => {
    const element = surface.current;
    if (!element) return undefined;
    const onWheel = (event: WheelEvent) => {
      const point = at(event.clientX, event.clientY);
      if (!point) return;
      event.preventDefault();
      send(wheelFrame(point, event.deltaX, event.deltaY));
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  });
  const mouse = (kind: "down" | "up" | "move") => (event: MouseEvent) => {
    if (kind === "move") {
      const now = Date.now();
      if (now - lastMove.current < MOVE_INTERVAL_MS) return;
      lastMove.current = now;
    }
    const point = at(event.clientX, event.clientY);
    if (!point) return;
    if (kind === "down") surface.current?.focus();
    send(mouseFrame(kind, point, event.button, event.detail, modsOf(event)));
  };
  const key = (kind: "down" | "up") => (event: KeyboardEvent) => {
    const frame = keyFrame(kind, event);
    if (!frame) return;
    event.preventDefault();
    send(frame);
  };
  const onPaste = (event: ClipboardEvent) => {
    event.preventDefault();
    const text = event.clipboardData.getData("text/plain");
    const frame = pasteFrame(text);
    if (frame) send(frame);
    else if (text) onNotice(TOO_LONG_TO_PASTE);
  };
  return {
    surface, image, onMouseDown: mouse("down"), onMouseUp: mouse("up"), onMouseMove: mouse("move"),
    onKeyDown: key("down"), onKeyUp: key("up"), onPaste,
  };
}

function LiveBar({ bot, url, givingBack, onSend, onGiveBack }: {
  bot: BotOut; url: string; givingBack: boolean; onSend: (frame: LiveInputFrame) => void; onGiveBack: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const show = async () => {
    setError(null);
    try {
      await liveApi.showWindow(bot.id);
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <div className="live-bar">
      <input className="live-bar__address" aria-label="Address" readOnly value={url} />
      <button type="button" className="btn btn--quiet btn--small" onClick={() => onSend({ t: "nav", action: "back" })}>Back</button>
      <button type="button" className="btn btn--quiet btn--small" onClick={() => onSend({ t: "nav", action: "reload" })}>Reload</button>
      <button type="button" className="btn btn--quiet btn--small" onClick={() => void show()}>Show window on Mac</button>
      {givingBack ? null : (
        <button type="button" className="btn btn--danger btn--small" onClick={onGiveBack}>Give it back</button>
      )}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}

function LiveContent({ bot, state, input, onOpen, onRetry }: {
  bot: BotOut; state: LiveScreenState; input: LiveInputHandlers; onOpen: () => void; onRetry: () => void;
}) {
  if (state.status === "live" && state.image) {
    return (
      <div ref={input.surface} className="live-screen__surface" role="application" aria-label={`${bot.name}’s page`}
        tabIndex={0} onMouseDown={input.onMouseDown} onMouseUp={input.onMouseUp} onMouseMove={input.onMouseMove}
        onKeyDown={input.onKeyDown} onKeyUp={input.onKeyUp} onPaste={input.onPaste}
        onContextMenu={(event) => event.preventDefault()}>
        <img ref={input.image} className="live-screen__image" src={state.image} alt={`${bot.name}’s live screen`}
          draggable={false} />
      </div>
    );
  }
  if (state.status === "asleep") {
    return <p className="screen-box__state">{bot.name}&rsquo;s computer is asleep · <button type="button" className="link-btn" onClick={onOpen}>Open it</button></p>;
  }
  if (state.status === "unreachable") {
    return <p className="screen-box__state">Can&rsquo;t reach {bot.name}&rsquo;s screen · <button type="button" className="link-btn" onClick={onRetry}>Retry</button></p>;
  }
  if (state.status === "refused" || state.status === "ended") {
    return <p className="screen-box__state">{state.reason || "The live screen was closed."}</p>;
  }
  return <p className="screen-box__state">Connecting to {bot.name}&rsquo;s screen&hellip;</p>;
}

export function LiveScreen({ bot, site, onGiveBack, onEnded, onOpen, connect }: LiveScreenProps) {
  const live = useLiveScreen(bot.id, connect);
  const [givingBack, setGivingBack] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const send = (frame: LiveInputFrame) => {
    setNotice(null);
    live.clearNotice();
    live.send(frame);
  };
  const input = useLiveInput(live.state, send, setNotice);
  const ended = live.state.status === "ended";
  useEffect(() => { if (ended) onEnded(); }, [ended, onEnded]);
  const open = async () => {
    setError(null);
    try {
      await onOpen();
      live.retry();
    } catch (err) {
      setError(describeError(err));
    }
  };
  const confirm = async (account: string | null) => {
    setError(null);
    try {
      await onGiveBack(account);
      setGivingBack(false);
    } catch (err) {
      setError(describeError(err));
    }
  };
  const shownNotice = notice ?? live.state.notice;
  return (
    <section className="live-screen" aria-label={`${bot.name}’s live screen`}>
      <LiveBar bot={bot} url={live.state.page?.url ?? ""} givingBack={givingBack} onSend={send}
        onGiveBack={() => setGivingBack(true)} />
      {givingBack ? (
        <GiveBackForm site={site || siteOf(live.state.page?.url)} botName={bot.name} onConfirm={confirm}
          onCancel={() => setGivingBack(false)} />
      ) : null}
      <div className="live-screen__box">
        <LiveContent bot={bot} state={live.state} input={input} onOpen={() => void open()} onRetry={live.retry} />
      </div>
      {shownNotice ? <p className="live-screen__notice" role="status">{shownNotice}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
```

Append this to the end of `web/src/styles/computer.css`:

```css

/* ---- The live screen (live control) ---------------------------------- */

.live-screen {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.live-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.live-bar__address {
  flex: 1 1 220px;
  min-width: 0;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: var(--pill);
  background: var(--sunken);
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
}

.live-screen__box {
  display: grid;
  place-items: center;
  min-height: 240px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--sunken);
}

.live-screen__surface {
  width: 100%;
  outline: none;
  cursor: default;
}

.live-screen__surface:focus-visible {
  box-shadow: inset 0 0 0 2px var(--emerald-edge);
}

/* The image keeps its own shape, so a point on it maps to the same point of the page. */
.live-screen__image {
  display: block;
  width: 100%;
  height: auto;
  user-select: none;
}

.live-screen__notice {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
}

/* ---- Give it back, with the account you used -------------------------- */

.give-back {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--surface);
}

.give-back__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.give-back__label {
  font-size: var(--fs-sm);
  font-weight: 600;
}

.give-back__input {
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--sunken);
  color: var(--text);
  font: inherit;
}

.give-back__hint {
  margin: 0;
  color: var(--faint);
  font-size: var(--fs-xs);
}

.give-back__actions {
  display: flex;
  gap: 8px;
}
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/liveInput.test.ts tests/LiveScreen.test.tsx`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm test`
Expected: PASS (every web test; nothing else imports the new files yet).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vocabulary.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm run build`
Expected: the type check and the build pass.

- [ ] **Step 8: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add web/src/api/live.ts web/src/lib/liveInput.ts web/src/hooks/useLiveScreen.ts web/src/components/GiveBackForm.tsx \
  web/src/components/profile/LiveScreen.tsx web/src/styles/computer.css web/tests/liveSocket.ts \
  web/tests/liveInput.test.ts web/tests/LiveScreen.test.tsx
git commit -m "feat: the live screen: the bot's page in real time, clicks, keys and paste, Give it back with the account"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the nine files is listed (`web/dist` is not tracked).

---

### Task 13: The web: the live screen on the Computer tab, from the Stuck card, and the Vault list

Design §1 and §2 "Profile":
- **The Computer tab.**
  - While you hold control, `LiveScreen` replaces the screenshot box, and the 3-second screenshots stop. Otherwise the screenshot box shows, with **Take control** and **Show window on Mac**.
  - Give it back goes through the live screen's form. With an open Stuck card it clears the card with `{ account }` (falling back to a plain give-back when the card was closed meanwhile, as today). Without one it calls `DELETE /control` with the account.
  - When the server ends the live screen (given back elsewhere), the tab looks again.
  - **Vault: site logins** lists the bot's accounts with **Forget**, and loads again after each Give it back.
- **The Stuck card.**
  - **Take control** takes control and opens the bot's Computer tab (`/bots/{id}/profile?tab=computer`), where the live screen is.
  - The Holding view says "You have control. Clear it on the live screen, then give it back.", links **Open the live screen**, and its **Give it back** opens the same form (the site is the card's host).
  - Try again, Done carry on, Use my main Brave and Give up are unchanged.
- **The API.**
  - `giveBack(botId, account = null)` sends `{ account }` only when there is one.
  - `clearStuck(cardId, body?)` takes `{ how?, account? }`. If a parallel change already gave `clearStuck` a second argument for `how`, merge both into this one body.
  - `vault.ts` adds `listSiteLogins` and `forgetSiteLogin`; `types.ts` adds `SiteLoginOut`.
- `ComputerTab.tsx`, `StuckCard.tsx` and their two test files are replaced whole (their current versions were read for this plan); every behaviour they had is kept unless this task names the change.

**Files:**
- Create: `web/src/api/vault.ts`, `web/src/components/profile/SiteLogins.tsx`, `web/tests/SiteLogins.test.tsx`, `web/tests/liveApi.test.ts`
- Modify:
  - `web/src/api/computer.ts`, `web/src/api/stuck.ts`, `web/src/api/types.ts`
  - `web/src/components/profile/ComputerTab.tsx` (whole file)
  - `web/src/components/StuckCard.tsx` (whole file)
  - `web/src/styles/computer.css` (append)
- Test: `web/tests/ComputerTab.test.tsx` and `web/tests/StuckCard.test.tsx` (whole files)

**Interfaces:**
- Consumes:
  - Task 12: `LiveScreen`, `GiveBackForm`, `api/live.ts` (`showWindow`, `openLiveSocket`), and `web/tests/liveSocket.ts` (`FakeSocket`, `showFrame`).
  - Task 11's routes; existing `useLiveState`, `mergeStuck`, `openStuckCards`, `stuckTitle`, `FoldCard`, `FoldedLine`, and `fixtures.ts` (`makeBot`, `makeStuckCard`, `STUCK_LINE`).
- Produces: `SiteLoginOut`, `listSiteLogins`, `forgetSiteLogin`, `giveBack(botId, account)`, `ClearBody`, `clearStuck(cardId, body?)`, `SiteLogins`; the Computer tab and Stuck card behaviour above, which Task 14's E2E drives.

- [ ] **Step 1: Path guard and disk guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: 8 or more. If fewer, stop and report.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/liveApi.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { giveBack } from "../src/api/computer";
import { showWindow } from "../src/api/live";
import { clearStuck } from "../src/api/stuck";
import { forgetSiteLogin, listSiteLogins } from "../src/api/vault";

function stubFetch(body: unknown) {
  const fetchMock = vi.fn(async (_path: string, _init: RequestInit) =>
    new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("the live control API", () => {
  it("gives the computer back with the account you used, or with no body at all", async () => {
    const fetchMock = stubFetch({ held: false, since: null });
    await giveBack("bot-1", "work email");
    await giveBack("bot-1");
    expect(fetchMock.mock.calls.map(([path, init]) => [init.method, path, init.body])).toEqual([
      ["DELETE", "/api/bots/bot-1/control", JSON.stringify({ account: "work email" })],
      ["DELETE", "/api/bots/bot-1/control", undefined],
    ]);
  });

  it("clears a Stuck card with the account you used, and still with no body", async () => {
    const fetchMock = stubFetch({});
    await clearStuck("card-1", { account: "work email" });
    await clearStuck("card-1");
    expect(fetchMock.mock.calls.map(([path, init]) => [init.method, path, init.body])).toEqual([
      ["POST", "/api/stuck/card-1/clear", JSON.stringify({ account: "work email" })],
      ["POST", "/api/stuck/card-1/clear", undefined],
    ]);
  });

  it("lists and forgets a bot's site logins, and shows its window", async () => {
    const fetchMock = stubFetch([]);
    await listSiteLogins("bot-1");
    await forgetSiteLogin("bot-1", "login-1");
    await showWindow("bot-1");
    expect(fetchMock.mock.calls.map(([path, init]) => [init.method, path])).toEqual([
      ["GET", "/api/bots/bot-1/site-logins"],
      ["DELETE", "/api/bots/bot-1/site-logins/login-1"],
      ["POST", "/api/bots/bot-1/window/show"],
    ]);
  });
});
```

Create `web/tests/SiteLogins.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SiteLogins } from "../src/components/profile/SiteLogins";
import { ApiError } from "../src/api/client";
import type { SiteLoginOut } from "../src/api/types";
import { makeBot } from "./fixtures";

const vault = { listSiteLogins: vi.fn(), forgetSiteLogin: vi.fn() };
vi.mock("../src/api/vault", () => ({
  listSiteLogins: (id: string) => vault.listSiteLogins(id),
  forgetSiteLogin: (id: string, loginId: string) => vault.forgetSiteLogin(id, loginId),
}));

const BOT = makeBot({ id: "bot-1", name: "Scout" });
const login = (id: string, host: string, label: string): SiteLoginOut =>
  ({ id, bot_id: "bot-1", host, label, created_at: "x", updated_at: "x" });
const LOGINS = [login("l-2", "shop.example", "ana@home"), login("l-1", "github.com", "work email")];

beforeEach(() => {
  vault.listSiteLogins.mockResolvedValue(LOGINS);
  vault.forgetSiteLogin.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); Object.values(vault).forEach((mock) => mock.mockReset()); });

describe("SiteLogins", () => {
  it("lists the accounts the bot is signed in with, as the server orders them", async () => {
    render(<SiteLogins bot={BOT} version={0} />);
    const list = await screen.findByRole("list", { name: "Scout’s site logins" });
    expect(within(list).getAllByRole("listitem").map((row) => row.textContent)).toEqual([
      "shop.exampleana@homeForget", "github.comwork emailForget",
    ]);
    expect(screen.getByRole("region", { name: "Vault: site logins" })).toHaveTextContent("Passwords are never kept.");
    expect(vault.listSiteLogins).toHaveBeenCalledWith("bot-1");
  });

  it("Forget removes one", async () => {
    render(<SiteLogins bot={BOT} version={0} />);
    await userEvent.click(await screen.findByRole("button", { name: "Forget github.com" }));
    expect(vault.forgetSiteLogin).toHaveBeenCalledWith("bot-1", "l-1");
    expect(screen.queryByText("github.com")).not.toBeInTheDocument();
    expect(screen.getByText("shop.example")).toBeInTheDocument();
  });

  it("a failed Forget says why and keeps the row", async () => {
    vault.forgetSiteLogin.mockRejectedValue(new ApiError(503, "Something went wrong."));
    render(<SiteLogins bot={BOT} version={0} />);
    await userEvent.click(await screen.findByRole("button", { name: "Forget github.com" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong.");
    expect(screen.getByText("github.com")).toBeInTheDocument();
  });

  it("with none it says how one is added", async () => {
    vault.listSiteLogins.mockResolvedValue([]);
    render(<SiteLogins bot={BOT} version={0} />);
    expect(await screen.findByText(/None yet/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("a failed list says why", async () => {
    vault.listSiteLogins.mockRejectedValue(new ApiError(500, "Could not load the site logins."));
    render(<SiteLogins bot={BOT} version={0} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the site logins.");
  });

  it("loads again when the version changes", async () => {
    const view = render(<SiteLogins bot={BOT} version={0} />);
    await screen.findByRole("list", { name: "Scout’s site logins" });
    view.rerender(<SiteLogins bot={BOT} version={1} />);
    await vi.waitFor(() => expect(vault.listSiteLogins).toHaveBeenCalledTimes(2));
  });
});
```

Replace the whole of `web/tests/ComputerTab.test.tsx` with:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ComputerTab, SCREEN_REFRESH_MS } from "../src/components/profile/ComputerTab";
import { ApiError } from "../src/api/client";
import type { StuckCardOut } from "../src/api/types";
import { makeBot, makeStuckCard } from "./fixtures";
import { FakeSocket, showFrame } from "./liveSocket";

const computer = { fetchScreen: vi.fn(), getControl: vi.fn(), takeControl: vi.fn(), giveBack: vi.fn() };
const desk = { getDeskStatus: vi.fn(), startBrowser: vi.fn(), stopBrowser: vi.fn(), execWorkspace: vi.fn() };
vi.mock("../src/api/computer", () => ({
  fetchScreen: (id: string) => computer.fetchScreen(id), getControl: (id: string) => computer.getControl(id),
  takeControl: (id: string) => computer.takeControl(id), giveBack: (...args: unknown[]) => computer.giveBack(...args),
}));
const stuck = { listStuck: vi.fn(), clearStuck: vi.fn() };
vi.mock("../src/api/stuck", () => ({
  listStuck: () => stuck.listStuck(), clearStuck: (...args: unknown[]) => stuck.clearStuck(...args),
}));
const vault = { listSiteLogins: vi.fn(), forgetSiteLogin: vi.fn() };
vi.mock("../src/api/vault", () => ({
  listSiteLogins: (id: string) => vault.listSiteLogins(id),
  forgetSiteLogin: (id: string, loginId: string) => vault.forgetSiteLogin(id, loginId),
}));
// The live screens this page opened, newest last.
let sockets: FakeSocket[] = [];
const live = { showWindow: vi.fn() };
vi.mock("../src/api/live", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../src/api/live")>()),
  openLiveSocket: (url: string) => {
    const socket = new FakeSocket(url);
    sockets.push(socket);
    return socket;
  },
  showWindow: (id: string) => live.showWindow(id),
}));
// The live stuck_card frames this page has heard, set per test.
let liveCards: Record<string, StuckCardOut> = {};
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ stuckCards: liveCards }) }));
vi.mock("../src/api/desk", () => ({
  getDeskStatus: (id: string) => desk.getDeskStatus(id), startBrowser: (id: string) => desk.startBrowser(id),
  stopBrowser: (id: string) => desk.stopBrowser(id), execWorkspace: (id: string, c: string) => desk.execWorkspace(id, c),
}));

const BOT = makeBot({ id: "bot-1", name: "Scout" });
const CARD = makeStuckCard({ thread_id: "t-2" });
const HELD = { held: true, since: "2026-10-14T10:00:00Z" };
const FREE = { held: false, since: null };
const renderTab = () => render(<MemoryRouter><ComputerTab bot={BOT} /></MemoryRouter>);
const lastSocket = () => sockets[sockets.length - 1];
const giveItBack = () => userEvent.click(screen.getByRole("button", { name: "Give it back" }));

beforeEach(() => {
  sockets = [];
  URL.createObjectURL = vi.fn(() => "blob:screen");
  URL.revokeObjectURL = vi.fn();
  computer.getControl.mockResolvedValue(FREE);
  computer.fetchScreen.mockResolvedValue({ kind: "asleep" });
  computer.giveBack.mockResolvedValue(FREE);
  desk.getDeskStatus.mockResolvedValue({ browser: "stopped", workspace: "absent" });
  stuck.listStuck.mockResolvedValue([]);
  stuck.clearStuck.mockResolvedValue({ ...CARD, state: "cleared", closed_at: "2026-10-14T10:05:00Z" });
  vault.listSiteLogins.mockResolvedValue([]);
  vault.forgetSiteLogin.mockResolvedValue(undefined);
  live.showWindow.mockResolvedValue({ shown: true });
  liveCards = {};
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  [...Object.values(computer), ...Object.values(desk), ...Object.values(stuck), ...Object.values(vault),
    ...Object.values(live)].forEach((mock) => mock.mockReset());
});

describe("ComputerTab", () => {
  it("a sleeping computer says so; Open it starts the browser, then the screen shows", async () => {
    computer.fetchScreen.mockResolvedValueOnce({ kind: "asleep" }).mockResolvedValue({ kind: "image", blob: new Blob(["x"]) });
    desk.startBrowser.mockResolvedValue({ browser: "running", workspace: "absent" });
    renderTab();
    expect(await screen.findByText(/Scout’s computer is asleep/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open it" }));
    expect(desk.startBrowser).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByRole("img", { name: "Scout’s screen" })).toHaveAttribute("src", "blob:screen");
  });

  it("refreshes about every 3 seconds only while the page is visible", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    computer.fetchScreen.mockResolvedValue({ kind: "image", blob: new Blob(["x"]) });
    renderTab();
    await act(async () => { await vi.advanceTimersByTimeAsync(SCREEN_REFRESH_MS); });
    const calls = computer.fetchScreen.mock.calls.length;
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(SCREEN_REFRESH_MS * 3); });
    expect(computer.fetchScreen.mock.calls.length).toBe(calls);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });

  it("an unreachable screen offers Retry", async () => {
    computer.fetchScreen.mockResolvedValue({ kind: "unreachable" });
    renderTab();
    expect(await screen.findByText(/Can’t reach Scout’s screen/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("Take control opens the live screen; Give it back with no account hands the computer back", async () => {
    computer.takeControl.mockResolvedValue(HELD);
    renderTab();
    await userEvent.click(await screen.findByRole("button", { name: "Take control" }));
    expect(computer.takeControl).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByText(/You have control/)).toBeInTheDocument();
    showFrame(lastSocket(), "about:blank");
    expect(screen.getByRole("img", { name: "Scout’s live screen" })).toBeInTheDocument();
    await giveItBack();
    expect(screen.queryByLabelText("Which account did you use?")).not.toBeInTheDocument();
    await giveItBack();
    expect(computer.giveBack).toHaveBeenCalledWith("bot-1", null);
    expect(await screen.findByRole("button", { name: "Take control" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "About this computer" })).toBeInTheDocument();
  });

  it("while the live screen is up, the 3-second screenshots stop", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    await screen.findByText(/You have control/);
    const calls = computer.fetchScreen.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(SCREEN_REFRESH_MS * 3); });
    expect(computer.fetchScreen.mock.calls.length).toBe(calls);
  });

  it("Give it back can name the account you used, and the Vault list loads again", async () => {
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    await screen.findByText(/You have control/);
    showFrame(lastSocket(), "https://shop.example/orders");
    await giveItBack();
    await userEvent.type(screen.getByLabelText("Which account did you use?"), "work email");
    await giveItBack();
    expect(computer.giveBack).toHaveBeenCalledWith("bot-1", "work email");
    await screen.findByRole("button", { name: "Take control" });
    expect(vault.listSiteLogins).toHaveBeenCalledTimes(2);
  });

  it("while the bot is stuck, Give it back clears its Stuck card with the account, so it carries on", async () => {
    stuck.listStuck.mockResolvedValue([CARD, makeStuckCard({ id: "card-2", bot_id: "bot-2" })]);
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    expect(await screen.findByText(/When you give it back, Scout carries on with the task it was stuck on/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the Stuck card" })).toHaveAttribute("href", "/bots/bot-1?thread=t-2");
    showFrame(lastSocket(), "https://accounts.example/");
    await giveItBack();
    const field = screen.getByLabelText("Which account did you use?");
    expect(field).toHaveAttribute("placeholder", "On shop.example, for example work email");
    await userEvent.type(field, "work email");
    await giveItBack();
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1", { account: "work email" });
    expect(computer.giveBack).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Take control" })).toBeInTheDocument();
  });

  it("a card heard about live counts too", async () => {
    liveCards = { [CARD.id]: CARD };
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    await screen.findByText(/carries on with the task it was stuck on/);
    await giveItBack();
    await giveItBack();
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1", { account: null });
  });

  it("a card closed meanwhile: Give it back still hands the computer back", async () => {
    stuck.listStuck.mockResolvedValue([CARD]);
    stuck.clearStuck.mockRejectedValue(new ApiError(409, "This card is already closed."));
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    await screen.findByText(/carries on with the task it was stuck on/);
    await giveItBack();
    await giveItBack();
    expect(computer.giveBack).toHaveBeenCalledWith("bot-1", null);
    expect(await screen.findByRole("button", { name: "Take control" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a failed clear says why and keeps the computer yours", async () => {
    stuck.listStuck.mockResolvedValue([CARD]);
    stuck.clearStuck.mockRejectedValue(new ApiError(500, "Something broke."));
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    await screen.findByText(/carries on with the task it was stuck on/);
    await giveItBack();
    await giveItBack();
    expect(await screen.findByRole("alert")).toHaveTextContent("Something broke.");
    expect(computer.giveBack).not.toHaveBeenCalled();
    expect(screen.getByRole("form", { name: "Give it back" })).toBeInTheDocument();
  });

  it("a closed card or another bot's card leaves Give it back as it is", async () => {
    liveCards = { [CARD.id]: { ...CARD, state: "given_up" } };
    stuck.listStuck.mockResolvedValue([CARD, makeStuckCard({ id: "card-2", bot_id: "bot-2" })]);
    computer.getControl.mockResolvedValue(HELD);
    renderTab();
    await screen.findByText(/You have control/);
    await giveItBack();
    await giveItBack();
    expect(computer.giveBack).toHaveBeenCalledWith("bot-1", null);
    expect(stuck.clearStuck).not.toHaveBeenCalled();
    expect(screen.queryByText(/carries on with the task/)).not.toBeInTheDocument();
  });

  it("a failed card list says why, and the tab still works", async () => {
    stuck.listStuck.mockRejectedValue(new ApiError(500, "Could not load your Stuck cards."));
    renderTab();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your Stuck cards.");
    expect(screen.getByRole("button", { name: "Take control" })).toBeInTheDocument();
  });

  it("Show window on Mac brings the bot's window up, and a failure says why", async () => {
    renderTab();
    await userEvent.click(await screen.findByRole("button", { name: "Show window on Mac" }));
    expect(live.showWindow).toHaveBeenCalledWith("bot-1");
    live.showWindow.mockRejectedValue(new ApiError(409, "asleep"));
    await userEvent.click(screen.getByRole("button", { name: "Show window on Mac" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("asleep");
  });

  it("when the server ends the live screen, the tab looks again", async () => {
    computer.getControl.mockResolvedValueOnce(HELD).mockResolvedValue(FREE);
    renderTab();
    await screen.findByText(/You have control/);
    lastSocket().end(4000, "Given back.");
    expect(await screen.findByRole("button", { name: "Take control" })).toBeInTheDocument();
    expect(computer.getControl).toHaveBeenCalledTimes(2);
  });
});
```

Replace the whole of `web/tests/StuckCard.test.tsx` with:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { StuckCard } from "../src/components/StuckCard";
import { ApiError } from "../src/api/client";
import type { StuckCardOut, StuckMessageData } from "../src/api/types";
import { makeStuckCard, STUCK_LINE } from "./fixtures";

const computer = { getControl: vi.fn(), takeControl: vi.fn() };
const stuck = { clearStuck: vi.fn(), giveUpStuck: vi.fn(), openInMainBrowser: vi.fn() };
vi.mock("../src/api/computer", () => ({
  getControl: (id: string) => computer.getControl(id),
  takeControl: (id: string) => computer.takeControl(id),
}));
vi.mock("../src/api/stuck", () => ({
  clearStuck: (...args: unknown[]) => stuck.clearStuck(...args),
  giveUpStuck: (id: string) => stuck.giveUpStuck(id),
  openInMainBrowser: (id: string) => stuck.openInMainBrowser(id),
}));

const CARD = makeStuckCard();
const CLOSED_AT = "2026-10-14T10:05:00Z";
const HOLDING = "You have control. Clear it on the live screen, then give it back.";
const COMPUTER_TAB = "/bots/bot-1/profile?tab=computer";
const dataOf = (card: StuckCardOut, line = STUCK_LINE): StuckMessageData => ({
  card_id: card.id, bot_id: card.bot_id, reason: card.reason, host: card.host, url: card.url, note: card.note,
  suggest_main_browser: card.suggest_main_browser, line,
});
// Where the router is now: Take control opens the bot's Computer tab.
function Where() {
  const location = useLocation();
  return <p data-testid="where">{`${location.pathname}${location.search}`}</p>;
}
const cardView = (card: StuckCardOut | undefined, data = dataOf(CARD), tainted = false) => (
  <MemoryRouter initialEntries={["/bots/bot-1"]}>
    <StuckCard data={data} card={card} botName="Scout" tainted={tainted} />
    <Where />
  </MemoryRouter>
);
const renderCard = (card: StuckCardOut | undefined, data = dataOf(CARD), tainted = false) =>
  render(cardView(card, data, tainted));
const click = (name: string) => userEvent.click(screen.getByRole("button", { name }));
const where = () => screen.getByTestId("where").textContent;

beforeEach(() => {
  stuck.clearStuck.mockResolvedValue({ ...CARD, state: "cleared", closed_at: CLOSED_AT });
  stuck.giveUpStuck.mockResolvedValue({ ...CARD, state: "given_up", closed_at: CLOSED_AT });
  stuck.openInMainBrowser.mockResolvedValue({ ...CARD, main_opened: true });
  computer.takeControl.mockResolvedValue({ held: true, since: "2026-10-14T10:01:00Z" });
  computer.getControl.mockResolvedValue({ held: false, since: null });
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

  it("Take control holds the computer, opens the live screen and says how to give it back", async () => {
    renderCard(CARD);
    await click("Take control");
    expect(computer.takeControl).toHaveBeenCalledWith("bot-1");
    expect(await screen.findByText(HOLDING)).toBeInTheDocument();
    expect(where()).toBe(COMPUTER_TAB);
    expect(screen.getByRole("link", { name: "Open the live screen" })).toHaveAttribute("href", COMPUTER_TAB);
    expect(screen.queryByRole("button", { name: "Take control" })).not.toBeInTheDocument();
  });

  it("a card whose computer you already hold opens on the Holding view, so its Give it back survives a visit to the screen", async () => {
    computer.getControl.mockResolvedValue({ held: true, since: "2026-10-14T10:01:00Z" });
    renderCard(CARD);
    expect(await screen.findByText(HOLDING)).toBeInTheDocument();
    expect(computer.getControl).toHaveBeenCalledWith("bot-1");
    expect(computer.takeControl).not.toHaveBeenCalled();
    expect(where()).toBe("/bots/bot-1");
    await click("Give it back");
    await click("Give it back");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1", { account: null });
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
  });

  it("an answer that you don't hold the computer never undoes a Take control pressed meanwhile", async () => {
    let answer: (value: { held: boolean; since: null }) => void = () => {};
    computer.getControl.mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    renderCard(CARD);
    await click("Take control");
    await screen.findByText(HOLDING);
    await act(async () => answer({ held: false, since: null }));
    expect(screen.getByRole("button", { name: "Give it back" })).toBeInTheDocument();
  });

  it("a failed check of who holds the computer says why and keeps the card's buttons", async () => {
    computer.getControl.mockRejectedValue(new ApiError(503, "desk unavailable"));
    renderCard(CARD);
    expect(await screen.findByRole("alert")).toHaveTextContent("desk unavailable");
    expect(screen.getByRole("button", { name: "Take control" })).toBeEnabled();
  });

  it("a closed or unknown card never asks who holds the computer", () => {
    renderCard({ ...CARD, state: "cleared", closed_at: CLOSED_AT });
    cleanup();
    renderCard(undefined);
    expect(computer.getControl).not.toHaveBeenCalled();
  });

  it("Give it back asks which account you used on the card's site, then folds to Cleared", async () => {
    renderCard(CARD);
    await click("Take control");
    await screen.findByText(HOLDING);
    await click("Give it back");
    const field = screen.getByLabelText("Which account did you use?");
    expect(field).toHaveAttribute("placeholder", "On shop.example, for example work email");
    await userEvent.type(field, "work email");
    await click("Give it back");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1", { account: "work email" });
    expect(await screen.findByText("Cleared: shop.example")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("Cancel keeps the card holding, and a card with no site asks for no account", async () => {
    computer.getControl.mockResolvedValue({ held: true, since: "2026-10-14T10:01:00Z" });
    const asked = makeStuckCard({ reason: "asked", host: "", url: "", note: "Approve the payment" });
    renderCard(asked, dataOf(asked));
    await screen.findByText(HOLDING);
    await click("Give it back");
    expect(screen.queryByLabelText("Which account did you use?")).not.toBeInTheDocument();
    await click("Cancel");
    expect(screen.getByRole("link", { name: "Open the live screen" })).toBeInTheDocument();
    expect(stuck.clearStuck).not.toHaveBeenCalled();
    await click("Give it back");
    await click("Give it back");
    expect(stuck.clearStuck).toHaveBeenCalledWith("card-1", { account: null });
  });

  it("a Give it back that fails says why and keeps the form", async () => {
    computer.getControl.mockResolvedValue({ held: true, since: "2026-10-14T10:01:00Z" });
    stuck.clearStuck.mockRejectedValue(new ApiError(400, "Roost can't tell which site that account is for. Give it back without one."));
    renderCard(CARD);
    await screen.findByText(HOLDING);
    await click("Give it back");
    await userEvent.type(screen.getByLabelText("Which account did you use?"), "work email");
    await click("Give it back");
    expect(await screen.findByRole("alert")).toHaveTextContent("Roost can't tell which site that account is for.");
    expect(screen.getByRole("form", { name: "Give it back" })).toBeInTheDocument();
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

  it("a suggestion for the main Brave with no address highlights Take control, not a button that isn't there", () => {
    const asked = makeStuckCard({ reason: "asked", host: "", url: "", note: "Approve the payment", suggest_main_browser: true });
    renderCard(asked, dataOf(asked));
    expect(screen.queryByRole("button", { name: "Use my main Brave" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Take control" })).toHaveClass("btn--primary");
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

  it.each([
    ["cleared", "Cleared"],
    ["given_up", "Stopped"],
    ["blocked", "Blocked"],
  ] as const)("a %s card with no site folds to the bare word, with or without a note", (state, word) => {
    const asked = makeStuckCard({ reason: "asked", host: "", url: "", note: "Approve the payment", state, closed_at: CLOSED_AT });
    renderCard(asked, dataOf(asked));
    expect(screen.getByRole("group", { name: word })).toBeInTheDocument();   // the name is matched whole
    expect(screen.getByText(word)).toBeInTheDocument();
    cleanup();
    const bare = makeStuckCard({ reason: "asked", host: "", url: "", note: "", state, closed_at: CLOSED_AT });
    renderCard(bare, dataOf(bare));
    expect(screen.getByRole("group", { name: word })).toBeInTheDocument();
    expect(screen.getByText(word)).toBeInTheDocument();
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

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/liveApi.test.ts tests/SiteLogins.test.tsx tests/ComputerTab.test.tsx tests/StuckCard.test.tsx`
Expected: FAIL.
- `liveApi.test.ts` and `SiteLogins.test.tsx`: `Failed to resolve import "../src/api/vault"` and `"../src/components/profile/SiteLogins"`.
- `ComputerTab.test.tsx`: `Failed to resolve import "../src/api/vault"`.
- `StuckCard.test.tsx`: the Holding tests fail on the new texts ("Clear it on the live screen", "Open the live screen", the account field).

- [ ] **Step 4: The API (`web/src/api/types.ts`, `computer.ts`, `stuck.ts`, `vault.ts`)**

In `web/src/api/types.ts`, replace these lines:

```ts
// Who holds the bot's computer (S1.8): `since` is the UTC ISO time the hold began.
export interface ControlOut { held: boolean; since: string | null }
```

with:

```ts
// Who holds the bot's computer (S1.8): `since` is the UTC ISO time the hold began.
export interface ControlOut { held: boolean; since: string | null }

// Vault: site logins (live control): an account the user said a bot is signed in with on a site.
// roost/vault/models.py SiteLoginOut. Only a site and an account name: never a password.
export interface SiteLoginOut { id: string; bot_id: string; host: string; label: string; created_at: string; updated_at: string }
```

In `web/src/api/computer.ts`, replace this line:

```ts
export const giveBack = (botId: string) => apiRequest<ControlOut>("DELETE", `/api/bots/${botId}/control`);
```

with:

```ts
// Give it back. Naming the account you used (live control) keeps it in the bot's Vault and tells the bot.
export const giveBack = (botId: string, account: string | null = null) =>
  apiRequest<ControlOut>("DELETE", `/api/bots/${botId}/control`, account ? { account } : undefined);
```

In `web/src/api/stuck.ts`, replace this line:

```ts
export const clearStuck = (cardId: string) => apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/clear`);
```

with:

```ts
// The optional body of /clear: which button (Try again has its own words) and, from Give it back, the
// account you used (live control). No body is Give it back with no account.
export interface ClearBody { how?: "try_again" | "gave_back"; account?: string | null }
export const clearStuck = (cardId: string, body?: ClearBody) =>
  apiRequest<StuckCardOut>("POST", `${cardPath(cardId)}/clear`, body);
```

Create `web/src/api/vault.ts`:

```ts
// web/src/api/vault.ts — Vault: site logins (live control): the accounts a bot is signed in with, and Forget.
import { apiRequest } from "./client";
import type { SiteLoginOut } from "./types";

const loginsPath = (botId: string) => `/api/bots/${encodeURIComponent(botId)}/site-logins`;

export const listSiteLogins = (botId: string) => apiRequest<SiteLoginOut[]>("GET", loginsPath(botId));
export const forgetSiteLogin = (botId: string, loginId: string) =>
  apiRequest<void>("DELETE", `${loginsPath(botId)}/${encodeURIComponent(loginId)}`);
```

- [ ] **Step 5: The Vault list (`web/src/components/profile/SiteLogins.tsx`)**

Create `web/src/components/profile/SiteLogins.tsx`:

```tsx
// web/src/components/profile/SiteLogins.tsx — Vault: site logins on the Computer tab (live control). The
// accounts you told the bot you used, newest first, each with Forget. Only a site and an account name are
// kept; a password never is.
import { useEffect, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import * as vaultApi from "../../api/vault";
import { describeError } from "../../api/client";
import type { BotOut, SiteLoginOut } from "../../api/types";

// `version` changes after each Give it back, so the list loads again.
export function SiteLogins({ bot, version }: { bot: BotOut; version: number }) {
  const [logins, setLogins] = useState<SiteLoginOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    vaultApi.listSiteLogins(bot.id)
      .then((rows) => { if (!cancelled) setLogins(rows); })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    return () => { cancelled = true; };
  }, [bot.id, version]);
  const forget = async (login: SiteLoginOut) => {
    setError(null);
    try {
      await vaultApi.forgetSiteLogin(bot.id, login.id);
      setLogins((current) => (current ?? []).filter((row) => row.id !== login.id));
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <section className="site-logins" aria-labelledby="site-logins-title">
      <h2 id="site-logins-title" className="site-logins__title">Vault: site logins</h2>
      <p className="site-logins__lede">The accounts you told {bot.name} you used. Passwords are never kept.</p>
      {logins && logins.length === 0 ? (
        <p className="site-logins__empty">
          None yet. When you give {bot.name}&rsquo;s computer back, you can say which account you used.
        </p>
      ) : null}
      {logins && logins.length > 0 ? (
        <ul className="site-logins__list" aria-label={`${bot.name}’s site logins`}>
          {logins.map((login) => (
            <li key={login.id} className="site-logins__row">
              <span className="site-logins__host">{login.host}</span>
              <span className="site-logins__label">{login.label}</span>
              <button type="button" className="btn btn--quiet btn--small" aria-label={`Forget ${login.host}`}
                onClick={() => void forget(login)}>Forget</button>
            </li>
          ))}
        </ul>
      ) : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
```

Append this to the end of `web/src/styles/computer.css`:

```css

/* ---- Vault: site logins (live control) -------------------------------- */

.site-logins {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 20px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
}

.site-logins__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--fs-md);
  font-weight: 700;
  letter-spacing: -0.015em;
}

.site-logins__lede,
.site-logins__empty {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
}

.site-logins__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.site-logins__row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.site-logins__host {
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
}

.site-logins__label {
  flex: 1;
  min-width: 0;
  color: var(--muted);
  font-size: var(--fs-sm);
  overflow-wrap: anywhere;
}

.control__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
```

- [ ] **Step 6: The Computer tab (`web/src/components/profile/ComputerTab.tsx`)**

Replace the whole of `web/src/components/profile/ComputerTab.tsx` with:

```tsx
// web/src/components/profile/ComputerTab.tsx — the profile's Computer tab (S1.8, live control). While you
// hold control the live screen fills it; otherwise its screenshot refreshes every 3 s, with Take control and
// Show window on Mac. Below: the bot's site logins (Vault), the window and terminal, and About this computer.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ComputerPanel } from "../ComputerPanel";
import { ErrorNotice } from "../ErrorNotice";
import { LiveScreen } from "./LiveScreen";
import { SiteLogins } from "./SiteLogins";
import * as computerApi from "../../api/computer";
import type { ScreenResult } from "../../api/computer";
import * as deskApi from "../../api/desk";
import * as liveApi from "../../api/live";
import * as stuckApi from "../../api/stuck";
import { ApiError, describeError } from "../../api/client";
import type { BotOut, ControlOut, DeskStatusOut, StuckCardOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { mergeStuck, openStuckCards } from "../../lib/stuck";

export const SCREEN_REFRESH_MS = 3000;
type Screen = { kind: "loading" } | { kind: "asleep" } | { kind: "unreachable" } | { kind: "image"; url: string };

// The latest screenshot, refreshed about every 3 s while the page is visible (S1.8) and the live screen is
// not up. One request at a time: a slow computer never piles screenshots up.
function useScreen(botId: string, enabled: boolean) {
  const [screen, setScreen] = useState<Screen>({ kind: "loading" });
  const [tick, setTick] = useState(0);
  const current = useRef<string | null>(null);
  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let busy = false;
    const load = async () => {
      if (busy || document.visibilityState !== "visible") return;
      busy = true;
      const result = await computerApi.fetchScreen(botId).catch((): ScreenResult => ({ kind: "unreachable" }));
      busy = false;
      if (cancelled) return;
      if (result.kind !== "image") return setScreen(result);
      const previous = current.current;
      current.current = URL.createObjectURL(result.blob);
      setScreen({ kind: "image", url: current.current });
      if (previous) URL.revokeObjectURL(previous);
    };
    void load();
    const timer = setInterval(() => void load(), SCREEN_REFRESH_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [botId, tick, enabled]);
  useEffect(() => () => { if (current.current) URL.revokeObjectURL(current.current); }, []);
  return { screen, refresh: useCallback(() => setTick((value) => value + 1), []) };
}

interface ScreenBoxProps { bot: BotOut; screen: Screen; onOpen: () => void; onRetry: () => void }

function ScreenBox({ bot, screen, onOpen, onRetry }: ScreenBoxProps) {
  if (screen.kind === "image") return <img className="screen-box__image" src={screen.url} alt={`${bot.name}’s screen`} />;
  if (screen.kind === "asleep") {
    return <p className="screen-box__state">{bot.name}&rsquo;s computer is asleep · <button type="button" className="link-btn" onClick={onOpen}>Open it</button></p>;
  }
  if (screen.kind === "unreachable") {
    return <p className="screen-box__state">Can&rsquo;t reach {bot.name}&rsquo;s screen · <button type="button" className="link-btn" onClick={onRetry}>Retry</button></p>;
  }
  return <p className="screen-box__state">Looking at {bot.name}&rsquo;s screen&hellip;</p>;
}

// A clear that answers 404 or 409 found the card already closed (another tab, Give up in the chat).
const CARD_GONE_STATUSES: ReadonlySet<number> = new Set([404, 409]);

// The bot's open Stuck card, if any: GET /api/stuck once, kept current by live stuck_card frames.
// A failed load is said; Give it back then only hands the computer back.
function useOpenStuckCard(botId: string) {
  const live = useLiveState();
  const [loaded, setLoaded] = useState<StuckCardOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    stuckApi.listStuck()
      .then((cards) => { if (!cancelled) setLoaded(cards); })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    return () => { cancelled = true; };
  }, [botId]);
  const card = openStuckCards(mergeStuck(loaded, live.stuckCards)).find((open) => open.bot_id === botId);
  return { card, error };
}

// Give it back, with the account you used when you name one (live control). While the bot has an open Stuck
// card it does what the card's own Give it back does: the card is cleared, which also hands the computer
// back, and the bot carries on.
async function giveBackFor(botId: string, card: StuckCardOut | undefined, account: string | null): Promise<ControlOut> {
  if (!card) return computerApi.giveBack(botId, account);
  try {
    await stuckApi.clearStuck(card.id, { account });
    return { held: false, since: null };
  } catch (err) {
    if (err instanceof ApiError && CARD_GONE_STATUSES.has(err.status)) return computerApi.giveBack(botId, account);
    throw err;
  }
}

// Who holds the bot's computer. giveBack throws, so the Give it back form can say why it failed.
function useControl(botId: string) {
  const [held, setHeld] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => {
    computerApi.getControl(botId).then((control) => setHeld(control.held))
      .catch((err: unknown) => setError(describeError(err)));
  }, [botId]);
  useEffect(() => { refresh(); }, [refresh]);
  const take = async () => {
    setError(null);
    try {
      setHeld((await computerApi.takeControl(botId)).held);
    } catch (err) {
      setError(describeError(err));
    }
  };
  const giveBack = async (card: StuckCardOut | undefined, account: string | null) => {
    setHeld((await giveBackFor(botId, card, account)).held);
  };
  return { held, error, refresh, take, giveBack };
}

type Control = ReturnType<typeof useControl>;

function ControlNote({ bot, card }: { bot: BotOut; card: StuckCardOut | undefined }) {
  return (
    <>
      <p className="control__note">You have control. {bot.name}&rsquo;s browser calls wait until you give it back. Click
        and type on the live screen; what you type goes to the page, never to {bot.name}.</p>
      {card ? (
        <p className="control__note">When you give it back, {bot.name} carries on with the task it was stuck on.{" "}
          <Link to={`/bots/${bot.id}?thread=${encodeURIComponent(card.thread_id)}`}>See the Stuck card</Link></p>
      ) : null}
    </>
  );
}

function ControlRow({ bot, control, card }: { bot: BotOut; control: Control; card: StuckCardOut | undefined }) {
  const [error, setError] = useState<string | null>(null);
  const show = async () => {
    setError(null);
    try {
      await liveApi.showWindow(bot.id);
    } catch (err) {
      setError(describeError(err));
    }
  };
  return (
    <div className="control">
      {control.held ? <ControlNote bot={bot} card={card} /> : (
        <div className="control__actions">
          <button type="button" className="btn btn--primary" onClick={() => void control.take()}>Take control</button>
          <button type="button" className="btn btn--quiet" onClick={() => void show()}>Show window on Mac</button>
        </div>
      )}
      {control.error ? <ErrorNotice message={control.error} /> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </div>
  );
}

// Open or close the bot's window, then look again; a failure is said, never swallowed.
function useWindowActions(botId: string, refresh: () => void) {
  const [status, setStatus] = useState<DeskStatusOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { deskApi.getDeskStatus(botId).then(setStatus).catch(() => setStatus(null)); }, [botId]);
  const run = useCallback(async (action: (id: string) => Promise<DeskStatusOut>) => {
    setError(null);
    try {
      setStatus(await action(botId));
    } catch (err) {
      setError(describeError(err));
    }
    refresh();
  }, [botId, refresh]);
  return { status, error, open: () => run(deskApi.startBrowser), close: () => run(deskApi.stopBrowser) };
}

export function ComputerTab({ bot }: { bot: BotOut }) {
  const control = useControl(bot.id);
  const { screen, refresh } = useScreen(bot.id, !control.held);
  const { status, error, open, close } = useWindowActions(bot.id, refresh);
  const stuck = useOpenStuckCard(bot.id);
  const [loginsVersion, setLoginsVersion] = useState(0);
  const giveBack = async (account: string | null) => {
    await control.giveBack(stuck.card, account);
    setLoginsVersion((value) => value + 1);
  };
  return (
    <div className="computer-tab">
      {control.held ? (
        <LiveScreen bot={bot} site={stuck.card?.host ?? ""} onGiveBack={giveBack} onEnded={control.refresh} onOpen={open} />
      ) : (
        <figure className="computer-tab__screen">
          <div className="screen-box"><ScreenBox bot={bot} screen={screen} onOpen={() => void open()} onRetry={refresh} /></div>
          <figcaption className="computer-tab__caption">{bot.name}&rsquo;s screen</figcaption>
        </figure>
      )}
      <ControlRow bot={bot} control={control} card={stuck.card} />
      {stuck.error ? <ErrorNotice message={stuck.error} /> : null}
      {error ? <ErrorNotice message={error} /> : null}
      <SiteLogins bot={bot} version={loginsVersion} />
      <ComputerPanel status={status} onStartBrowser={open} onStopBrowser={close}
        onExec={(command) => deskApi.execWorkspace(bot.id, command)} />
      <section className="about-computer" aria-labelledby="about-computer-title">
        <h2 id="about-computer-title" className="about-computer__title">About this computer</h2>
        <p>{bot.name} has its own Brave window on your Mac and its own sealed box for commands. Other bots can&rsquo;t see
          its pages or logins; they can ask {bot.name} about them.</p>
      </section>
    </div>
  );
}
```

- [ ] **Step 7: The Stuck card (`web/src/components/StuckCard.tsx`)**

Replace the whole of `web/src/components/StuckCard.tsx` with:

```tsx
// web/src/components/StuckCard.tsx — the Stuck card (stuck flow, Piece A; live control). The bot hit a block
// it can't get past alone: a check that it's human, a sign-in page, a code check, a site that refused it,
// or something it asked you for. Take control opens its live screen on the Computer tab, where you clear
// it; then you give it back (saying which account you used, if you like), let it try again, open the page
// in your main Brave, or stop the task. Once the card is no longer open it folds to one line.
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorNotice } from "./ErrorNotice";
import { FoldCard, FoldedLine } from "./FoldCard";
import { GiveBackForm } from "./GiveBackForm";
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
const HOLDING_TEXT = "You have control. Clear it on the live screen, then give it back.";
const FOLDED: Record<Exclude<StuckState, "open">, { word: string; icon: string }> = {
  cleared: { word: "Cleared", icon: "✓" },
  given_up: { word: "Stopped", icon: "×" },
  blocked: { word: "Blocked", icon: "!" },
};

// The bot's Computer tab, where its live screen is.
const computerTab = (botId: string) => `/bots/${botId}/profile?tab=computer`;

// The card as this page last heard of it. A closed live copy always wins, because a cleared card
// can still turn blocked. An open one gives way to what a button here just got back.
function latest(card: StuckCardOut | undefined, answered: StuckCardOut | null): StuckCardOut | undefined {
  if (!answered || (card && card.state !== "open")) return card;
  return answered;
}

// The buttons' calls: one at a time, and a failure is said on the card, never swallowed.
// An open card starts from who holds the bot's computer, so the Holding view (and its Give it
// back) survives a visit to the bot's screen. A "not held" answer never undoes a Take control.
// Take control opens the live screen on the bot's Computer tab.
function useStuckActions(cardId: string, botId: string, open: boolean) {
  const navigate = useNavigate();
  const [answered, setAnswered] = useState<StuckCardOut | null>(null);
  const [holding, setHolding] = useState(false);
  const [givingBack, setGivingBack] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    computerApi.getControl(botId)
      .then((control) => { if (!cancelled && control.held) setHolding(true); })
      .catch((err: unknown) => { if (!cancelled) setError(describeError(err)); });
    return () => { cancelled = true; };
  }, [botId, open]);
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
  const takeControl = () => run(async () => {
    const held = (await computerApi.takeControl(botId)).held;
    setHolding(held);
    if (held) navigate(computerTab(botId));
  });
  return {
    answered, holding, givingBack, busy, error, setGivingBack, takeControl,
    clear: () => answer(stuckApi.clearStuck),
    giveBack: (account: string | null) => answer((id) => stuckApi.clearStuck(id, { account })),
    giveUp: () => answer(stuckApi.giveUpStuck),
    openInMain: () => answer(stuckApi.openInMainBrowser),
  };
}

type Actions = ReturnType<typeof useStuckActions>;

function StuckFooter({ view, data, actions }: { view: View; data: StuckMessageData; actions: Actions }) {
  const button = (label: string, onClick: () => Promise<void> | void, primary = false) => (
    <button type="button" className={`btn ${primary ? "btn--primary" : "btn--quiet"} btn--small`}
      disabled={actions.busy} onClick={() => void onClick()}>{label}</button>
  );
  if (view === "holding") {
    return (
      <>
        <Link className="btn btn--quiet btn--small" to={computerTab(data.bot_id)}>Open the live screen</Link>
        {button("Give it back", () => actions.setGivingBack(true), true)}
      </>
    );
  }
  if (view === "main_opened") return <>{button("Done, carry on", actions.clear, true)}{button("Give up", actions.giveUp)}</>;
  return (
    <>
      {button("Take control", actions.takeControl, !(data.suggest_main_browser && data.url))}
      {button("Try again", actions.clear)}
      {data.url ? button("Use my main Brave", actions.openInMain, data.suggest_main_browser) : null}
      {button("Give up", actions.giveUp)}
    </>
  );
}

function StuckBody({ view, data, tainted, error }: {
  view: View; data: StuckMessageData; tainted: boolean; error: string | null;
}) {
  return (
    <>
      {data.url ? <p className="stuck-card__url"><bdi dir="ltr">{data.url}</bdi></p> : null}
      {tainted && data.url ? <p className="fold-card__taint" role="note">{TAINT_NOTE}</p> : null}
      {view === "holding" ? <p className="stuck-card__state">{HOLDING_TEXT}</p> : null}
      {view === "main_opened" ? <p className="stuck-card__state">Opened in your main Brave.</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </>
  );
}

export function StuckCard({ data, card, botName, tainted }: StuckCardProps) {
  const actions = useStuckActions(data.card_id, data.bot_id, card?.state === "open");
  const shown = latest(card, actions.answered);
  if (!shown) return <div className="message__body">{data.line}</div>;
  const state = shown.state;
  if (state !== "open") {
    // A card with no site (the bot asked for help before any page) folds to the bare word.
    const { word } = FOLDED[state];
    const line = data.host ? `${word}: ${data.host}` : word;
    return <FoldedLine icon={FOLDED[state].icon} ariaLabel={line}>{line}</FoldedLine>;
  }
  const view: View = actions.holding ? "holding" : shown.main_opened ? "main_opened" : "open";
  const title = stuckTitle(data.host, data.url);
  const hasBody = Boolean(data.url) || view !== "open" || actions.error !== null;
  const footer = view === "holding" && actions.givingBack ? (
    <GiveBackForm site={data.host} botName={botName} onConfirm={actions.giveBack}
      onCancel={() => actions.setGivingBack(false)} />
  ) : <StuckFooter view={view} data={data} actions={actions} />;
  return (
    <FoldCard ariaLabel={title} title={title} explanation={data.line} footer={footer}>
      {hasBody ? <StuckBody view={view} data={data} tainted={tainted} error={actions.error} /> : null}
    </FoldCard>
  );
}
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npx vitest run tests/liveApi.test.ts tests/SiteLogins.test.tsx tests/ComputerTab.test.tsx tests/StuckCard.test.tsx tests/LiveScreen.test.tsx tests/stuck.test.ts tests/Chat.test.tsx tests/MessageList.test.tsx tests/Profile.test.tsx`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm test`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm run build && npm run size`
Expected: the type check, the build and the bundle budget pass.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vocabulary.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add web/src/api/types.ts web/src/api/computer.ts web/src/api/stuck.ts web/src/api/vault.ts \
  web/src/components/profile/SiteLogins.tsx web/src/components/profile/ComputerTab.tsx \
  web/src/components/StuckCard.tsx web/src/styles/computer.css web/tests/liveApi.test.ts \
  web/tests/SiteLogins.test.tsx web/tests/ComputerTab.test.tsx web/tests/StuckCard.test.tsx
git commit -m "feat: the Computer tab shows the live screen, the Stuck card opens it, and the Vault lists site logins"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the twelve files is listed.

---

### Task 14: E2E and the docs

Design §3 "E2E (Playwright, fake desk)", and the docs that load on every turn:
- **`web/e2e/stuck.spec.ts`** becomes the live-control flow:
  1. Porter is stuck on the fake sign-in page `https://login.example/` (`FakeDesk`'s scripted wall). The card and My turn show, as before.
  2. **Take control** opens Porter's Computer tab, and the live screen shows the fake browser's scripted screencast (`FakeCdp`, Task 5) with the address `https://login.example/`.
  3. The test clicks the page and types. **Give it back** asks "Which account did you use?" and gets "work email".
  4. The Vault lists `login.example` and `work email`.
  5. Back in the chat, the card is folded, your continue line starts "I signed in on login.example as work email.", and Porter carries on ("Signed in and done.").
- **`web/e2e/computer.spec.ts`** becomes: asleep, Open it, Take control opens the live screen (the address `about:blank`), Give it back with no account question, and Take control is back.
- **The docs.**
  - `CLAUDE.md` gets the design and this plan in its Documentation Map, and an Architecture paragraph on live control and the Vault.
  - `README.md` gets a Safety note: live control is this Mac only, what you type stays on the page, and the Vault keeps an account name, never a password.
  - `tests/test_docs.py` pins all three.

**Files:**
- Modify: `web/e2e/stuck.spec.ts` and `web/e2e/computer.spec.ts` (whole files), `CLAUDE.md`, `README.md`
- Test: `tests/test_docs.py` (tests appended)

**Interfaces:**
- Consumes: everything above. `web/e2e/helpers.ts` (`signIn`, `createBot`, `detailPane`, `say`, `openChat`); `web/e2e/fixtures/team-script.json`'s Porter script, unchanged (open the page, read it again, "Signed in and done.").
- Produces: the E2E proof and the docs.

- [ ] **Step 1: Path guard and disk guard**

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Run: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: 8 or more. If fewer, stop and report: `make e2e` installs a browser and builds the web app.

- [ ] **Step 2: Write the failing tests**

Append this to the end of `tests/test_docs.py`:

```python


# Live control: the design and the plan are on the map, the architecture says where it lives, and the
# README's safety notes say what live control keeps private.
LIVE_DOCS = (
    "docs/plans/2026-10-15-roost-live-control-design.md",
    "docs/plans/2026-10-15-roost-live-control.md",
)


def test_the_documentation_map_names_the_live_control_design_and_plan():
    assert [path for path in LIVE_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_live_control_and_the_vault_live():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    for name in ("/api/bots/{id}/live", "roost/desk/live.py", "roost/vault/", "site_logins"):
        assert name in architecture, name


def test_the_readme_says_live_control_is_this_mac_only_and_private():
    safety = _section(README.read_text(encoding="utf-8"), "## Safety notes")
    assert "**Live control is this Mac only, and private.**" in safety
    assert "never a password" in safety
```

Replace the whole of `web/e2e/stuck.spec.ts` with:

```ts
import { expect, test } from "@playwright/test";
import { createBot, detailPane, openChat, say, signIn } from "./helpers";

// Stuck flow and live control, against ROOST_DESK=fake + fixtures/team-script.json ("Porter").
// FakeDesk serves https://login.example/ as a sign-in wall first and the signed-in page after it
// (roost/desk/fake_pages.py), and its FakeCdp streams a scripted screencast (roost/desk/fake_cdp.py).
const HOST = "login.example";
const CARD_LINE = `I'm stuck on ${HOST}: a sign-in page.`;
const MY_TURN_ROW = `Porter · Stuck on ${HOST}`;
const ACCOUNT = "work email";
const SIGNED_IN_LINE = `I signed in on ${HOST} as ${ACCOUNT}.`;
const REPLY = "Signed in and done.";
const SLOW = { timeout: 20_000 };

test("a bot stuck on a sign-in page: Take control opens its live screen, Give it back names the account, and it carries on", async ({ page }) => {
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
  await expect(porterRow).toContainText(/Stuck(?! on)/, SLOW);

  // Home lives in the Chats pane on every desktop route. After a reload My turn still lists the card.
  await page.goto("/");
  const myTurn = listPane.getByRole("region", { name: "My turn" });
  await expect(myTurn).toBeVisible(SLOW);
  await myTurn.getByRole("link", { name: MY_TURN_ROW }).click();
  await expect(detail.getByRole("heading", { name: "Porter", exact: true })).toBeVisible();

  // Take control opens the live screen on Porter's Computer tab: the fake browser's page, moving.
  await card.getByRole("button", { name: "Take control", exact: true }).click();
  await expect(page).toHaveURL(/\/bots\/[^/]+\/profile\?tab=computer$/, SLOW);
  const live = detail.getByRole("region", { name: "Porter’s live screen" });
  await expect(live.getByRole("img", { name: "Porter’s live screen" })).toBeVisible(SLOW);
  await expect(live.getByRole("textbox", { name: "Address" })).toHaveValue(`https://${HOST}/`);
  await live.getByRole("application", { name: "Porter’s page" }).click();
  await page.keyboard.type("not-a-real-password");

  // Give it back, naming the account: the Vault keeps it, and the tab is back to Take control.
  await live.getByRole("button", { name: "Give it back" }).click();
  await live.getByLabel("Which account did you use?").fill(ACCOUNT);
  await live.getByRole("button", { name: "Give it back" }).click();
  await expect(detail.getByRole("button", { name: "Take control" })).toBeVisible(SLOW);
  const vault = detail.getByRole("region", { name: "Vault: site logins" });
  await expect(vault.getByRole("listitem")).toHaveText([new RegExp(`${HOST}.*${ACCOUNT}`)], SLOW);

  // Back in the chat: the card is folded, your continue line names the account, and Porter carries on.
  await openChat(page, "Porter");
  await expect(detail.getByRole("group", { name: `Cleared: ${HOST}` })).toBeVisible(SLOW);
  await expect(detail.getByText(SIGNED_IN_LINE, { exact: false })).toBeVisible(SLOW);
  await expect(detail.getByText(REPLY)).toBeVisible(SLOW);
  await expect(porterRow).toContainText(REPLY, SLOW);
  await page.goto("/");
  await expect(myTurn).toBeHidden(SLOW);
});
```

Replace the whole of `web/e2e/computer.spec.ts` with:

```ts
import { expect, test } from "@playwright/test";
import { createBot, detailPane, signIn } from "./helpers";

test("the Computer tab: asleep, Open it, Take control opens the live screen, and Give it back", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Scout", "Finds prices and opening hours");
  const detail = detailPane(page);
  await detail.getByRole("link", { name: "Open Scout's profile" }).click();
  await detail.getByRole("tab", { name: "Computer" }).click();
  await expect(detail.getByText("Scout’s computer is asleep")).toBeVisible();
  await detail.getByRole("button", { name: "Open it" }).click();
  await expect(detail.getByRole("img", { name: "Scout’s screen" })).toBeVisible();
  await detail.getByRole("button", { name: "Take control" }).click();
  await expect(detail.getByText(/You have control/)).toBeVisible();
  const live = detail.getByRole("region", { name: "Scout’s live screen" });
  await expect(live.getByRole("img", { name: "Scout’s live screen" })).toBeVisible();
  await expect(live.getByRole("textbox", { name: "Address" })).toHaveValue("about:blank");
  await live.getByRole("button", { name: "Give it back" }).click();
  await expect(live.getByLabel("Which account did you use?")).toHaveCount(0);   // no site on about:blank
  await live.getByRole("button", { name: "Give it back" }).click();
  await expect(detail.getByRole("button", { name: "Take control" })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "About this computer" })).toBeVisible();
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_docs.py -q`
Expected: FAIL: the three new tests (the map lacks the two files, the Architecture section lacks the names, the README lacks the note).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && make e2e`
Expected: the two changed specs pass already, because Tasks 12 and 13 built the face they drive. If either fails, fix the code, not the spec, unless the spec contradicts this plan. Every other spec passes as before.

- [ ] **Step 4: The docs**

In `CLAUDE.md`, replace this line:

```markdown
- `docs/plans/2026-10-14-roost-projects-hub.md` — the projects hub plan: Category becomes Project, schema v13, `roost/projects/` (`numbers.py`, `ProjectService`, the project tools), the `/api/projects` and top-up routes, and the Board's Projects tab with a page per project.
```

with:

```markdown
- `docs/plans/2026-10-14-roost-projects-hub.md` — the projects hub plan: Category becomes Project, schema v13, `roost/projects/` (`numbers.py`, `ProjectService`, the project tools), the `/api/projects` and top-up routes, and the Board's Projects tab with a page per project.
- `docs/plans/2026-10-15-roost-live-control-design.md` — live control (Grok-style Take control) design: a CDP screencast plus input on a live screen, this Mac only, nothing typed ever logged, Vault: site logins, bot windows out of the way.
- `docs/plans/2026-10-15-roost-live-control.md` — the live control plan: `CdpClient.subscribe`, `roost/desk/live_input.py`, `LiveSession` (`roost/desk/live.py`), `WS /api/bots/{id}/live`, Show window on Mac, `read_page` skipping text boxes, schema v14 (`site_logins`, `roost/vault/`), and the `LiveScreen` on the Computer tab.
```

Then append this paragraph to the end of the "## Architecture (Night-1 slice)" section of `CLAUDE.md` (after the paragraph that starts "A project (the `money_projects` table, schema v13)"):

```markdown

Take control opens a live screen (live control, `docs/plans/2026-10-15-roost-live-control-design.md`). `WS /api/bots/{id}/live` (`roost/gateway/routes/live.py`) accepts only this Mac (127.0.0.1 or ::1; any peer of the gateway container, whose port is published on the Mac's 127.0.0.1 alone; never a forwarded request), Roost's origin, your own bot and a held control, and closes with 4000 the moment control is released. `LiveSession` (`roost/desk/live.py`) screencasts the bot's page over the bot's own CDP connection (`CdpClient.subscribe`), acks each frame, follows pop-ups the bot's page opens and comes back when they close, and sends checked input (`roost/desk/live_input.py`): an allow-list of keys, a capped paste, a rate limit. Nothing typed is ever logged, stored or published, and `read_page` skips every node inside a text box, so typed values never reach a bot. Give it back can name the account you used: Vault: site logins (`roost/vault/`, schema v14 `site_logins`, host and label `enc:v2`) keeps it per bot and site, it goes into that bot's prompt, and a password is never kept. Bot windows step aside when their tab opens (`BOT_WINDOW_ASIDE_STEPS`); Show window on Mac brings one back.
```

In `README.md`, replace these lines:

```markdown
- **Workspace containers are sealed.** Each bot's shell commands run in
```

with:

```markdown
- **Live control is this Mac only, and private.** Take control shows the
  bot's own page as a live screen in Roost: a CDP screencast over that
  bot's private browser connection, never VNC, screen sharing or a
  DevTools page, and only to a browser on this Mac (`roost/gateway/live_socket.py`).
  What you type there goes to that page and nowhere else: it is never
  logged, stored, published or shown to the bot, and a bot's `read_page`
  leaves out everything inside a page's text boxes. The one thing a bot
  may learn is which account you used, if you say so on Give it back
  (Vault: site logins, encrypted): an account name, never a password.
- **Workspace containers are sealed.** Each bot's shell commands run in
```

- [ ] **Step 5: Run everything**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_docs.py tests/test_vocabulary.py -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost/web && npm test`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && make e2e`
Expected: every spec passes, `stuck.spec.ts` and `computer.spec.ts` included.

- [ ] **Step 6: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost
git add web/e2e/stuck.spec.ts web/e2e/computer.spec.ts CLAUDE.md README.md tests/test_docs.py
git commit -m "test: E2E for live control on a Stuck card and the Computer tab; docs: live control and the Vault"
```

Run: `git -C /Users/blckit/Desktop/Code_Projects/roost status --short`
Expected: none of the five files is listed.

- [ ] **Step 7: The manual check, on the user's Mac (not in any test)**

With the user, on the always-on stack after it is rebuilt (`make rebuild`, then the keeper's own restart):
- A bot opens a real sign-in page. Take control from its Stuck card, sign in on the live screen (a "Sign in with Google" pop-up is followed and comes back), and give it back with the account's name.
- The bot carries on, the Computer tab lists the account, and `grep` finds the typed password nowhere in `~/Roost/data` or the gateway's logs.
- Note anything the spike line (Task 1) did not predict, such as a window that came to the front.

---

