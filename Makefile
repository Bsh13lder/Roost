.PHONY: sync test test-desk test-docker keeper server dev smoke e2e workspace-image computer-image egress-image web web-test
.PHONY: disk-guard desk-keeper-install desk-keeper-uninstall desk-keeper-status
.PHONY: up down logs rebuild claude-login claude-status deploy mobile-publish
.PHONY: voice-install voice-update voice-uninstall voice-status

sync:
	uv sync

test:
	uv run pytest --cov=roost --cov-report=term-missing

test-desk:
	uv run pytest -m desk

test-docker:
	uv run pytest -m docker

# The keeper: a separate host process from the gateway, owning the real
# Brave windows, Docker workspace containers and the egress proxy
# (127.0.0.1:18801, proxy on 18803 — see roost/keeper/__main__.py).
keeper:
	uv run python -m roost.keeper

# The gateway: the web API + the built SPA (once `make web` has run),
# on 127.0.0.1:18800 (see roost/__main__.py).
server:
	uv run python -m roost

# One-command dev run (Task 13): keeper + server together in one
# terminal. `trap ... EXIT INT TERM` plus `kill 0` means Ctrl-C (or this
# make target exiting for any other reason) kills BOTH background jobs
# instead of leaving the keeper (and whatever Brave/Docker it started)
# running headless after the terminal closes. The two `&`-ed commands
# and the `wait` all run in one shell (joined by the `\` continuations)
# so `trap` and `kill 0` apply to that shell's own process group.
dev:
	@trap 'kill 0' EXIT INT TERM; \
	uv run python -m roost.keeper & \
	uv run python -m roost & \
	wait

# Builds roost-workspace:dev from docker/workspace/Dockerfile. Refuses to
# build on a nearly-full disk (`docker build`'s layer cache/export can eat
# several GB) instead of failing mid-build with a less legible error.
workspace-image:
	@free_gb=$$(df -g /System/Volumes/Data | awk 'NR==2{print $$4}'); \
	if [ "$$free_gb" -lt 8 ]; then \
		echo "workspace-image: only $${free_gb}G free on /System/Volumes/Data (need >= 8G) — refusing to build" >&2; \
		exit 1; \
	fi
	docker build -t roost-workspace:dev docker/workspace

# A bot's Linux computer (Brave Browser, Xvnc on a Unix socket, JWM, xterm). Same disk guard as workspace-image.
computer-image:
	@free_gb=$$(df -g /System/Volumes/Data | awk 'NR==2{print $$4}'); \
	if [ "$$free_gb" -lt 8 ]; then \
		echo "computer-image: only $${free_gb}G free on /System/Volumes/Data (need >= 8G) — refusing to build" >&2; \
		exit 1; \
	fi
	docker build -t roost-computer:dev docker/computer

# The one outbound proxy, in the VM, that every bot's internal network reaches. Same disk guard.
egress-image:
	@free_gb=$$(df -g /System/Volumes/Data | awk 'NR==2{print $$4}'); \
	if [ "$$free_gb" -lt 8 ]; then \
		echo "egress-image: only $${free_gb}G free on /System/Volumes/Data (need >= 8G) — refusing to build" >&2; \
		exit 1; \
	fi
	docker build -t roost-egress:dev -f docker/egress/Dockerfile .

# Builds the web SPA (roost/gateway/routes/static.py serves web/dist
# once this has run). Disk guard mirrors the one every npm-install step
# in this project uses: refuse rather than risk filling the disk.
web:
	@free_gb=$$(df -g /System/Volumes/Data | awk 'NR==2{print $$4}'); \
	if [ "$$free_gb" -lt 8 ]; then \
		echo "BLOCKED: only $${free_gb}GB free on /System/Volumes/Data (need >= 8GB) — not running npm ci" >&2; \
		exit 1; \
	fi
	cd web && npm ci && npm run build

web-test:
	cd web && npm test

# Real-desk smoke test (Task 13): starts a real keeper + gateway itself
# on the real ports (aborting if they're busy), drives one real bot
# through register -> create -> desk/browser/start -> a real turn loop
# -> workspace exec -> delete, against a real Brave window and a real
# Docker container. Prints a PASS/FAIL table; exits non-zero on any FAIL.
smoke:
	uv run python scripts/smoke.py

# Playwright E2E (Ruling 4, 2026-10-13): `playwright.config.ts`'s
# `webServer` starts the gateway itself (ROOST_MODEL=scripted,
# ROOST_DESK=fake, a fresh temp data dir), so this is one command. Disk
# guard mirrors `web`'s: installing a browser binary can need real disk
# space even when it's already cached.
# M2 D7: the live gateway may already hold 18800, so this picks 5173 (an
# allowed origin, roost/config.py) for the throwaway, scripted gateway
# whenever 18800 answers /api/health.
e2e:
	@free_gb=$$(df -g /System/Volumes/Data | awk 'NR==2{print $$4}'); \
	if [ "$$free_gb" -lt 8 ]; then \
		echo "BLOCKED: only $${free_gb}GB free on /System/Volumes/Data (need >= 8GB) — not running playwright install" >&2; \
		exit 1; \
	fi
	@port=18800; if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi; \
	echo "E2E gateway on 127.0.0.1:$$port"; \
	cd web && npx playwright install chromium && npm run build && ROOST_E2E_PORT=$$port npx playwright test

# ---------------------------------------------------------------------------
# Run it all the time: the gateway in Docker (docker-compose.yml, project
# `roost`, 127.0.0.1:18800) + the desk keeper as a launchd agent on the Mac
# (app.roost.desk-keeper, 127.0.0.1:18801). Nothing here names a container
# or touches any other compose project on this Mac.
# ---------------------------------------------------------------------------

ROOST_HOME := $(HOME)/Roost
KEEPER_VENV := $(ROOST_HOME)/venv
KEEPER_LABEL := app.roost.desk-keeper
KEEPER_PLIST := $(HOME)/Library/LaunchAgents/$(KEEPER_LABEL).plist
KEEPER_DOMAIN = gui/$$(id -u)

# Same >= 8 GB rule as workspace-image/web, for every `docker compose build`.
disk-guard:
	@free_gb=$$(df -g /System/Volumes/Data | awk 'NR==2{print $$4}'); \
	if [ "$$free_gb" -lt 8 ]; then \
		echo "BLOCKED: only $${free_gb}GB free on /System/Volumes/Data (need >= 8GB) — not building" >&2; \
		exit 1; \
	fi

# Installs Roost into ~/Roost/venv (from a wheel, with uv.lock's exact
# versions — never from the repo checkout: macOS TCC blocks launchd jobs
# from ~/Desktop) and (re)loads the keeper's launchd agent. The wheel is
# built BEFORE the running keeper is stopped, so a failed build leaves it
# running; the keeper is stopped BEFORE its venv is replaced underneath it.
desk-keeper-install:
	mkdir -p $(ROOST_HOME)/logs $(ROOST_HOME)/data
	rm -f dist/roost-*.whl dist/keeper-requirements.txt
	uv build --wheel
	uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt --quiet -o dist/keeper-requirements.txt
	launchctl bootout $(KEEPER_DOMAIN)/$(KEEPER_LABEL) 2>/dev/null || true
	uv venv --clear $(KEEPER_VENV) --python 3.12
	uv pip install --python $(KEEPER_VENV)/bin/python -r dist/keeper-requirements.txt dist/roost-*.whl --reinstall
	$(KEEPER_VENV)/bin/python -m roost.keeper.launchd write $(KEEPER_PLIST)
	launchctl bootstrap $(KEEPER_DOMAIN) $(KEEPER_PLIST)
	@for i in $$(seq 1 20); do \
		if lsof -nP -iTCP:18801 -sTCP:LISTEN >/dev/null 2>&1; then \
			echo "desk keeper running on 127.0.0.1:18801 — logs: $(ROOST_HOME)/logs/keeper.log"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "desk keeper did not start listening on 127.0.0.1:18801 within 20s — see $(ROOST_HOME)/logs/keeper.log" >&2; \
	exit 1

# Stops the keeper and removes its launchd agent. Leaves ~/Roost/venv,
# ~/Roost/data and ~/Roost/desks alone.
desk-keeper-uninstall:
	launchctl bootout $(KEEPER_DOMAIN)/$(KEEPER_LABEL) 2>/dev/null || true
	rm -f $(KEEPER_PLIST)
	@echo "desk keeper stopped and unloaded ($(ROOST_HOME) left in place)"

desk-keeper-status:
	@launchctl print $(KEEPER_DOMAIN)/$(KEEPER_LABEL) 2>/dev/null \
		| grep -E '^[[:space:]]*(state|pid|runs|last exit code) =' \
		|| echo "desk keeper: not loaded (run make desk-keeper-install)"
	@lsof -nP -iTCP:18801 -sTCP:LISTEN || echo "desk keeper: nothing listening on 127.0.0.1:18801"

# ---------------------------------------------------------------------------
# Voice (docs/plans/2026-10-30-roost-voice.md): the voice service as a launchd
# agent on the Mac (app.roost.voice, 127.0.0.1:18804) in its own venv —
# Roost's wheel without its deps, plus mlx-audio (MIT) for the two pinned
# models, fetched once into ~/Roost/voice-models. MLX needs the Mac's GPU,
# so this never runs in Docker.
# ---------------------------------------------------------------------------

VOICE_VENV := $(ROOST_HOME)/voice-venv
VOICE_LABEL := app.roost.voice
VOICE_PLIST := $(HOME)/Library/LaunchAgents/$(VOICE_LABEL).plist
VOICE_PACKAGES := "mlx-audio==0.6.3" "fastapi>=0.115" "uvicorn>=0.30" "pydantic>=2.8"

# After a change under roost/voice*: Roost's own code into the voice venv
# (the models and packages stay), then a restart.
voice-update:
	rm -f dist/roost-*.whl
	uv build --wheel
	uv pip install --python $(VOICE_VENV)/bin/python --no-deps --reinstall dist/roost-*.whl
	launchctl kickstart -k $(KEEPER_DOMAIN)/$(VOICE_LABEL)

voice-install: disk-guard
	mkdir -p $(ROOST_HOME)/logs $(ROOST_HOME)/data $(ROOST_HOME)/voice-models
	rm -f dist/roost-*.whl
	uv build --wheel
	launchctl bootout $(KEEPER_DOMAIN)/$(VOICE_LABEL) 2>/dev/null || true
	uv venv --clear $(VOICE_VENV) --python 3.12
	uv pip install --python $(VOICE_VENV)/bin/python --no-deps --reinstall dist/roost-*.whl
	uv pip install --python $(VOICE_VENV)/bin/python $(VOICE_PACKAGES)
	$(VOICE_VENV)/bin/python -c "import roost.voice_host.app, roost.voice_host.mlx_engine"
	$(VOICE_VENV)/bin/python -m roost.voice_host.launchd write $(VOICE_PLIST)
	launchctl bootstrap $(KEEPER_DOMAIN) $(VOICE_PLIST)
	@for i in $$(seq 1 30); do \
		if lsof -nP -iTCP:18804 -sTCP:LISTEN >/dev/null 2>&1; then \
			echo "voice running on 127.0.0.1:18804 — logs: $(ROOST_HOME)/logs/voice.log"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "voice did not start listening on 127.0.0.1:18804 within 30s — see $(ROOST_HOME)/logs/voice.log" >&2; \
	exit 1

voice-uninstall:
	launchctl bootout $(KEEPER_DOMAIN)/$(VOICE_LABEL) 2>/dev/null || true
	rm -f $(VOICE_PLIST)
	@echo "voice stopped and unloaded ($(VOICE_VENV) and ~/Roost/voice-models left in place)"

voice-status:
	@launchctl print $(KEEPER_DOMAIN)/$(VOICE_LABEL) 2>/dev/null \
		| grep -E '^[[:space:]]*(state|pid|runs|last exit code) =' \
		|| echo "voice: not loaded (run make voice-install)"
	@lsof -nP -iTCP:18804 -sTCP:LISTEN || echo "voice: nothing listening on 127.0.0.1:18804"

up: disk-guard
	mkdir -p $(ROOST_HOME)/data
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200 gateway

rebuild: disk-guard
	docker compose build gateway
	docker compose up -d gateway

# One-time login for the Claude Agent SDK's bundled `claude` CLI inside the
# gateway container; the credentials persist in the roost_claude volume.
# API-key env vars are blanked so the CLI uses your subscription login.
claude-login:
	docker compose exec -it -e ANTHROPIC_API_KEY= -e ANTHROPIC_AUTH_TOKEN= gateway claude auth login

# Prints "logged in until <date>", "expired" or "not logged in" — by the
# token's expiry, not just whether a credentials file exists.
claude-status:
	@docker compose exec -T gateway python -m roost.llm.claude_status

# Everything, first time or after an update: the workspace image (only if
# missing), the desk keeper's launchd agent, then the gateway container.
deploy:
	@docker image inspect roost-workspace:dev >/dev/null 2>&1 || $(MAKE) workspace-image
	@docker image inspect roost-computer:dev >/dev/null 2>&1 || $(MAKE) computer-image
	@docker image inspect roost-egress:dev >/dev/null 2>&1 || $(MAKE) egress-image
	$(MAKE) desk-keeper-install
	$(MAKE) up

# Publish the phone app for its in-app update: builds the APK (debug unless
# mobile/android/key.properties exists), copies it to ~/Roost/mobile and writes
# latest.json. Bump `version:` in mobile/pubspec.yaml first. NOTES="one line".
mobile-publish:
	scripts/publish_mobile.sh "$(NOTES)"
