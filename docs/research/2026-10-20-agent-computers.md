# Giving each Roost bot a full computer (and maybe a phone): open-source survey

Date: 2026-10-20. All licences, star counts and last-push dates come from the GitHub API (`gh api repos/...`) and the LICENSE files, checked on that day. I read the code only. Nothing was cloned or run.

Licence rule: only MIT, Apache-2.0, BSD, ISC and MPL-2.0 are **usable**. GPL, AGPL, SSPL, BSL, FSL (source-available) and repos with no licence are marked **not usable** and appear only for reference.

## Summary table

| Project | Licence (verified) | Stars | Last push | What it gives an agent | Self-host on a Mac | Roost fit |
|---|---|---|---|---|---|---|
| [trycua/cua](https://github.com/trycua/cua): SDK, `cua` CLI, Cua Driver, Lume | **MIT** (but Cua Spaces app, cua-spacesd, Keyvault and streaming client are **FSL-1.1-MIT**; optional `cua-som` and `cua-perception` are AGPL) | 30.3k | 2026-10-20 | Screenshots, mouse and keyboard, exec, files; local Linux sandboxes (gVisor containers) and macOS/Linux VMs (Lume) | Yes | **High** for the MIT parts. Do not use Spaces, cua-spacesd or the perception extension |
| Lume (in `trycua/cua/libs/lume`) | **MIT** | (monorepo) | 2026-10-20 | CLI and HTTP API for macOS/Linux VMs on Virtualization.framework | Yes, Apple Silicon | **High** for per-bot VMs |
| [lima-vm/lima](https://github.com/lima-vm/lima) | **Apache-2.0** | 22.1k | 2026-10-20 | Linux VMs (vz or QEMU), SSH, port forwards bound to 127.0.0.1 by default | Yes | **High**. Mature, scriptable, CNCF project |
| [abiosoft/colima](https://github.com/abiosoft/colima) | **MIT** | 31.3k | 2026-10-13 | One Lima VM that runs Docker | Yes | High, as a shared host for desktop containers |
| [Code-Hex/vz](https://github.com/Code-Hex/vz) | **MIT** | 0.9k | 2026-10-20 | Go bindings for Virtualization.framework | Yes | Medium. A low-level option |
| [utmapp/UTM](https://github.com/utmapp/UTM) | Apache-2.0, but bundles QEMU (GPL-2) | 36.0k | 2026-10-20 | GUI VM manager with `utmctl` | Yes | Low. Built for people at a GUI, not for automation |
| [openai/tart](https://github.com/openai/tart) | **FSL-1.1-ALv2: not usable** | 7.6k | 2026-10-17 | macOS/Linux VMs for CI | Yes | Reference only |
| [anthropics/claude-quickstarts](https://github.com/anthropics/claude-quickstarts) computer-use-demo | **MIT** | 18.9k | 2026-10-08 | Ubuntu, Xvfb, x11vnc, noVNC and the reference computer tool | Docker | **Good pattern** to copy. Its sample `docker run` publishes 5900/6080/8080 on all interfaces |
| [agent-infra/sandbox](https://github.com/agent-infra/sandbox) (AIO Sandbox) | **Apache-2.0** | 6.2k | 2026-09-14 | Browser (CDP), VNC, shell, files, VS Code, Jupyter and MCP behind one port; optional API key | Docker | **High**. Its documentation already uses `-p 127.0.0.1:8080:8080` |
| [e2b-dev/desktop](https://github.com/e2b-dev/desktop) + [e2b-dev/infra](https://github.com/e2b-dev/infra) | **Apache-2.0** (both) | 1.5k / 1.7k | 2026-10-19/20 | Desktop SDK: screenshots, input, streaming | Infra needs Linux with KVM (Firecracker), **not macOS** | Low on a Mac. Medium on a Linux box later |
| [bytedance/UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop) | **Apache-2.0** | 39.3k | 2026-10-09 | Agent app that drives the local desktop or browser | App | Low. It is an agent, not a sandbox |
| [openinterpreter/openinterpreter](https://github.com/openinterpreter/openinterpreter) | **Apache-2.0** | 68.6k | 2026-10-11 | OS mode drives the **host** machine | n/a | Low. No isolation |
| [bytebot-ai/bytebot](https://github.com/bytebot-ai/bytebot) | Apache-2.0, **archived** | 11.1k | 2025-09-12 | Ubuntu desktop container with an agent | Docker | Reference only (unmaintained) |
| [steel-dev/steel-browser](https://github.com/steel-dev/steel-browser) | **Apache-2.0** | 7.8k | 2026-10-20 | Browser sessions over CDP, a session viewer, stealth | Docker | Medium. Browser only, close to what Roost already has |
| [daytonaio/daytona](https://github.com/daytonaio/daytona) | **AGPL-3.0, archived June 2026: not usable** | 71.5k | 2026-07-24 | n/a | n/a | Reference only |
| [kasmtech/workspaces-images](https://github.com/kasmtech/workspaces-images) | Dockerfiles are MIT, but they ship [KasmVNC](https://github.com/kasmtech/KasmVNC) (**GPL-2.0**) | 1.2k / 5.3k | 2026-10 | Desktop images streamed through KasmVNC | Docker | **Not usable** as a dependency |
| [linuxserver/docker-webtop](https://github.com/linuxserver/docker-webtop) | **GPL-3.0: not usable** | 4.4k | 2026-10-20 | Desktop container | Docker | Reference only |
| [m1k1o/neko](https://github.com/m1k1o/neko) | **Apache-2.0** | 22.5k | 2026-10-20 | Desktop or browser streamed over WebRTC with audio; several viewers can control it | Docker | **High** for watching and Take control |
| [selkies-project/selkies](https://github.com/selkies-project/selkies) | **MPL-2.0** | 2.4k | 2026-10-20 | GStreamer WebRTC streaming of an X desktop | Docker | High as a streaming layer |
| [apache/guacamole-server](https://github.com/apache/guacamole-server) and [-client](https://github.com/apache/guacamole-client) | **Apache-2.0** | 4.0k / 1.7k | 2026-10 | HTML5 gateway for VNC, RDP and SSH with its own auth | Docker; Java plus guacd | Medium. Heavy |
| [novnc/noVNC](https://github.com/novnc/noVNC) | **MPL-2.0** (core) | 14.1k | 2026-10-16 | Browser VNC client | Static JS | Medium. Fine behind the gateway |
| [any1/wayvnc](https://github.com/any1/wayvnc) | **ISC** | 1.8k | 2026-10-18 | VNC server for Wayland | Linux | Medium |
| TigerVNC, x11vnc, Xpra, RustDesk | GPL-2 / GPL-2 / GPL-2 / AGPL-3: **not usable** | n/a | n/a | n/a | n/a | Reference only |
| [mobile-next/mobile-mcp](https://github.com/mobile-next/mobile-mcp) | **Apache-2.0** | 9.8k | 2026-10-18 | MCP tools for Android and iOS: accessibility tree first, screenshots, taps; works with emulators, simulators and real devices | Yes | **High**. PostHog/Scarf telemetry must be turned off (`MOBILEMCP_DISABLE_TELEMETRY=1`) |
| [droidrun/mobilerun](https://github.com/droidrun/mobilerun) (formerly DroidRun) | **MIT** | 9.7k | 2026-10-16 | A complete mobile agent framework (Android, plus iOS) with its own LLM loop | Yes | Medium. Overlaps Roost's own agent loop |
| [minitap-ai/mobile-use](https://github.com/minitap-ai/mobile-use) | **Apache-2.0** | 3.3k | 2026-10-18 | Mobile agent framework | Yes | Medium |
| [TencentQQGYLab/AppAgent](https://github.com/TencentQQGYLab/AppAgent) | MIT | 6.9k | 2025-03-19 | Research Android agent | Yes | Low (stale) |
| [appium/appium](https://github.com/appium/appium) + [appium/appium-mcp](https://github.com/appium/appium-mcp) | **Apache-2.0** | 22.1k / 0.5k | 2026-10-19/20 | WebDriver for Android (UiAutomator2) and iOS (XCUITest) | Yes (Node) | Medium-high. Heavier but standard |
| [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy) | **Apache-2.0** | 152.6k | 2026-10-17 | Mirrors and controls an Android screen over adb | Yes | **High** for watching and taking over a phone |
| [DeviceFarmer/stf](https://github.com/DeviceFarmer/stf) | Apache-2.0 | 4.6k | 2026-10-02 | Web device farm for Android | Linux | Low. Old stack |
| [budtmo/docker-android](https://github.com/budtmo/docker-android) | "Custom Apache-2.0" with extra amendments: **not usable** | 16.0k | 2026-10-18 | Emulator in Docker | Needs /dev/kvm, so not on a Mac | Reference only |
| [remote-android/redroid-doc](https://github.com/remote-android/redroid-doc) | Apache-2.0 per its README; **no licence on the repo** | 7.0k | 2026-05-17 | Android in a container | Needs Linux binder modules | Not on a Mac |
| [facebook/idb](https://github.com/facebook/idb) | **MIT** | 5.4k | 2026-10-20 | iOS Simulator and device control: screenshots, tap, swipe, video | macOS | **High** for simulators |
| [appium/WebDriverAgent](https://github.com/appium/WebDriverAgent) | **BSD-3**, repo **archived** | 1.9k | 2026-10-17 | XCUITest server on the device | macOS + Xcode | Medium (archived; check where it moved) |
| [joshuayoes/ios-simulator-mcp](https://github.com/joshuayoes/ios-simulator-mcp), [getsentry/MobileBuildMCP](https://github.com/getsentry/MobileBuildMCP) | **MIT** | 2.2k / 6.5k | 2026-08 / 2026-10 | MCP for the Simulator and Xcode | macOS | Medium |

## 1. Agent desktop sandboxes

**Best usable fits:**

- **AIO Sandbox** (agent-infra, Apache-2.0). One container holds Chromium with CDP, a VNC desktop, a shell, a file API and MCP, all behind one port. It supports an API key (`SANDBOX_API_KEY`), and its quick start already binds `127.0.0.1`. That is the closest off-the-shelf match to "a bot's Computer" with a single control point. Inside the container it listens on 0.0.0.0, so the host port mapping must stay on 127.0.0.1. It also needs `seccomp=unconfined`, which weakens isolation.
- **Anthropic's computer-use demo** (MIT). Small and readable: Xvfb, a window manager, x11vnc, noVNC and the computer tool. It is a good pattern to copy with an SPDX header. Its sample `docker run` publishes VNC 5900 on all interfaces with no password, so never copy that line.
- **cua** (MIT core). The cua SDK and Cua Driver give a typed screenshot and input API for macOS, Linux and Windows. The `cua sb` sandboxes are gVisor containers. Since Oct 2026 the polished parts (Spaces, the cua-spacesd daemon, Keyvault, the streaming client) are FSL-1.1-MIT, so Roost may only take the MIT libraries.

**Not a fit on a Mac:**

- E2B's runtime is Firecracker and needs Linux with KVM.
- Daytona is AGPL and archived.
- Bytebot is archived.
- Kasm images carry GPL KasmVNC.
- Open Interpreter and UI-TARS desktop drive the host machine itself. That is the opposite of per-bot isolation.

## 2. macOS and Apple Silicon (16 GB M2)

- **Lima** (Apache-2.0) is the safest Linux VM base. It uses the `vz` driver (Virtualization.framework) and Rosetta for x86 binaries. Its forwarded ports bind 127.0.0.1 by default, and `limactl` scripts cleanly. The default VM is 4 GiB, but you can set it per VM.
- **Colima** (MIT) puts one Lima VM under Docker. Running all bot desktops as containers in **one** VM is far cheaper than one VM per bot.
- **Lume** (MIT, inside the cua repo) adds macOS guests and an HTTP API.
- **Tart** is now under `openai/tart` and FSL-1.1-ALv2, so it is not usable. UTM is Apache-2.0 but bundles QEMU (GPL) and is meant for a person at the GUI.
- **RAM on 16 GB:** macOS plus Roost plus the user's own apps take about 7–9 GB. That leaves about 7 GB.
  - A light Linux desktop (Xfce, Chromium, VNC or WebRTC) costs about **0.8–1.5 GB as a container** and **1.5–2.5 GB as its own VM** (kernel plus page cache), plus about 0.3 GB per stream encoder.
  - Realistic capacity: **3–5 container desktops in one Colima VM**, or **2 full Linux VMs**.
  - A **macOS VM needs 4–8 GB**. Apple's licence and Virtualization.framework both cap it at **2 concurrent macOS guests** per Mac, so 16 GB holds about **one**. That suits only an occasional "Mac computer" bot.

## 3. Mobile

**Android (works on Apple Silicon without a real phone):**

- The official Android Emulator runs arm64 system images natively through Hypervisor.framework. Each instance needs about **2–4 GB** of RAM.
- Control it with:
  - **mobile-mcp** (Apache-2.0): reads the accessibility tree first, falls back to screenshots, and offers a single set of tools for both Android and iOS.
  - Plain **adb** and UiAutomator.
  - **scrcpy** (Apache-2.0): for the user to watch and take over.
- Appium (Apache-2.0) is the heavier, standard alternative.
- **mobilerun** (MIT) is a full agent loop. Roost already has its own agent loop, so mobilerun is better treated as a reference or a source of tool ideas.
- Docker Android options (docker-android, redroid) need Linux KVM or binder modules, so they do not run on a Mac.
- A real phone over USB with adb also works.
- Play Store images fall under Google's SDK terms (they are not open source), so the user installs them.

**iOS:**

- The **Simulator** runs on Apple Silicon and is driven by **idb** (MIT), WebDriverAgent (BSD-3) or mobile-mcp. Each one needs about 1.5–3 GB of RAM and requires Xcode.
- The Simulator **cannot install App Store apps**. It runs only Safari, the built-in apps and apps you build yourself. That makes it a poor fit for "use my bank app".
- A **real iPhone** needs USB, trust pairing and a WebDriverAgent build signed with the user's Apple ID (free profiles expire every 7 days). That is fragile but doable for one device.
- No iOS emulation exists outside Apple tooling.

## 4. Live view and Take control without exposing VNC

- **Neko** (Apache-2.0) streams over WebRTC with audio and lets several people control one screen (an "implicit hosting" control handoff), which maps directly onto Take control / Give it back. Its v3 has pluggable member providers (multi-user passwords, a file, no-auth) and session cookies.
  - **Roost should use no-auth bound to 127.0.0.1 behind the gateway**, or let the gateway mint the session.
  - WebRTC needs a UDP port range (or the TCP/UDP mux mode). Pin it to a single muxed port on 127.0.0.1 and disable public STUN/ICE.
- **Selkies** (MPL-2.0) is a lighter GStreamer WebRTC layer that you could embed in your own image.
- **Guacamole** (Apache-2.0) proxies VNC/RDP/SSH to HTML5 and has mature auth: database, LDAP, OIDC/SAML and header auth. But it is a Java web app plus guacd (about 0.5–1 GB), which is too heavy per bot. One shared instance could serve them all.
- **noVNC** (MPL-2.0) over a WebSocket proxy is the simplest option. Proxy it **through the Roost gateway** with the user's session. VNC itself must never be published.

## Recommendation

**Full Linux desktop per bot, on a Mac, best building blocks:**

1. **Colima or Lima (MIT / Apache-2.0)** as the single host VM, with **one desktop container per bot** (`roost-desk-<bot_id>`), each on its own Docker network behind Roost's egress proxy. Start the image from AIO Sandbox (Apache-2.0) or the Anthropic demo's Xvfb + x11vnc + noVNC pattern (MIT). Note that x11vnc is GPL, so swap in an MIT/ISC/MPL-compatible server or a WebRTC path.
2. **Neko (Apache-2.0) or Selkies (MPL-2.0)** for the live view and Take control, served only through the gateway on 127.0.0.1 with gateway-issued sessions.
3. **cua's MIT SDK and Driver, or Lume**, if a bot ever needs a macOS computer or a real per-bot VM. Use Lume for at most one macOS guest.

**Android:** the official emulator (arm64) plus **mobile-mcp** (Apache-2.0, telemetry off), with **scrcpy** (Apache-2.0) for watching and taking over. Budget 2–4 GB per phone, which means one phone at a time on 16 GB.

**iOS:** realistic only as one Simulator, through idb or mobile-mcp, for Safari and the built-in apps. Real App Store apps need a real, USB-tethered iPhone with a WebDriverAgent build signed with the user's Apple ID. Treat that as experimental and opt-in.

**Main risks:**

- **RAM.** 16 GB holds about 3–5 Linux container desktops, *or* 2 Linux VMs, *or* 1 macOS VM, *or* 1–2 phones. You cannot have all of them at once. Plan for "On it" computers being started on demand and paused when Resting.
- **IP reputation.** Everything runs on the home IP, which is good for avoiding datacenter-IP blocks and captchas. But many bots on one home IP can trigger rate limits, and a bot's mistake is attributed to the user. Any cloud/VPS fallback (E2B, a Linux KVM box) brings datacenter IPs and more human checks.
- **Licences.** Watch for licences moving under you: Tart (FSL), cua Spaces (FSL), Daytona (AGPL), Kasm/KasmVNC, webtop, x11vnc, TigerVNC and Xpra (GPL), docker-android (custom terms), redroid (no repo licence), Play system images (Google terms). Pin versions and re-check licences at each upgrade.
- **Exposed VNC and streaming.**
  - Sample commands publish 5900/6080 on 0.0.0.0, and many images listen on 0.0.0.0 inside the container. Always map to `127.0.0.1`, keep VNC off the host entirely, and reach it only through the gateway with the user's session.
  - WebRTC ICE can leak LAN or public IPs and open UDP ports. Use mux on loopback with no external STUN.
  - AIO Sandbox needs `seccomp=unconfined`. gVisor or one VM per bot gives stronger isolation.
- **Privacy.** Turn off telemetry (mobile-mcp sends to PostHog/Scarf; check every image). Bots logged into real accounts inside desktop containers need the profile directory encrypted at rest. Docker volumes in Colima are not, unless they live on FileVault-backed host storage.

## Follow-up: AIO Sandbox up close (2026-10-20)
- Contents: Chromium (CDP 9222), TigerVNC + Openbox (GPL-2.0) web VNC, code-server, JupyterLab, terminal, file/shell REST API, MCP hub; nginx front on :8080; user `gem` after root start. Native arm64 image (verified on M-series).
- RAM idle: default ~0.8–0.9 GB; Jupyter + code-server off ~0.4 GB; + an open browser page ≈ 1.2–1.5 GB per bot (estimate). Compose defaults 8 GB / 4 CPU / shm 2 GB. `DISABLE_*` env flags exist.
- Security: listens 0.0.0.0 in-container (publish as 127.0.0.1:port); auth `SANDBOX_API_KEY` or JWT (open if unset); needs `seccomp=unconfined` (or a custom profile); runs root then drops; no egress control (use an internal network + our proxy).
- Control: REST `/v1/docs` (screenshot, shell exec, files), MCP, raw CDP; Python SDK `agent-sandbox` Apache-2.0.
- Verdict for Roost: good quick prototype (extras off); for production a slim custom image (Xvfb + Chromium + small CDP/screenshot/exec API, custom seccomp profile, licence-clean parts) at ~0.3–0.5 GB per bot, reusing the SDK's API shape.
