"""The zone the suite was written in: conftest sets ROOST_TIMEZONE to it, so it is the install's zone in tests."""

from __future__ import annotations

from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")
