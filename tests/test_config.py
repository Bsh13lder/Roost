import pytest
from pathlib import Path

from roost.config import load_config


def test_defaults_bind_loopback_and_live_outside_desktop(tmp_path):
    cfg = load_config({"ROOST_DATA_DIR": str(tmp_path / "d"), "ROOST_DESKS_DIR": str(tmp_path / "k")})
    assert cfg.host == "127.0.0.1" and cfg.port == 18800
    assert cfg.keeper_url == "http://127.0.0.1:18801"
    from roost.constants import DEFAULT_DATA_DIR, DEFAULT_DESKS_DIR   # pure Path constants, never created by tests
    assert DEFAULT_DATA_DIR == Path.home() / "Roost" / "data"
    assert DEFAULT_DESKS_DIR == Path.home() / "Roost" / "desks"
    assert "Desktop" not in str(DEFAULT_DATA_DIR) and "Desktop" not in str(DEFAULT_DESKS_DIR)


def test_secrets_created_0600(tmp_path):
    cfg = load_config({"ROOST_DATA_DIR": str(tmp_path)})
    for name in ("server.secret", "keeper.secret"):
        p = tmp_path / name
        assert p.exists() and (p.stat().st_mode & 0o777) == 0o600
    assert load_config({"ROOST_DATA_DIR": str(tmp_path)}).server_secret == cfg.server_secret


def test_refuses_non_loopback_host(tmp_path):
    with pytest.raises(ValueError):
        load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_HOST": "0.0.0.0"})


def test_refuses_empty_secret_file(tmp_path):
    # Simulates the write-failure / concurrent-first-boot aftermath: a
    # secret file that exists but holds no content. Deriving keys from an
    # empty secret makes encryption void; this must never be read silently.
    secret_path = tmp_path / "server.secret"
    secret_path.touch()
    secret_path.chmod(0o600)
    with pytest.raises(ValueError, match="server.secret"):
        load_config({"ROOST_DATA_DIR": str(tmp_path)})


def test_refuses_loose_permission_secret_file(tmp_path):
    # A secret file with group/other bits set could have been read by
    # another local user; refuse to use it rather than trust it silently.
    secret_path = tmp_path / "server.secret"
    secret_path.write_text("x" * 64)
    secret_path.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        load_config({"ROOST_DATA_DIR": str(tmp_path)})


def test_refuses_too_short_env_secret(tmp_path):
    with pytest.raises(ValueError):
        load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_SERVER_SECRET": "short"})


# ---------------------------------------------------------------------------
# Container mode (docker/gateway/Dockerfile sets ROOST_IN_CONTAINER=1)
#
# Inside the gateway container the server has to bind 0.0.0.0, or Docker's
# port publishing can't reach it at all. That is safe ONLY because
# docker-compose.yml publishes the port on the host's 127.0.0.1 alone
# (tests/test_compose.py pins that) — so 0.0.0.0 is allowed with the
# container flag and refused everywhere else, exactly as before.
# ---------------------------------------------------------------------------


def test_allows_all_interfaces_host_inside_container(tmp_path):
    cfg = load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_HOST": "0.0.0.0", "ROOST_IN_CONTAINER": "1"})
    assert cfg.host == "0.0.0.0"
    assert cfg.in_container is True


def test_defaults_are_not_container_mode(tmp_path):
    cfg = load_config({"ROOST_DATA_DIR": str(tmp_path)})
    assert cfg.in_container is False


@pytest.mark.parametrize("flag", ["", "0", "true", "yes", " 1x"])
def test_refuses_all_interfaces_host_without_the_exact_container_flag(tmp_path, flag):
    with pytest.raises(ValueError, match="loopback"):
        load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_HOST": "0.0.0.0", "ROOST_IN_CONTAINER": flag})


@pytest.mark.parametrize("host", ["192.168.1.5", "10.0.0.1", "::", "example.com"])
def test_container_mode_still_refuses_any_other_non_loopback_host(tmp_path, host):
    with pytest.raises(ValueError):
        load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_HOST": host, "ROOST_IN_CONTAINER": "1"})


def test_container_mode_still_accepts_loopback(tmp_path):
    cfg = load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_HOST": "127.0.0.1", "ROOST_IN_CONTAINER": "1"})
    assert cfg.host == "127.0.0.1" and cfg.in_container is True


def test_model_script_is_read_from_the_env(tmp_path):
    base = {"ROOST_DATA_DIR": str(tmp_path / "d"), "ROOST_DESKS_DIR": str(tmp_path / "k")}
    assert load_config(base).model_script is None
    script = tmp_path / "script.json"
    assert load_config({**base, "ROOST_MODEL_SCRIPT": str(script)}).model_script == script


def test_the_scheduler_tick_override_is_for_the_scripted_gateway_only(tmp_path):
    base = {"ROOST_DATA_DIR": str(tmp_path), "ROOST_SCHEDULER_TICK_SECONDS": "2"}
    assert load_config({**base, "ROOST_MODEL": "scripted"}).scheduler_tick_seconds == 2.0
    assert load_config({**base, "ROOST_MODEL": "claude"}).scheduler_tick_seconds is None
    assert load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_MODEL": "scripted"}).scheduler_tick_seconds is None


def test_the_steer_debounce_override_is_for_the_scripted_gateway_only(tmp_path):
    base = {"ROOST_DATA_DIR": str(tmp_path), "ROOST_STEER_DEBOUNCE_SECONDS": "0.5"}
    assert load_config({**base, "ROOST_MODEL": "scripted"}).steer_debounce_seconds == 0.5
    assert load_config({**base, "ROOST_MODEL": "claude"}).steer_debounce_seconds is None
    assert load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_MODEL": "scripted"}).steer_debounce_seconds is None


@pytest.mark.parametrize("bad", ["-1", "soon", "11"])
def test_a_bad_steer_debounce_is_refused(tmp_path, bad):
    with pytest.raises(ValueError, match="ROOST_STEER_DEBOUNCE_SECONDS"):
        load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_MODEL": "scripted", "ROOST_STEER_DEBOUNCE_SECONDS": bad})


@pytest.mark.parametrize("bad", ["0", "-1", "soon", "3601"])
def test_a_bad_scheduler_tick_is_refused(tmp_path, bad):
    with pytest.raises(ValueError, match="ROOST_SCHEDULER_TICK_SECONDS"):
        load_config({"ROOST_DATA_DIR": str(tmp_path), "ROOST_MODEL": "scripted", "ROOST_SCHEDULER_TICK_SECONDS": bad})


def test_extra_origins_add_https_addresses_only(tmp_path):
    env = {"ROOST_DATA_DIR": str(tmp_path / "d"), "ROOST_DESKS_DIR": str(tmp_path / "k"),
           "ROOST_EXTRA_ORIGINS": " https://mac.tail1.ts.net , https://Other.example:8443"}
    config = load_config(env)
    assert config.allowed_origins[-2:] == ("https://mac.tail1.ts.net", "https://other.example:8443")
    assert "http://127.0.0.1:18800" in config.allowed_origins
    assert config.tailnet_origins == ("https://mac.tail1.ts.net", "https://other.example:8443")


@pytest.mark.parametrize("bad", ["http://mac.tail1.ts.net", "https://", "*", "https://a.b/path", "https://a b"])
def test_extra_origins_refuse_anything_but_a_plain_https_origin(tmp_path, bad):
    env = {"ROOST_DATA_DIR": str(tmp_path / "d"), "ROOST_DESKS_DIR": str(tmp_path / "k"), "ROOST_EXTRA_ORIGINS": bad}
    with pytest.raises(ValueError):
        load_config(env)


def test_mobile_dir_is_outside_the_repo_and_configurable(tmp_path):
    from roost.constants import CONTAINER_MOBILE_DIR, DEFAULT_MOBILE_DIR
    base = {"ROOST_DATA_DIR": str(tmp_path / "d")}
    assert DEFAULT_MOBILE_DIR == Path.home() / "Roost" / "mobile"
    assert load_config(base).mobile_dir == DEFAULT_MOBILE_DIR
    assert load_config({**base, "ROOST_IN_CONTAINER": "1"}).mobile_dir == CONTAINER_MOBILE_DIR == Path("/mobile")
    assert load_config({**base, "ROOST_MOBILE_DIR": str(tmp_path / "m")}).mobile_dir == tmp_path / "m"
    assert not (tmp_path / "m").exists()   # only read, never created
