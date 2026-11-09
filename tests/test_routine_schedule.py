"""Routine schedules: Madrid wall-clock times, DST, cron limits, jitter and missed slots (pure)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from roost.constants import ROUTINE_JITTER_SECONDS, ROUTINE_MAX_TIMES
from roost.routines.schedule import (
    CronSchedule,
    ScheduleRefused,
    TimesSchedule,
    jitter_seconds,
    next_after,
    parse_schedule,
    readable,
    slots_between,
    upcoming,
)

MADRID = ZoneInfo("Europe/Madrid")
UTC = timezone.utc
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]


def madrid(y, mo, d, h=0, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=MADRID).astimezone(UTC)


def local(dt: datetime) -> str:
    return dt.astimezone(MADRID).strftime("%Y-%m-%d %H:%M")


def times(days, *hhmm) -> TimesSchedule:
    return parse_schedule({"kind": "times", "days": days, "times": list(hhmm)})


def test_every_day_three_times_gives_the_next_one():
    sched = times(ALL_DAYS, "20:07", "10:07", "15:07", "10:07")
    assert sched.times == ("10:07", "15:07", "20:07")
    assert local(next_after(sched, madrid(2026, 10, 21, 9, 0))) == "2026-10-21 10:07"
    assert local(next_after(sched, madrid(2026, 10, 21, 10, 7))) == "2026-10-21 15:07"
    assert local(next_after(sched, madrid(2026, 10, 21, 21, 0))) == "2026-10-22 10:07"
    assert next_after(sched, madrid(2026, 10, 21, 9, 0)).tzinfo == UTC


def test_weekdays_skip_the_weekend():
    sched = times([1, 2, 3, 4, 5], "09:00")
    friday_evening = madrid(2026, 10, 23, 18, 0)  # 23 Oct 2026 is a Friday
    assert local(next_after(sched, friday_evening)) == "2026-10-26 09:00"
    assert local(next_after(times([7], "09:00"), friday_evening)) == "2026-10-25 09:00"


def test_spring_forward_0230_fires_at_0300_on_2026_03_29():
    sched = times(ALL_DAYS, "02:30")
    fire = next_after(sched, madrid(2026, 3, 28, 12, 0))
    assert local(fire) == "2026-03-29 03:00"
    assert fire == datetime(2026, 3, 29, 1, 0, tzinfo=UTC)
    assert local(next_after(sched, fire)) == "2026-03-30 02:30"


def test_fall_back_0230_fires_once_on_2026_10_25():
    sched = times(ALL_DAYS, "02:30")
    first = next_after(sched, madrid(2026, 10, 24, 12, 0))
    assert first == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # the first 02:30, still summer time
    assert local(next_after(sched, first)) == "2026-10-26 02:30"
    cron = parse_schedule({"kind": "cron", "expr": "30 2 * * *"})
    assert next_after(cron, madrid(2026, 10, 24, 12, 0)) == first
    assert local(next_after(cron, first)) == "2026-10-26 02:30"


def test_cron_follows_madrid_wall_clock_across_dst():
    cron = parse_schedule({"kind": "cron", "expr": "0 10 * * *"})
    winter = next_after(cron, madrid(2026, 3, 28, 12, 0))
    summer = next_after(cron, madrid(2026, 3, 29, 12, 0))
    assert winter == datetime(2026, 3, 29, 8, 0, tzinfo=UTC)   # 10:00 CEST
    assert summer == datetime(2026, 3, 30, 8, 0, tzinfo=UTC)
    before = next_after(cron, madrid(2026, 3, 27, 12, 0))
    assert before == datetime(2026, 3, 28, 9, 0, tzinfo=UTC)   # 10:00 CET
    gap = parse_schedule({"kind": "cron", "expr": "30 2 * * *"})
    assert local(next_after(gap, madrid(2026, 3, 28, 12, 0))) == "2026-03-29 03:00"


def test_cron_closer_than_fifteen_minutes_is_refused():
    with pytest.raises(ScheduleRefused) as err:
        parse_schedule({"kind": "cron", "expr": "*/5 * * * *"})
    assert err.value.text == "That schedule runs more often than every 15 minutes."
    with pytest.raises(ScheduleRefused):
        parse_schedule({"kind": "cron", "expr": "0,10 9 * * *"})
    assert isinstance(parse_schedule({"kind": "cron", "expr": "*/15 * * * *"}), CronSchedule)
    with pytest.raises(ScheduleRefused):
        times(ALL_DAYS, "10:00", "10:10")


def _refused(raw, **kw) -> str:
    with pytest.raises(ScheduleRefused) as err:
        parse_schedule(raw, **kw)
    return err.value.text


def test_bad_times_and_too_many_times_are_refused_with_plain_text():
    assert _refused({"kind": "times", "days": ALL_DAYS, "times": ["10:07"]}, name="  ") == "A routine needs a name."
    assert _refused({"kind": "times", "days": [], "times": ["10:07"]}) == "Pick at least one day and one time."
    assert _refused({"kind": "times", "days": ALL_DAYS, "times": []}) == "Pick at least one day and one time."
    for bad in ("25:00", "9am", "10:70", "10:7", ""):
        assert _refused({"kind": "times", "days": ALL_DAYS, "times": [bad]}) == "Times look like 10:07."
    assert _refused({"kind": "times", "days": [0], "times": ["10:07"]}) == "Pick at least one day and one time."
    many = [f"{h:02d}:00" for h in range(ROUTINE_MAX_TIMES + 1)]
    assert _refused({"kind": "times", "days": ALL_DAYS, "times": many}) == f"Up to {ROUTINE_MAX_TIMES} times a day."
    assert _refused({"kind": "cron", "expr": "not a cron"}) == "That custom schedule isn't valid."
    assert _refused({"kind": "cron", "expr": ""}) == "That custom schedule isn't valid."
    assert _refused({"kind": "cron", "expr": "0 0 10 * * *"}) == "That custom schedule isn't valid."
    assert _refused({"kind": "weekly"}) == "That custom schedule isn't valid."
    assert _refused("nope") == "That custom schedule isn't valid."  # type: ignore[arg-type]


def test_jitter_is_deterministic_and_within_bounds():
    slot = datetime(2026, 10, 21, 8, 7, tzinfo=UTC)
    first = jitter_seconds("routine-1", slot)
    assert first == jitter_seconds("routine-1", slot)
    assert 0 <= first <= ROUTINE_JITTER_SECONDS
    spread = {jitter_seconds(f"r{i}", slot) for i in range(60)}
    assert len(spread) > 5 and all(0 <= s <= ROUTINE_JITTER_SECONDS for s in spread)
    assert jitter_seconds("r", slot) == jitter_seconds("r", slot.astimezone(MADRID))


def test_slots_between_lists_every_missed_slot_up_to_the_limit():
    sched = times(ALL_DAYS, "10:07", "15:07", "20:07")
    slots = slots_between(sched, madrid(2026, 10, 21, 9, 0), madrid(2026, 10, 22, 12, 0), 10)
    assert [local(s) for s in slots] == [
        "2026-10-21 10:07", "2026-10-21 15:07", "2026-10-21 20:07", "2026-10-22 10:07"]
    assert len(slots_between(sched, madrid(2026, 10, 21, 9, 0), madrid(2026, 11, 21, 9, 0), 5)) == 5
    assert slots_between(sched, madrid(2026, 10, 21, 10, 7), madrid(2026, 10, 21, 10, 7), 5) == ()
    assert slots_between(sched, madrid(2026, 10, 21, 10, 6), madrid(2026, 10, 21, 10, 7), 5) == (madrid(2026, 10, 21, 10, 7),)


def test_upcoming_lists_the_next_fires_in_order():
    sched = times([1, 2, 3, 4, 5], "09:00")
    got = upcoming(sched, madrid(2026, 10, 22, 10, 0), 3)
    assert [local(s) for s in got] == ["2026-10-23 09:00", "2026-10-26 09:00", "2026-10-27 09:00"]


def test_readable_words_for_times_and_cron():
    assert readable(times(ALL_DAYS, "10:07", "15:07", "20:07")) == "Every day at 10:07, 15:07 and 20:07"
    assert readable(times([1, 2, 3, 4, 5], "09:00")) == "Weekdays at 09:00"
    assert readable(times([6, 7], "09:00")) == "Weekends at 09:00"
    assert readable(times([1, 3, 5], "18:30")) == "Mon, Wed and Fri at 18:30"
    assert readable(times([2], "08:00")) == "Tue at 08:00"
    cron = parse_schedule({"kind": "cron", "expr": "0 10 * * *"})
    now = madrid(2026, 10, 21, 9, 0)
    assert readable(cron, now=now) == "Custom: next 21 Oct 10:00, 22 Oct 10:00 and 23 Oct 10:00"
    assert readable(cron) == "Custom: 0 10 * * *"


def test_a_utc_clock_in_the_far_future_still_works():
    sched = times(ALL_DAYS, "10:07")
    assert next_after(sched, datetime(2030, 1, 1, tzinfo=UTC) + timedelta(hours=1)) > datetime(2030, 1, 1, tzinfo=UTC)
