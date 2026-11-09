"""The real engine: Qwen3-ASR for hearing and Qwen3-TTS CustomVoice for speaking, through mlx-audio on the Mac's
GPU. Only the voice service imports this module (its venv alone has mlx-audio); the models are fetched once at the
pinned revisions into ``HF_HOME`` and loaded on first use. Nothing it hears or says is written to disk.

Not covered by the test suite (it needs Apple's GPU and the models); ``make voice-install`` ends with a real check."""

from __future__ import annotations

import logging
from math import gcd
from typing import Any

import numpy as np

from roost.voice.constants import (
    VOICE_HEAR_MODEL,
    VOICE_HEAR_REVISION,
    VOICE_IDLE_UNLOAD_S,
    VOICE_SPEAK_MODEL,
    VOICE_SPEAK_REVISION,
)
from roost.voice.envelope import HearHint, context_prompt
from roost.voice.wav import WavInfo, encode_wav
from roost.voice_host.engine import ModelSlot

logger = logging.getLogger(__name__)

_HEAR_RATE = 16000
_PCM_SCALE = 32767.0
_LANGUAGE = "auto"   # the speaking model reads the language itself


def _local_copy(repo: str, revision: str) -> str:
    from huggingface_hub import snapshot_download

    return snapshot_download(repo, revision=revision)


def _load_hear() -> Any:
    from mlx_audio.stt import load

    return load(_local_copy(VOICE_HEAR_MODEL, VOICE_HEAR_REVISION))


def _load_speak() -> Any:
    from mlx_audio.tts.utils import load_model

    return load_model(_local_copy(VOICE_SPEAK_MODEL, VOICE_SPEAK_REVISION))


def _samples(recording: WavInfo) -> np.ndarray:
    pcm = np.frombuffer(recording.data, dtype="<i2").astype(np.float32) / _PCM_SCALE
    if recording.rate == _HEAR_RATE:
        return pcm
    from scipy.signal import resample_poly

    step = gcd(_HEAR_RATE, recording.rate)
    return resample_poly(pcm, _HEAR_RATE // step, recording.rate // step).astype(np.float32)


class MlxEngine:
    def __init__(self) -> None:
        self._hear: ModelSlot[Any] = ModelSlot("hear", _load_hear, VOICE_IDLE_UNLOAD_S)
        self._speak: ModelSlot[Any] = ModelSlot("speak", _load_speak, VOICE_IDLE_UNLOAD_S)

    def hear(self, recording: WavInfo, hint: HearHint = HearHint()) -> str:
        """Voice tuning D1/D2: the hint's terms go to Qwen3-ASR as its ``system_prompt`` (what it reads before it
        writes; measured to fix names and site names), and a chosen language as its ``language``; ``None`` lets the
        model read the language itself."""
        result = self._hear.get().generate(_samples(recording), language=hint.language,
                                           system_prompt=context_prompt(hint))
        return str(result.text).strip()

    def speak(self, text: str, speaker: str, instruct: str | None) -> bytes:
        model = self._speak.get()
        pieces = [np.array(r.audio) for r in model.generate_custom_voice(
            text=text, speaker=speaker, language=_LANGUAGE, instruct=instruct)]
        audio = np.clip(np.concatenate(pieces) if pieces else np.zeros(1, np.float32), -1.0, 1.0)
        return encode_wav((audio * _PCM_SCALE).astype("<i2").tobytes(), int(model.sample_rate))

    def warm(self) -> None:
        """Load both models now (a call is about to start), so the first answer doesn't wait ~25 s."""
        self._hear.get()
        self._speak.get()

    def loaded(self) -> list[str]:
        return [slot.name for slot in (self._hear, self._speak) if slot.loaded]

    def unload_idle(self, now: float) -> None:
        dropped = [slot.name for slot in (self._hear, self._speak) if slot.unload_idle(now)]
        if dropped:
            import mlx.core as mx

            mx.clear_cache()
            logger.info("voice: unloaded %s after idle", ", ".join(dropped))
