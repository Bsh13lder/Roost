# roost-computer: a bot's own Linux computer (Brave Browser, Xvnc on a Unix socket, JWM, a small desktop:
# pcmanfm for files, LXTerminal and GPicView), and
# xdotool for roost-input, the computer-use loop's clicks and keys (C3), and roost-apt, which installs a Debian
# package the owner said Yes to (Install an app).
# Built with `make computer-image` (disk guard first). It exposes no port: the keeper reaches it with
# `docker exec -i ... roost-pipe cdp|vnc` and the Unix sockets in /run/screen.
# Bases: spike-proven set (docs/research/2026-10-20-computers-c0-spike.md). GPL parts (TigerVNC, the GNU
# userland) are separate, unmodified Debian packages that Roost never links.
# The browser is Brave Browser (MPL-2.0; owner decision 2026-10-22, because Google refuses sign-in on Debian's
# Chromium), the release channel from Brave's official apt repo (arm64 or amd64). Its signing key is fetched
# over HTTPS, must match BRAVE_KEY_SHA256 and is pinned with `signed-by=`; brave-policies.json (a managed
# policy) turns Rewards, Wallet, VPN, Leo, Tor, News, Talk, the stats ping and usage reports off.
FROM debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8

ENV DEBIAN_FRONTEND=noninteractive
ARG BRAVE_REPO=https://brave-browser-apt-release.s3.brave.com
ARG BRAVE_KEY_SHA256=c85e85aa3d1783ffaa649ee8dbbc22af7f87192d304602d37e3018226b394788
ARG BRAVE_KEYRING=/usr/share/keyrings/brave-browser-archive-keyring.gpg
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates \
    && python3 -c "import sys, urllib.request as u; open(sys.argv[2], 'wb').write(u.urlopen(sys.argv[1], timeout=60).read())" \
         "$BRAVE_REPO/brave-browser-archive-keyring.gpg" "$BRAVE_KEYRING" \
    && echo "$BRAVE_KEY_SHA256  $BRAVE_KEYRING" | sha256sum -c - \
    && echo "deb [signed-by=$BRAVE_KEYRING] $BRAVE_REPO/ stable main" > /etc/apt/sources.list.d/brave-browser-release.list \
    && apt-get update && apt-get install -y --no-install-recommends \
      tigervnc-standalone-server jwm xterm tini brave-browser fonts-liberation procps \
      pcmanfm lxterminal gpicview papirus-icon-theme fonts-dejavu-core tzdata xdotool \
    && rm -rf /var/lib/apt/lists/*
COPY brave-policies.json /etc/brave/policies/managed/roost.json

RUN groupadd -g 10002 comp && useradd -m -u 10002 -g 10002 comp \
    && mkdir -p /run/screen /home/comp/profile \
    && chown 10002:10002 /run/screen /home/comp/profile && chmod 0700 /run/screen

COPY --chmod=0755 start.sh /start.sh
COPY --chmod=0755 roost_computerd.py /usr/local/bin/roost-computerd
COPY --chmod=0755 roost_pipe.py /usr/local/bin/roost-pipe
# C3: a bot's clicks and keys, only inside Chromium's window (xdotool, text on stdin only).
COPY --chmod=0755 roost_input.py /usr/local/bin/roost-input
# Install an app (docs/plans/2026-10-22-roost-install-app.md): roost-apt, run as root only by the keeper's signed
# apps route after the owner's Yes. Its own apt sources are Debian bookworm main only (never the Brave repo), with
# an empty sources folder and its own lists folder.
COPY --chmod=0755 roost_apt.py /usr/local/bin/roost-apt
COPY config/roost-apt-debian.list /etc/roost-apt/debian.list
RUN mkdir -p /etc/roost-apt/sources.list.d /var/lib/roost-apt/lists/partial
COPY system.jwmrc /etc/jwm/system.jwmrc
COPY --chmod=0755 roost-browser /usr/local/bin/roost-browser
COPY make_wallpaper.py /usr/local/share/make_wallpaper.py
RUN mkdir -p /usr/share/roost && python3 /usr/local/share/make_wallpaper.py /usr/share/roost/wallpaper.png

# The apps' settings. The home folder is a fresh tmpfs at every start, so start.sh copies
# this skeleton into it before the desktop starts.
COPY config/libfm.conf /usr/share/roost/home/.config/libfm/libfm.conf
COPY config/lxterminal.conf /usr/share/roost/home/.config/lxterminal/lxterminal.conf
COPY config/gtk-settings.ini /usr/share/roost/home/.config/gtk-3.0/settings.ini
COPY config/gtkrc-2.0 /usr/share/roost/home/.gtkrc-2.0
RUN chmod -R a+rX /usr/share/roost
COPY --chmod=0755 licences.sh /usr/local/share/licences.sh

# Last RUN: fails the build on an AGPL or SSPL package and prints the GPL/LGPL list.
RUN sh /usr/local/share/licences.sh

USER 10002
ENTRYPOINT ["/usr/bin/tini", "--", "/start.sh"]
