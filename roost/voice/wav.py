"""The one sound format voice moves: WAV, PCM 16-bit, mono. ``read_wav`` checks a recording before anything decodes
it (both the gateway and the voice service call it), ``encode_wav`` writes one. Standard library only."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from roost.voice.constants import VOICE_MAX_SECONDS, VOICE_RATE_MAX, VOICE_RATE_MIN, VOICE_WAV_BYTES_MAX

_PCM = 1
_HEADER = 12
_CHUNK = 8
_FMT_MIN = 16


class WavError(ValueError):
    """Not a WAV this module accepts; the message says why, in words."""


@dataclass(frozen=True)
class WavInfo:
    rate: int
    channels: int
    bits: int
    data: bytes     # the samples

    @property
    def seconds(self) -> float:
        return len(self.data) / (self.rate * self.channels * self.bits // 8)


def _chunks(raw: bytes):
    at = _HEADER
    while at + _CHUNK <= len(raw):
        tag, size = raw[at:at + 4], struct.unpack("<I", raw[at + 4:at + 8])[0]
        start = at + _CHUNK
        if start + size > len(raw):
            raise WavError("The recording is cut short.")
        yield tag, raw[start:start + size]
        at = start + size + (size & 1)


def _format(body: bytes) -> tuple[int, int, int]:
    if len(body) < _FMT_MIN:
        raise WavError("The recording has no format.")
    kind, channels, rate = struct.unpack("<HHI", body[:8])
    bits = struct.unpack("<H", body[14:16])[0]
    if kind != _PCM or channels != 1 or bits != 16:
        raise WavError("The recording must be 16-bit mono PCM.")
    if not VOICE_RATE_MIN <= rate <= VOICE_RATE_MAX:
        raise WavError("The recording's sample rate is not supported.")
    return rate, channels, bits


def read_wav(raw: bytes) -> WavInfo:
    """The recording's format and samples, or a ``WavError``: not RIFF/WAVE, not 16-bit mono PCM at 8–48 kHz, cut
    short, or longer than ``VOICE_MAX_SECONDS``."""
    if len(raw) > VOICE_WAV_BYTES_MAX:
        raise WavError(f"The recording is longer than {VOICE_MAX_SECONDS} seconds.")
    if len(raw) < _HEADER or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise WavError("That is not a WAV recording.")
    fmt = data = None
    for tag, body in _chunks(raw):
        if tag == b"fmt " and fmt is None:
            fmt = _format(body)
        elif tag == b"data" and data is None:
            data = body
    if fmt is None or data is None:
        raise WavError("That is not a WAV recording.")
    info = WavInfo(rate=fmt[0], channels=fmt[1], bits=fmt[2], data=data)
    if info.seconds > VOICE_MAX_SECONDS:
        raise WavError(f"The recording is longer than {VOICE_MAX_SECONDS} seconds.")
    return info


def encode_wav(samples: bytes, rate: int, *, channels: int = 1, bits: int = 16) -> bytes:
    """A RIFF/WAVE file around little-endian PCM ``samples``."""
    block = channels * bits // 8
    fmt = struct.pack("<HHIIHH", _PCM, channels, rate, rate * block, block, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(samples)) + samples
    return b"RIFF" + struct.pack("<I", len(body)) + body
