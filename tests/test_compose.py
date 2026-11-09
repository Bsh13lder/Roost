"""Guards on ``docker-compose.yml`` — the always-on Roost gateway stack.

This machine also runs the OLD LazyClaw stack (containers ``lazyclaw``,
``lazyclaw-web``, ``lazyclaw-caddy``, ``lazyclaw-n8n``; its live DB under
``~/Desktop/.../lazyclaw/data``). Roost's compose file must never collide
with or reach into it, and must never expose anything beyond the Mac
itself (spec S2/S20, "Compose checks (step 0)"):

- its own project name (``roost``) and no fixed ``container_name`` at all;
- exactly one published port, ``127.0.0.1:18800:18800`` — loopback only;
- two bind mounts, ``${HOME}/Roost/data`` and ``${HOME}/Roost/mobile`` (read only) — nothing under
  ``~/Desktop``, ``~/.claude`` (Claude Code transcripts) or any
  ``lazyclaw`` path, and never the Docker socket.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMPOSE_FILE = _REPO_ROOT / "docker-compose.yml"

_DATA_BIND_SOURCE = "${HOME}/Roost/data"
_MOBILE_BIND = "${HOME}/Roost/mobile:/mobile:ro"
_ONLY_PORT = "127.0.0.1:18800:18800"
_OLD_STACK_NAMES = ("lazyclaw", "lazyclaw-web", "lazyclaw-caddy", "lazyclaw-n8n")
_BIND_PREFIXES = ("/", ".", "~", "$")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(_COMPOSE_FILE.read_text())


def _services(compose: dict) -> dict:
    return compose["services"]


def _volume_entries(compose: dict) -> list[tuple[str, str]]:
    """Every ``(source, target)`` volume pair across all services."""
    pairs = []
    for service in _services(compose).values():
        for entry in service.get("volumes", []):
            if isinstance(entry, dict):
                pairs.append((str(entry.get("source", "")), str(entry["target"])))
            else:
                source, target = str(entry).split(":")[:2]
                pairs.append((source, target))
    return pairs


def _bind_sources(compose: dict) -> list[str]:
    return [src for src, _ in _volume_entries(compose) if src.startswith(_BIND_PREFIXES)]


def test_project_name_is_roost(compose):
    assert compose["name"] == "roost"


def test_one_gateway_service_only(compose):
    assert list(_services(compose)) == ["gateway"]


def test_no_service_sets_a_container_name(compose):
    for name, service in _services(compose).items():
        assert "container_name" not in service, name


def test_no_service_reuses_an_old_stack_name(compose):
    for name in _services(compose):
        assert name not in _OLD_STACK_NAMES


def test_only_port_is_gateway_on_loopback(compose):
    ports = [str(p) for service in _services(compose).values() for p in service.get("ports", [])]
    assert ports == [_ONLY_PORT]


def test_no_service_uses_host_networking_or_privilege(compose):
    for name, service in _services(compose).items():
        assert service.get("network_mode") != "host", name
        assert not service.get("privileged", False), name


def test_bind_mounts_are_roost_data_and_the_read_only_mobile_dir(compose):
    assert _bind_sources(compose) == [_DATA_BIND_SOURCE, "${HOME}/Roost/mobile"]


def test_mobile_dir_is_mounted_read_only(compose):
    assert _MOBILE_BIND in _services(compose)["gateway"]["volumes"]


@pytest.mark.parametrize("forbidden", ["Desktop", ".claude", "lazyclaw", "docker.sock"])
def test_no_mount_reaches_forbidden_paths(compose, forbidden):
    for source, target in _volume_entries(compose):
        assert forbidden not in source, source
        if forbidden == "docker.sock":
            assert forbidden not in target, target


def test_claude_credentials_live_in_their_own_named_volume(compose):
    volumes = dict(_volume_entries(compose))
    named = {src: dst for src, dst in volumes.items() if not src.startswith(_BIND_PREFIXES)}
    assert named == {"roost_claude": "/home/roost/.claude"}
    assert compose["volumes"]["roost_claude"]["name"] == "roost_claude"


def test_data_mount_lands_on_the_containers_data_dir(compose):
    assert dict(_volume_entries(compose))[_DATA_BIND_SOURCE] == "/data"


def test_gateway_reaches_the_keeper_on_the_host(compose):
    gateway = _services(compose)["gateway"]
    env = gateway["environment"]
    assert env["ROOST_KEEPER_URL"] == "http://host.docker.internal:18801"
    assert env["ROOST_MODEL"] == "claude"
    assert env["ROOST_DESK"] == "keeper"
    assert env["ROOST_VOICE_URL"] == "http://host.docker.internal:18804"
    assert "host.docker.internal:host-gateway" in gateway["extra_hosts"]


def test_gateway_never_gets_an_api_key(compose):
    env = _services(compose)["gateway"]["environment"]
    assert "ANTHROPIC_API_KEY" not in env


def test_gateway_builds_its_own_image(compose):
    gateway = _services(compose)["gateway"]
    assert gateway["build"] == {"context": ".", "dockerfile": "docker/gateway/Dockerfile"}
    assert gateway["image"] == "roost-gateway:dev"


def test_gateway_restarts_and_is_bounded(compose):
    gateway = _services(compose)["gateway"]
    assert gateway["restart"] == "unless-stopped"
    assert gateway["mem_limit"] == "1g"


def test_gateway_healthcheck_probes_api_health(compose):
    test = " ".join(_services(compose)["gateway"]["healthcheck"]["test"])
    assert "http://127.0.0.1:18800/api/health" in test
