"""The voice service: signed requests only, a WAV checked before the engine hears it, a tone's words from the fixed
table, and models that leave memory when idle."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from roost.desk.signing import signed_headers
from roost.voice.constants import TONES, VOICE_PART_CHARS_MAX
from roost.voice.wav import encode_wav, read_wav
from roost.voice_host.app import create_app
from roost.voice_host.engine import FakeEngine, ModelSlot

SECRET = "s" * 40


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def client(engine):
    with TestClient(create_app(SECRET, engine, unload_loop=False)) as c:
        yield c


def _post(client, path: str, body: bytes, secret: str = SECRET):
    return client.post(path, content=body, headers=signed_headers(secret, "POST", path, body))


def _speak(client, **fields):
    return _post(client, "/speak", json.dumps({"text": "Hello there.", "speaker": "aiden", "tone": "calm",
                                               **fields}).encode())


def test_unsigned_or_wrongly_signed_is_refused(client):
    assert client.get("/health").status_code == 401
    assert _post(client, "/speak", b"{}", secret="x" * 40).status_code == 401


def test_health_says_what_is_loaded(client):
    r = client.get("/health", headers=signed_headers(SECRET, "GET", "/health", b""))
    assert r.json() == {"ok": True, "loaded": [], "warm": False}
    _post(client, "/warm", b"")
    r = client.get("/health", headers=signed_headers(SECRET, "GET", "/health", b""))
    assert r.json() == {"ok": True, "loaded": ["hear", "speak"], "warm": True}


def test_a_recording_is_heard(client, engine):
    r = _post(client, "/transcribe", encode_wav(b"\x00\x00" * 16000, 16000))
    assert r.status_code == 200 and r.json() == {"text": "Add milk to my list"}
    assert engine.recordings == [1.0]


def test_a_bad_recording_never_reaches_the_engine(client, engine):
    r = _post(client, "/transcribe", b"OggS not a wav")
    assert r.status_code == 422 and engine.recordings == []


def test_speak_returns_a_wav_with_the_tones_own_words(client, engine):
    r = _speak(client)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert read_wav(r.content).rate == 24000
    assert engine.spoken == [("Hello there.", "aiden", TONES["calm"].instruct)]


@pytest.mark.parametrize("fields", [{"speaker": "nobody"}, {"tone": "Say 'fits'."}, {"text": ""},
                                    {"text": "a" * (VOICE_PART_CHARS_MAX + 1)}, {"extra": 1}])
def test_speak_refuses_anything_off_the_lists(client, engine, fields):
    assert _speak(client, **fields).status_code == 422
    assert engine.spoken == []


def test_a_slot_loads_once_and_lets_go_when_idle():
    now = [100.0]
    loads = []
    slot = ModelSlot("hear", lambda: loads.append(1) or "model", idle_s=60, clock=lambda: now[0])
    assert slot.get() == "model" and slot.get() == "model" and loads == [1]
    assert not slot.unload_idle(150.0) and slot.loaded
    assert slot.unload_idle(161.0) and not slot.loaded
    assert not slot.unload_idle(500.0)
    slot.get()
    assert loads == [1, 1]


def test_the_launchd_agent_runs_from_roost_and_never_from_desktop(tmp_path):
    from pathlib import Path

    from roost.voice_host.launchd import build_plist, main

    plist = build_plist(Path("/Users/me"))
    assert plist["ProgramArguments"] == ["/Users/me/Roost/voice-venv/bin/python", "-m", "roost.voice_host"]
    assert plist["EnvironmentVariables"]["HF_HOME"] == "/Users/me/Roost/voice-models"
    with pytest.raises(ValueError):
        build_plist(Path("/Users/me/Desktop"))
    with pytest.raises(ValueError):
        build_plist(Path("relative"))
    target = tmp_path / "agent.plist"
    assert main(["write", str(target)]) == 0 and target.exists()
    assert main(["oops"]) == 2


def test_the_service_entry_picks_its_engine():
    from roost.voice_host.__main__ import _engine

    assert isinstance(_engine("fake"), FakeEngine)


def test_warm_loads_both_models_ahead_of_a_call(client, engine):
    r = _post(client, "/warm", b"")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert engine.warmed == 1
    assert client.post("/warm").status_code == 401


# --- Call mode (§3): hearing and speaking at the same time, and the timing log -----------------------------------

import logging    # noqa: E402
import threading  # noqa: E402

from roost.voice_host.app import TIMING_LOGGER  # noqa: E402


class BlockingSpeakEngine(FakeEngine):
    """``speak`` waits until the test lets it go, like a long synthesis."""

    def __init__(self) -> None:
        super().__init__()
        self.speaking = threading.Event()
        self.go = threading.Event()

    def speak(self, text, speaker, instruct):
        self.speaking.set()
        assert self.go.wait(5)
        return super().speak(text, speaker, instruct)


def test_a_speak_in_flight_does_not_block_a_hear():
    engine = BlockingSpeakEngine()
    with TestClient(create_app(SECRET, engine, unload_loop=False)) as client:
        speaker = threading.Thread(target=_speak, args=(client,))
        speaker.start()
        assert engine.speaking.wait(5)
        heard = _post(client, "/transcribe", encode_wav(b"\x00\x00" * 1600, 16000))   # while speak is still held
        assert heard.status_code == 200 and engine.recordings == [0.1]
        health = client.get("/health", headers=signed_headers(SECRET, "GET", "/health", b""))
        assert health.status_code == 200
        engine.go.set()
        speaker.join(5)
    assert len(engine.spoken) == 1


def test_timings_are_logged_at_info_with_sizes_only(client, caplog):
    logging.getLogger().setLevel(logging.WARNING)
    with caplog.at_level(logging.INFO, logger=TIMING_LOGGER):
        _speak(client)
        _post(client, "/transcribe", encode_wav(b"\x00\x00" * 16000, 16000))
    lines = [r.getMessage() for r in caplog.records if r.name == TIMING_LOGGER and r.levelno == logging.INFO]
    assert any("spoke 12 chars" in line for line in lines) and any("heard 1.0 s" in line for line in lines)
    assert all("Hello there" not in line and "Add milk" not in line for line in lines)
    assert logging.getLogger(TIMING_LOGGER).level == logging.INFO
