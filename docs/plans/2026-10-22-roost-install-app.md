# Roost: Install an app (design and plan)

**Owner decision 2026-10-22** (lifts the v1 freeze for this one feature): a bot may install apps on its own
Linux computer, but only with the owner's Yes on an Ask card, every time.

**Goal:** a bot on its Linux computer can ask for a Debian package (`install_app`), and remove one it installed
(`remove_app`); `list_apps` shows what it has. Nothing installs or removes without the owner's Yes on a card
that names the package, the bot's reason and Debian's own one-line description of it. The bot never gets root:
the keeper runs a small script baked into the image as root, through one fixed argv.

## 1. The tools

| Tool | Gate kind | What it does |
|---|---|---|
| `install_app(package, why)` | `write_change`, `asks_always` | Asks; Yes installs exactly the stored package |
| `remove_app(package)` | `write_change`, `asks_always` | Asks; Yes removes exactly the stored package (only one `install_app` put there) |
| `list_apps()` | `read` | The packages the owner approved for this bot |

- Offered only to a bot on its Linux computer (`app_tools_for(bot)`, like the screen tools), never on Mac Brave,
  never to a helper (`HELPER_DENIED`).
- Topic `programs` (the bot's own computer), floor kind **`install_app`** in `FLOOR_TOOLS`, and both names in
  `ASK_WHEN_TAINTED_TOOLS`: they ask in every approval mode (Ask every time, Auto-edit, Review first) and in clean
  and tainted runs alike; a tainted card says "Based on outside content". A Proposal never carries one (the
  floor needs its own card).
- Where no card can be shown (a handoff, a room post, a helper) the gate answers `never` with
  `NEEDS_YOUR_OK_TEXT`, exactly as connector writes do. A routine run may park on a card, which waits for the
  next run like every other hard-floor ask there (the owner's condition "if that matches how other hard-floor
  asks behave there" does not hold, so routines are not refused outright).
- The card (`AppTools.prepare`): title **"<Bot> wants to install <package>"** ("… remove …"), the rows Package and
  Why, and as its detail Debian's one-line description, read on the bot's computer (`roost-apt describe`). A
  package that is not in Debian bookworm main, is denied, is not a valid name or is already on the computer
  gets a plain sentence and no card.
- Yes runs exactly the stored call (`ApprovedCalls` → `AppTools.execute`), which checks the name and the bot again.

## 2. Package names

- Debian's rule: `^[a-z0-9][a-z0-9+.-]{1,62}$` (`APP_NAME_PATTERN`).
- A hard deny list in `roost/constants.py` (`APP_DENIED_PATTERNS`, shell-style patterns, and `APP_IMAGE_PACKAGES`,
  every package the image's Dockerfile installs; a test keeps the Dockerfile and the list equal): browsers
  (`chromium*`, `brave*`, `firefox*`, `google-chrome*`, `epiphany*`, …), `sudo*`, `doas*`, su helpers,
  `openssh-server`, `tor*`, `proxychains*`, `docker*`, `podman*`, anything with `vpn` in it, `wireguard*`,
  `xserver*`, `tigervnc*`, `jwm*`, the system `python3`, `xdotool*`, `apt*` and `dpkg*`.
- The name is checked three times: the gateway (tool and route), the keeper's route, and `roost-apt` inside
  the computer (its own copy of the lists; a test keeps them equal).

## 3. Where packages come from

`roost-apt` (`docker/computer/roost_apt.py` → `/usr/local/bin/roost-apt`, standard library only) runs apt with its
own configuration on every call: `Dir::Etc::SourceList` is `/etc/roost-apt/debian.list` (Debian bookworm,
bookworm-updates and bookworm-security, `main` only, over https), `Dir::Etc::SourceParts` an empty folder and
`Dir::State::Lists` its own lists folder. The Brave repository is never visible to it, so no install and no
dependency can come from there. On top of that, before an install it reads `apt-cache policy <package>` and
refuses unless the candidate version's origin is `deb.debian.org` `bookworm`, `bookworm-updates` or
`bookworm-security`, component `main` (`not_debian`).

Install: `apt-get install -y --no-install-recommends <package>` (argv list, no shell). No `dpkg -i`, no files, no
URLs. Remove: `apt-get -s remove` first, refused (`would_remove_others`) when it would take anything but the one
package; then `apt-get remove -y --no-auto-remove <package>`. Install refuses a package already on the computer
(`already_installed`), so a base package never enters the list and so can never be removed through it.

apt goes out through the egress proxy (`Acquire::http(s)::Proxy http://roost-egress:3128`). `roost-egress` has no
host allowlist, only its address rules (no private, loopback, link-local, CGNAT or Roost ports), and
`deb.debian.org` is a public CDN on 443: **no egress change**.

Exit codes: 0 done, 2 bad arguments, 3 refused (one fixed word on stderr: `denied`, `not_found`, `not_debian`,
`already_installed`, `not_installed`, `would_remove_others`), 4 failed. apt's own output is never passed on.
Deadlines: `APP_INSTALL_TIMEOUT_S` for install, remove and ensure, `APP_DESCRIBE_TIMEOUT_S` for describe.

## 4. The keeper route

`POST /desks/{bot_id}/computer/apps` (`roost/keeper/computer_apps.py`), signed (401), a UUID4 id (400), a strict
body `{"verb": "describe"|"install"|"remove"|"ensure", "packages": [...]}` (422; one package for the first three,
up to `APPS_PER_BOT_MAX` for `ensure`), names and deny list checked again (422), and only on a running computer
(409 `asleep`; it never wakes one). One fixed argv, no shell, no stdin:
`docker exec --user 0:0 roost-computer-<id> /usr/local/bin/roost-apt <verb> <package>...`, bounded by the
deadline plus `APP_KEEPER_GRACE_S`, its output capped at `APP_OUTPUT_MAX_BYTES`. A refusal word is 409
`{word}`; anything else 500 `apps failed`. The keeper audit gets `computer_apps`, the bot id, the verb and a
result word, never a package name.

**Capabilities.** apt needs a writable root filesystem and, as root, `CHOWN`, `DAC_OVERRIDE` and `FOWNER`. The
computer's `docker run` drops `--read-only` and adds those three to the bounding set (`COMPUTER_APT_CAPS`); its
own processes still run as uid 10002 with `no-new-privileges`, so they have no effective capability (checked:
`CapEff 0`) and cannot write `/usr`. `/var/tmp` becomes a tmpfs, so nothing the bot writes outside its profile
and home survives a stop. A computer created before this change is still read-only: it needs one fresh start
(remove the container; the profile volume stays).

## 5. Persistence and reinstall

Schema **v32** `bot_apps`: `id`, `user_id`, `bot_id` (cascade), `package` (`enc:v2`, `bot_apps:package`),
`package_key` (keyed HMAC of the name, a sub-key of the DEK, unique per user and bot), `tainted` (the card came
from a tainted run), `installed_at`. Every statement names `user_id`; another user's bot or app is a 404. At most
`APPS_PER_BOT_MAX` per bot.

A stopped computer keeps its container, so its apps stay. A computer the keeper creates fresh (`docker run`: a
new image or a removed container) answers its start with `"fresh": true`; the desk then calls the factory's boot
hook, and `AppReinstaller` reinstalls the bot's approved list in the background with one `roost-apt ensure`
(only the missing ones, one apt call). It never blocks the start, and a failure is a log line and an audit row
(`reinstall_failed`), never a crash. The reinstaller is a system job like the scheduler: it finds the owner from
`bot_apps` by bot id, then reads the list with that `user_id`.

## 6. Audit

The gate's own rows (`ask`, then `do`/`approved`) carry the call, sealed and redacted (`{"chars": n}` for the
name). `roost/apps/audit.py` adds one row per result with no detail: `install_app` `installed` / `install_failed`,
`remove_app` `removed` / `remove_failed` / `owner_removed`, `reinstall_app` `reinstall_failed`.

## 7. Web

Profile → Computer tab, Linux only: an "Apps" list (`web/src/components/computer/AppsList.tsx`) of the approved
packages with Remove. Remove is the owner's own click, so it needs no card:
`DELETE /api/bots/{id}/apps/{app_id}` wakes the computer, runs `roost-apt remove`, and drops the row (503 when the
computer can't be reached, and the row stays). `GET /api/bots/{id}/apps` lists them. Plain for now; Roost Lead
styles it later.

## 8. Tasks (tests first)

1. Constants, `roost/apps/names.py`: name rule and deny list (tests: names, deny, Dockerfile parity).
2. `docker/computer/roost_apt.py` and its apt config files in the image (tests: argv shapes, the Debian-only
   policy parse, remove simulation, deny parity with the constants).
3. Keeper route (tests: signed, bad id, bad body, denied name, asleep, argv, refusal word, audit).
4. Schema v32, `AppStore` (tests: sealed name, unique key, 404 for another user, owners).
5. Gate: tool defs, topics, floor, allowlist (tests: asks in every mode, tainted too, never without cards, Linux only).
6. `AppTools` and `AppService` (tests: card text, Yes installs and records, remove, refusals).
7. Fresh flag, boot hook and `AppReinstaller` (tests: fresh start calls the hook, reinstall list, failure is quiet).
8. Routes and the web list (tests: list, remove, 404 for another user's bot or app).
