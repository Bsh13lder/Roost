# Per-bot workspace container image (``roost-workspace:dev``) — a locked
# down Debian sandbox where a bot's own shell commands run. The keeper
# (``roost/keeper/workspaces.py``) runs this image with ``--network none``,
# ``--read-only``, a dropped capability set and ``--user 10001:10001``, so
# everything baked in here is picked for a minimal, auditable shell
# environment, never for convenience extras.
#
# Built with ``make workspace-image`` (never ``docker build`` by hand —
# that target runs the disk guard first).
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        coreutils \
        procps \
        findutils \
        grep \
        sed \
        gawk \
        curl \
        ca-certificates \
        python3 \
        jq \
        less \
    && rm -rf /var/lib/apt/lists/*

# Fixed uid/gid 10001 matches the ``--user 10001:10001`` the keeper always
# launches this image with (roost/keeper/workspaces.py) — the image's own
# user must exist for `-m`'s home directory and shell to mean anything,
# even though the container never actually runs as root at runtime.
RUN useradd -u 10001 -m -s /bin/bash desk

WORKDIR /workspace

USER 10001

CMD ["sleep", "infinity"]
