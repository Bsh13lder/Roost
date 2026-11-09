"""A bot's own picture (look & feel redesign P1, the avatar editor's Upload): POST puts it on the
robot's screen, DELETE takes it off, GET serves it. It is sealed (enc:v2) in the avatar JSON, only
PNG, JPEG and WebP get in (by their bytes), and another user's bot is a 404."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from roost.bots.picture import NotAPicture, Picture, PictureTooBig, open_picture, picture_tag, read_picture, seal_picture
from roost.config import load_config
from roost.constants import AVATAR_PICTURE_MAX_BYTES
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64))
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + bytes(24)
PICTURE_URL = re.compile(r"^/api/bots/[\w-]+/picture\?v=[0-9a-f]{12}$")
KEY = bytes(range(32))


@pytest.fixture
async def client_and_user():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    await register_user(cfg, "alice", "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
    user_id = (await client.get("/api/auth/me")).json()["id"]
    yield cfg, client, user_id
    await client.aclose()


def _upload(client: httpx.AsyncClient, bot_id: str, data: bytes, content_type: str = "image/png"):
    return client.post(f"/api/bots/{bot_id}/picture", content=data, headers={**O, "Content-Type": content_type})


async def test_a_picture_goes_on_the_screen_and_is_served_back(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    up = await _upload(client, bot.id, PNG)
    assert up.status_code == 200
    url = up.json()["avatar"]["picture"]
    assert PICTURE_URL.match(url)
    got = await client.get(url)
    assert (got.status_code, got.content, got.headers["content-type"]) == (200, PNG, "image/png")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["cache-control"] == "private, no-store"   # user content is never kept in a cache
    assert (await client.get("/api/bots")).json()[0]["avatar"]["picture"] == url


async def test_the_picture_is_sealed_in_the_avatar_json(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    await _upload(client, bot.id, WEBP, "image/webp")
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT avatar FROM bots WHERE id = ?", (bot.id,))).fetchone()
    stored = json.loads(row["avatar"])
    assert stored["picture"].startswith("enc:v2:")
    assert "UklGR" not in stored["picture"]   # the WebP's base64 start never appears in the clear
    assert {key: stored[key] for key in ("shape", "color", "badge", "screen")} == {
        "shape": "round", "color": "#22c55e", "badge": "none", "screen": "glow"}


async def test_a_new_look_keeps_the_picture_and_a_new_picture_gets_a_new_address(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    first = (await _upload(client, bot.id, PNG)).json()["avatar"]["picture"]
    looked = await client.patch(f"/api/bots/{bot.id}", headers=O,
                                json={"avatar": {"shape": "monitor", "color": "#3b82f6", "screen": "signal"}})
    assert looked.json()["avatar"] == {"shape": "monitor", "color": "#3b82f6", "badge": "none", "screen": "signal",
                                       "picture": first}
    second = (await _upload(client, bot.id, WEBP, "image/webp")).json()["avatar"]["picture"]
    assert second != first


async def test_remove_takes_it_off(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    url = (await _upload(client, bot.id, PNG)).json()["avatar"]["picture"]
    gone = await client.delete(f"/api/bots/{bot.id}/picture", headers=O)
    assert (gone.status_code, gone.json()["avatar"]["picture"]) == (200, None)
    assert (await client.get(url)).status_code == 404


async def test_only_png_jpeg_and_webp_get_in_and_their_bytes_must_say_so(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    for data, content_type in ((svg, "image/svg+xml"), (svg, "image/png"), (PNG, "image/jpeg"), (b"GIF89a" + bytes(8), "image/gif")):
        refused = await _upload(client, bot.id, data, content_type)
        assert (refused.status_code, refused.json()["detail"]) == (415, "Upload a PNG, JPEG or WebP picture."), content_type
    big = await _upload(client, bot.id, PNG + bytes(AVATAR_PICTURE_MAX_BYTES))
    assert (big.status_code, big.json()["detail"]) == (413, "That picture is too big (512 KB at most). Try a smaller one.")
    assert (await client.get("/api/bots")).json()[0]["avatar"]["picture"] is None


async def test_another_users_bot_is_a_404_and_an_upload_needs_the_origin(client_and_user):
    cfg, client, user_id = client_and_user
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs = await make_bot(cfg, bob, "Secret")
    assert (await _upload(client, bobs.id, PNG)).status_code == 404
    assert (await client.get(f"/api/bots/{bobs.id}/picture")).status_code == 404
    assert (await client.delete(f"/api/bots/{bobs.id}/picture", headers=O)).status_code == 404
    mine = await make_bot(cfg, user_id, "Scout")
    no_origin = await client.post(f"/api/bots/{mine.id}/picture", content=PNG, headers={"Content-Type": "image/png"})
    assert no_origin.status_code == 403


def test_a_picture_sealed_for_another_key_or_user_does_not_open():
    sealed = seal_picture(Picture("image/png", PNG), KEY, "u1")
    assert open_picture(sealed, KEY, "u1") == Picture("image/png", PNG)
    assert open_picture(sealed, bytes(32), "u1") is None    # another key
    assert open_picture(sealed, KEY, "u2") is None          # another user's AAD
    assert open_picture("enc:v2:bad:bad", KEY, "u1") is None


async def test_a_streamed_upload_with_no_length_is_cut_off_at_the_cap_not_read_whole(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    sent = []

    async def endless():
        yield PNG
        for _ in range(4096):               # 4 MB in 1 KB pieces, if anyone keeps reading
            sent.append(1)
            yield bytes(1024)

    big = await client.post(f"/api/bots/{bot.id}/picture", content=endless(), headers={**O, "Content-Type": "image/png"})
    assert (big.status_code, big.json()["detail"]) == (413, "That picture is too big (512 KB at most). Try a smaller one.")
    assert len(sent) <= AVATAR_PICTURE_MAX_BYTES // 1024 + 8     # it stopped reading just past the cap


async def test_remove_needs_the_origin_and_every_route_needs_a_login(client_and_user):
    cfg, client, user_id = client_and_user
    mine = await make_bot(cfg, user_id, "Scout")
    await _upload(client, mine.id, PNG)
    assert (await client.delete(f"/api/bots/{mine.id}/picture")).status_code == 403
    assert (await client.get("/api/bots")).json()[0]["avatar"]["picture"] is not None   # still on
    client.cookies.clear()                                                             # now signed out
    assert (await client.get(f"/api/bots/{mine.id}/picture")).status_code == 401
    assert (await _upload(client, mine.id, PNG)).status_code == 401
    assert (await client.delete(f"/api/bots/{mine.id}/picture", headers=O)).status_code == 401


def test_the_bytes_decide_what_a_picture_is_and_the_content_type_must_agree():
    assert read_picture("image/png; charset=binary", PNG) == Picture("image/png", PNG)
    assert read_picture("IMAGE/WEBP", WEBP) == Picture("image/webp", WEBP)
    assert read_picture("image/jpeg", b"\xff\xd8\xff\xe0" + bytes(8)).media_type == "image/jpeg"
    for content_type, data in (("image/png", WEBP), ("", PNG), ("image/svg+xml", b"<svg/>"), ("image/png", b"")):
        with pytest.raises(NotAPicture):
            read_picture(content_type, data)
    with pytest.raises(PictureTooBig):
        read_picture("image/png", PNG + bytes(AVATAR_PICTURE_MAX_BYTES))


def test_a_pictures_tag_is_short_and_changes_with_the_picture():
    first = seal_picture(Picture("image/png", PNG), KEY, "u1")
    second = seal_picture(Picture("image/png", PNG), KEY, "u1")   # a fresh nonce: a new sealed value, a new tag
    assert PICTURE_URL.match(f"/api/bots/b/picture?v={picture_tag(first)}")
    assert picture_tag(first) == picture_tag(first) != picture_tag(second)
