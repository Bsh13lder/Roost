"""Connectors: the one place a request leaves Roost (design §2–§3). httpx MockTransport only; no real network."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from roost.connectors import texts
from roost.connectors.address import check_base_url
from roost.connectors.http import ConnectorClient, Credentials, redact
from roost.constants import CONNECTOR_REDACTED, CONNECTOR_RESPONSE_MAX_BYTES

SECRET = "sk-live-0123456789abcdef"
BASE = check_base_url("https://api.example.com/v1")


async def _public(host: str) -> list[str]:
    return ["93.184.216.34"]


async def _private(host: str) -> list[str]:
    return ["93.184.216.34", "10.0.0.7"]


async def _nowhere(host: str) -> list[str]:
    raise OSError("no such host")


def _client(handler, resolver=_public) -> tuple[ConnectorClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    factory = lambda _pin: httpx.AsyncClient(transport=httpx.MockTransport(record))  # noqa: E731
    return ConnectorClient(client_factory=factory, resolver=resolver), seen


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})


async def _send(client, creds, method="GET", path="/sites", query=None, body=None, has_body=False):
    return await client.send(BASE, creds, method, BASE.url + path, query or {}, body, has_body)


async def test_bearer_header_style():
    client, seen = _client(_ok)
    result = await _send(client, Credentials("bearer", "Authorization", SECRET))
    assert result.status == 200 and json.loads(result.body) == {"ok": True}
    assert seen[0].headers["authorization"] == f"Bearer {SECRET}"
    assert str(seen[0].url) == "https://api.example.com/v1/sites"


async def test_raw_header_style_and_query_style():
    client, seen = _client(_ok)
    await _send(client, Credentials("header", "X-API-Key", SECRET))
    assert seen[0].headers["x-api-key"] == SECRET and "authorization" not in seen[0].headers
    await _send(client, Credentials("query", "key", SECRET), query={"q": "roost"})
    assert seen[1].url.params["key"] == SECRET and seen[1].url.params["q"] == "roost"


async def test_json_body_is_sent():
    client, seen = _client(_ok)
    await _send(client, Credentials("bearer", "Authorization", SECRET), method="POST", body={"a": 1}, has_body=True)
    assert seen[0].method == "POST" and json.loads(seen[0].content) == {"a": 1}
    assert seen[0].headers["content-type"] == "application/json"


async def test_an_echoed_key_is_redacted():
    def echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad key {SECRET} at {request.url}", headers={"content-type": "text/plain"})

    client, _ = _client(echo)
    result = await _send(client, Credentials("query", "key", SECRET))
    assert result.status == 401
    assert SECRET not in result.body and CONNECTOR_REDACTED in result.body


def test_redact_covers_encoded_forms():
    secret = "a+b/c=d e"
    text = "x a+b/c=d e y a%2Bb%2Fc%3Dd%20e z a%2Bb%2Fc%3Dd+e w a%2bb%2fc%3dd%20e"
    out = redact(text, secret)
    assert "a+b/c=d e" not in out and "a%2Bb%2Fc%3Dd%20e" not in out and "a%2Bb%2Fc%3Dd+e" not in out
    assert "a%2bb%2fc%3dd%20e" not in out and out.count(CONNECTOR_REDACTED) == 4
    assert redact("Mixed", "Mixed") == CONNECTOR_REDACTED and redact("mixed", "Mixed") == "mixed"
    assert redact("text", "") == "text"


async def test_redirects_are_not_followed_and_location_is_not_shown():
    def moved(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": f"https://evil.example.org/?key={SECRET}"})

    client, seen = _client(moved)
    result = await _send(client, Credentials("query", "key", SECRET))
    assert len(seen) == 1 and result.status == 302
    assert result.body == texts.REDIRECT and "evil" not in result.body


async def test_a_name_that_resolves_private_is_refused_before_sending():
    client, seen = _client(_ok, resolver=_private)
    result = await _send(client, Credentials("bearer", "Authorization", SECRET))
    assert seen == [] and result.status is None and result.body == texts.PRIVATE_ADDRESS


async def test_an_unknown_name_is_refused():
    client, seen = _client(_ok, resolver=_nowhere)
    result = await _send(client, Credentials("bearer", "Authorization", SECRET))
    assert seen == [] and result.body == texts.DNS_FAILED


async def test_the_answer_is_capped():
    big = "x" * (CONNECTOR_RESPONSE_MAX_BYTES * 2)
    client, _ = _client(lambda r: httpx.Response(200, text=big, headers={"content-type": "text/plain"}))
    result = await _send(client, Credentials("bearer", "Authorization", SECRET))
    assert result.cut and len(result.body.encode()) <= CONNECTOR_RESPONSE_MAX_BYTES


async def test_binary_and_empty_bodies():
    client, _ = _client(lambda r: httpx.Response(200, content=b"\x89PNG....", headers={"content-type": "image/png"}))
    result = await _send(client, Credentials("bearer", "Authorization", SECRET))
    assert result.body == texts.BINARY_BODY.format(size=8)
    client, _ = _client(lambda r: httpx.Response(204))
    assert (await _send(client, Credentials("bearer", "Authorization", SECRET))).body == texts.EMPTY_BODY


@pytest.mark.parametrize("exc,text", [
    (httpx.ConnectTimeout, texts.TIMED_OUT),
    (httpx.ConnectError, texts.NO_CONNECT),
    (httpx.RemoteProtocolError, texts.FAILED),
])
async def test_errors_never_carry_the_key(exc, text, caplog):
    def boom(request: httpx.Request) -> httpx.Response:
        raise exc(f"failed for {request.url}", request=request)

    client, _ = _client(boom)
    with caplog.at_level(logging.DEBUG):
        result = await _send(client, Credentials("query", "key", SECRET))
    assert result.status is None and result.body == text
    assert SECRET not in caplog.text and "api.example.com" not in caplog.text


async def test_an_ip_literal_base_is_checked_without_dns():
    base = check_base_url("https://93.184.216.34/v1")
    client, seen = _client(_ok, resolver=_nowhere)
    result = await client.send(base, Credentials("bearer", "Authorization", SECRET), "GET", base.url + "/x", {}, None,
                               False)
    assert result.status == 200 and len(seen) == 1
