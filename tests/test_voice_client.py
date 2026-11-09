"""The gateway's voice client: every request signed with voice.secret, failures named, a reply that is not a WAV
refused, the health check remembered; and which messages can be read aloud."""

from __future__ import annotations

import json

import httpx
import pytest

from roost.config import load_config
from roost.desk.signing import NonceCache, verify
from roost.routines.models import ReportBody
from roost.talk.store import Message
from roost.voice.client import FakeVoice, VoiceClient, VoiceFailed, VoiceUnavailable, make_voice
from roost.voice.spoken import SpeechCache, message_parts
from roost.voice.wav import WavError, encode_wav

WAV = encode_wav(b"\x00\x00" * 160, 16000)


def _client(handler, clock=lambda: 0.0) -> VoiceClient:
    return VoiceClient(load_config(), transport=httpx.MockTransport(handler), clock=clock)


async def test_requests_are_signed_with_the_voice_secret():
    config = load_config()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        ok = verify(config.voice_secret, request.method, request.url.path, request.content, request.headers,
                    now=int(request.headers["X-Roost-Ts"]), seen=NonceCache())
        seen.append((request.url.path, ok, json.loads(request.content) if request.url.path == "/speak" else None))
        if request.url.path == "/transcribe":
            return httpx.Response(200, json={"text": " hello "})
        return httpx.Response(200, content=WAV)

    client = _client(handler)
    assert await client.transcribe(WAV) == "hello"
    assert await client.speak("Hi.", "ryan", "calm") == WAV
    assert seen == [("/transcribe", True, None), ("/speak", True, {"text": "Hi.", "speaker": "ryan", "tone": "calm"})]
    assert config.voice_secret != config.keeper_secret


async def test_failures_are_named():
    def down(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(VoiceUnavailable):
        await _client(down).transcribe(WAV)
    with pytest.raises(VoiceFailed):
        await _client(lambda r: httpx.Response(500)).speak("Hi.", "ryan", "calm")
    with pytest.raises(WavError):
        await _client(lambda r: httpx.Response(200, content=b"<html>")).speak("Hi.", "ryan", "calm")


async def test_health_is_remembered_for_a_while():
    calls = []
    now = [0.0]

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, clock=lambda: now[0])
    assert await client.available() and await client.available()
    assert len(calls) == 1
    now[0] = 31.0
    assert await client.available() and len(calls) == 2
    assert not await _client(lambda r: httpx.Response(401)).available()


def test_make_voice_follows_the_config(monkeypatch):
    assert isinstance(make_voice(load_config()), FakeVoice)
    monkeypatch.setenv("ROOST_VOICE", "service")
    assert isinstance(make_voice(load_config()), VoiceClient)
    monkeypatch.setenv("ROOST_VOICE", "loud")
    with pytest.raises(ValueError):
        load_config()


def _message(role="bot", kind="text", body="Hello there.") -> Message:
    return Message(id="m", user_id="u", thread_id="t", role=role, body=body, tainted=False, seq=1,
                   created_at="2026-10-30T10:00:00+00:00", kind=kind)


def test_which_messages_are_read_aloud():
    assert message_parts(_message()) == ["Hello there."]
    assert message_parts(_message(role="user")) == []
    assert message_parts(_message(kind="approval", body="{}")) == []
    report = ReportBody(source="routine", headline="Morning news", text="Three things happened.")
    assert message_parts(_message(kind="report", body=report.model_dump_json())) == ["Three things happened."]
    bare = ReportBody(source="routine", headline="Morning news", text="")
    assert message_parts(_message(kind="report", body=bare.model_dump_json())) == ["Morning news"]
    assert message_parts(_message(kind="report", body="not json")) == []


def test_the_cache_keeps_the_newest_parts():
    cache = SpeechCache(size=2)
    cache.put(("a", 0, "s", "t"), b"1")
    cache.put(("b", 0, "s", "t"), b"2")
    assert cache.get(("a", 0, "s", "t")) == b"1"
    cache.put(("c", 0, "s", "t"), b"3")
    assert cache.get(("b", 0, "s", "t")) is None and cache.get(("a", 0, "s", "t")) == b"1"


async def test_warm_is_a_signed_post():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"ok": True})

    await _client(handler).warm()
    assert seen == [("POST", "/warm")]


# --- Keep-alive and the hear timeout (§3) ---------------------------------------------------------------------------

from roost.voice.constants import VOICE_HEAR_TIMEOUT_S, VOICE_SERVICE_TIMEOUT_S   # noqa: E402


class CountingTransport(httpx.MockTransport):
    def __init__(self, handler) -> None:
        super().__init__(handler)
        self.requests = 0
        self.closes = 0

    async def handle_async_request(self, request):
        self.requests += 1
        return await super().handle_async_request(request)

    async def aclose(self) -> None:
        self.closes += 1
        await super().aclose()


async def test_one_connection_is_kept_across_calls_and_closed_once():
    transport = CountingTransport(lambda r: httpx.Response(200, json={"ok": True, "loaded": [], "warm": False}))
    client = VoiceClient(load_config(), transport=transport)
    await client.warm()
    await client.warm()
    assert await client.available()
    assert (transport.requests, transport.closes) == (3, 0)
    await client.aclose()
    assert transport.closes == 1
    await client.aclose()   # twice is fine
    assert transport.closes == 1


async def test_a_transcript_waits_less_once_the_service_is_warm():
    seen = []
    warm = [False]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "loaded": ["hear", "speak"] if warm[0] else [], "warm": warm[0]})
        seen.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"text": "hi"})

    now = [0.0]
    client = _client(handler, clock=lambda: now[0])
    await client.transcribe(WAV)
    assert await client.available()
    await client.transcribe(WAV)
    warm[0] = True
    now[0] = 100.0
    assert await client.available()
    await client.transcribe(WAV)
    assert seen == [VOICE_SERVICE_TIMEOUT_S, VOICE_SERVICE_TIMEOUT_S, VOICE_HEAR_TIMEOUT_S]
    assert VOICE_HEAR_TIMEOUT_S < VOICE_SERVICE_TIMEOUT_S


async def test_the_fake_voice_closes_quietly():
    await FakeVoice().aclose()
