# Computers 2.0, C0 spike results (2026-10-20)

Mac: Apple Silicon, 8 CPUs, Docker Desktop 29.3.1 (arm64). **The Docker VM has only 3.83 GiB RAM**, and it
already runs the gateway and other containers. No app code was changed. Spike files: `spikes/computers-c0/`
(Dockerfile, `start.sh`, `ram.sh`, `trial.sh`, `vnc_probe.py`, `licences.sh`, seccomp profiles, raw licence lists).
Every image, container and network was named `roost-spike-*` / `roost-computer-spike*` and has been removed.

Image contents: `debian:bookworm-slim`, TigerVNC 1.12 `Xvnc` (`-rfbport -1`, Unix socket only, mode 0600),
JWM 2.4.3, xterm, tini, Chromium 155.0.8059 (Debian) or Brave 1.97.59 (official apt repo, arm64).
Runs as uid 10002, `--cap-drop ALL`, `no-new-privileges`, `--shm-size 512m --memory 1500m --cpus 1.5 --pids-limit 512`.

## 1. Image size

| Variant | `docker image inspect .Size` (compressed) | On disk, unpacked (`docker images`) |
|---|---|---|
| Chromium (`roost-computer-spike:chromium-noviewer`) | 320 MB | 1.23 GB |
| Chromium + websockify (`:dev`, spike only) | 349 MB | 1.36 GB |
| Brave (`:brave`) | 375 MB | 1.40 GB |

The design's "image ~0.6 GB" estimate is low if read as unpacked size. Brave costs about 170 MB more than Chromium on disk.
The image has 280 dpkg packages (Chromium) or 271 (Brave). Mesa, LLVM 15, GTK3 and CUPS libraries come in as Chromium dependencies.

## 2. RAM (`docker stats --no-stream`, 25-50 s after start)

| Case | Chromium | Brave |
|---|---|---|
| Xvnc + JWM + xterm, no browser | 26 MiB | n/a (same) |
| 1 computer, about:blank | 208 MiB | 196 MiB |
| 3 computers, about:blank (each) | 199 / 208 / 207 MiB (614 total) | 196 / 195 / 193 MiB (584 total) |
| 1 on news.ycombinator.com | 212 MiB | 210 MiB |
| 1 on instagram.com (login page) | 313 MiB, 18% CPU | 304 MiB, 7% CPU |
| 3 busy: HN + Instagram + Reddit | 211 + 281 + 307 = 799 MiB | 212 + 290 + 333 = 835 MiB |
| Animated full-page page (software rendering) | ~250 MiB, ~55% of one CPU | not run |

Chromium and Brave are within about 5% of each other on RAM. Real numbers are well under the design estimate (0.35-0.55 GB idle,
~1.1 GB busy). Caveats:
- No GPU. Rendering is in software.
- The Instagram page tested is the logged-out one, not a feed.
- `docker stats` leaves out some page cache.
- Three computers fit comfortably in the 3.83 GiB VM, but only about 1.5 GB of it is free next to the other containers.
  Docker Desktop's memory may need raising before `COMPUTERS_MAX_RUNNING` is raised.

## 3. Live view (noVNC path)

Setup: websockify inside the container, `--unix-target=/run/screen/vnc.sock`, published only on `127.0.0.1:16080`.
Client: `vnc_probe.py`, a stdlib Python WebSocket + RFB 3.8 client, Raw encoding only (the worst case for bytes, the best case for CPU).

- **Time to first frame** (5 runs, includes Docker Desktop's port forward): WebSocket upgrade 3.5-7.5 ms, RFB handshake done at 5-11 ms,
  **first full 1280x800 frame at 28-40 ms**.
- **Key press to the screen updating** (xterm, 30 samples): median **2.5 ms**, p90 12 ms, max 13 ms. This is the server path only;
  Chromium repaint time is not included.
- **Update rate:** 26.6 full-screen-ish updates/s (avg 563k px, 60 MB/s of Raw) against an animating page, with a strict
  request/response client. This is a lower bound for the pipe, not a cap. Real noVNC pipelines requests and uses Tight/ZRLE, so it
  will be lighter.
- **CPU cost of streaming:** an animating page took 55.5% of a CPU unwatched and 64.5% watched, so watching costs about 9 points
  (Raw). An idle page cost ~0.3% either way. Memory +10 MiB while watched. websockify idle added ~22 MiB.
- **Not measured:** the `docker exec -i ... roost-pipe vnc` relay and the gateway hops. A bare `docker exec` spawn costs ~90-100 ms once
  per session. The extra per-byte latency of a stdio relay should be small but is unmeasured; it needs a prototype in C1.
- `LIVE_LATENCY_TARGET_MS` is met with a wide margin on the server side, so Neko is not needed.

## 4. Pause and resume

- `docker pause` took 116 ms and `docker unpause` took 82 ms. Chromium survived with all 10 processes, no restart, the same animation state,
  and the same memory (262 MiB).
- A new RFB connection after unpause got its first full frame about 196 ms after the unpause command began, and incremental
  updates flowed at 17-35 ms spacing straight away. **Usable again in about 0.2 s.**
- Stop then start (RAM freed, profile kept in the writable layer): the first start failed because Xvnc found a stale
  `/tmp/.X1-lock` and the old socket, and the container exited. After `start.sh` removes the stale X lock, the VNC socket and Chromium's
  `Singleton*` files, **the first Chromium process was up 1.3 s after `docker start`**. The real image must clean these on every
  boot, or keep `/tmp` as a tmpfs.

## 5. Sandbox

- **Default seccomp (with `--cap-drop ALL`): Chromium and Brave both fail** ("No usable sandbox" / zygote exits). The cause is that
  `unshare -U` (user namespaces) is denied, because Docker's default profile only allows `clone`/`unshare` with `CAP_SYS_ADMIN`.
- `seccomp=unconfined` works, but the design forbids it.
- **Minimum change that works: Docker's default profile plus one unconditional allow rule for `clone`, `clone3`, `unshare`, `setns` and
  `chroot`** (`chromium-seccomp.json`, generated from moby/profiles `default.json`, Apache-2.0, kept next to it).
  With it, Chromium and Brave both start with the sandbox on, under `--cap-drop ALL` and `no-new-privileges`, with no `--no-sandbox` and no added capability.
  - Allowing only `clone` and `unshare` was not enough. The sandbox helper then dies on `chroot("/proc/self/fdinfo/")`, so `chroot` is needed.
  - `setns` and `clone3` were not tested individually; trim them in C1 if desired.
  - `clone`/`unshare` unconditionally allows user namespaces inside the container, which widens the kernel attack surface a little.
    The profile stays far narrower than unconfined.

## 6. DNS

Yes. Tested on a `docker network create --internal` network: the container's `getent hosts news.ycombinator.com` fails,
while container names still resolve through Docker's embedded DNS. `--network none` resolves nothing. So the plan (an internal network
holding the computer and `roost-egress` only) leaves the computer no DNS or route except the proxy. Chromium should also run with
`--proxy-server=http://roost-egress:PORT` (CONNECT, so the proxy resolves names) and optionally
`--host-resolver-rules="MAP * ~NOTFOUND , EXCLUDE roost-egress"`, so it never tries to resolve locally. This combination was not
exercised end to end in C0, because there is no proxy in the spike.

## 7. Licences (GPL / LGPL packages in the image)

Method: `licences.sh` scans each installed package's Debian `copyright` file for GPL/LGPL/AGPL names (a heuristic: a package that is
mostly permissive but has some GPL files, or is dual-licensed, is listed too). Full per-package lists:
`spikes/computers-c0/lic-chromium.txt` (184 packages) and `lic-brave.txt` (181). Everything is a separate, unmodified Debian package
or shared library, installed by apt and never patched.

No AGPL package was found. Packages that matter to the Roost story, one line each:
- `tigervnc-standalone-server`, `tigervnc-common` 1.12.0: GPL-2+ (some GPL-3). The Xvnc X server and VNC server, a separate program run
  unmodified; Roost speaks RFB to its socket only.
- `jwm` 2.4.3: **Expat (MIT)**, with GPL-2+ only for the Debian packaging files. This confirms the design's "MIT".
- `xterm`: not flagged (X11/MIT). `tini`: not flagged (MIT/Expat).
- `chromium`, `chromium-common` 155: lists GPL-2+/GPL-3+/LGPL-2.1 parts, for bundled third-party code. Debian's build, unmodified.
  Brave's own package ships no `copyright` file in `/usr/share/doc`; it is MPL-2.0 plus Chromium's bundled components.
- `libmp3lame0` (LGPL-2), `libflac12`, `libsndfile1`, `libmpg123-0`, `libpulse0`, `libasound2` (LGPL-2.1+): audio libraries
  pulled in by Chromium, dynamically linked and unmodified.
- `libgnutls30`, `libnettle8`, `libhogweed6`, `libgmp10`, `libidn2-0`, `libunistring2`, `libtasn1-6`, `libp11-kit0`: LGPL-2.1+/LGPL-3+
  (gmp/idn2 also GPL-2+/3+ dual). Shared libraries, unmodified.
- GTK / GNOME stack (`libgtk-3-0`, `libglib2.0-0`, `libpango*`, `libcairo*`, `libatk*`, `libatspi2.0-0`, `libgdk-pixbuf-2.0-0`,
  `librsvg2-2`, `dbus*`, `libdconf1`, `dconf-service`, `adwaita-icon-theme`, `gtk-update-icon-cache`): LGPL-2.1+/LGPL-2+ (some tools GPL-2/3). Shared libraries, unmodified.
- Mesa and LLVM (`libgl1-mesa-dri`, `libglx-mesa0`, `libglapi-mesa`, `libllvm15`, `libgbm1`): the copyright file mentions GPL only for
  build or helper files; the libraries are MIT-style. Treat as a false positive until checked by hand.
- Base system (`bash`, `coreutils`, `grep`, `sed`, `tar`, `gzip`, `findutils`, `diffutils`, `util-linux`, `mount`, `login`, `passwd`, `dpkg`, `apt`,
  `perl*`, `procps`, `sysvinit-utils`, `e2fsprogs`, `mawk`, `dash`, `debianutils`, `hostname`, `adduser`, `init-system-helpers`, `base-files`,
  `base-passwd`, `usr-is-merged`, `gpgv`, `debian-archive-keyring`, `ca-certificates` and their libs `libc6`, `libc-bin`, `libgcc-s1`, `libstdc++6`,
  `libgcrypt20`, `libgpg-error0`, `libpam*`, `libsystemd*`, `systemd`, `systemd-sysv`, `libudev1`, `libmount1`, `libblkid1`, `libuuid1`, `libfdisk1`,
  `libsmartcols1`, `libacl1`, `libattr1`, `libcap*`, `libaudit*`, `libselinux1`, `libsemanage*`, `libsepol2`, `libseccomp2`, `libkmod2`, `libelf1`,
  `libdb5.3`, `libgdbm*`, `libzstd1`, `liblz4-1`, `liblzma5`, `libbz2-1.0`, `libpng16-16`, `libjbig0`, `libssl3`, `openssl`, `libsqlite3-0`,
  `libxxhash0`, `libz3-4`, `libffi8`, `libcrypt1`, `libicu72`, `libfreetype6`, `libharfbuzz*`, `libgraphite2-3`, `libfribidi0`, `libthai*`,
  `libdatrie1`, `liblcms2-2`, `libcolord2`, `libcups2`, `libavahi-*`, `libkrb5*`, `libgssapi-krb5-2`, `libk5crypto3`, `libcom-err2`, `libkeyutils1`,
  `libapparmor1`, `libcryptsetup12`, `libdevmapper1.02.1`, `dmsetup`, `libip4tc2`, `libsensors*`, `libxnvctrl0`, `libutempter0`, `libasyncns0`,
  `libproc2-0`, `libdebconfclient0`, `libss2`, `libext2fs2`, `libapt-pkg6.0`, `libfile-readbackwards-perl`, `libperl5.36`, `perl-modules-5.36`,
  `shared-mime-info`, `x11-common`, `hicolor-icon-theme`, `at-spi2-common`, `fonts-liberation` (GPL-2 with font exception)): GPL-2/3 or LGPL,
  all stock Debian packages, never modified. `fonts-liberation` is the only font listed (SIL OFL / GPL font exception); fonts are data.
- Spike-only: `websockify` / `python3-websockify` 0.10.0 (LGPL-3 plus BSD-2 and GPL-2+ parts). The design keeps it out: the gateway relays.
- Brave-only extras: `libcurl4`, `libldap-2.5-0`, `libnghttp2-14`, `librtmp1`, `libsasl2-2`, `wget` (GPL-3): came through the apt-repo
  setup and Brave's deps. `wget` and `libcurl4` would not be in a hardened build.

Action for the build: run `licences.sh` in CI and fail on AGPL/SSPL or a non-Debian GPL source; list TigerVNC and the GNU userland as
"separate, unmodified" in `THIRD_PARTY_NOTICES.md`.

## Recommendation

- **Browser: Chromium (Debian).** It matches Brave on RAM (within ~5%), is 55 MB smaller compressed and 170 MB smaller on disk, comes with the
  Debian security-update channel, and needs no third-party apt repo or signing key in the build. Brave's only measured plus is slightly lower
  idle memory. Both need the same seccomp change. Whether Brave's fingerprint or Shields help with challenge rates was not measured.
  If challenge rates matter, test Brave in C1 behind the per-bot switch.
- **noVNC through the gateway: go.** First frame ~35 ms, input echo ~2.5 ms at the server, ~0.2 s to resume from pause.
  Neko is not needed.
- **Go with C1**, given: the custom seccomp profile (default plus `clone`/`clone3`/`unshare`/`setns`/`chroot`), a boot script that clears stale
  X and Chromium lock files, and a check of Docker Desktop's VM memory before raising `COMPUTERS_MAX_RUNNING` above 3.
- Open items for C1: time the real `docker exec roost-pipe vnc` relay and a pipelined Tight/ZRLE client, run the proxy-only network end
  to end, and measure a logged-in heavy site (feeds, video).
