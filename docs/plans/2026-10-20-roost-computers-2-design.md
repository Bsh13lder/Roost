# Roost Computers 2.0 (a small Linux desktop per bot): Design

**Status:** DRAFT, 2026-10-20. Nothing is approved yet. §11 lists the user's open decisions.

**Sources:** `docs/research/2026-10-20-agent-computers.md` (verdict: a slim custom image, ~0.3–0.5 GB
per bot); `docs/plans/2026-10-15-roost-live-control-design.md` (L1–L4, approved, not built); the spec
(§4.4, §4.6, §4.7, the keeper table, §5.2, §5.4, step 9); `docs/plans/2026-10-20-roost-memory-design.md`;
today's `roost/desk/`, `roost/keeper/` and `docker/workspace/Dockerfile`.

**User decisions (binding):** a Linux desktop per bot first, Android later; 3–5 bots, 2–3 active at
once, on this Mac first; Grok-like (a live Computer tab or "Computer is asleep", full-screen Take
control with "You're in control · I'm done", the user signs in once); a terminal; API keys made with
the user's OK, sealed and injected per command; Skills; later a seed phrase and encrypted volumes;
privacy first, 127.0.0.1 only, permissive licences.

## 1. Why, and what changes

**Today:** each bot has a headed Brave on the Mac (CDP over pipes, egress through the proxy on 18803),
plus an idle workspace container (`roost-desk-<bot_id>`, `--network none`) that no model tool reaches.
The bot has only `open_page`, `read_page` and `ask_for_help`. To sign in, the user hunts for the bot's
Brave window; those windows clutter the Mac, and the profiles have only FileVault.

**Computers 2.0:** each bot gets a small Linux desktop in a container (screen, window manager,
browser, terminal window). The user watches it in the Computer tab and takes control there; nothing
appears on the Mac. The bot gains a terminal, sealed API keys and Skills.

**What stays:** the keeper as the only thing that touches Docker, signed keeper requests, the egress
policy, the stuck flow, the `ControlLock`, and "Use my main Brave" (open-only).

## 2. The image (`roost-computer:dev`)

**One image for every bot**, built from our own Dockerfile and pinned by digest.

| Part | Choice | Licence position |
|---|---|---|
| Base | `debian:*-slim`, same release as `docker/workspace` | Debian packages, unmodified |
| Screen and stream | **TigerVNC `Xvnc`** (X server and VNC server in one): `-rfbport -1` (no TCP), `-rfbunixpath /run/screen/vnc.sock`, `-rfbunixmode 0600` | GPL-2.0, run unmodified as **a separate program**. Roost speaks RFB to its socket and never links it |
| Window manager | **JWM**, small, with a taskbar | MIT since 2.3.6 |
| Browser | **Chromium** from Debian (native arm64). Brave has official Linux arm64 builds too (D3) | BSD-3 and permissive parts. Brave: MPL-2.0 |
| Terminal app | **xterm**, showing the bot's command feed (§4) | X11/MIT |
| PID 1 | **tini** plus `roost-computerd`, our small Python supervisor | MIT, and our code |
| Screenshots | **mss** in `roost-computerd` | MIT |
| Web viewer | **noVNC** core (with its pako), vendored as a lazy web chunk, notices kept | MPL-2.0, file-level: unmodified, or our changed files stay MPL |

**Not used:** x11vnc, Xpra and KasmVNC (GPL), websockify (LGPL; the gateway relays, §3), and AIO
Sandbox beyond its API shape. A licence scan runs at build time; `THIRD_PARTY_NOTICES.md` names every
GPL program as "separate, unmodified".

**Two containers and two users per bot**, so a command can never read the browser's cookies or watch
the screen:
- **`roost-computer-<bot_id>`** (new) runs the screen, JWM, the browser and xterm as uid 10002.
  - The profile lives on a per-bot volume.
  - CDP is `--remote-debugging-pipe`, held by `roost-computerd` and exposed only on a 0700 Unix
    socket.
  - X needs an Xauthority cookie that only 10002 can read.
- **`roost-desk-<bot_id>`** stays today's workspace: uid 10001, a read-only root, and a reap after
  every command (§5.4). Every step-9 rule holds; only its network changes (§5).
- Downloads keep today's rule: the keeper copies a file into the workspace only after the §5.4 checks.

**No ports:** neither container publishes one. The keeper reaches the CDP and VNC sockets through
`docker exec -i --user 10002 roost-computer-<id> roost-pipe <cdp|vnc>`, our own stdio relay (the
`pipe_relay.py` idea). The Mac keeps only 18800, 18801 and 18803.

**Where it runs:** on the Docker engine Roost already uses (Docker Desktop's VM). A Colima VM next to
it would cost another 1–2 GB. A server later uses plain Docker Engine.

**Size and limits per bot** (estimates; C0 measures them):

| | Idle, one page | Busy page | Limit |
|---|---|---|---|
| Xvnc 1280×800 + JWM + xterm + `roost-computerd` | 60–100 MB | same | |
| Chromium | 250–450 MB | 0.6–1 GB | |
| **Computer total** | **0.35–0.55 GB** | ~1.1 GB | `--memory 1.5g --shm-size 512m --cpus 1.5 --pids-limit 512` |
| Workspace (today) | ~10 MB | up to 1 GB | `1g`, unchanged |
| Disk | image ~0.6 GB, shared (~0.8 GB with OpenCode) | profile 50–300 MB | warning at `COMPUTER_PROFILE_WARN_MB` |

**Sleep and wake** (`COMPUTERS_MAX_RUNNING = 3`, to be revisited after C0):
- **On it:** running.
- **Resting:** idle for `COMPUTER_PAUSE_AFTER_S` (5 min) → `docker pause` (under 1 s to wake, RAM
  kept); after `COMPUTER_STOP_AFTER_S` (30 min) → `docker stop` (RAM freed, profile kept).
- **Off duty:** stopped.
- A 4th start stops the least recently used Resting computer. If all 3 are On it, the work item waits
  in the work queue, and the bot shows "Waiting for a free computer".
- Paused or stopped shows "Computer is asleep" with **Wake it**. A bot's browser call also wakes it.

**Hardening:** like the workspace (`--cap-drop ALL`, `no-new-privileges`, non-root). Chromium keeps
its sandbox through a custom seccomp profile, never `unconfined`.

## 3. Live view and control

| Option | Latency (Mac, loopback) | Extra RAM | Port | Fit |
|---|---|---|---|---|
| **noVNC + Xvnc socket, relayed by the gateway** | ~30–80 ms (est.) | ~0 until watched | **none** | **Recommended** |
| Neko (Apache-2.0, WebRTC) | ~50–150 ms; best on a phone network | +0.3 GB per stream | a UDP/TCP mux port from the VM | Phone later; its media port breaks "no port exposed" |
| CDP screencast + xdotool | ~100–300 ms at 10 fps | low | none | Only the page, never the desktop or terminal |
| Xpra | — | — | — | GPL, heavy client. Out |

**Recommendation: noVNC in the web app, talking to Xvnc's socket, every byte through the gateway.**
- **Route:** `GET /api/bots/{id}/live` (WebSocket), with the live-control design's accept rules word for
  word: the user's session; their own bot (else 4404); Roost's `Origin` (else 4403); **a loopback peer
  only (L1)**.
- **Path:** browser ⇄ gateway WS ⇄ keeper WS (`/desks/{id}/vnc`, per-desk token like `/cdp`) ⇄
  `roost-pipe vnc` ⇄ `vnc.sock`.
- **Watching vs control:** the gateway parses RFB client messages and drops `KeyEvent`,
  `PointerEvent` and `ClientCutText` unless the user holds the `ControlLock`, so "watch" is enforced
  on the server, not only by noVNC's `viewOnly`. `ServerCutText` is never forwarded.
- **Nothing is logged (L2):** the bytes are opaque. A test types a known password over the relay and
  greps logs, events and the audit.
- **UI:** the Computer tab shows the live view. **Take control** goes full screen with **"You're in
  control · I'm done"**; **I'm done** is Give it back, with L2's optional "Which account did you
  use?". The bot's browser calls are refused while the user is in control, as today.

**How the approved live-control design changes:**
- **L1 and L2 stay**, along with Vault: site logins (`site_logins`, the prompt line, Forget) and the
  `read_page` fix (skip every node inside a text box).
- **L4 is replaced** for Linux computers: the whole-desktop stream replaces the page screencast. VNC
  was rejected because it would share **the Mac's** screen; here it is a sandboxed screen with no
  port. Pop-up following, frame mapping and the key allow-list are no longer needed.
- **L3 and Show window on Mac go away.**
- The CDP screencast exists only if "Mac Brave" stays a per-bot option (D1).

## 4. How the bot drives its computer

- **CDP stays for the browser tools.** `open_page`, `read_page` and the stuck detector (unchanged) run
  over a `docker exec` pipe instead of Brave's pipe on the Mac. `KeeperDesk` gains a computer backend
  behind the same `Desk` protocol.
- **Page click and type tools are needed now** (`click`, `type`, `press_key`, `select`):
  - Making a Search Console key means clicking and filling a form.
  - They are spec §4.6 single-action CDP tools under the §4.4 gate: typing in a tainted run asks
    unless the text and the origin are trusted, and submits are gated.
- **Desktop click and type for the bot (xdotool) are not needed now.** They wait for Android or
  desktop apps.
- **`run_command(argv, timeout_s?, keys?)`**, gate kind `write_change`:
  - It reuses the keeper's exec in `roost-desk-<bot_id>` with every §5.4 rule (argv only, 120 s, the
    reap, output cut in the middle, a scrubbed environment, per-workspace taint, asking in a tainted
    run or workspace).
  - `keys` names Vault: API keys entries (§6).
  - The keeper writes each command and its scrubbed output to `roost-pipe feed`, which the desktop's
    **terminal window** shows, so the user watches the bot work.
  - The user's own xterm during Take control runs as 10002 in the computer, never in the workspace.
- **Screenshots** of the whole screen go to the Computer tab's sleeping thumbnail and to activity
  lines, for **the user only, as today**. A model "look at the screen" tool waits: the screen can show
  what the user typed (spec S15).
- **OpenCode (optional, D4)** (anomalyco/opencode, formerly sst/opencode, MIT), preinstalled in the
  workspace image and used through a "use-opencode" skill:
  - It runs as `opencode run --format json` through `run_command` with:
    - a permission config that denies by default, with bash deny rules and
      `external_directory: deny`;
    - `OPENCODE_TIMEOUT_S` and a cost cap `OPENCODE_MAX_COST`.
  - Its output is **tainted content**.
  - Its only credential is an API key from the Vault (§6), scoped to it, with its provider's hosts
    as the allowlist. It never gets a subscription login or any Roost secret.
  - **Free "Zen" models** may keep or train on data, so they are allowed only for public-web research,
    only behind an Ask card, and never with user data.

## 5. Network

- **`roost-egress`** is one container in the VM, running our `roost/keeper/proxy.py` with the same
  `is_blocked_address` policy. It is the only container on an outbound network.
  - The VM's ranges and `host.docker.internal` are private, so they are blocked; a test pins them.
  - The Mac's 18803 stays for "Mac Brave" bots.
- **Per-bot internal networks:** `roost-net-<bot_id>` holds the computer and the egress;
  `roost-wnet-<bot_id>` holds the workspace and the egress, attached only while the bot's command
  internet switch (A24) is on. No bot reaches another bot's containers.
- **Who is asking:** the proxy has a browser listener and a command listener. Each networked command
  gets a **per-command proxy token** (`HTTPS_PROXY=http://<token>@…`) that names the bot and the
  command, so the keeper taints the workspace for network use (§5.4). It dies with the command.
- **Allowlists:**
  - **Browser: none**, only the blocklist and the gate, as today.
  - **Commands: off by default.** With the switch on, they reach the open web through the blocklist.
  - **A command that injects a key reaches only that key's `hosts`**, so a leaked key can only go back
    to its own API.
- **DNS:** both containers get a `--dns` that answers nothing. Names go to the proxy, which resolves
  one only for a connection the gate passed (§5.2). A test proves `getent hosts example.com` fails in
  both; if that can't be proven, commands stay offline.

## 6. Vault: API keys

**Schema** (a migration after memory v15 and site_logins), table `api_keys`:
- `id`, `user_id`, `bot_id` (cascade);
- `env_name` (e.g. `GSC_API_KEY`), `label`, `secret` and `hosts` (a JSON list), each `enc:v2` with AAD
  `api_keys:<column>`;
- `policy` (`ask_each_time` | `clean_runs_ok`), `status` (`active` | `revoked`), `created_by` (`user` |
  `bot`);
- `use_count`, `created_at`, `last_used_at`;
- unique per `(user_id, bot_id, env_name)` through a keyed fingerprint, as memories do.

Every query has `user_id` in its WHERE.

**How a key gets in:**
1. **Ask first.** Before the bot clicks "Create key" or "Create credentials", the gate raises an
   **Ask card**, a new `grant_access` floor item (§4.4): "Make an API key on search.google.com for
   Search Console?". The env name, label and hosts are editable.
2. **The model never sees the key.**
   - `read_page` masks key-like strings (known prefixes such as `AIza`, `sk-`, `ghp_`, plus long
     high-entropy tokens) as `[key-like text, node N]`.
   - `save_api_key(node=N, env_name)` has the gateway read that node over CDP straight into the
     Vault, and returns only "Saved as GSC_API_KEY".
3. **Fallback:** the user pastes the key into the card, or adds it under **Vault: API keys** on the
   Profile, which lists keys with **Revoke** and **Delete**.

**How a key reaches a command:**
- The keeper runs `docker exec -i … roost-run <argv>`. `roost-run`, a tiny launcher in the workspace
  image, reads one JSON line of env from **stdin**, sets it and runs the argv.
- The key is never in an argv, a `docker inspect`, a file or `/workspace`, and the reap ends every
  process that held it.
- A tool that needs a credentials file (a service-account JSON) gets it on a per-command tmpfs,
  `/run/roost-keys` (mode 0400), and the reap deletes it.

**Approval and taint:** `ask_each_time` (the default) puts an Ask card naming the key and the command
before each use; `clean_runs_ok` skips it in a clean run and a clean workspace. **A tainted run or a
tainted workspace always asks.** A command that used a key had the network on, so its output taints
the run (§5.4). The prompt shows only key names, labels and hosts.

**Output scrubbing:** the keeper scrubs every command's stdout and stderr, and the terminal feed, for
**all of the bot's active key values** (raw, base64 and URL-encoded); each becomes `[GSC_API_KEY]`
before anything leaves the keeper. The same scrub runs on `read_page` text and stored tool results. A
test prints a key in each form and greps messages, events, logs and the audit.

## 7. Skills

**Format: the open Agent Skills format** (agentskills.io/specification).
- A skill is a folder `<name>/` with a `SKILL.md`, whose YAML frontmatter holds:
  - `name`: lowercase with hyphens, ≤64 chars, equal to the folder name;
  - `description`: what it does and when to use it, ≤1024 chars;
  - optional `license`, `compatibility`, `allowed-tools` and `metadata`.
- The body has the steps. Optional `scripts/`, `references/` and `assets/` folders hold the rest.
- **Roost's own fields go under `metadata`:** `roost-kind` (`playbook` | `strategy`), `roost-host`,
  `roost-version`, `roost-provenance` (run id and date), `roost-used`, `roost-worked`.
- Every skill is validated with skills-ref (github.com/agentskills/agentskills) at save time.

**Two kinds, one format:**
- **Site playbook:** one per (bot, host). A plain-language how-to, plus setup URLs and checkpoints
  ("you're on the right page when you see …"). This is the one thing worth rebuilding from LazyClaw's
  learning code.
- **Strategy:** a ReasoningBank item (google-research/reasoning-bank, Apache-2.0, idea only). Its
  title is the `name`, its description is the `description`, and its content is the body. It comes
  from successes **and** failures; a failure gives a "what to avoid" item.

**Store:**
- **The encrypted DB is the source of truth.** Table `skills` (in §6's migration):
  - plaintext: `id`, `user_id`, `bot_id`, `kind`, `host_key` (a keyed HMAC, never the host),
    `status` (`proposed` | `active` | `retired`), `user_edited`, `score`, `used_count`,
    `succeeded_count` and the timestamps;
  - `bundle`: `enc:v2`, AAD `skills:bundle`, holding the whole skill folder as validated JSON (path →
    text, size-capped).
- **Writing a run's folder.** For each run the gateway writes the bot's **active** skills that
  retrieval picked into a fresh per-run folder, `.claude/skills/<name>/` (mode 0700, outside every
  workspace and every path a tool or tainted input can write). The folder is deleted after the run.
- **Loading.** claude-agent-sdk (pinned 0.2.143) loads that folder natively through
  `ClaudeAgentOptions(setting_sources=[...], skills=[names])`. It has no registration API, so files are
  the way in. OpenCode reads the same `.claude/skills/` layout when it is used.
- **Scripts.** A skill's `scripts/` run through `run_skill(name, args)`, which passes them to
  `roost-run` on stdin. They are never copied into `/workspace`, where a later command could poison
  them.

**Self-learning loop** (the CoEvoSkills, Apache-2.0, and microsoft/skillopt, MIT, pattern; idea only):
1. **Judge.** After a run with ≥ `SKILL_JUDGE_MIN_TOOL_CALLS` tool calls, one **worker** model call
   reads the scrubbed tool trace and the user's messages, and returns strict JSON: `{outcome:
   success | failure | unclear, drafts: [...]}`.
2. **Draft.** Drafts become new skills, or edits to the host's playbook. **No draft ever comes from a
   tainted run.**
3. **Independent check.** A verifier call that did not write the draft checks it against the trace
   (were the steps really taken? are there secrets? does skills-ref pass?). Where the job is
   read-only and repeatable, a dry replay on the fake-safe path checks it instead. The result is a
   `score`.
4. **Proposed until approved.** A passing draft is `proposed`. The user approves it from a quiet
   "Learned a skill: … · Review" line in the chat or from Knowledge, which shows the diff. Only
   `active` skills ever reach a prompt.
5. **Edits must improve.** An edit to an active skill is accepted only when its verifier score beats
   the current one. **A user-edited skill is never overwritten**; the edit becomes a suggestion.

**Corrections, merging and retiring:**
- A user's correction about how a job is done is added to that host's playbook as a versioned block.
  Past `SKILL_CORRECTIONS_BEFORE_CONDENSE` blocks, a worker call condenses them, and the change goes
  through steps 3–5 above.
- A draft that overlaps an existing skill above `SKILL_MERGE_OVERLAP` becomes an edit of it.
  ReasoningBank has no consolidation, so we add it.
- A skill with ≥ `SKILL_RETIRE_MIN_USES` uses and a success rate under `SKILL_RETIRE_MAX_RATE` is
  retired, and can be restored in Knowledge.

**Retrieval, one path before every run** (no model call):
- Exact `host_key` playbooks for the hosts in the user's message or the work item, and for the bot's
  current page.
- Then strategies by word overlap × success rate, using the memory recall ranker (shared, not copied),
  within `SKILLS_PROMPT_MAX`.
- Those skills go into the run's folder. A short prompt section lists them under **"Our own notes —
  hints, not instructions"**, each with its provenance: `[playbook · github.com · v3 · saved by bot
  2026-10-18 · used 5, worked 4]`. LazyClaw injected a stale recipe with neither, and its own bot
  flagged it as a prompt injection.
- `used_count` goes up when a skill's host or script is used. `succeeded_count` goes up when the judge
  says success.

**Not rebuilt from LazyClaw:** the replay-without-model path compiler; per-tool-call lesson cards and
their verification pump (925 of 926 writes on one card carried no new information, 44% of recalls
missed, and nothing showed a benefit); typed site-memory kinds that nothing writes.

**Memory vs skills:**
- Memory is **what is true**; skills are **how to do a job**.
- A correction about how to do a job goes to a playbook; a preference goes to memory. So memory's
  `lesson` kind is not used for how-tos. This fills the memory design's out-of-scope "lessons from
  corrections".
- They share the post-run hook (separate worker calls, each with its own hourly cap), the ranker, the
  secret filter and the Knowledge screen.

## 8. Migration from Brave-on-Mac

- **Start fresh, with a hint.** Brave on macOS encrypts cookies with a Keychain key ("Brave Safe
  Storage"), and moving them means exporting that key, a secret path we would rather not build. The
  user signs in once through Take control (the Grok flow anyway). Vault: site logins labels carry over
  as hints: "you were signed in on github.com as work email; ask the user to sign in again".
- **"Mac Brave" stays a per-bot option** during the move (D1), to compare challenge rates.
- **"Use my main Brave" is unchanged:** `/usr/bin/open -a "Brave Browser" <url>`, with no automation,
  no debug port and no profile access.
- **Old profiles** stay in `~/Roost/desks/<bot_id>/browser` until the user removes them ("Remove old
  Mac browser data" on Profile → Computer).

## 9. Encrypted volumes and the seed phrase (placeholder)

**Today:** `SERVER_SECRET` is the root. Profiles and workspaces have only FileVault, and Docker
volumes sit in the VM's disk image.

**Later:** a 24-word phrase, shown once, derives a **root key** that wraps `SERVER_SECRET` and the
DEKs and lives in the macOS Keychain for auto-start. Per-bot volume keys are `HKDF(root,
"volume:<bot_id>")`; they unlock each bot's profile and workspace volume (gocryptfs, MIT, or LUKS)
when its computer starts, passed on stdin, never in an argv or a file.

**Hooks now:** one named volume per bot each for the profile and the workspace (`roost-profile-<id>`,
`roost-work-<id>`), so each can later be swapped for an encrypted one. Settings says honestly: "Bot
computers are not encrypted beyond your Mac's disk yet."

## 10. Build steps (each one shippable)

- **C0. Spike on the user's Mac** (a throwaway branch, disk guard first). It measures image size, RAM
  for 3 computers (idle and with 3 busy pages), wake time from pause and stop, noVNC input-to-screen
  latency through the `docker exec` relay, Chromium's sandbox under a custom seccomp profile, and DNS
  blocking. Neko is tried only if latency misses `LIVE_LATENCY_TARGET_MS`. Ends with a results file
  and a go/no-go.
- **C1. A computer per bot, view only:** the image, start/pause/stop, `roost-egress` and the networks,
  and CDP via `roost-pipe` (so `open_page`, `read_page` and the stuck flow run inside); the live view
  or "Computer is asleep"; a per-bot switch, "Computer: Linux | Mac Brave".
- **C2. Take control:** RFB input filtering on the `ControlLock`, the full-screen bar, Vault: site
  logins, and the `read_page` fix.
- **C3. Terminal:** `run_command`, the terminal feed, and the command internet switch with per-command
  tokens. Step 9's "done when" list applies.
- **C4. Click and type tools, and Vault: API keys:** the `grant_access` card, `save_api_key`,
  `roost-run` injection, host allowlists and scrubbing. **E2E (fake desk):** the bot makes a key on a
  fixture page, the user approves, a command uses it, and the key is in no message, log or audit row.
- **C5. Skills.** The format, store and run folder; the judge, verifier and proposals; retrieval with
  provenance; and Knowledge.
- **C6.** Optional OpenCode (if D4), and retiring Mac Brave if challenge rates are no worse.
- **Later:** §9, the phone (Neko, or noVNC with Tight encoding over a paired link), and Android.

## 11. Open decisions for the user

1. **D1. Keep "Mac Brave" next to Linux computers?** (a) Yes, a per-bot switch until C6
   (**recommended**: it compares challenge rates, and nothing breaks during the move). (b) No, all
   move at C1.
2. **D2. Live control (R2), planned before this.** (a) Build only what carries over (Vault: site
   logins, the `read_page` fix, the route rules, the full-screen bar) and skip the CDP screencast
   (**recommended**: the screencast and its input mapping would be thrown away at C2). (b) Build R2 in
   full now for Mac Brave.
3. **D3. The browser in the computer.** (a) Debian Chromium (**recommended for C0–C1**: smaller,
   simple updates). (b) Brave's official Linux arm64 build. (c) Measure both in C0, then pick by
   challenge rate.
4. **D4. OpenCode, and free models.** (a) No OpenCode for now. (b) OpenCode with a Vault API key only
   and no free models (**recommended** if the user wants a coding agent in the computer at all).
   (c) OpenCode with free "Zen" models allowed for public-web research behind an Ask card, never with
   user data.
5. **D5. How Roost signs in to Claude.** Anthropic's legal page
   (code.claude.com/docs/en/legal-and-compliance) says Agent SDK products should use API keys, and that
   third-party apps must not route requests through Pro/Max credentials on their users' behalf. Roost
   uses the SDK with the owner's subscription login. (a) Ask Anthropic to confirm that a self-hosted,
   single-owner app is fine, and keep the login until they answer (**recommended first step**).
   (b) Switch to an API key now; this changes the CLAUDE.md rule that keeps `ANTHROPIC_API_KEY` out of
   the SDK env. (c) Support both, with the API key as the default.

## 12. Risks

- **The subscription login** (D5): Roost may be outside Anthropic's terms for Agent SDK products. The
  account could be limited until this is confirmed or switched.
- **RAM on 16 GB.** Docker Desktop's VM needs about 6–8 GB, and heavy pages push a computer past 1 GB.
  Pause, stop, LRU and the cap contain it, and C0 measures it.
- **Captchas and fingerprints.** Linux Chromium in a VM looks less human than Mac Brave, and Roost does
  no evasion. D1 keeps a fallback, and the stuck flow handles walls.
- **Isolation.** Containers in one VM share a kernel, and Chromium needs a wider seccomp profile. Two
  users and two containers per bot, no ports and internal networks limit the damage. A per-bot VM or
  gVisor is the upgrade.
- **Key exfiltration by a determined injected bot** (it could encode a key into a file and send it
  later). Asking when tainted, host allowlists, scrubbing every key value, and commands being offline
  by default make it hard, not impossible. The Vault screen says so.
- **Skill poisoning.** No drafts from tainted runs, an independent check, user approval, and a
  per-run folder that no tool can write keep it out. Stale skills are contained by provenance,
  counters and retirement.
- **OpenCode and free models.** A second agent loop with its own tools, and free models that may keep
  data. It is optional, its permissions deny by default, its output is tainted, and it runs on a
  scoped key with a cost cap.
- **The `docker exec` relay** may add latency. C0 measures it, and Neko is the fallback.
- **Licence drift.** Pin digests, scan at build time, and re-check TigerVNC, JWM, noVNC, Brave and
  OpenCode at each upgrade. GPL parts stay separate, unmodified programs.
- **Volumes outside FileVault's reach** until §9. Settings says so.

## User decisions (2026-10-20)

- **D1. Mac Brave stays, as a per-bot switch.** It is off by default. A bot uses the user's Mac Brave
  only after the user turns the switch on in that bot's settings, says so in the chat, or the bot asks
  and the user agrees.
- **D2. Live control:** build only the parts that carry over: L1, L2, Vault: site logins and the
  `read_page` fix. The CDP page screencast is skipped.
- **D3. Browser:** measure Chromium and Brave in the C0 spike, then pick.
- **D4. OpenCode:** still open, under discussion with the user. Leaning yes, as the bot's coding tool,
  with these providers:
  - an API key for private work;
  - a local model later (the user plans a DGX Spark);
  - free models only for public tasks.
- **D5. Claude subscription login versus an API key:** open. The user checks with Anthropic.

## Addendum: the skill finder (research 2026-10-20)

**Sources:**
1. `anthropics/skills`, as a pinned shallow clone. Each skill has its own licence. The docx, pdf,
   pptx and xlsx skills are source-available, so they are blocked.
2. `skills.sh` (Vercel), for discovery only. Each result is resolved to its GitHub repo, and the
   licence is checked in that repo.
3. Any Claude plugin marketplace repo (`.claude-plugin/marketplace.json`) that the user adds.

**Index:** a scheduled `git clone --depth 1`. The SKILL.md front matter and the LICENSE files go
into a local search index, with the commit SHA of each skill. No live scraping.

**The risk:** in the ClawHavoc incident (Jan 2026), 341 of 2,857 skills on one marketplace stole
API keys, SSH keys and agent memory through fake "Prerequisites" steps. No skill is signed anywhere,
and scanners alone don't catch prompt injection.

**Install rules (binding):**
- A skill is installed as **proposed** only. It runs only after the user approves it.
- It is pinned to a commit SHA, with a content hash. Any update shows a diff and needs approval
  again.
- **Licence gate:** MIT, Apache-2.0, BSD, ISC or MPL-2.0 only. A missing, unknown or
  source-available licence blocks the skill.
- Before approval, the user sees the full SKILL.md and every file in the skill. Flags are shown for
  shell commands, `curl|sh`, base64, network calls, `~/.ssh` and `.env`, and install steps.
- Scripts run only in the bot's command container: no host, no vault access, network only through
  the egress proxy.
- Text from a third-party skill counts as untrusted, and taints writes like web content does.
- Size and file-count caps apply. Symlinks and paths that leave the skill's folder are refused.

## D4 update (user, 2026-10-20): code work runs in Claude Code on the user's subscription

- **Coding jobs**, including client code, run in the official, unmodified **Claude Code CLI** inside
  the bot's computer. The user signs in to it once, through Take control in the terminal.
- **Why not OpenCode for this:** Anthropic's legal page allows an end user to sign in to the
  unmodified Claude Code binary with their own subscription. OpenCode says Anthropic prohibits
  Pro/Max subscription login in third-party tools, and it removed those plugins in v1.3.0. So
  OpenCode never uses the subscription.
- **OpenCode is optional**, for:
  - an API key;
  - the future local model (DGX Spark);
  - free models for public tasks only.
- **Guard rail:** Claude Code's sign-in credentials must not be readable by the bot's own commands
  or by skill scripts. It runs as its own user, or in its own container, and the bot reaches it
  through a tool (`code_job`), never through raw file access.
- **Usage:** it shares one subscription limit with Roost's brain and with the user's own Claude Code
  use. Add a per-day cap.

## User decisions, round 2 (2026-10-20)

- **D6. Usage limit.**
  - The default is a daily cap for bot work.
  - When the user tells a bot "use the full limit", that bot may use the subscription until about
    **10% of the limit is left**. That 10% stays reserved so the bot can still report what happened
    and answer the user.
  - It needs a reliable usage reading. Check in C0 what claude-agent-sdk reports (rate-limit events
    or headers). If there is no reading, count tokens per run and calibrate.
- **D7. Vault: the model never sees a secret.**
  - Site logins, API keys and the Claude Code login are all stored sealed (`enc:v2`).
  - The bot may see only a label and an id, for example "Google: work account (key k_3f2a)".
  - Passwords and key values are never shown to it: not in prompts, tool results, logs, memory or
    skills.
- **D8. The skill hub.**
  - **Built in:** Anthropic's marketplace, for skills and Claude Code plugins.
  - **Roost's own hub:** a small marketplace with Anthropic's skills plus Roost's skills.
  - **Roost's skill pack** is ported from LazyClaw's skills where they are good, or written new.
  - **skills.sh is optional.** It is searched only when the user asks, and every result goes through
    the same install rules.
  - **Plugins:** a plugin can bring hooks and MCP servers, which run code. They follow the same
    rules as skill scripts: proposed until approved, pinned, the licence gate, and they run in the
    bot's computer only.
- **D9. An AI skill creator is included.** It creates, updates and upgrades skills (the idea of
  Anthropic's skill-creator plus the learning loop above). Every change is proposed, shows a diff,
  and needs approval.
- **D10. Each skill keeps a run log.**
  - **Each use records:** when it ran, the bot, success or failure, the step where it failed, and a
    short error.
  - **Storage:** sealed, kept to the last `SKILL_LOG_KEEP` entries, and shown on the skill's page
    for debugging.
  - **Who reads it:** the skill creator reads it to fix a skill that keeps failing.

## Addendum: lessons from a real agent run (2026-10-21)
These come from a report by the user's Grok "Upwork Worker" bot, which did a full day of real work in a shared Linux box. They are product input only; we copy no art or wording.

- **Human-like control.** A background *desktop agent* drives the computer by clicking and typing on the real screen at 1280×800, from screenshots, instead of scripted page automation. Sites saw normal human input, and it was never flagged as a bot. For Roost:
  - add a **computer-use loop** in C3/C4: screenshot → model → OS-level click and type through `xdotool` in the computer, alongside the CDP read tools;
  - only one such loop per computer at a time, using the existing control lock.
- **The user signs in once, inside the bot's browser** (Take control), and the bot never sees or stores the password. This is the same as our Vault rule.
- **Drafts on disk, actions behind a Yes.** Text drafts, cover letters and images go in the bot's scratch workspace. Submitting, sending, paying, buying credits or changing account plans always waits for the user's Yes in chat. This maps to Ask/Proposal cards and the hard floor.
- **Routines for scouting and inbox.**
  - A scout routine finds and drafts, but never applies on its own.
  - The inbox check may gather information. Prices, deadlines, offers, contracts and calls always go to the user first.
  - This maps to Routines plus the approval modes' topic switches (Posting/sending is locked to ask).
- **A daily "how I worked" security report**, a Report from the bot covering:
  - where it ran;
  - what it clicked or typed;
  - which shell paths it touched;
  - what it changed in the user's accounts;
  - what it spent;
  - who it messaged;
  - what it never did.

  Roost should be able to generate this from the audit log (redacted, no secrets) as a built-in routine Report. This fits the v1 "honest states" goal.

## Addendum: computer-use loop rules (from the Upwork Worker Q&A, 2026-10-21)
These rules are for C3/C4. We take the ideas, not the wording.

1. **Act, then check.** After each meaningful action the bot looks again. No blind multi-step chains. A step is one outcome, with one stated success check (for example "the success URL is shown" or "the dialog is gone").
2. **Wait for the page to settle before acting.** That means no navigation in flight, the layout stable for about 500 ms, and no spinner or skeleton showing. A reliable "page ready" signal (CDP lifecycle + layout-shift + screenshot diff) matters more than fake human typing delays. Scroll naturally when the target is below the fold.
3. **Two views of the page.** Screenshots (vision) decide which control to use and whether a dialog appeared. Structured text (AX tree / `read_page`) is the source for facts: amounts, balances, counts and confirmation URLs. Facts are never read from pixels when text is available.
4. **Recovery ladder.**
   - Dismiss a cookie or notice dialog.
   - When a target is missing or the page changed, re-read the screen and try ONCE more. If it still fails, go Stuck with the URL and a one-line reason.
   - When a popup covers the target, dismiss it or click outside, then retry once.
   - A login, a 2FA code, a captcha the bot can't pass, or a secret only the user has means a Stuck card asking the user to Take control.
5. **Similar buttons.** Before any click on a control whose label suggests spending, sending or committing, the bot re-reads the label as text. Example: telling "Boost" from "Submit".
6. **Exact inputs.** Text to paste and numbers to enter come from a file or card the user approved. The computer-use step never invents them.
7. **"Done" only after the confirmation is checked,** for example a confirmation URL or the new state read back as text. After any spending step, read the balance back from its source of truth.
8. **Handing back after Take control.** On "I'm done", ask (optional, one line) "logged in? finished the step?". Then re-read the screen and URL before resuming. Never ask for the password again.
9. **Always ask, even in Auto-edit.** Spending, buying credits or plans, accepting or declining offers or contracts, moving the user off a platform, sharing contact details, and anything that looks like fraud or terms-of-service abuse. This adds to the hard floor.
10. **Reports.** A Report goes out only when there is something to act on. Empty runs stay quiet, and Reports never narrate every page.
