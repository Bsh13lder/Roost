"""Voice tuning D1 on the wire: the voice service's ``POST /hear`` hands the envelope's hint to the engine (and logs
its size, never its words), and the gateway's ``VoiceClient`` sends a hint in the signed envelope, falling back to
the plain ``/transcribe`` for a service too old to have ``/hear`` (until the owner's ``make voice-update``)."""

from __future__ import annotations

import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.desk.signing import NonceCache, signed_headers, verify
from roost.voice.client import FakeVoice, VoiceClient, VoiceFailed
from roost.voice.constants import VOICE_HEAR_FALLBACK_S
from roost.voice.envelope import HearHint, pack_hear, unpack_hear
from roost.voice.wav import encode_wav
from roost.voice_host.app import TIMING_LOGGER, create_app
from roost.voice_host.engine import FakeEngine

SECRET = "s" * 40
WAV = encode_wav(b"\x00\x00" * 16000, 16000)
HINT = HearHint(terms=("Maka Eremadze", "WhatsApp"), language="Spanish")


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def client(engine):
    with TestClient(create_app(SECRET, engine, unload_loop=False)) as c:
        yield c


def _post(client, path: str, body: bytes):
    return client.post(path, content=body, headers=signed_headers(SECRET, "POST", path, body))


# --- the service -----------------------------------------------------------------------------------------------------


def test_hear_passes_the_hint_to_the_engine_and_transcribe_passes_none(client, engine):
    r = _post(client, "/hear", pack_hear(HINT, WAV))
    assert r.status_code == 200 and r.json() == {"text": "Add milk to my list"}
    assert engine.hints == [HINT] and engine.recordings == [1.0]
    _post(client, "/transcribe", WAV)
    assert engine.hints[-1] == HearHint()


def test_hear_refuses_a_bad_envelope_or_a_bad_wav_before_the_engine(client, engine):
    assert _post(client, "/hear", b"\x00\x00\x00\x02{}OggS").status_code == 422
    assert _post(client, "/hear", pack_hear(HINT, b"OggS not a wav")).status_code == 422
    dirty = b'{"terms":["<x>"]}'
    assert _post(client, "/hear", len(dirty).to_bytes(4, "big") + dirty + WAV).status_code == 422
    assert engine.hints == []
    assert client.post("/hear", content=pack_hear(HINT, WAV)).status_code == 401


def test_the_timing_log_keeps_the_hints_size_never_its_words(client, caplog):
    with caplog.at_level(logging.INFO, logger=TIMING_LOGGER):
        _post(client, "/hear", pack_hear(HearHint(terms=("Maka Eremadze",), partial=True), WAV))
    line = next(r.getMessage() for r in caplog.records if "heard" in r.getMessage())
    assert "1 terms" in line and "partial" in line and "Maka" not in line


# --- the gateway's client -------------------------------------------------------------------------------------------


def _client(handler, clock=lambda: 0.0) -> VoiceClient:
    return VoiceClient(load_config(), transport=httpx.MockTransport(handler), clock=clock)


async def test_a_hint_travels_in_the_signed_hear_envelope():
    config = load_config()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        ok = verify(config.voice_secret, request.method, request.url.path, request.content, request.headers,
                    now=int(request.headers["X-Roost-Ts"]), seen=NonceCache())
        seen.append((request.url.path, ok, unpack_hear(request.content) if request.url.path == "/hear" else None))
        return httpx.Response(200, json={"text": " hola "})

    client = _client(handler)
    assert await client.transcribe(WAV, HINT) == "hola"
    assert await client.transcribe(WAV) == "hola"                 # no hint: the plain route
    assert seen == [("/hear", True, (HINT, WAV)), ("/transcribe", True, None)]


async def test_an_old_service_without_hear_gets_the_plain_route_for_a_while():
    paths = []
    now = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/hear":
            return httpx.Response(404)
        return httpx.Response(200, json={"text": "hi"})

    client = _client(handler, clock=lambda: now[0])
    assert await client.transcribe(WAV, HINT) == "hi"
    assert await client.transcribe(WAV, HINT) == "hi"
    assert paths == ["/hear", "/transcribe", "/transcribe"]          # the 404 is remembered
    now[0] = VOICE_HEAR_FALLBACK_S + 1
    await client.transcribe(WAV, HINT)
    assert paths[-2:] == ["/hear", "/transcribe"]                      # tried again later (make voice-update)


async def test_any_other_failure_of_hear_is_still_a_failure():
    with pytest.raises(VoiceFailed):
        await _client(lambda r: httpx.Response(500)).transcribe(WAV, HINT)


async def test_the_fake_voice_records_the_hint():
    fake = FakeVoice()
    await fake.transcribe(WAV, HINT)
    await fake.transcribe(WAV)
    assert fake.engine.hints == [HINT, HearHint()]
