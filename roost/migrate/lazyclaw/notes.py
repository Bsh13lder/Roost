"""A run-local log of anomalies, skips and lost fields. Built once per mapping call."""

from __future__ import annotations

from roost.migrate.lazyclaw.models import Anomaly


class Log:
    def __init__(self) -> None:
        self.anomalies: list[Anomaly] = []
        self.skipped: dict[str, int] = {}
        self.lost: dict[str, int] = {}

    def note(self, kind: str, ref: str, detail: str, *, blocking: bool = False) -> None:
        self.anomalies.append(Anomaly(kind=kind, ref=ref, detail=detail, blocking=blocking))

    def skip(self, key: str, count: int = 1) -> None:
        self.skipped[key] = self.skipped.get(key, 0) + count

    def lose(self, key: str, count: int = 1) -> None:
        self.lost[key] = self.lost.get(key, 0) + count
