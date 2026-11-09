"""One uploaded picture made safe to keep and show: decoded by Pillow, turned upright by its EXIF orientation, every
bit of metadata dropped (EXIF, GPS, ICC, comments), shrunk to ``CHAT_MEDIA_LONG_SIDE`` and re-encoded as a JPEG."""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from roost.constants import CHAT_MEDIA_JPEG_QUALITY, CHAT_MEDIA_LONG_SIDE, CHAT_MEDIA_MAX_PIXELS

NOT_A_PICTURE_TEXT = "That isn't a picture Roost can read. Send it as a JPEG, PNG or WebP picture."
TOO_LARGE_TEXT = "That picture is too large. Send a smaller one."
_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "HEIF"})     # HEIF only when this Pillow can read it
_WHITE = (255, 255, 255)


class NotAPicture(ValueError):
    """Not a JPEG, PNG or WebP picture (or one too large to decode); its text is for the owner."""


@dataclass(frozen=True)
class CleanPicture:
    data: bytes          # the re-encoded JPEG
    width: int
    height: int


def _opened(data: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.format not in _FORMATS:
                raise NotAPicture(NOT_A_PICTURE_TEXT)
            if image.width * image.height > CHAT_MEDIA_MAX_PIXELS:
                raise NotAPicture(TOO_LARGE_TEXT)
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise NotAPicture(NOT_A_PICTURE_TEXT) from exc
    return image


def _rgb(image: Image.Image) -> Image.Image:
    """A see-through picture lands on white; every other mode becomes plain RGB."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, _WHITE)
        flat.paste(rgba, mask=rgba.getchannel("A"))
        return flat
    return image.convert("RGB")


def normalise_picture(data: bytes) -> CleanPicture:
    """The picture upright, at most ``CHAT_MEDIA_LONG_SIDE`` on its long side, as a metadata-free JPEG."""
    upright = _rgb(ImageOps.exif_transpose(_opened(data)))
    upright.thumbnail((CHAT_MEDIA_LONG_SIDE, CHAT_MEDIA_LONG_SIDE), Image.Resampling.LANCZOS)
    clean = Image.new("RGB", upright.size)      # a fresh image: nothing of the upload's info rides along
    clean.paste(upright)
    buffer = io.BytesIO()
    clean.save(buffer, "JPEG", quality=CHAT_MEDIA_JPEG_QUALITY, optimize=True)
    return CleanPicture(buffer.getvalue(), clean.width, clean.height)
