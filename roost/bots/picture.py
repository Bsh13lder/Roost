"""A bot's own picture (look & feel redesign P1, the avatar editor's Upload): a small PNG, JPEG or
WebP its robot shows on its screen. It is the user's content, so it is stored sealed (``enc:v2``,
AAD ``bots:avatar_picture``) inside the bot's avatar JSON: no schema change, and only the owner's key
opens it. The web shrinks a picture to 256 px before it uploads (``web/src/lib/picture.ts``)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag

from roost.constants import AVATAR_PICTURE_MAX_BYTES
from roost.crypto.encryption import decrypt, encrypt, user_aad

logger = logging.getLogger(__name__)

PICTURE_AAD = "bots:avatar_picture"
PICTURE_TAG_CHARS = 12
TOO_BIG_TEXT = f"That picture is too big ({AVATAR_PICTURE_MAX_BYTES // 1024} KB at most). Try a smaller one."
NOT_A_PICTURE_TEXT = "Upload a PNG, JPEG or WebP picture."
# What each kind of file starts with: the bytes say what a picture is, never its Content-Type alone.
_STARTS = (("image/png", b"\x89PNG\r\n\x1a\n"), ("image/jpeg", b"\xff\xd8\xff"))
_WEBP_RIFF, _WEBP_MARK = b"RIFF", b"WEBP"


class PictureTooBig(ValueError):
    """More than AVATAR_PICTURE_MAX_BYTES (HTTP 413)."""


class NotAPicture(ValueError):
    """Not a PNG, JPEG or WebP, or not what its Content-Type says (HTTP 415)."""


@dataclass(frozen=True)
class Picture:
    media_type: str
    data: bytes


def _kind(data: bytes) -> str | None:
    for media_type, start in _STARTS:
        if data.startswith(start):
            return media_type
    return "image/webp" if data[:4] == _WEBP_RIFF and data[8:12] == _WEBP_MARK else None


def read_picture(content_type: str, data: bytes) -> Picture:
    """The upload as a Picture. Raises PictureTooBig or NotAPicture with a sentence for the user."""
    if len(data) > AVATAR_PICTURE_MAX_BYTES:
        raise PictureTooBig(TOO_BIG_TEXT)
    kind = _kind(data)
    if kind is None or content_type.split(";")[0].strip().lower() != kind:
        raise NotAPicture(NOT_A_PICTURE_TEXT)
    return Picture(kind, data)


def seal_picture(picture: Picture, dek: bytes, user_id: str) -> str:
    payload = f"{picture.media_type};{base64.b64encode(picture.data).decode('ascii')}"
    return encrypt(payload, dek, user_aad(user_id, PICTURE_AAD))


def open_picture(sealed: str, dek: bytes, user_id: str) -> Picture | None:
    """None, logged, when a stored picture cannot be opened: the robot shows its screen instead."""
    try:
        media_type, encoded = decrypt(sealed, dek, user_aad(user_id, PICTURE_AAD)).split(";", 1)
        return Picture(media_type, base64.b64decode(encoded, validate=True))
    except (InvalidTag, ValueError, binascii.Error):
        logger.warning("A bot picture of user %s could not be opened", user_id, exc_info=True)
        return None


def picture_tag(sealed: str) -> str:
    """A short version for the picture's address, so a new picture is never shown from the cache."""
    return hashlib.sha256(sealed.encode("ascii")).hexdigest()[:PICTURE_TAG_CHARS]
