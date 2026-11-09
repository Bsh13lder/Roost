"""Static guards on the gateway image — ``docker/gateway/Dockerfile`` and
the repo-root ``.dockerignore`` it builds with.

The real build is verified by running it (``make up``); these catch the
regressions that a build would happily succeed with: secrets or the dev
venv baked into an image layer, running as root, the old app's VNC /
Playwright / global npm Claude Code coming back, or the built web app
landing somewhere ``roost/gateway/routes/static.py`` doesn't look.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from roost.gateway.routes import static as static_module

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = _REPO_ROOT / "docker" / "gateway" / "Dockerfile"
_DOCKERIGNORE = _REPO_ROOT / ".dockerignore"

_APP_DIR = "/app"


def _dockerfile() -> str:
    return _DOCKERFILE.read_text()


def _instructions(keyword: str) -> list[str]:
    """Every instruction line starting with ``keyword`` (comments skipped)."""
    lines = [line.strip() for line in _dockerfile().splitlines()]
    return [line for line in lines if line.upper().startswith(keyword.upper() + " ")]


def test_runtime_stage_is_python_312_slim_bookworm():
    froms = _instructions("FROM")
    assert froms[0].startswith("FROM node:22-bookworm-slim")
    assert froms[-1].startswith("FROM python:3.12-slim-bookworm")


def test_runs_as_the_non_root_roost_user():
    users = _instructions("USER")
    assert users and users[-1] in ("USER roost", "USER 10010")
    assert re.search(r"useradd[^\n]*(-u|--uid) 10010[^\n]*roost", _dockerfile())


def test_container_env_enables_container_mode_and_data_dir():
    text = _dockerfile()
    for setting in (
        "ROOST_IN_CONTAINER=1",
        "ROOST_HOST=0.0.0.0",
        "ROOST_DATA_DIR=/data",
        "ROOST_DESKS_DIR=/data/desks-unused",
        "CLAUDE_CONFIG_DIR=/home/roost/.claude",
    ):
        assert setting in text, setting


def test_entrypoint_is_tini_and_cmd_runs_the_gateway():
    assert any("tini" in line for line in _instructions("ENTRYPOINT"))
    assert _instructions("CMD")[-1] == 'CMD ["python", "-m", "roost"]'


@pytest.mark.parametrize("forbidden", ["playwright", "vnc", "npm install -g", "@anthropic-ai/claude-code"])
def test_none_of_the_old_apps_extras(forbidden):
    instructions = "\n".join(line for line in _dockerfile().splitlines() if not line.lstrip().startswith("#"))
    assert forbidden.lower() not in instructions.lower()


def test_built_web_app_lands_where_static_py_looks():
    # static.py resolves web/dist three levels up from its own file, so
    # with the package copied to /app/roost the SPA must be at /app/web/dist.
    static_file = Path(_APP_DIR) / "roost" / "gateway" / "routes" / "static.py"
    expected = static_file.parents[3] / "web" / "dist"
    assert static_module._web_dist_dir().relative_to(_REPO_ROOT) == Path("web/dist")
    copies = _instructions("COPY")
    assert any(line.endswith(f" {expected}") or line.endswith(f" {expected}/") for line in copies), copies
    assert any(line.endswith(f" {_APP_DIR}/roost") or line.endswith(f" {_APP_DIR}/roost/") for line in copies)


def test_bundled_claude_cli_is_on_path():
    assert re.search(r"claude_agent_sdk/_bundled/claude[^\n]*/usr/local/bin/claude", _dockerfile())


@pytest.mark.parametrize(
    "entry",
    [".venv", "web/node_modules", "web/dist", "web/test-results", "tests", "docs", ".git", "*.secret", ".superpowers"],
)
def test_dockerignore_keeps_secrets_and_dev_state_out_of_the_build(entry):
    entries = {line.strip() for line in _DOCKERIGNORE.read_text().splitlines() if line.strip() and not line.startswith("#")}
    assert entry in entries
