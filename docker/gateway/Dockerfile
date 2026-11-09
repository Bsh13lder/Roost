# Roost gateway image (`roost-gateway:dev`) — the web API plus the built
# web app, served on 18800. Built and run by docker-compose.yml (`make up`
# / `make deploy`; never `docker build` by hand — those targets run the
# disk guard first).
#
# Deliberately small: no VNC, no browser automation, no global npm
# Claude Code. Real browsers and workspace containers belong to the desk
# keeper on the Mac itself (a launchd agent), reached over
# host.docker.internal:18801. The only `claude` binary here is the one the
# Claude Agent SDK already bundles, linked onto PATH for `make claude-login`.

# ---------------------------------------------------------------------------
# Stage 1: build the web app (web/dist)
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS web

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Fixed uid 10010, distinct from the workspace image's 10001 (`desk`).
# ~/.claude is created here, owned by roost, so the `roost_claude` named
# volume mounted over it starts out writable by this user.
RUN useradd --uid 10010 --create-home --home-dir /home/roost roost \
    && mkdir -p /home/roost/.claude /data \
    && chown roost:roost /home/roost/.claude /data

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first (cached across code-only rebuilds), then the package
# itself — installed editable, so `roost` imports from /app/roost and
# roost/gateway/routes/static.py finds the web app at /app/web/dist.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY roost/ /app/roost/
RUN uv sync --frozen --no-dev \
    && test -x /app/.venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude \
    && ln -s /app/.venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude /usr/local/bin/claude

COPY --from=web /web/dist /app/web/dist

ENV PATH="/app/.venv/bin:${PATH}" \
    HOME=/home/roost \
    ROOST_IN_CONTAINER=1 \
    ROOST_HOST=0.0.0.0 \
    ROOST_DATA_DIR=/data \
    ROOST_DESKS_DIR=/data/desks-unused \
    CLAUDE_CONFIG_DIR=/home/roost/.claude

USER roost

EXPOSE 18800

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "roost"]
