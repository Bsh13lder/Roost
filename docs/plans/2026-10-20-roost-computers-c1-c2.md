# Roost Computers 2.0, C1 and C2 (a view-only Linux computer per bot, then Take control on it): Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to run this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.
> The SDD workspace is `.superpowers/sdd/2026-10-20-roost-computers-c1c2/` (contract, one brief per task, progress).

**Goal (C1):** each bot gets its own small Linux computer, a `roost-computer-<bot_id>` container with a screen
(TigerVNC `Xvnc` on a Unix socket), JWM, Chromium and a terminal button. The keeper starts, pauses, wakes and stops
it under a cap and a VM memory check. The bot's browser tools, the stuck detector and screenshots run against that
Chromium over CDP. You watch it live in the Computer tab (noVNC, every byte relayed through the gateway, view only),
or see "Computer is asleep". A per-bot switch picks "Linux computer" (the default) or "Mac Brave" (D1).

**Goal (C2):** **Take control** on that live view: the gateway forwards keyboard and mouse only while you hold the
control lock. It goes full screen with the bar "You're in control · I'm done". **I'm done** gives it back and asks the
optional "Which account did you use?", saved under **Vault: site logins**. `read_page` never sees what you typed in a
text box, and nothing you type is ever logged.

**Design:** `docs/plans/2026-10-20-roost-computers-2-design.md` §2, §3, §4 (CDP part), §5 (browser part), §8, §10
C1–C2, and its "User decisions" (D1 Mac Brave stays as a per-bot switch, off by default; D2 only the live-control parts
that carry over; D3 the browser is picked by the spike). **Measurements:** `docs/research/2026-10-20-computers-c0-spike.md`
and `spikes/computers-c0/` (Chromium; the custom seccomp profile; `start.sh` clears stale X and Singleton files; the
Docker VM has 3.83 GiB). **Carried over from live control** (`docs/plans/2026-10-15-roost-live-control-design.md` and
`docs/plans/2026-10-15-roost-live-control.md`): the accept rules (L1, D1 of that plan), no input logging (L2), the
`ControlLock`, Vault: site logins (its Tasks 9–11) and the `read_page` text-box fix (its Task 8). The CDP screencast
(its Tasks 2–5, 7, 12) is **not** built (D2). **Shell:** `docs/plans/2026-10-20-roost-polish-r1-design.md` R1.5
(the Computer tab lives in the bot panel, `?panel=computer`) and R1.13 (Computer is asleep).

**Not in scope:** the terminal feed and `run_command` (C3), click/type tools and Vault: API keys (C4), Skills (C5),
OpenCode and Claude Code in the computer, the phone, Android, whole-screen screenshots with mss (CDP screenshots stay),
moving cookies from Mac Brave (start fresh, design §8), encrypted volumes (§9; only the per-bot volume hook is made),
and the bot changing its own computer kind from the chat (D1's "says so in the chat / the bot asks" comes later; C1
has the Profile switch only).

**Tech:** Python 3.12+ (uv), FastAPI/Starlette, `websockets`, aiosqlite, pydantic 2, `cryptography` (`enc:v2`).
Docker Desktop (arm64) driven only by the keeper, always as an argv list. Images: `debian:bookworm-slim` (computer),
`python:3.12-slim-bookworm` (egress). Web: React 19 + Vite; **`@novnc/novnc`** (MPL-2.0, unmodified, from npm, a lazy
chunk). pytest, vitest (jsdom), Playwright.

---

## Global Constraints

- **Path guard, first in every task:** `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel`
  prints `/Users/blckit/Desktop/Code_Projects/roost` and `git … branch --show-current` prints `night-1`; else stop.
- **Where you may edit:** only under the repo, never `roost-ui/`. Never open `~/Roost/data`, the lazyclaw repo,
  `~/.claude/projects/**`, `~/Roost-review/` or the open-dot repos. No browser MCP tools.
- **The live Roost is never touched:** never stop, restart or call the gateway (18800) or the keeper (18801), never
  `make deploy`/`up`/`desk-keeper-install`. Scripts that import `roost` run with `ROOST_DATA_DIR=$(mktemp -d)
  ROOST_DESKS_DIR=$(mktemp -d)`. Only the manual check (Task 16, Part C) deploys, done by the orchestrator with the
  user's OK.
- **Docker:** implementers never run `docker` (unit tests fake the runner). Tests that need Docker carry
  `@pytest.mark.docker` and run only in the manual check. Every name the code creates starts with `roost-`
  (`roost-computer-<id>`, `roost-net-<id>`, `roost-profile-<id>`, `roost-egress`, `roost-out`); never prune or remove
  anything else. Before any `docker build` or `npm install`: `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`;
  fewer than 8 GB: stop and report.
- **127.0.0.1 only on the Mac.** No new host port. Neither container publishes a port (`-p`/`--publish`/`-P` never
  appear in an argv; a test pins it). The Mac keeps 18800, 18801 and 18803 only. The egress proxy inside the VM
  listens on `roost-egress:3128`, reachable only from the internal per-bot networks (Design meets code 6).
- **Licences:** only MIT/Apache-2.0/BSD/ISC/MPL-2.0 dependencies. GPL programs in the image (TigerVNC, the GNU
  userland) are separate, unmodified Debian packages that Roost never links; `THIRD_PARTY_NOTICES.md` says so.
  `web/tests/licenseGate.test.ts` stays green. noVNC files are used unmodified (MPL-2.0 file-level).
- **Data rules (CLAUDE.md):** `site_logins.host` and `.label` are `enc:v2` with `user_aad(user_id,
  "site_logins:<column>")`; `bots.computer` is a plaintext setting (`linux` | `mac_brave`). Every query names
  `user_id` in its WHERE; another user's bot is a **404** (or close **4404** on a socket).
- **Secrets of the screen (L2):** RFB bytes, keystrokes, pointer events and clipboard text are never logged, stored,
  audited or put in an event. The keeper audit records only the action, the bot id and a result word.
- **No LLM in tests** (`ROOST_MODEL=scripted`). Tests first (red, then green); ≥80% line coverage on new code
  (`uv run pytest --cov=roost --cov-fail-under=80`).
- **Code rules:** files ≤800 lines (typically 200–400), functions <50 lines, frozen dataclasses, pydantic at every
  boundary, plain-sentence errors, no magic values (server numbers in `roost/constants.py` section "Computers",
  web numbers in `web/src/components/computer/constants.ts`). Every colour/size from `tokens.css`; controls from
  `web/src/ui/`; the entry stays within `web/bundle-budget.json`.
- **Vocabulary:** Computer, Take control / Give it back (the bar's button says **I'm done**, which is Give it back),
  Computer is asleep, Vault: site logins, Stuck, Resting, On it, Off duty. "Linux computer" and "Mac Brave" name the
  two kinds.
- **Git:** other agents commit at the same time. Commit after each task's green tests; stage files **by name** (never
  `git add -A`, `-a` or `.`); never amend, rebase or reset; conventional messages with **no Co-Authored-By or any AI
  attribution line**.
- **Commands:** prefix `cd /Users/blckit/Desktop/Code_Projects/roost &&`. One file:
  `ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/<file>.py -q`. Web:
  `cd web && npx vitest run tests/<file>`, `npm test`, `npm run build && npm run size`. E2E:
  `ROOST_DESKS_DIR=$(mktemp -d) make e2e` (its own throwaway gateway, fake desk).

## Design meets code

1. **Schema v19 (Amendment S).** v16 is R1, v17 Tasks & Money, v18 Models & helpers, **v19 is Computers**, v20
   Routines. One migration, `Migration(19, "computers", …)`, holds both `bots.computer` (C1) and the `site_logins`
   table (C2), so C1 ships it whole and C2 adds no migration. **Task 1 starts only when `latest_version()` is 18.**
   If it is lower, stop and report (a gap would make v17/v18 never run on a database already at 19). If it is
   higher than 18, stop and ask: the number is fixed by the controller.
2. **The default kind.** `bots.computer TEXT NOT NULL DEFAULT 'linux'`: every bot, old and new, starts on its Linux
   computer (D1: Mac Brave only after the user turns it on). An old bot's Brave profile stays in
   `~/Roost/desks/<id>/browser`; switching back to Mac Brave uses it again.
3. **One `Desk` per (bot, kind).** `DeskFactory.for_bot(bot_id, computer)` caches by `(bot_id, computer)`. `"linux"`
   builds `KeeperDesk(..., computer="linux")`, which uses the keeper's `/computer/*` routes; `"mac_brave"` keeps today's
   `/browser/*` routes. Callers pass `bot.computer`. Switching the kind stops the old one and forgets it.
4. **Asleep means not running.** `DeskStatus.browser` is `"running"` only when the computer is running; paused,
   stopped and absent are `"stopped"`, so the web's asleep logic is unchanged. `DeskStatus` gains `computer:
   ComputerKind` and `state: ComputerState` (`running | paused | stopped | absent`). Viewing (screenshot, the live
   socket, `current_url`) never wakes; a browser call or **Open it** does.
5. **No room.** Starting a computer when `COMPUTERS_MAX_RUNNING` are running first stops the least recently used one
   that no viewer or control holds and that is not On it (the gateway passes the bot ids that are On it). If none can
   go, or the VM has less than `COMPUTER_START_MIN_FREE_MB` free after that, the keeper answers 409
   `{"detail": "no_room"}`. `KeeperDesk` then waits (activity line "Waiting for a free computer") and retries every
   `COMPUTER_ROOM_POLL_S` up to `COMPUTER_ROOM_WAIT_S`, then raises `DeskBusy`, which the browser tools turn into
   "All computers are busy right now. Try again in a few minutes." (Design §2's "the work item waits in the work
   queue" is approximated by this bounded wait; a real requeue comes with routines.)
6. **The egress listener.** The CLAUDE.md rule "bind 127.0.0.1, never 0.0.0.0" is about the Mac. Inside the VM,
   `roost-egress` must be reachable from the computers, so its proxy binds `0.0.0.0:3128` **inside its own network
   namespace**, publishes nothing, and is attached only to `roost-out` (the one outbound bridge, nothing else on it)
   and to each `roost-net-<id>` (internal). Its `is_blocked_address` policy refuses every private range, so a
   computer can't reach another computer, the gateway, `host.docker.internal` or the keeper through it (test pins).
   **The user confirms this exception at the manual check** (Open for the user, 1).
7. **No DNS in the computer.** The computer sits only on `roost-net-<id>` (`--internal`), so outside names don't
   resolve (spike §6); Docker's embedded DNS still resolves `roost-egress`. Chromium runs with
   `--proxy-server=http://roost-egress:3128`, `--proxy-bypass-list=<-loopback>` and
   `--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE roost-egress`.
8. **CDP path.** gateway `CdpClient` ⇄ keeper `WS /desks/{id}/computer/cdp` (text frames) ⇄ `docker exec -i --user
   10002:10002 roost-computer-<id> /usr/local/bin/roost-pipe cdp` ⇄ `/run/screen/cdp.sock` ⇄ `roost-computerd` ⇄
   Chromium's `--remote-debugging-pipe` (fds 3/4, NUL-framed JSON). The keeper splits the exec's stdout on NUL into
   text frames and writes each inbound frame plus NUL, exactly as `pipe_relay.py` does for Brave, so `CdpClient`,
   `DeskBrowserPage` and the stuck detector are unchanged.
9. **VNC path.** browser (noVNC) ⇄ gateway `WS /api/bots/{id}/live` (binary) ⇄ keeper `WS /desks/{id}/computer/vnc`
   (binary, per-computer `vnc_token`) ⇄ `docker exec -i … roost-pipe vnc` ⇄ `/run/screen/vnc.sock` (Xvnc, mode 0600,
   uid 10002). Bytes pass unchanged server→client. Client→server bytes go through `RfbClientFilter` (Task 8).
10. **Watching is enforced on the server.** `RfbClientFilter` parses every client→server RFB message. KeyEvent (4),
    PointerEvent (5), ClientCutText (6) and the QEMU extended key event (255/0) are input: forwarded only when the
    socket is in control mode **and** the user holds the lock at that moment (C2); in C1 every socket is view mode and
    input is always dropped. SetDesktopSize (251) and xvp (250) are always dropped. The extended-clipboard
    pseudo-encoding is stripped from SetEncodings, and an extended ClientCutText (negative length) is always dropped.
    Any unknown type, a client version other than `RFB 003.008\n`, a security type other than None (1), or an
    over-long message closes the socket with 4400. Server→client clipboard is turned off at the source: Xvnc runs
    with `-SendCutText=0 -SendPrimary=0 -AcceptSetDesktopSize=0`.
11. **Control is a second socket.** The Computer tab's view socket is `?mode=view` (never input). Take control opens
    a second socket `?mode=control`: accepted only while you hold the lock (else 4409 "Take control first."); it
    closes with 4000 "Given back." when the lock is released (`ControlLock.wait_released`). This is live control's
    accept rule word for word.
12. **The account's host.** "Which account did you use?" needs the site. `Desk.current_url()` reads the bot's page
    URL over CDP without waking it ("" when asleep); a Stuck card uses its own host. `VaultService` from live
    control's Task 11 uses it.
13. **R1 comes first.** C1's web task (Task 10) needs R1's bot panel (built) and R1 Task 10's `ComputerAsleep`. If
    `web/src/components/profile/ComputerAsleep.tsx` (or R1's name for it) is not in the tree, stop and report.

## Review Focus

- **Security review (a), the live socket relay and input gating** — after Task 9 (C1) and again after Task 11 (C2):
  the accept rules (session, 4404 for another user's bot, Origin 4403, loopback/container peer 4403, forwarded
  headers refused); `RfbClientFilter` fails closed on anything it doesn't know; input forwarded only in control mode
  while the lock is held (checked per message, not only at accept); the control socket closes on give-back; no RFB
  byte or typed text in logs, events, the audit or exceptions (`test_a_typed_password_is_in_no_log_event_or_audit`);
  the keeper's vnc token check; viewer cap.
- **Security review (b), keeper and container hardening** — after Task 6: `--cap-drop ALL`, `--security-opt
  no-new-privileges`, the custom seccomp profile (Docker's default plus exactly `clone`, `clone3`, `unshare`, `setns`,
  `chroot`; never `unconfined`; no `--no-sandbox`), `--read-only` with tmpfs, `--user 10002:10002`, no published
  port, `--internal` network, resource limits, the 0700 `/run/screen`, `docker exec --user 10002:10002` only, argv
  lists only (no shell), bot ids validated as UUID4 before any argv, names only `roost-*`, the egress blocklist on
  VM ranges.
- **Light reviews elsewhere** (user's standing rule): the rest is checked by tests and the manual check.

---

## Shared Contract (every task uses these exact names)

### Constants (`roost/constants.py`, new section "Computers" at the end; Task 1 creates it, later tasks add)

```python
# Computers 2.0, C1/C2 (docs/plans/2026-10-20-roost-computers-c1-c2.md)
COMPUTER_KINDS = ("linux", "mac_brave")
DEFAULT_COMPUTER = "linux"
COMPUTER_IMAGE = "roost-computer:dev"
EGRESS_IMAGE = "roost-egress:dev"
COMPUTER_CONTAINER_PREFIX = "roost-computer-"
COMPUTER_NETWORK_PREFIX = "roost-net-"
COMPUTER_PROFILE_VOLUME_PREFIX = "roost-profile-"
EGRESS_CONTAINER = "roost-egress"
EGRESS_OUT_NETWORK = "roost-out"
EGRESS_PORT = 3128                         # inside the VM only; never published
COMPUTER_UID = 10002
COMPUTER_MEMORY = "1500m"
COMPUTER_SHM_SIZE = "512m"
COMPUTER_CPUS = "1.5"
COMPUTER_PIDS_LIMIT = "512"
COMPUTER_TMPFS_TMP = "/tmp:rw,size=256m"
COMPUTER_SCREEN_WIDTH = 1280
COMPUTER_SCREEN_HEIGHT = 800
COMPUTERS_MAX_RUNNING = 3
COMPUTER_PAUSE_AFTER_S = 300               # idle → docker pause (RAM kept, ~0.2 s to wake)
COMPUTER_STOP_AFTER_S = 1800               # idle → docker stop (RAM freed, profile kept)
COMPUTER_SWEEP_EVERY_S = 30
COMPUTER_START_MIN_FREE_MB = 600           # the VM must have this much free to start one more
COMPUTER_ROOM_WAIT_S = 60
COMPUTER_ROOM_POLL_S = 5
COMPUTER_BOOT_TIMEOUT_S = 20               # until roost-pipe can reach cdp.sock
COMPUTER_DOCKER_CALL_TIMEOUT_S = 15.0
LIVE_VIEWERS_MAX = 2                       # view sockets per bot (tabs); control is one more
LIVE_RELAY_CHUNK_MAX = 262144
RFB_CLIENT_VERSION = b"RFB 003.008\n"
RFB_SECURITY_NONE = 1
RFB_SET_ENCODINGS_MAX = 64
RFB_FENCE_MAX = 64
RFB_EXT_CLIPBOARD_ENCODING = -1063131698   # 0xC0A1E5CE, always stripped
LIVE_PASTE_MAX_CHARS = 2000
LIVE_INPUT_MAX_PER_SECOND = 240
LIVE_INPUT_RATE_WINDOW_S = 1.0
LIVE_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
LIVE_FORWARDED_HEADERS = ("forwarded", "x-forwarded-for", "x-real-ip")
LIVE_CLOSE_GIVEN_BACK = 4000
LIVE_CLOSE_PROTOCOL = 4400
LIVE_CLOSE_UNAUTHENTICATED = 4401
LIVE_CLOSE_REFUSED = 4403
LIVE_CLOSE_NOT_FOUND = 4404
LIVE_CLOSE_NOT_HELD = 4409
LIVE_CLOSE_ASLEEP = 4410
LIVE_CLOSE_TOO_MANY = 4429
LIVE_CLOSE_UNAVAILABLE = 4503
SITE_LOGIN_LABEL_MAX_CHARS = 100
SITE_LOGIN_LIST_LIMIT = 50
SITE_LOGINS_IN_PROMPT = 10
FAKE_SCREEN_WIDTH = 320
FAKE_SCREEN_HEIGHT = 200
```

### Schema v19 "computers" (`roost/db/migrations.py`, Task 1; `tests/fixtures/schema_v18.sql` frozen first)

```python
# Computers 2.0 C1/C2: the per-bot computer kind (plaintext setting) and Vault: site logins.
Migration(19, "computers", (
    AddColumn("bots", "computer", "TEXT NOT NULL DEFAULT 'linux'"),   # linux | mac_brave
    _SITE_LOGINS,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_site_logins_one ON site_logins(user_id, bot_id, host_key)",
    "CREATE INDEX IF NOT EXISTS idx_site_logins_bot ON site_logins(user_id, bot_id, updated_at)",
)),
```

`_SITE_LOGINS` is live control's table exactly: `id`, `user_id` (cascade), `bot_id` (cascade), `host` (`enc:v2`,
AAD `site_logins:host`), `host_key` (HMAC of the normalised host with the DEK; the unique key, never the host),
`label` (`enc:v2`, AAD `site_logins:label`), `created_at`, `updated_at`.

### Python names

**`roost/bots/models.py`, `roost/bots/store.py`** (Task 1): `ComputerKind = Literal["linux", "mac_brave"]`;
`Bot.computer: ComputerKind = "linux"`; `BotPatch.computer: ComputerKind | None = None` (None keeps it);
`BotStore.update` writes it; `BotOut.computer`; the `bot_updated` frame carries it. Never in a prompt, roster or
Template file.

**`docker/computer/`** (Task 2): `Dockerfile`, `start.sh`, `roost_computerd.py` (installed as
`/usr/local/bin/roost-computerd`), `roost_pipe.py` (`/usr/local/bin/roost-pipe`), `system.jwmrc`, `licences.sh`.
`roost/keeper/seccomp/chromium.json` (package data). Pure functions tested from the repo:

```python
# docker/computer/roost_computerd.py (stdlib only)
def xvnc_argv(width: int, height: int, socket_path: str) -> list[str]: ...
def chromium_argv(profile_dir: str, proxy: str) -> list[str]: ...
def stale_files(home: str, display: int) -> tuple[str, ...]: ...   # X lock, X socket, vnc.sock, cdp.sock, Singleton*
class RestartBudget:                                                 # at most N restarts per window
    def __init__(self, limit: int, window_s: float, clock: Callable[[], float]) -> None: ...
    def allow(self) -> bool: ...
# docker/computer/roost_pipe.py (stdlib only)
SOCKETS = {"cdp": "/run/screen/cdp.sock", "vnc": "/run/screen/vnc.sock"}
def socket_for(name: str) -> str: ...                                # ValueError for anything else
```

**`roost/keeper/networks.py`** (Task 3): `network_name(bot_id)`, `build_network_create_argv(bot_id)`
(`--internal`, label `app.roost.bot=<id>`), `build_network_remove_argv(bot_id)`, `build_egress_connect_argv(bot_id)`,
`build_egress_run_argv()`, `build_out_network_create_argv()`; `class EgressNetworks` (`ensure_egress()`,
`ensure_bot_network(bot_id)`, `remove_bot_network(bot_id)`), runner injectable like `WorkspaceManager`.
**`roost/keeper/egress_main.py`** (Task 3): `main()` runs `EgressProxy(host="0.0.0.0", port=EGRESS_PORT,
database_dir=None)` inside `roost-egress` only; refuses to start unless `ROOST_IN_EGRESS=1`.

**`roost/keeper/computers.py`** (Task 4):

```python
ComputerState = Literal["running", "paused", "stopped", "absent"]
def container_name(bot_id: str) -> str: ...                 # "roost-computer-<id>"; ValueError unless UUID4
def profile_volume(bot_id: str) -> str: ...
def build_run_argv(bot_id: str, seccomp_path: Path) -> list[str]: ...
def build_pipe_argv(bot_id: str, which: Literal["cdp", "vnc"]) -> list[str]: ...   # docker exec -i --user 10002:10002 …
def build_pause_argv / build_unpause_argv / build_stop_argv / build_start_existing_argv / build_remove_argv /
    build_volume_remove_argv / build_list_argv (bot_id) -> list[str]
def parse_list_output(stdout: str) -> dict[str, ComputerState]: ...
class ComputerStartError(RuntimeError): ...
@dataclass(frozen=True)
class ComputerHandle:
    bot_id: str; cdp_token: str; vnc_token: str
class ComputerManager:
    def __init__(self, config: RoostConfig, networks: EgressNetworks, *, runner: Runner | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None: ...
    def state(self, bot_id: str) -> ComputerState: ...
    def handle(self, bot_id: str) -> ComputerHandle | None: ...   # only while running; mints tokens once per process
    async def reconcile(self) -> None: ...
    async def start(self, bot_id: str) -> ComputerHandle: ...      # run, start or unpause; waits for boot
    async def pause(self, bot_id: str) -> None: ...
    async def stop(self, bot_id: str) -> None: ...
    async def remove(self, bot_id: str) -> None: ...               # container, profile volume, network
    def touch(self, bot_id: str) -> None: ...                      # last used = now
    def last_used(self, bot_id: str) -> float | None: ...
```

**`roost/keeper/computer_room.py`** (Task 5):

```python
@dataclass(frozen=True)
class RoomView:
    running: tuple[str, ...]          # bot ids running (not paused)
    last_used: Mapping[str, float]
    held: frozenset[str]              # a viewer or control socket is open
    busy: frozenset[str]              # On it, from the gateway
    free_mb: int | None               # None: the reading failed (treated as no room)
@dataclass(frozen=True)
class RoomDecision:
    kind: Literal["start", "evict_then_start", "no_room"]
    evict: str | None = None
def decide(bot_id: str, view: RoomView) -> RoomDecision: ...
def idle_actions(view: RoomView, paused: frozenset[str], now: float) -> tuple[tuple[str, Literal["pause", "stop"]], ...]: ...
def parse_mem_total(stdout: str) -> int | None: ...       # `docker info --format {{.MemTotal}}` → MB
def parse_mem_usage(stdout: str) -> int | None: ...       # `docker stats --no-stream --format {{.MemUsage}}` lines → MB
class ComputerRoom:
    def __init__(self, manager: ComputerManager, *, runner: Runner | None = None, clock=time.monotonic) -> None: ...
    def hold(self, bot_id: str) -> None: ...; def release(self, bot_id: str) -> None: ...
    async def free_mb(self) -> int | None: ...
    async def admit(self, bot_id: str, busy: frozenset[str]) -> ComputerHandle: ...   # NoRoom
    async def sweep(self) -> None: ...                    # one pass of idle_actions
    async def run_sweeper(self) -> None: ...              # every COMPUTER_SWEEP_EVERY_S until cancelled
class NoRoom(RuntimeError): ...
```

**`roost/keeper/exec_pipe.py`** (Task 6):

```python
class ExecPipe:                                          # one `docker exec -i … roost-pipe <which>` process
    @classmethod
    async def open(cls, argv: Sequence[str]) -> "ExecPipe": ...
    async def write(self, data: bytes) -> None: ...
    async def read(self) -> bytes: ...                   # b"" at EOF; at most LIVE_RELAY_CHUNK_MAX
    async def close(self) -> None: ...                   # terminate, then kill after a grace; never raises
class NulFramer:                                         # CDP framing over a byte stream
    def feed(self, data: bytes) -> tuple[str, ...]: ...  # complete UTF-8 messages
```

**`roost/desk/__init__.py`** (Tasks 7, 8, 14):

```python
ComputerKind = Literal["linux", "mac_brave"]
ComputerState = Literal["running", "paused", "stopped", "absent"]
@dataclass(frozen=True)
class DeskStatus:
    browser: Literal["running", "stopped"]
    workspace: Literal["running", "stopped", "absent"]
    computer: ComputerKind = "mac_brave"
    state: ComputerState | None = None                   # None for Mac Brave
class DeskBusy(RuntimeError): ...                         # no free computer after COMPUTER_ROOM_WAIT_S
class ScreenStream(Protocol):                            # RFB bytes, both ways (Task 8)
    async def send(self, data: bytes) -> None: ...
    async def receive(self) -> bytes: ...                # b"" when the far end closed
    async def close(self) -> None: ...
class Desk(Protocol):
    ...                                                  # today's methods
    async def open_screen(self) -> ScreenStream: ...     # never wakes: DeskAsleep / DeskUnavailable; Mac Brave: DeskUnavailable
    async def current_url(self) -> str: ...              # Task 14; "" when asleep, never wakes
DeskFactory.for_bot(self, bot_id: str, computer: ComputerKind) -> Desk
DeskFactory.forget(self, bot_id: str) -> None            # both kinds
```

**`roost/desk/client.py`** (Tasks 7, 8): `KeeperClient.start_computer(bot_id, busy) / attach_computer / pause_computer /
stop_computer`; `KeeperDesk(config, bot_id, *, computer: ComputerKind = "mac_brave", busy: Callable[[], frozenset[str]]
= frozenset, on_wait: Callable[[], Awaitable[None]] | None = None, …)`; `_cdp_url(keeper_url, bot_id, computer)`;
`_vnc_url(keeper_url, bot_id)`; `KeeperScreen` (a `ScreenStream` over a `websockets` client).

**`roost/desk/rfb.py`** (Task 8):

```python
RfbVerdict = Literal["forward", "drop", "close"]
@dataclass(frozen=True)
class RfbMessage:
    kind: Literal["handshake", "set_pixel_format", "set_encodings", "update_request", "key", "pointer",
                  "cut_text", "continuous_updates", "fence", "desktop_size", "xvp", "qemu_key"]
    data: bytes                                          # the exact bytes to forward (set_encodings may be rewritten)
    is_input: bool
class RfbProtocolError(ValueError): ...                  # never carries the bytes
class RfbClientFilter:
    def __init__(self, *, paste_max: int = LIVE_PASTE_MAX_CHARS) -> None: ...
    def feed(self, data: bytes) -> tuple[RfbMessage, ...]: ...          # buffers partial messages; RfbProtocolError
def verdict(message: RfbMessage, input_allowed: bool) -> RfbVerdict: ...
class InputRateLimit:                                    # as live control's, LIVE_INPUT_MAX_PER_SECOND
    def __init__(self, *, limit: int | None = None, clock: Callable[[], float] = time.monotonic) -> None: ...
    def allow(self) -> bool: ...
```

**`roost/desk/fake_screen.py`** (Task 8): `FakeScreen` (a `ScreenStream` and a tiny RFB 3.8 server: security None,
`ServerInit` `FAKE_SCREEN_WIDTH`×`FAKE_SCREEN_HEIGHT`, 32 bpp, name "Fake computer"; a non-incremental
FramebufferUpdateRequest gets one Raw rectangle of the whole screen in one colour); `received_input: int` (count only,
never the bytes). `FakeDesk(..., computer="linux")`: `open_screen()` returns a fresh `FakeScreen` while
`browser == "running"`, else `DeskAsleep`; `current_url()` returns the last opened page or "".

**`roost/gateway/live_socket.py`** (Task 9; live control's Task 6 accept rules):

```python
NOT_THIS_MAC_REASON = "Live control works only on this Mac for now."
ORIGIN_REASON = "Origin not allowed."
SIGN_IN_REASON = "Sign in first."
NOT_FOUND_REASON = "Bot not found"
NOT_HELD_REASON = "Take control first."
GIVEN_BACK_REASON = "Given back."
ASLEEP_REASON = "asleep"
TOO_MANY_REASON = "The screen is open in too many tabs."
PROTOCOL_REASON = "The screen sent something Roost doesn't understand."
UNAVAILABLE_REASON = "The bot's computer stopped answering."
LiveMode = Literal["view", "control"]
@dataclass(frozen=True)
class Refusal:
    code: int; reason: str
def peer_is_this_mac(websocket: WebSocket, config: RoostConfig) -> bool: ...
async def live_refusal(websocket: WebSocket, bot_id: str, mode: LiveMode) -> tuple[Bot, None] | tuple[None, Refusal]: ...
class LiveViewers:                                       # app.state.live_viewers; per-bot count, cap LIVE_VIEWERS_MAX
    def enter(self, bot_id: str, mode: LiveMode) -> bool: ...
    def leave(self, bot_id: str, mode: LiveMode) -> None: ...
```

**`roost/gateway/routes/live.py`** (Task 9, Task 11): `live_router`; `WS /api/bots/{bot_id}/live?mode=view|control`;
`async def relay_screen(websocket, screen, *, input_allowed: Callable[[], bool]) -> None` (two pumps; the client pump
runs `RfbClientFilter` + `verdict` + `InputRateLimit`; the server pump forwards bytes).

**`roost/desk/control.py`** (Task 11): `ControlLock.wait_released(bot_id: str) -> None` (async; returns at once when
nobody holds it).

**Vault (Tasks 13–14):** live control's `roost/vault/models.py`, `roost/vault/store.py`, `roost/vault/service.py`
names exactly (`SiteLogin`, `SignIn`, `SiteLoginOut`, `NoSite`, `NO_SITE_TEXT`, `clean_label`, `AccountLabel`,
`GiveBackIn`, `normalize_host`, `signed_in_line`, `host_key`, `SiteLoginStore`, `VaultService`), except that
`VaultService.sign_in` reads the host from `Desk.current_url()` instead of live control's `bot_page_url`, and the
schema is v19 (already made by Task 1).

### Keeper routes (signed like today; the WebSocket routes use `X-Roost-Desk-Token`)

| Route | Task | Result |
|---|---|---|
| `GET /desks/{id}` | 6 | today's body plus `"computer": ComputerState` |
| `POST /desks/{id}/computer/start` body `{"busy": [bot_id, …]}` | 6 | 200 `{"computer": "running", "cdp_token", "vnc_token"}` · 409 `{"detail": "no_room"}` · 500 `"failed to start the bot's computer"` |
| `POST /desks/{id}/computer/attach` | 6 | running only: 200 tokens · 409 `"asleep"` (never wakes) |
| `POST /desks/{id}/computer/pause` · `/stop` | 6 | 200 `{"computer": state}` |
| `WS /desks/{id}/computer/cdp` | 6 | text frames; 4400 bad id · 4401 bad token · 4404 not running · 4409 taken over |
| `WS /desks/{id}/computer/vnc` | 6 | binary frames; 4400 · 4401 · 4404 · 4429 more than `LIVE_VIEWERS_MAX + 1` |
| `DELETE /desks/{id}` | 6 | also removes the computer, its profile volume and its network |

### Gateway routes and wire

| Route | Task | Result |
|---|---|---|
| `PATCH /api/bots/{id}` | 1, 10 | takes `"computer": "linux" \| "mac_brave"`; switching stops the old kind (Task 10) |
| `GET /api/bots/{id}/desk` | 7 | `{"browser", "workspace", "computer", "state"}` |
| `POST /api/bots/{id}/desk/browser/start` · `/stop` | 7 | start = wake the bot's computer of its kind; 409 `"All computers are busy right now. Try again in a few minutes."` on `DeskBusy` |
| `WS /api/bots/{id}/live?mode=view` | 9 | binary RFB both ways; input always dropped |
| `WS /api/bots/{id}/live?mode=control` | 11 | as view, plus input while the lock is held; 4409 without it; 4000 on give-back |
| `DELETE /api/bots/{id}/control` | 14 | optional `{"account": str \| null}` (live control) |
| `GET /api/bots/{id}/site-logins` · `DELETE …/site-logins/{login_id}` | 14 | live control's |
| `POST /api/stuck/{id}/clear` | 14 | optional `account` (live control) |

**Close codes on `/live`:** 4000 "Given back." · 4400 PROTOCOL · 4401 "Sign in first." · 4403 NOT_THIS_MAC / ORIGIN ·
4404 "Bot not found" · 4409 "Take control first." · 4410 "asleep" · 4429 TOO_MANY · 4503 UNAVAILABLE. A Mac Brave bot
has no live screen: 4410 is never sent for it; it closes 4503 and the web never opens one (Task 10).

### Web names

- `web/src/components/computer/constants.ts`: `LIVE_CLOSE` (`givenBack: 4000, protocol: 4400, signIn: 4401,
  refused: 4403, notFound: 4404, notHeld: 4409, asleep: 4410, tooMany: 4429, unavailable: 4503`),
  `COMPUTER_KIND_LABELS = { linux: "Linux computer", mac_brave: "Mac Brave" }`, `ACCOUNT_MAX_CHARS = 100`.
- `web/src/lib/novnc.ts`: `loadRfb(): Promise<RfbClass>`, the **only** module that imports `@novnc/novnc`.
- `web/src/api/live.ts`: `liveUrl(botId, mode)`, `LiveMode`, `statusFor(code): LiveStatus`.
- `web/src/hooks/useLiveScreen.ts`: `LiveStatus = "connecting" | "live" | "ended" | "asleep" | "refused" |
  "unreachable"`; `useLiveScreen(botId, mode, container: RefObject<HTMLDivElement>, open?: SocketOpener) → { status,
  reason, retry }`. It opens its own `WebSocket` (to read close codes) and hands it to `new RFB(container, socket,
  { viewOnly: mode === "view" })` with `scaleViewport = true`, `resizeSession = false`.
- `web/src/components/computer/LiveScreen.tsx` (`{ bot, mode, onEnded? }`), `ComputerKindSwitch.tsx`
  (`{ bot, onChange }`), `ControlScreen.tsx` (full screen; bar "You're in control" · **I'm done**), `GiveBackForm.tsx`
  (`{ site, botName, onConfirm(account | null), onCancel }`, "Which account did you use?"), `SiteLogins.tsx`.
- `web/src/api/types.ts`: `BotOut.computer`, `DeskStatusOut.computer` / `.state`, `SiteLoginOut`;
  `web/src/api/vault.ts`: `listSiteLogins`, `forgetSiteLogin`; `web/src/api/computer.ts`: `giveBack(botId, account =
  null)`; `web/src/api/stuck.ts`: `clearStuck(cardId, body?)`.

### File structure

| File | Task |
|---|---|
| `tests/fixtures/schema_v18.sql` (new, frozen first), `roost/db/migrations.py`, `roost/bots/{models,store}.py`, `roost/gateway/routes/bots.py`, `roost/constants.py` | 1 |
| `docker/computer/{Dockerfile,start.sh,roost_computerd.py,roost_pipe.py,system.jwmrc,licences.sh}`, `roost/keeper/seccomp/chromium.json`, `Makefile` | 2 |
| `docker/egress/Dockerfile`, `roost/keeper/egress_main.py`, `roost/keeper/networks.py`, `Makefile` | 3 |
| `roost/keeper/computers.py` | 4 |
| `roost/keeper/computer_room.py` | 5 |
| `roost/keeper/exec_pipe.py`, `roost/keeper/computer_routes.py`, `roost/keeper/app.py` | 6 |
| `roost/desk/__init__.py`, `roost/desk/client.py`, `roost/desk/fake.py`, `roost/gateway/routes/desk.py`, `roost/talk/runner.py`, `roost/gateway/routes/bots.py` | 7 |
| `roost/desk/rfb.py`, `roost/desk/fake_screen.py`, `roost/desk/client.py`, `roost/desk/fake.py` | 8 |
| `roost/gateway/live_socket.py`, `roost/gateway/routes/live.py`, `roost/gateway/app.py` | 9 |
| `web/package.json`, `web/src/lib/novnc.ts`, `web/src/api/live.ts`, `web/src/hooks/useLiveScreen.ts`, `web/src/components/computer/*`, `web/src/components/profile/ComputerTab.tsx`, `web/src/styles/computer.css` | 10 |
| `roost/desk/control.py`, `roost/gateway/routes/live.py` | 11 |
| `roost/desk/browser.py` | 12 |
| `roost/vault/{__init__,models,store}.py`, `roost/talk/{instructions,turn,runner}.py` | 13 |
| `roost/vault/service.py`, `roost/gateway/routes/vault.py`, `roost/gateway/routes/desk.py`, `roost/stuck/service.py`, `roost/gateway/routes/stuck.py`, `roost/desk/*` (`current_url`) | 14 |
| `web/src/components/computer/{ControlScreen,GiveBackForm,SiteLogins}.tsx`, `web/src/components/StuckCard.tsx`, `web/src/api/{computer,stuck,vault,types}.ts` | 15 |
| `web/e2e/computer-live.spec.ts`, `web/e2e/{computer,stuck}.spec.ts`, `THIRD_PARTY_NOTICES.md`, `CLAUDE.md`, `README.md`, `tests/test_docs.py`, `docs/research/2026-10-20-computers-c0-spike.md` (C1 addendum) | 16 |

---

## Batches

| Batch | Tasks | Phase | Review |
|---|---|---|---|
| A | 1, 2, 3 | C1 foundations: schema v19 and the switch field, the computer image, the egress | — |
| B | 4, 5, 6 | C1 keeper: lifecycle, room, routes and the exec relay | **Security review (b)** after Task 6 |
| C | 7, 8, 9 | C1 gateway: the computer desk, the RFB filter and fake screen, the view socket | **Security review (a)** after Task 9 |
| D | 10 | C1 web: noVNC chunk, live view, asleep, the switch | Manual check C1 (Task 16 Part C, steps 1–8) |
| E | 11, 12, 13, 14 | C2 server: control mode, `read_page` fix, Vault | **Security review (a)** again after Task 11 |
| F | 15, 16 | C2 web, E2E, notices, docs, manual check C2 | — |

Order inside a batch: A: 1 is independent of 2–3. B: 4 → 5 → 6. C: 7 → 8 → 9. E: 11 and 12 are independent; 13 → 14.

---

### Task 1: Schema v19 "computers" and the bot's computer kind

**Precondition:** `uv run python -c "from roost.db.migrations import latest_version; print(latest_version())"` prints
`18` (Design meets code 1). Otherwise stop and report.

**Files:**
- Create: `tests/fixtures/schema_v18.sql` (**first**, dumped from a fresh v18 database, like `schema_v15.sql`),
  `tests/test_migration_v19.py`
- Modify: `roost/db/migrations.py` (`_SITE_LOGINS`, `Migration(19, "computers", …)`), `roost/constants.py` (the
  "Computers" section, the whole block from the Shared Contract), `roost/bots/models.py` (`ComputerKind`,
  `Bot.computer`, `BotPatch.computer`), `roost/bots/store.py` (read and write `computer`), `roost/gateway/routes/bots.py`
  (`BotOut.computer`, PATCH field, the `bot_updated` frame), `tests/test_bot_store.py`, `tests/test_bots_api.py`,
  `tests/test_migrations.py` (latest is 19)

**Tests:**
- `test_v18_upgrades_to_v19_additively` (fixture → migrate: `bots.computer` exists with `'linux'` on old rows;
  `site_logins` and both indexes exist; running twice is a no-op).
- `test_a_new_bot_gets_the_linux_computer`, `test_patch_sets_the_computer_kind_and_keeps_it_when_absent`,
  `test_an_unknown_computer_kind_is_a_422`, `test_another_users_bot_cannot_switch_its_computer` (404, unchanged).
- `test_the_computer_kind_never_reaches_a_prompt_or_template` (`build_instructions`, the roster and
  `template_file` don't contain it).

- [ ] Step 1: Path guard and the precondition.
- [ ] Step 2: Freeze `tests/fixtures/schema_v18.sql`; write the tests; red.
- [ ] Step 3: Implement; green; full `uv run pytest -q`.
- [ ] Step 4: Commit

```bash
git add tests/fixtures/schema_v18.sql tests/test_migration_v19.py tests/test_migrations.py roost/db/migrations.py roost/constants.py roost/bots/models.py roost/bots/store.py roost/gateway/routes/bots.py tests/test_bot_store.py tests/test_bots_api.py && git commit -m "feat: schema v19 gives each bot a computer kind (Linux computer by default) and the site_logins table"
```

### Task 2: The `roost-computer` image

Spike-proven parts (`spikes/computers-c0/`): `debian:bookworm-slim` **pinned by digest**, `tigervnc-standalone-server`,
`jwm`, `xterm`, `tini`, `chromium`, `fonts-liberation`, `python3` (for our two stdlib scripts), `ca-certificates`,
`--no-install-recommends`, apt lists removed. User `comp` uid/gid 10002; `/home/comp/profile` and `/run/screen` owned by
10002 (`/run/screen` mode 0700). No `EXPOSE`. `USER 10002`. `ENTRYPOINT ["/usr/bin/tini", "--", "/start.sh"]`.

- **`start.sh`** removes `stale_files()` (`/tmp/.X1-lock`, `/tmp/.X11-unix/X1`, `/run/screen/vnc.sock`,
  `/run/screen/cdp.sock`, `/home/comp/profile/Singleton*`), then `exec roost-computerd`.
- **`roost_computerd.py`** (stdlib, <400 lines): starts `Xvnc :1 -geometry 1280x800 -depth 24 -rfbport -1
  -rfbunixpath /run/screen/vnc.sock -rfbunixmode 0600 -SecurityTypes None -AlwaysShared -nolisten tcp
  -SendCutText=0 -SendPrimary=0 -AcceptSetDesktopSize=0`; then `jwm`; then Chromium with
  `--remote-debugging-pipe` on fds 3/4 (`pass_fds`), `--user-data-dir=/home/comp/profile`, `--no-first-run`,
  `--no-default-browser-check`, the three anti-throttling flags `browsers.py` uses, `--window-size=1280,800`,
  `--start-maximized`, `--disk-cache-dir=/tmp/chromium-cache`, the proxy flags of Design meets code 7,
  `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`, and **never** `--no-sandbox`. It serves
  `/run/screen/cdp.sock` (mode 0600): one client at a time, the newest replaces the older, bytes copied both ways
  unchanged. It restarts Chromium when it exits, within `RestartBudget(5, 60 s)`; Xvnc dying ends the container
  (Docker restarts nothing: the keeper sees it stopped). Its log lines say only which program started or stopped.
- **`roost_pipe.py`**: `roost-pipe cdp|vnc` connects stdin/stdout to the socket from `socket_for()` and copies bytes
  until either side closes; anything else exits 2.
- **`system.jwmrc`**: one tray with a "Terminal" button (`xterm`) and a "Browser" button that does nothing when
  Chromium is already running; no root-menu "Exit" or "Restart".
- **`roost/keeper/seccomp/chromium.json`**: `spikes/computers-c0/chromium-seccomp.json` (moby/profiles `default.json`,
  Apache-2.0, plus one unconditional allow for `clone`, `clone3`, `unshare`, `setns`, `chroot`), with an SPDX
  header line in a sibling `chromium.json.license` and a `THIRD_PARTY_NOTICES.md` entry (Task 16 writes the entry;
  this task adds the `.license` file). Packaged in the wheel (check `uv build` includes it).
- **`licences.sh`**: the spike's scan, run as the last `RUN` of the build: fails the build on an AGPL or SSPL package,
  and prints the GPL/LGPL list.
- **`Makefile`**: `computer-image` (disk guard, then `docker build -t roost-computer:dev docker/computer`), and
  `deploy` builds it when missing, like `workspace-image`.

**Files:** Create the `docker/computer/` files above, `roost/keeper/seccomp/__init__.py` (empty, for
`importlib.resources`), `roost/keeper/seccomp/chromium.json`, `roost/keeper/seccomp/chromium.json.license`,
`tests/test_computer_image_spec.py`, `tests/test_computerd.py`, `tests/test_computer_image_real.py`
(`@pytest.mark.docker`). Modify `Makefile`, `tests/test_makefile.py` (if it exists; else the guard goes in
`test_computer_image_spec.py`).

**Tests:**
- `test_computer_image_spec.py`: the base is pinned by `@sha256:`; `USER 10002`; no `EXPOSE`; tini is PID 1; no
  `websockify`, `x11vnc`, `xpra` or `kasmvnc` anywhere; `licences.sh` runs in the build; `make computer-image` runs the
  disk guard before `docker build`; the seccomp profile equals Docker's default plus exactly the five syscalls (diff
  against `spikes/computers-c0/default-seccomp.json`), and has no `SCMP_ACT_ALLOW` default.
- `test_computerd.py` (loads `docker/computer/roost_computerd.py` by path with `importlib.util`):
  `test_xvnc_listens_on_a_unix_socket_only_with_clipboard_out_off`, `test_chromium_keeps_its_sandbox_and_uses_the_proxy`,
  `test_stale_files_cover_the_x_lock_the_sockets_and_singleton`, `test_restart_budget_stops_a_crash_loop`,
  `test_roost_pipe_knows_only_cdp_and_vnc`.
- `test_computer_image_real.py` (docker, run in the manual check only): builds nothing; given the built image, runs it
  with Task 4's argv and checks Chromium is up with the sandbox on (no "No usable sandbox" in its log), `getent hosts
  example.com` fails, a stop/start boots again (stale files cleared).

- [ ] Step 1: Path guard.
- [ ] Step 2: Tests; red.
- [ ] Step 3: Implement (no `docker build` here).
- [ ] Step 4: Green; commit

```bash
git add docker/computer/Dockerfile docker/computer/start.sh docker/computer/roost_computerd.py docker/computer/roost_pipe.py docker/computer/system.jwmrc docker/computer/licences.sh roost/keeper/seccomp/__init__.py roost/keeper/seccomp/chromium.json roost/keeper/seccomp/chromium.json.license tests/test_computer_image_spec.py tests/test_computerd.py tests/test_computer_image_real.py Makefile && git commit -m "feat: the roost-computer image (Chromium, Xvnc on a Unix socket, JWM, xterm, a small supervisor, the Chromium seccomp profile)"
```

### Task 3: `roost-egress` and the per-bot networks

**Files:** Create `docker/egress/Dockerfile` (`python:3.12-slim-bookworm` pinned by digest; copies only
`roost/__init__.py`, `roost/constants.py`, `roost/keeper/__init__.py`, `roost/keeper/proxy.py`,
`roost/keeper/egress_main.py`; `USER 10003`; `ENV ROOST_IN_EGRESS=1`; no `EXPOSE`; `CMD ["python", "-I", "-m",
"roost.keeper.egress_main"]`), `roost/keeper/egress_main.py`, `roost/keeper/networks.py`, `tests/test_networks.py`,
`tests/test_egress_main.py`. Modify `Makefile` (`egress-image` with the disk guard; `deploy` builds it when missing),
`tests/test_keeper_proxy.py` or a new `tests/test_proxy_vm_ranges.py`.

Check first that `roost/keeper/__init__.py` and `roost/constants.py` import nothing beyond the stdlib; if they do, the
Dockerfile copies the smallest set that imports cleanly with `python -I` (record it in the Dockerfile comment).

`EgressNetworks`:
- `ensure_egress()`: creates `roost-out` (a plain bridge) if missing; runs `roost-egress` if missing (`docker run -d
  --name roost-egress --network roost-out --read-only --cap-drop ALL --security-opt no-new-privileges --user
  10003:10003 --memory 128m --pids-limit 64 --label app.roost.part=egress roost-egress:dev`), starts it if stopped.
- `ensure_bot_network(bot_id)`: `docker network create --internal --label app.roost.bot=<id> roost-net-<id>` if
  missing, then `docker network connect roost-net-<id> roost-egress` if not connected.
- `remove_bot_network(bot_id)`: disconnect the egress, remove the network; "not found" is fine.

**Tests:**
- `test_networks.py`: `test_a_bot_network_is_internal_and_labelled`, `test_no_argv_publishes_a_port` (no `-p`,
  `--publish`, `-P` in any builder), `test_every_name_starts_with_roost`, `test_a_bad_bot_id_builds_no_argv`
  (ValueError), `test_ensure_bot_network_is_idempotent` (fake runner: "already exists" is fine),
  `test_the_egress_runs_read_only_without_capabilities`.
- `test_egress_main.py`: `test_refuses_to_run_outside_the_egress_container` (no `ROOST_IN_EGRESS`: exits non-zero,
  never binds), `test_binds_the_egress_port_inside_the_container` (monkeypatched `EgressProxy`).
- `test_proxy_vm_ranges.py`: `is_blocked_address` refuses Docker's ranges and the VM's (`172.16.0.0/12`,
  `192.168.65.0/24`, `192.168.65.254` = `host.docker.internal`, `10.0.0.0/8`, `fd00::/8`), so no computer reaches
  another, the gateway or the keeper through the egress.

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add docker/egress/Dockerfile roost/keeper/egress_main.py roost/keeper/networks.py tests/test_networks.py tests/test_egress_main.py tests/test_proxy_vm_ranges.py Makefile && git commit -m "feat: roost-egress in the VM and an internal network per bot, with no published port"
```

### Task 4: The keeper's `ComputerManager` (security review b)

Follows `roost/keeper/workspaces.py`'s style: every docker argv from one small, tested function; `asyncio.
create_subprocess_exec`, never a shell; an injectable runner; `docker` calls bounded by
`COMPUTER_DOCKER_CALL_TIMEOUT_S`.

`build_run_argv(bot_id, seccomp_path)` is exactly:

```
docker run -d --name roost-computer-<id> --hostname computer
  --label app.roost.bot=<id> --network roost-net-<id>
  --user 10002:10002 --cap-drop ALL --security-opt no-new-privileges
  --security-opt seccomp=<seccomp_path> --read-only
  --tmpfs /tmp:rw,size=256m --tmpfs /run/screen:rw,mode=0700,uid=10002,gid=10002,size=1m
  --tmpfs /home/comp:rw,uid=10002,gid=10002,size=64m
  --mount type=volume,src=roost-profile-<id>,dst=/home/comp/profile
  --memory 1500m --memory-swap 1500m --shm-size 512m --cpus 1.5 --pids-limit 512
  roost-computer:dev
```

`start(bot_id)`: `ensure_egress()` and `ensure_bot_network()`, then by state: absent → run; stopped → start;
paused → unpause; running → nothing. Then it waits until `docker exec … roost-pipe cdp` connects (a short probe),
within `COMPUTER_BOOT_TIMEOUT_S`, else `ComputerStartError`. It mints `cdp_token` and `vnc_token`
(`secrets.token_urlsafe(32)`) once per keeper process per bot and keeps them until `stop`/`remove`. `remove` deletes the
container, then `roost-profile-<id>`, then the network ("no such" is fine; a real failure raises). `reconcile()` reads
`docker ps -a --filter name=roost-computer-` (and `label=app.roost.bot`) at keeper start.

**Files:** Create `roost/keeper/computers.py`, `tests/test_computer_spec.py`, `tests/test_computer_manager.py`.

**Tests:**
- `test_computer_spec.py`: `test_run_argv_is_exactly_the_hardened_one` (the list above), `test_no_argv_publishes_a_port`,
  `test_never_unconfined_never_privileged_never_no_sandbox`, `test_pipe_argv_execs_as_10002_and_only_cdp_or_vnc`,
  `test_a_bad_bot_id_builds_no_argv`, `test_parse_list_output_reads_paused_and_exited`.
- `test_computer_manager.py` (fake runner): `test_start_runs_an_absent_computer_after_its_network`,
  `test_start_unpauses_a_paused_one`, `test_start_starts_a_stopped_one`, `test_start_fails_cleanly_when_it_never_boots`,
  `test_tokens_stay_the_same_while_running_and_change_after_stop`, `test_remove_deletes_container_volume_and_network`,
  `test_reconcile_reads_existing_computers`.

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/keeper/computers.py tests/test_computer_spec.py tests/test_computer_manager.py && git commit -m "feat: the keeper starts, pauses, wakes, stops and removes a bot's hardened Linux computer"
```

### Task 5: The room: a cap, the VM memory check, and sleep when idle

`decide(bot_id, view)`:
- the bot is already running → `start` (no-op start);
- fewer than `COMPUTERS_MAX_RUNNING` running and `free_mb >= COMPUTER_START_MIN_FREE_MB` → `start`;
- otherwise the least recently used running bot not in `held` or `busy` → `evict_then_start` (stop it), but only if
  `free_mb` is known; the memory check is made again after the stop, and `no_room` if it still fails;
- else `no_room`. A failed reading (`free_mb is None`) is `no_room` unless a stop is possible and frees room.

Free memory = `MemTotal` (from `docker info --format '{{.MemTotal}}'`) − the sum of `docker stats --no-stream --format
'{{.MemUsage}}'` (left side of each `used / limit`, MiB/GiB parsed). A paused computer counts as running for memory,
not for the cap.

`idle_actions`: a running computer idle past `COMPUTER_PAUSE_AFTER_S` and not held → `pause`; a paused one idle past
`COMPUTER_STOP_AFTER_S` → `stop`. `ComputerManager.touch` is called on every start, every CDP frame either way (at most
once a second), and while any live socket is open (`hold`/`release`). The sweeper starts in the keeper lifespan.

**Files:** Create `roost/keeper/computer_room.py`, `tests/test_computer_room.py`.

**Tests:** `test_starts_when_under_the_cap_with_memory`, `test_stops_the_least_recently_used_resting_one_at_the_cap`,
`test_never_evicts_one_you_are_watching_or_one_on_it`, `test_no_room_when_all_are_busy`,
`test_no_room_when_the_vm_is_short_of_memory`, `test_a_failed_memory_reading_is_no_room`,
`test_parse_docker_memory_figures` (`"3.83GiB"`, `"212.4MiB / 1.465GiB"`), `test_idle_pause_then_stop`,
`test_a_held_computer_never_sleeps`, `test_admit_raises_no_room`.

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/keeper/computer_room.py tests/test_computer_room.py && git commit -m "feat: at most three computers run, the VM memory is checked before a start, and idle computers pause then stop"
```

### Task 6: Keeper routes and the `docker exec` relays (security review b)

**Files:** Create `roost/keeper/exec_pipe.py`, `roost/keeper/computer_routes.py` (an `APIRouter` factory
`computer_routes(app) -> APIRouter`, keeping `app.py` under 400 lines), `tests/test_exec_pipe.py`,
`tests/test_keeper_computer_routes.py`, `tests/test_computer_relay_real.py` (`@pytest.mark.docker`). Modify
`roost/keeper/app.py` (state: `networks`, `computers`, `room`; the router; `GET /desks/{id}` gains `computer`; retire
also calls `computers.remove`; the lifespan runs `computers.reconcile()` and starts `room.run_sweeper()`),
`tests/test_keeper_app.py` (or the existing keeper route tests).

Rules:
- The HTTP routes: signed body, UUID4 bot id (400), strict bodies (422, `extra="forbid"`); start's body is
  `{"busy": list[UUID4], max 50}`. Audit: `computer_start` / `computer_attach` / `computer_pause` / `computer_stop` with
  `ok` / `no_room` / `error` / `not_running`.
- The WebSockets accept first, then close with the code (keeper Ruling 9). CDP: one client per bot (the newest takes
  over with 4409, as `RelayRegistry` does). VNC: up to `LIVE_VIEWERS_MAX + 1` at once (4429 past that), each its own
  `ExecPipe`; `room.hold` on connect, `release` on close.
- `ExecPipe.read` returns at most `LIVE_RELAY_CHUNK_MAX`; nothing it reads or writes is logged; `close()` terminates the
  exec, then kills it after 2 s.
- Audit `computer_vnc` with `connected` / `closed` and `computer_cdp` the same; never byte counts or content.

**Tests:**
- `test_exec_pipe.py` (a real subprocess: `python -I -c` echo program, no docker): `test_bytes_round_trip_unchanged`,
  `test_read_is_bounded`, `test_close_kills_a_stuck_process`, `test_nul_framer_splits_and_buffers_partial_messages`.
- `test_keeper_computer_routes.py` (fake runner, `ExecPipe` replaced by an in-memory pair): unsigned 401; bad id 400;
  extra field 422; `test_start_answers_tokens`, `test_start_answers_no_room_with_409`,
  `test_attach_never_wakes_a_paused_computer` (409 asleep, no unpause argv run),
  `test_vnc_socket_refuses_a_wrong_token_with_4401`, `test_vnc_socket_relays_bytes_both_ways`,
  `test_a_fourth_vnc_socket_is_refused_with_4429`, `test_cdp_socket_relays_nul_framed_messages_as_text`,
  `test_retire_removes_the_computer_too`, `test_the_audit_has_no_bytes`.
- `test_computer_relay_real.py` (docker; manual check only): a pipelined RFB client (several
  FramebufferUpdateRequests in flight, Tight or ZRLE requested) through the keeper's `/computer/vnc` relay; prints the
  first-frame time and key-to-update median/p90 (the spike's open item).

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/keeper/exec_pipe.py roost/keeper/computer_routes.py roost/keeper/app.py tests/test_exec_pipe.py tests/test_keeper_computer_routes.py tests/test_computer_relay_real.py tests/test_keeper_app.py && git commit -m "feat: keeper routes for a bot's computer, with CDP and VNC relayed over docker exec and no published port"
```

**Then: security review (b)** of Tasks 2–6 (Review Focus). Fix CRITICAL/HIGH before Batch C.

### Task 7: The gateway drives the Linux computer

**Files:** Modify `roost/desk/__init__.py` (`ComputerKind`, `ComputerState`, `DeskStatus` fields, `DeskBusy`,
`DeskFactory.for_bot(bot_id, computer)`, `forget` for both kinds), `roost/desk/client.py` (`KeeperClient` computer
calls; `KeeperDesk(computer=…)`: `_ensure_page` calls `/computer/start` for Linux, with the room wait of Design meets
code 5; `screenshot` attaches with `/computer/attach`; `status` maps the keeper's state; `stop_browser` stops the
computer), `roost/desk/fake.py` (`FakeDesk(bot_id, computer="linux")`, `state`), `roost/gateway/routes/desk.py`
(`_owned_bot_or_404` returns the bot; `for_bot(bot.id, bot.computer)`; 409 on `DeskBusy`), `roost/gateway/routes/bots.py`
(retire uses both kinds), `roost/talk/runner.py` (`for_bot(bot.id, bot.computer)`; `busy` = the ids of the user's
bots that are On it; `on_wait` posts the activity line "Waiting for a free computer"), `roost/talk/tools.py` or the
browser tool module (DeskBusy → the tool text of Design meets code 5). Create `tests/test_keeper_desk_computer.py`.
Update `tests/test_desk_api.py`, `tests/test_keeper_client.py`, `tests/test_fake_desk.py`.

**Tests:** `test_a_linux_bot_opens_pages_through_the_computer_relay` (keeper app in-process via `ASGITransport`, CDP
socket faked), `test_read_page_and_the_stuck_detector_run_unchanged_on_the_computer`,
`test_a_screenshot_never_wakes_a_paused_computer`, `test_waits_for_a_free_computer_then_says_so`,
`test_desk_busy_becomes_a_plain_tool_result`, `test_a_mac_brave_bot_still_uses_brave_routes`,
`test_status_says_paused_is_asleep`, `test_retire_removes_both_kinds`, `test_another_users_bot_desk_is_404`.

- [ ] Steps: path guard → tests red → implement → green (full suite) → commit

```bash
git add roost/desk/__init__.py roost/desk/client.py roost/desk/fake.py roost/gateway/routes/desk.py roost/gateway/routes/bots.py roost/talk/runner.py roost/talk/tools.py tests/test_keeper_desk_computer.py tests/test_desk_api.py tests/test_keeper_client.py tests/test_fake_desk.py && git commit -m "feat: a bot's browser tools, stuck detector and screenshots run on its Linux computer, waiting for a free one when all are busy"
```

(Stage only the files you changed; if the browser tools live elsewhere than `roost/talk/tools.py`, name that file.)

### Task 8: The RFB filter, the screen stream and the fake screen

**Files:** Create `roost/desk/rfb.py`, `roost/desk/fake_screen.py`, `tests/test_rfb_filter.py`,
`tests/test_fake_screen.py`. Modify `roost/desk/__init__.py` (`ScreenStream`, `Desk.open_screen`), `roost/desk/client.py`
(`KeeperScreen`, `KeeperDesk.open_screen`: `/computer/attach` then `websockets.connect(_vnc_url, additional_headers=
{token})`; Mac Brave → `DeskUnavailable`), `roost/desk/fake.py`.

`RfbClientFilter.feed` parses per Design meets code 10: handshake (12-byte version, must equal `RFB_CLIENT_VERSION`;
1-byte security, must be `RFB_SECURITY_NONE`; 1-byte ClientInit), then messages: 0 (20 bytes), 2 (4 + 4n, n ≤
`RFB_SET_ENCODINGS_MAX`; `RFB_EXT_CLIPBOARD_ENCODING` removed and n rewritten), 3 (10), 4 (8, input), 5 (6, input),
6 (8 + len, input; negative len → always dropped; len > `LIVE_PASTE_MAX_CHARS` → close), 150 (10), 248 (9 + len, len ≤
`RFB_FENCE_MAX`), 250 (4, always dropped), 251 (8 + 16n, always dropped), 255 subtype 0 (12, input), anything else
→ `RfbProtocolError`. A partial message waits for more bytes; a buffer past 64 KiB without a whole message is an error.
`RfbProtocolError` messages name the message type only, never bytes.

**Tests:** `test_handshake_passes_and_wrong_versions_close`, `test_security_other_than_none_closes`,
`test_each_message_type_is_split_at_its_exact_length`, `test_partial_messages_wait_for_more_bytes`,
`test_input_is_dropped_when_not_allowed_and_forwarded_when_allowed`, `test_desktop_size_and_xvp_are_always_dropped`,
`test_extended_clipboard_is_stripped_and_never_forwarded`, `test_a_long_paste_closes`,
`test_unknown_types_close_without_echoing_bytes`, `test_rate_limit_drops_input_past_the_cap`;
`test_fake_screen.py`: `test_the_fake_screen_speaks_rfb_3_8_and_sends_a_frame`, `test_it_counts_input_but_keeps_no_bytes`,
`test_a_sleeping_fake_desk_has_no_screen`.

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/desk/rfb.py roost/desk/fake_screen.py roost/desk/__init__.py roost/desk/client.py roost/desk/fake.py tests/test_rfb_filter.py tests/test_fake_screen.py && git commit -m "feat: an RFB filter that only lets input through when allowed, the bot's screen stream, and a fake screen for tests"
```

### Task 9: The view socket `WS /api/bots/{id}/live` (security review a)

Read live control's plan Task 6 (`docs/plans/2026-10-15-roost-live-control.md`, "Task 6", and its D1 at line 26) for
`peer_is_this_mac` and the accept order; reuse them word for word.

Accept order: accept; Origin in `config.allowed_origins` (else 4403 ORIGIN); `peer_is_this_mac` (else 4403
NOT_THIS_MAC); session cookie (else 4401); the user's bot (else 4404); `mode` is `view` (C1; `control` is 4409 until
Task 11); a Mac Brave bot → 4503; `LiveViewers.enter` (else 4429); `desk.open_screen()` (DeskAsleep → 4410,
DeskUnavailable → 4503). Then `relay_screen(websocket, screen, input_allowed=lambda: False)` until either side ends;
`finally` closes the screen and leaves the viewers count. Exceptions are caught and closed with 4503 and a log line
that names only the bot id and the exception type.

**Files:** Create `roost/gateway/live_socket.py`, `roost/gateway/routes/live.py`, `tests/test_live_socket.py`,
`tests/test_live_route.py`. Modify `roost/gateway/app.py` (router, `app.state.live_viewers`).

**Tests:** `test_only_the_loopback_peer_is_this_mac`, `test_any_peer_in_the_gateway_container_is_this_mac`,
`test_a_forwarded_connection_is_refused_even_from_this_mac`, `test_a_foreign_origin_is_4403`,
`test_no_session_is_4401`, `test_another_users_bot_is_4404`, `test_a_sleeping_computer_is_4410`,
`test_a_mac_brave_bot_has_no_live_screen`, `test_a_third_tab_is_4429`, `test_bytes_flow_both_ways_with_the_fake_screen`,
`test_view_mode_never_forwards_input` (KeyEvent and PointerEvent sent; `FakeScreen.received_input == 0`),
`test_a_protocol_error_closes_4400`, `test_a_typed_password_is_in_no_log_event_or_audit` (KeyEvents spelling
`hunter2-секрет` through the socket; caplog, the events table and the keeper audit file have none of it).

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/gateway/live_socket.py roost/gateway/routes/live.py roost/gateway/app.py tests/test_live_socket.py tests/test_live_route.py && git commit -m "feat: watch a bot's computer live through the gateway, view only, from this Mac only"
```

**Then: security review (a)** of Tasks 6, 8 and 9.

### Task 10: The web: noVNC as a lazy chunk, the live Computer tab, the switch

**Precondition:** Design meets code 13 (R1's asleep component exists). Disk guard before `npm install`.

**noVNC licence check (do it first, record it in the commit body):** `npm view @novnc/novnc@<version> license`
must print `MPL-2.0`; pin the newest release that is at least two weeks old with an exact version (no `^`). Find its
RFB entry (`core/rfb.js` in the ES-module releases) and its bundled pako (MIT). The licence gate already allows
MPL-2.0; add `it("noVNC is MPL-2.0 and imported only by web/src/lib/novnc.ts")` to `web/tests/licenseGate.test.ts`
(a source scan, like the Markdown one-module rule). The files are used as published: no patch, no fork; Vite emits
them as their own chunk (`import()` in `loadRfb`), and `npm run size` shows the entry unchanged.

**Files:** Modify `web/package.json`, `web/package-lock.json`, `web/tests/licenseGate.test.ts`,
`web/src/api/types.ts`, `web/src/api/bots.ts` (PATCH `computer`), `web/src/components/profile/ComputerTab.tsx`,
`web/src/styles/computer.css` (or R1's split file), `web/src/styles.css` if a new sheet is added. Create
`web/src/lib/novnc.ts`, `web/src/api/live.ts`, `web/src/hooks/useLiveScreen.ts`,
`web/src/components/computer/{constants.ts,LiveScreen.tsx,ComputerKindSwitch.tsx}`, `web/tests/useLiveScreen.test.tsx`,
`web/tests/LiveScreen.test.tsx`, `web/tests/ComputerKindSwitch.test.tsx`, `web/src/types/novnc.d.ts` (the small part
of the RFB API we use, if the package ships no types). Update `web/tests/ComputerTab.test.tsx`.

The Computer tab, Linux computer: status from `GET /desk`; running → `LiveScreen mode="view"` in the screen box (the
figure keeps its caption "{name}'s screen" and the canvas container has `aria-label="{name}'s screen, live"`);
asleep → R1's Computer is asleep with **Open it** (`startBrowser`, then the live screen); a 409 busy → "All
computers are busy right now. Try again in a few minutes." with **Retry**; a socket that ends with 4410 shows asleep,
4503 "Can't reach {name}'s screen · Retry". Mac Brave: today's screenshot box, window card and text, unchanged.
`ComputerKindSwitch` ("Computer: Linux computer | Mac Brave", a kit Select or two-segment control) sits under the
screen with one line: Linux computer: "Runs in a sealed Linux computer on this Mac. Sign in once with Take control."
Mac Brave: "Uses its own Brave window on your Mac." Switching PATCHes `computer`; the server stops the old kind
(Task 7's route does `desk.stop_browser()` on the old kind and `forget`). "About this computer" words follow the kind.
Take control on a Linux bot stays today's pause-only button until Task 15.

**Tests:** `useLiveScreen.test.tsx` (a fake socket and a fake RFB class injected): `it("opens the view socket and
hands it to noVNC view only")`, `it("maps 4410 to asleep and 4503 to unreachable")`, `it("closes the socket and
disconnects on unmount")`; `LiveScreen.test.tsx`: `it("shows the live canvas named for the bot")`;
`ComputerKindSwitch.test.tsx`: `it("switches to Mac Brave and back, saying what each does")`, `it("shows the
server's refusal and keeps the old choice")`; `ComputerTab.test.tsx`: `it("a Linux bot shows the live screen when
running and Computer is asleep otherwise")`, `it("a Mac Brave bot keeps the screenshot")`, `it("says when all
computers are busy")`.

- [ ] Steps: path guard → disk guard → licence check → tests red → implement → green (`npm test`, `npm run build &&
  npm run size`) → commit

```bash
git add web/package.json web/package-lock.json web/tests/licenseGate.test.ts web/src/lib/novnc.ts web/src/api/live.ts web/src/api/types.ts web/src/api/bots.ts web/src/hooks/useLiveScreen.ts web/src/components/computer/constants.ts web/src/components/computer/LiveScreen.tsx web/src/components/computer/ComputerKindSwitch.tsx web/src/components/profile/ComputerTab.tsx web/src/styles/computer.css web/src/types/novnc.d.ts web/tests/useLiveScreen.test.tsx web/tests/LiveScreen.test.tsx web/tests/ComputerKindSwitch.test.tsx web/tests/ComputerTab.test.tsx && git commit -m "feat: the Computer tab shows a Linux bot's computer live (noVNC, a lazy chunk) and switches between Linux computer and Mac Brave"
```

(Stage only files that exist; `novnc.d.ts` only if added.)

**C1 is done here.** The orchestrator runs Task 16 Part C steps 1–8 with the user before Batch E.

### Task 11: Take control on the live socket (C2; security review a)

**Files:** Modify `roost/desk/control.py` (`wait_released`), `roost/gateway/routes/live.py` (mode `control`),
`roost/gateway/live_socket.py` (control mode rules), `tests/test_live_route.py`, `tests/test_control_lock.py`. Create
`tests/test_live_control_mode.py`.

Control mode: after the view rules, the lock must be held for this bot (else 4409 "Take control first."). The relay
runs with `input_allowed=lambda: control.held(bot_id) is not None` (checked per message), input past
`InputRateLimit` is dropped, and a third task awaits `control.wait_released(bot_id)` and then closes with 4000 "Given
back.". Only one control socket per bot (a second one replaces the first, which closes 4000). The view socket never
forwards input, even while you hold the lock.

**Tests:** `test_control_without_the_lock_is_4409`, `test_input_reaches_the_screen_while_you_hold_control`,
`test_input_stops_the_moment_control_is_given_back` (give back mid-stream: later KeyEvents are dropped, the socket
closes 4000), `test_the_view_socket_never_forwards_input_even_while_held`, `test_a_long_paste_closes_4400`,
`test_wait_released_returns_at_once_when_free`, `test_a_typed_password_in_control_is_in_no_log_event_or_audit`.

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/desk/control.py roost/gateway/routes/live.py roost/gateway/live_socket.py tests/test_live_route.py tests/test_control_lock.py tests/test_live_control_mode.py && git commit -m "feat: Take control on a bot's computer, with keys and clicks let through only while you hold control"
```

**Then: security review (a)** of Task 11.

### Task 12: Typed values never reach `read_page`

Live control's Task 8, as written there (`docs/plans/2026-10-15-roost-live-control.md`, "Task 8"):
`_extract_readable_lines` skips every node inside a `textbox`, `searchbox`, `combobox` or `spinbutton` (walk
`parentId` / `childIds` from `Accessibility.getFullAXTree`), with a realistic AX tree where a password and an email
field each hold a value as a child `StaticText`.

**Files:** Modify `roost/desk/browser.py`; create `tests/test_read_page_text_boxes.py`.

**Tests:** `test_values_inside_text_boxes_never_reach_read_page`, `test_labels_and_buttons_around_them_still_do`,
`test_a_search_box_and_a_combobox_are_skipped_too`.

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/desk/browser.py tests/test_read_page_text_boxes.py && git commit -m "fix: read_page skips everything inside a text box, so what you type never reaches the bot"
```

### Task 13: Vault: site logins, the store and the prompt line

Live control's Tasks 9 and 10, **without their migration** (Task 1 made the table in v19): `roost/vault/__init__.py`,
`models.py`, `store.py` exactly as named in the Shared Contract; `build_instructions(..., site_logins=())` adds "You are
signed in on: github.com (as work email), …" (escaped with `_escape_tags`), `TurnRunner`/`RunInputs` gain the store,
newest `SITE_LOGINS_IN_PROMPT` rows. Copy their test names, renaming any `v14` to `v19`.

**Files:** Create `roost/vault/__init__.py`, `roost/vault/models.py`, `roost/vault/store.py`,
`tests/test_vault_store.py`, `tests/test_vault_prompt.py`. Modify `roost/talk/instructions.py`, `roost/talk/turn.py`,
`roost/talk/runner.py`.

**Tests (at least):** `test_remember_upserts_one_row_per_bot_and_host`, `test_host_and_label_are_stored_sealed`,
`test_another_users_bot_cannot_be_written_or_read`, `test_the_prompt_names_the_accounts_newest_first_and_capped`,
`test_a_label_with_tags_is_escaped`.

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/vault/__init__.py roost/vault/models.py roost/vault/store.py roost/talk/instructions.py roost/talk/turn.py roost/talk/runner.py tests/test_vault_store.py tests/test_vault_prompt.py && git commit -m "feat: Vault: site logins remembers which account a bot is signed in with, sealed, and its prompt names them"
```

### Task 14: The account on Give it back, the list and Forget

Live control's Task 11, with `Desk.current_url()` (Design meets code 12): `KeeperDesk.current_url` attaches without
waking (`/computer/attach` or `/browser/attach`; 409 → ""), sends `Target.getTargetInfo` for the bot's page and returns
its `url`; `FakeDesk.current_url` returns the last opened URL. `VaultService.sign_in` normalises its host, and with no
host raises `NoSite`.

**Files:** Create `roost/vault/service.py`, `roost/gateway/routes/vault.py`, `tests/test_vault_routes.py`. Modify
`roost/desk/__init__.py`, `roost/desk/client.py`, `roost/desk/fake.py`, `roost/gateway/routes/desk.py`
(`DELETE /control` takes `GiveBackIn`), `roost/stuck/service.py`, `roost/gateway/routes/stuck.py` (`ClearIn.account`),
`roost/gateway/app.py`, `tests/test_stuck_routes.py` (or the existing stuck API test file).

**Tests:** `test_give_back_with_an_account_saves_it_and_tells_the_bot` ("I signed in on {host} as {label}." as a user
message), `test_give_back_without_an_account_saves_and_says_nothing`, `test_clearing_a_stuck_card_with_an_account_puts_it_in_the_continue_line`,
`test_no_site_is_a_400_with_the_plain_sentence`, `test_an_over_long_account_is_a_422`,
`test_list_is_newest_first_and_forget_removes_one`, `test_another_users_logins_are_404`,
`test_current_url_never_wakes_the_computer`.

- [ ] Steps: path guard → tests red → implement → green → commit

```bash
git add roost/vault/service.py roost/gateway/routes/vault.py roost/desk/__init__.py roost/desk/client.py roost/desk/fake.py roost/gateway/routes/desk.py roost/stuck/service.py roost/gateway/routes/stuck.py roost/gateway/app.py tests/test_vault_routes.py tests/test_stuck_routes.py && git commit -m "feat: on Give it back, say which account you used; Vault: site logins lists it with Forget"
```

### Task 15: The web: full-screen Take control, I'm done, the account and the Vault list

**Files:** Create `web/src/components/computer/ControlScreen.tsx`, `GiveBackForm.tsx`, `SiteLogins.tsx`,
`web/src/api/vault.ts`, `web/tests/ControlScreen.test.tsx`, `web/tests/GiveBackForm.test.tsx`,
`web/tests/SiteLogins.test.tsx`. Modify `web/src/api/{computer,stuck,types}.ts`,
`web/src/components/profile/ComputerTab.tsx`, `web/src/components/StuckCard.tsx`, `web/src/styles/computer.css`,
`web/tests/{ComputerTab,StuckCard}.test.tsx`.

- **Take control** (Linux bot): wakes the computer if asleep, `POST /control`, then `ControlScreen` covers the window
  (a kit `Sheet size="full"`, modal, focus inside; Escape does **not** close it, because Escape belongs to the page):
  the bar on top says **"You're in control"** and has **I'm done**; below it `LiveScreen mode="control"` (noVNC
  `viewOnly=false`, keyboard focus on the canvas).
- **I'm done** opens `GiveBackForm` in the bar: "Which account did you use?" (one line, `ACCOUNT_MAX_CHARS`, optional,
  with the site's host when known), **Give it back** and **Back**. Confirm → `giveBack(botId, account)` or, with an
  open Stuck card, `clearStuck(card.id, { account })`; the control socket then closes 4000 and the sheet closes back to
  the view.
- A control socket closed 4409 or 4000 by someone else (another tab gave it back) closes the sheet with a toast
  "Control was given back.".
- `SiteLogins` under the switch: "Vault: site logins", rows "{host} · {label}" with **Forget**, empty: "No sign-ins
  saved yet." Mac Brave bots keep today's control button and text.
- **StuckCard:** Take control takes control and navigates to `/bots/{id}?panel=computer`, where the held state opens
  `ControlScreen` at once.

**Tests:** `ControlScreen.test.tsx`: `it("covers the screen with You're in control and I'm done")`, `it("Escape goes
to the page, not the sheet")`, `it("closes when the server says Given back")`; `GiveBackForm.test.tsx`: `it("gives it
back with or without an account")`, `it("refuses an account over 100 characters")`; `SiteLogins.test.tsx`:
`it("lists sign-ins and forgets one")`; `StuckCard.test.tsx`: `it("Take control opens the computer panel in
control")`; `ComputerTab.test.tsx`: `it("a Mac Brave bot keeps the old Take control")`.

- [ ] Steps: path guard → tests red → implement → green (`npm test`, build, size) → commit

```bash
git add web/src/components/computer/ControlScreen.tsx web/src/components/computer/GiveBackForm.tsx web/src/components/computer/SiteLogins.tsx web/src/api/vault.ts web/src/api/computer.ts web/src/api/stuck.ts web/src/api/types.ts web/src/components/profile/ComputerTab.tsx web/src/components/StuckCard.tsx web/src/styles/computer.css web/tests/ControlScreen.test.tsx web/tests/GiveBackForm.test.tsx web/tests/SiteLogins.test.tsx web/tests/ComputerTab.test.tsx web/tests/StuckCard.test.tsx && git commit -m "feat: full-screen Take control with You're in control · I'm done, the optional account, and the Vault list"
```

### Task 16: E2E with a fake computer, the notices, the docs and the manual check

**Part A, E2E (fake desk, `ROOST_DESK=fake`):** `web/e2e/computer-live.spec.ts`:
1. Open a bot's panel → Computer: the live canvas named "{name}'s screen, live" shows (the fake screen's frame
   arrives: the noVNC canvas has a non-zero size).
2. Switch to Mac Brave and back; the line under the switch changes.
3. Take control → the full-screen sheet with "You're in control" and **I'm done**; type `secret-pass` and click the
   canvas; **I'm done** → "Which account did you use?" → `work email` → **Give it back** → the sheet closes; the
   Vault list shows the fake page's host · work email; **Forget** removes it.
4. The chat shows "I signed in on {host} as work email.".
Update `web/e2e/stuck.spec.ts` (Take control from a Stuck card opens the panel in control; I'm done with an account;
the bot carries on) and `web/e2e/computer.spec.ts` (the fake bot is a Linux computer now; the screenshot path is
checked on a Mac Brave bot). Run `ROOST_DESKS_DIR=$(mktemp -d) make e2e` (disk guard first).

**Part B, notices and docs:**
- `THIRD_PARTY_NOTICES.md`: a section "Computers 2.0" with: **noVNC** (MPL-2.0, npm `@novnc/novnc@<pinned>`,
  unmodified, source at github.com/novnc/noVNC) and its **pako** (MIT); the **seccomp profile** (Apache-2.0, adapted
  from moby/profiles `default.json` @ the commit the spike used, five syscalls allowed); and "Programs in the
  `roost-computer` image": TigerVNC `Xvnc` (GPL-2.0+, a separate, unmodified Debian package; Roost speaks RFB to its
  socket and never links it), JWM (MIT), xterm (X11), tini (MIT), Chromium (BSD-3 and its bundled licences, Debian's
  build, unmodified), the GNU userland and the shared libraries listed by `docker/computer/licences.sh` (separate,
  unmodified Debian packages), `python3` (PSF). `roost-egress`: `python:3.12-slim-bookworm` (PSF and Debian).
- `CLAUDE.md`: the Documentation Map gains the design and this plan; the Architecture gains one paragraph: a bot's
  computer is `roost-computer-<id>` (Chromium, Xvnc on a Unix socket, JWM), started/paused/stopped by the keeper under
  `COMPUTERS_MAX_RUNNING` and the VM memory check, on `roost-net-<id>` with `roost-egress` the only way out, CDP and VNC
  only through `docker exec … roost-pipe`, the live view `WS /api/bots/{id}/live` (view, or control while you hold the
  lock; `roost/desk/rfb.py` filters input), the per-bot "Linux computer | Mac Brave" switch (`bots.computer`, v19), and
  Vault: site logins (`roost/vault/`). Ports stay 18800/18801/18803.
- `README.md`: "Your bots' computers" (what you see, Take control, I'm done, the account, the switch, "Bot computers
  are not encrypted beyond your Mac's disk yet.").
- `tests/test_docs.py`: `COMPUTERS_DOCS` exist and are in the map; `COMPUTERS_PLACES` (`roost/keeper/computers.py`,
  `roost/desk/rfb.py`, `/api/bots/{id}/live`, `roost/vault/`, `bots.computer`) are named in CLAUDE.md.

**Part C, the manual check on the user's Mac (orchestrator with the user; not the implementer):**
1. Disk guard. `make computer-image egress-image`; `docker image ls roost-computer` (size noted).
2. `make deploy` (the user's OK; the database backup first, like earlier deploys); `user_version` is 19.
3. Open a bot's Computer tab: the live screen appears; first frame time noted. `docker port roost-computer-<id>`
   prints nothing; `docker inspect` shows `CapDrop [ALL]`, `no-new-privileges`, the seccomp profile, `ReadonlyRootfs`.
4. In the computer's Chromium, `chrome://sandbox` shows the sandbox on. `docker exec --user 10002
   roost-computer-<id> getent hosts example.com` fails.
5. `uv run pytest -m docker tests/test_computer_relay_real.py tests/test_computer_image_real.py -s`: relay first-frame
   and key-to-update times; record them.
6. Ask a bot to open a page; watch it live; it reads the page; a human-check page gives the Stuck card.
7. Three bots busy, a fourth asks: it waits ("Waiting for a free computer") or takes a Resting one's place;
   `docker stats` total noted against the 3.83 GiB VM. Wait 5 min: a Resting computer pauses; Open it wakes it.
8. **A logged-in heavy site** (the user signs in to a feed or a video site with Take control after C2, or in C1 just
   loads a heavy public page): RAM and CPU noted.
9. (C2) Take control, sign in to one real site, I'm done with an account; the bot carries on signed in; the Vault
   lists it. `grep -r <the password> ~/Roost/data/*.log ~/Roost/logs` finds nothing (the user types the grep).
10. Record steps 1–9 as "C1/C2 measurements" at the end of `docs/research/2026-10-20-computers-c0-spike.md`, commit it
    by name with `docs:`.

**Files (Parts A–B):** Create `web/e2e/computer-live.spec.ts`. Modify `web/e2e/stuck.spec.ts`,
`web/e2e/computer.spec.ts`, `web/e2e/helpers.ts` (if needed), `THIRD_PARTY_NOTICES.md`, `CLAUDE.md`, `README.md`,
`tests/test_docs.py`.

- [ ] Steps: path guard → E2E red → fix what the E2E finds (in the task that owns it) → green; full `uv run pytest
  --cov=roost --cov-fail-under=80`, `npm test`, `npm run build && npm run size`, `make e2e` → commit

```bash
git add web/e2e/computer-live.spec.ts web/e2e/stuck.spec.ts web/e2e/computer.spec.ts THIRD_PARTY_NOTICES.md CLAUDE.md README.md tests/test_docs.py && git commit -m "test: E2E for the live computer and Take control on a fake computer; docs: Computers 2.0 C1-C2 in CLAUDE.md, README and the notices"
```

---

## Open for the user

1. **The egress listener inside the VM** binds all interfaces of the `roost-egress` container (no published port,
   only `roost-out` and the bots' internal networks reach it). This is the one listener that is not 127.0.0.1;
   confirm it (Design meets code 6).
2. **Existing bots move to the Linux computer** (D1: Mac Brave only when you switch it on). Their Brave sign-ins stay
   on disk and come back if you switch a bot to Mac Brave.
3. **Paste during Take control** goes into the computer's clipboard and stays there after I'm done (Roost can't clear
   an X clipboard without another program). Pages need a click and a permission to read it.
4. **`COMPUTERS_MAX_RUNNING` stays 3** and needs about 0.6 GB free in Docker Desktop's VM per start; raising it means
   raising Docker Desktop's memory first.

## Risks

- **Schema order:** v19 must land after v17 (Tasks & Money) and v18 (Models & helpers). Task 1 stops if they aren't in.
- **The `docker exec` relay** is not yet timed with a pipelined client (spike open item); Task 6's docker test and the
  manual check measure it. If it is slow, the fallback is a keeper-held long-lived exec per computer, not a port.
- **noVNC's package layout** (ES modules, the `core/rfb.js` entry, no TypeScript types) may need a small `.d.ts`; it is
  used unmodified, so MPL-2.0 needs only the notice.
- **User namespaces inside the container** (the seccomp change) widen the kernel surface a little; a per-bot VM or
  gVisor is the upgrade (design §12).
- **The bounded room wait** stands in for a real requeue until routines (Design meets code 5).
