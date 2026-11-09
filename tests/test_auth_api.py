"""Contract tests for the auth HTTP API — ``roost/gateway/app.py``.

The first three tests are verbatim from the Task 2 brief. The rest cover
behavior the contract requires but the brief's starter tests don't
exercise: Origin enforcement on login/logout (not just register), the
exact 201/204/401 response shapes, and the single-account "closed"
registration rule not caring about username.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}


def test_first_register_then_closed():
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O).status_code == 201
    assert c.post("/api/auth/register", json={"username": "x", "password": "pw-123456"}, headers=O).status_code == 403


def test_login_me_logout():
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    r = c.post("/api/auth/login", json={"username": "me", "password": "pw-123456"}, headers=O)
    assert r.status_code == 200 and "roost_session" in r.cookies
    assert c.get("/api/auth/me").json()["username"] == "me"
    assert c.post("/api/auth/logout", headers=O).status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_post_without_allowed_origin_is_403():
    c = TestClient(create_app())
    assert c.post(
        "/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=BAD_O
    ).status_code == 403


def test_register_response_shape_is_exactly_id_and_username():
    c = TestClient(create_app())
    r = c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    assert r.status_code == 201
    assert set(r.json()) == {"id", "username"}
    assert r.json()["username"] == "me"


def test_login_response_shape_is_exactly_id_and_username():
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    r = c.post("/api/auth/login", json={"username": "me", "password": "pw-123456"}, headers=O)
    assert set(r.json()) == {"id", "username"}


def test_me_returns_401_before_any_login():
    c = TestClient(create_app())
    assert c.get("/api/auth/me").status_code == 401


def test_login_without_allowed_origin_is_403():
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    assert c.post(
        "/api/auth/login", json={"username": "me", "password": "pw-123456"}, headers=BAD_O
    ).status_code == 403


def test_logout_without_allowed_origin_is_403():
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    c.post("/api/auth/login", json={"username": "me", "password": "pw-123456"}, headers=O)
    assert c.post("/api/auth/logout", headers=BAD_O).status_code == 403


def test_second_register_closed_even_with_matching_username():
    # "any user exists" must trigger regardless of whether the second
    # attempt reuses the first username or picks a new one.
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    assert c.post(
        "/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O
    ).status_code == 403


def test_login_wrong_password_is_401():
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    r = c.post("/api/auth/login", json={"username": "me", "password": "wrong-pw-1"}, headers=O)
    assert r.status_code == 401


def test_register_rejects_too_short_password():
    c = TestClient(create_app())
    r = c.post("/api/auth/register", json={"username": "me", "password": "short1"}, headers=O)
    assert r.status_code == 422


def test_register_rejects_common_password():
    c = TestClient(create_app())
    r = c.post("/api/auth/register", json={"username": "me", "password": "password123"}, headers=O)
    assert r.status_code == 422


def test_session_cookie_is_httponly_and_samesite_strict():
    c = TestClient(create_app())
    r = c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    set_cookie = r.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "samesite=strict" in set_cookie.lower()
    # Loopback HTTP in Night-1 — never Secure (there's no TLS to require it).
    assert "secure" not in set_cookie.lower()


def test_too_many_logins_from_one_ip_are_rate_limited(monkeypatch):
    # S1 Task 10 found this the hard way: Playwright's `make e2e` runs every
    # spec file against ONE shared gateway process, so LOGIN_RATE_LIMIT_PER_IP
    # (5/60s) is real and reachable from plain, correct logins, not just an
    # attacker. This pins today's production behavior before the next test
    # proves the E2E-only exemption leaves it alone. The conftest tripwire
    # forces ROOST_MODEL=scripted suite-wide (never a real LLM in tests);
    # this one test opts back into "claude" mode to see production's limit.
    monkeypatch.setenv("ROOST_MODEL", "claude")
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"username": "me", "password": "pw-123456"}, headers=O).status_code == 200
    r = c.post("/api/auth/login", json={"username": "me", "password": "pw-123456"}, headers=O)
    assert r.status_code == 429
    assert r.json()["detail"] == "Too many login attempts. Try again later."


def test_scripted_mode_is_exempt_from_the_login_rate_limit(monkeypatch):
    # ROOST_MODEL=scripted is the E2E-only mode (playwright.config.ts's
    # webServer); it never runs with a real model in production, so lifting
    # the limiter there can't open a hole for a real attacker.
    monkeypatch.setenv("ROOST_MODEL", "scripted")
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    for _ in range(20):
        assert c.post("/api/auth/login", json={"username": "me", "password": "pw-123456"}, headers=O).status_code == 200


def test_session_cookie_is_not_secure_inside_the_gateway_container(monkeypatch):
    """In the container the gateway binds 0.0.0.0, but it is still served
    over plain HTTP on the host's 127.0.0.1:18800 only (compose publishes
    nothing else). A ``Secure`` cookie there would be dropped by any
    browser that doesn't treat http://127.0.0.1 as a secure origin, and
    login would silently never stick -- so container mode must keep the
    same non-Secure cookie as a bare loopback run."""
    monkeypatch.setenv("ROOST_IN_CONTAINER", "1")
    monkeypatch.setenv("ROOST_HOST", "0.0.0.0")
    c = TestClient(create_app())
    r = c.post("/api/auth/register", json={"username": "me", "password": "pw-123456"}, headers=O)
    assert r.status_code == 201
    set_cookie = r.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "secure" not in set_cookie.lower()
