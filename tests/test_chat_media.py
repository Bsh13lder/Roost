"""Chat pictures (owner, 2026-11-05, docs/plans/2026-11-05-roost-chat-pictures.md): you attach pictures (or a
video's frames) to a message, the server re-encodes them with every bit of metadata dropped, seals them, serves
them back, and a run of your message shows them to the model."""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image

from roost.config import load_config
from roost.constants import CHAT_MEDIA_LONG_SIDE, CHAT_MEDIA_MAX_BYTES, CHAT_MEDIA_UPLOADS_PER_WINDOW
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.media.process import NotAPicture, normalise_picture
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
_ORIENTATION, _GPS = 0x0112, 0x8825


def _jpeg(width: int = 3000, height: int = 2000, *, rotate: bool = False, gps: bool = False) -> bytes:
    image = Image.new("RGB", (width, height), (200, 30, 30))
    exif = Image.Exif()
    if rotate:
        exif[_ORIENTATION] = 6          # the phone held upright: turn 90° clockwise to show it
    if gps:
        exif[_GPS] = {1: "N", 2: (41.0, 23.0, 0.0)}
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif.tobytes())
    return buffer.getvalue()


def _png(width: int = 40, height: int = 30) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 255, 128)).save(buffer, "PNG")
    return buffer.getvalue()


# -- the picture itself --------------------------------------------------------------------------------------

def test_a_big_photo_is_turned_upright_shrunk_and_stripped():
    picture = normalise_picture(_jpeg(rotate=True, gps=True))
    image = Image.open(io.BytesIO(picture.data))
    assert image.format == "JPEG"
    assert (picture.width, picture.height) == image.size == (CHAT_MEDIA_LONG_SIDE * 2 // 3, CHAT_MEDIA_LONG_SIDE)
    assert not image.getexif() and "icc_profile" not in image.info


def test_a_png_with_transparency_becomes_a_jpeg():
    picture = normalise_picture(_png())
    assert Image.open(io.BytesIO(picture.data)).format == "JPEG"
    assert (picture.width, picture.height) == (40, 30)


@pytest.mark.parametrize("data", [b"", b"not a picture", b"%PDF-1.7 ..."])
def test_anything_else_is_not_a_picture(data):
    with pytest.raises(NotAPicture):
        normalise_picture(data)


# -- the routes ----------------------------------------------------------------------------------------------

@pytest.fixture
async def rig():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    await register_user(cfg, "alice", "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
    user_id = (await client.get("/api/auth/me")).json()["id"]
    bot = await make_bot(cfg, user_id, "Gela")
    thread = (await client.post(f"/api/bots/{bot.id}/chat", headers=O)).json()
    yield cfg, client, user_id, thread["id"], app
    await client.aclose()


def _upload(client, thread_id: str, data: bytes, *, name: str = "p.jpg", mime: str = "image/jpeg", video: bool = False):
    form = {"video": "1"} if video else None
    return client.post(f"/api/threads/{thread_id}/media", files={"file": (name, data, mime)}, data=form, headers=O)


async def test_an_upload_answers_its_id_and_size_and_is_sealed(rig):
    cfg, client, user_id, thread_id, _ = rig
    up = await _upload(client, thread_id, _jpeg(800, 600))
    assert up.status_code == 200
    assert up.json()["width"] == 800 and up.json()["height"] == 600
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT blob, message_id, source FROM chat_media WHERE id = ?",
                                      (up.json()["id"],))).fetchone()
    assert row["blob"].startswith("enc:v2:") and row["message_id"] is None and row["source"] == "you"


async def test_something_that_is_not_a_picture_is_415(rig):
    _, client, _, thread_id, _ = rig
    up = await _upload(client, thread_id, b"hello", name="a.txt", mime="text/plain")
    assert up.status_code == 415


async def test_a_file_over_the_limit_is_413(rig, monkeypatch):
    _, client, _, thread_id, _ = rig
    monkeypatch.setattr("roost.gateway.routes.media.CHAT_MEDIA_MAX_BYTES", 1000)
    assert (await _upload(client, thread_id, _jpeg(400, 400))).status_code == 413
    assert CHAT_MEDIA_MAX_BYTES == 15 * 1024 * 1024


async def test_too_many_loose_uploads_in_a_thread_is_429(rig):
    _, client, _, thread_id, _ = rig
    small = _jpeg(20, 20)
    for _ in range(CHAT_MEDIA_UPLOADS_PER_WINDOW):
        assert (await _upload(client, thread_id, small)).status_code == 200
    assert (await _upload(client, thread_id, small)).status_code == 429


async def test_another_users_thread_is_404(rig):
    cfg, client, _, _, _ = rig
    other = await register_user(cfg, "bob", "pw-123456")
    bob_bot = await make_bot(cfg, other.id, "Bob's")
    from roost.talk.store import TalkStore
    bob_thread = await TalkStore(cfg).create_thread(other.id, bob_bot.id)
    assert (await _upload(client, bob_thread.id, _jpeg(20, 20))).status_code == 404


async def test_a_message_carries_its_pictures_and_serves_them(rig):
    _, client, _, thread_id, _ = rig
    first = (await _upload(client, thread_id, _jpeg(64, 48))).json()
    frame = (await _upload(client, thread_id, _jpeg(32, 32), video=True)).json()
    sent = await client.post(f"/api/threads/{thread_id}/messages",
                             json={"text": "", "media_ids": [first["id"], frame["id"]]}, headers=O)
    assert sent.status_code == 202
    mine = [m for m in (await client.get(f"/api/threads/{thread_id}/messages")).json() if m["role"] == "user"][-1]
    assert mine["body"] == ""
    assert mine["media"] == [
        {"id": first["id"], "width": 64, "height": 48, "source": "you", "group": None},
        {"id": frame["id"], "width": 32, "height": 32, "source": "you", "group": "video"},
    ]
    got = await client.get(f"/api/media/{first['id']}")
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert got.headers["cache-control"] == "private, max-age=86400"
    assert Image.open(io.BytesIO(got.content)).size == (64, 48)


async def test_every_message_has_a_media_list(rig):
    _, client, _, thread_id, _ = rig
    await client.post(f"/api/threads/{thread_id}/messages", json={"text": "hi"}, headers=O)
    assert all(m["media"] == [] for m in (await client.get(f"/api/threads/{thread_id}/messages")).json())


async def test_an_empty_message_without_pictures_is_refused(rig):
    _, client, _, thread_id, _ = rig
    assert (await client.post(f"/api/threads/{thread_id}/messages", json={"text": ""}, headers=O)).status_code == 422


async def test_pictures_already_sent_or_unknown_or_too_many_are_400(rig):
    _, client, _, thread_id, _ = rig
    one = (await _upload(client, thread_id, _jpeg(20, 20))).json()["id"]
    ok = await client.post(f"/api/threads/{thread_id}/messages", json={"text": "a", "media_ids": [one]}, headers=O)
    assert ok.status_code == 202
    again = await client.post(f"/api/threads/{thread_id}/messages", json={"text": "b", "media_ids": [one]}, headers=O)
    assert again.status_code == 400
    unknown = await client.post(f"/api/threads/{thread_id}/messages", json={"text": "c", "media_ids": ["nope"]},
                                headers=O)
    assert unknown.status_code == 400
    many = await client.post(f"/api/threads/{thread_id}/messages", json={"text": "d", "media_ids": ["x"] * 9},
                             headers=O)
    assert many.status_code == 400


async def test_another_users_picture_is_404(rig):
    cfg, client, _, thread_id, app = rig
    pid = (await _upload(client, thread_id, _jpeg(20, 20))).json()["id"]
    await register_user(cfg, "bob", "pw-123456")
    bob = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await bob.post("/api/auth/login", json={"username": "bob", "password": "pw-123456"}, headers=O)
    assert (await bob.get(f"/api/media/{pid}")).status_code == 404
    assert (await client.get("/api/media/unknown")).status_code == 404
    await bob.aclose()


async def test_retiring_the_bot_takes_its_pictures(rig):
    cfg, client, user_id, thread_id, _ = rig
    await _upload(client, thread_id, _jpeg(20, 20))
    from roost.bots.store import BotStore
    from roost.talk.store import TalkStore
    thread = await TalkStore(cfg).get_thread(user_id, thread_id)
    await BotStore(cfg).delete(user_id, thread.bot_id)
    async with db_session(cfg) as db:
        left = await (await db.execute("SELECT COUNT(*) FROM chat_media WHERE user_id = ?", (user_id,))).fetchone()
    assert left[0] == 0
