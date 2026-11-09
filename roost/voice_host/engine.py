"""What the voice service asks of a model engine, a slot that loads a model on first use and lets it go when idle,
and the fake engine the tests and the scripted gateway use."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from roost.voice.envelope import HearHint
from roost.voice.wav import WavInfo, encode_wav

T = TypeVar("T")


class Engine(Protocol):
    """Blocking calls; the service runs them in a worker thread, one at a time."""

    def hear(self, recording: WavInfo, hint: HearHint) -> str: ...

    def speak(self, text: str, speaker: str, instruct: str | None) -> bytes: ...

    def warm(self) -> None: ...

    def loaded(self) -> list[str]: ...

    def unload_idle(self, now: float) -> None: ...


class ModelSlot(Generic[T]):
    """One model: ``get`` loads it the first time (and after an unload), ``unload_idle`` drops it once it has gone
    unused for ``idle_s``. Thread-safe: the loader runs at most once at a time."""

    def __init__(self, name: str, loader: Callable[[], T], idle_s: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.name = name
        self._loader = loader
        self._idle_s = idle_s
        self._clock = clock
        self._lock = threading.Lock()
        self._model: T | None = None
        self._used_at = 0.0

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def get(self) -> T:
        with self._lock:
            if self._model is None:
                self._model = self._loader()
            self._used_at = self._clock()
            return self._model

    def unload_idle(self, now: float) -> bool:
        """True when it let the model go."""
        with self._lock:
            if self._model is None or now - self._used_at < self._idle_s:
                return False
            self._model = None
            return True


_FAKE_RATE = 24000
_FAKE_SECONDS_PER_CHAR = 0.01


@dataclass
class FakeEngine:
    """Hears every recording as ``heard`` and speaks silence about as long as the words; records what it was asked
    (the tone's words included) so a test can check them. Loads nothing, but reports both models loaded once
    warmed, like the real engine does."""

    heard: str = "Add milk to my list"
    spoken: list[tuple[str, str, str | None]] = field(default_factory=list)
    recordings: list[float] = field(default_factory=list)
    hints: list[HearHint] = field(default_factory=list)
    warmed: int = 0

    def hear(self, recording: WavInfo, hint: HearHint = HearHint()) -> str:
        self.recordings.append(recording.seconds)
        self.hints.append(hint)
        return self.heard

    def speak(self, text: str, speaker: str, instruct: str | None) -> bytes:
        self.spoken.append((text, speaker, instruct))
        frames = max(1, int(len(text) * _FAKE_SECONDS_PER_CHAR * _FAKE_RATE))
        return encode_wav(b"\x00\x00" * frames, _FAKE_RATE)

    def warm(self) -> None:
        self.warmed += 1

    def loaded(self) -> list[str]:
        return ["hear", "speak"] if self.warmed else []

    def unload_idle(self, now: float) -> None:
        return None
