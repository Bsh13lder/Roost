"""The control lock (S1.8, ported from OpenMausBot's computer-control rules)."""

from __future__ import annotations

import asyncio
import time

from roost.desk.control import ControlLock


async def test_a_free_computer_lets_the_call_through_at_once():
    assert await ControlLock(wait_seconds=0.05).wait_for_hands("b1") == "free"


async def test_while_held_a_call_waits_then_is_not_performed():
    lock = ControlLock(wait_seconds=0.05)
    lock.take("b1")
    assert await lock.wait_for_hands("b1") == "still_held"


async def test_a_call_that_waited_through_a_hold_is_not_performed_even_after_give_back():
    lock = ControlLock(wait_seconds=2.0)
    lock.take("b1")
    waiting = asyncio.create_task(lock.wait_for_hands("b1"))
    await asyncio.sleep(0.01)
    lock.give_back("b1")
    assert await waiting == "handed_back"
    assert await lock.wait_for_hands("b1") == "free"


async def test_wait_taken_is_true_at_once_when_the_computer_is_already_held():
    lock = ControlLock()
    lock.take("b1")
    started = time.monotonic()
    assert await lock.wait_taken("b1", timeout=5.0) is True
    assert time.monotonic() - started < 1.0


async def test_wait_taken_is_true_when_the_computer_is_taken_mid_wait():
    lock = ControlLock()
    waiting = asyncio.create_task(lock.wait_taken("b1", timeout=5.0))
    await asyncio.sleep(0.01)
    assert not waiting.done()
    lock.take("b1")
    assert await asyncio.wait_for(waiting, timeout=1.0) is True


async def test_wait_taken_is_false_when_nobody_takes_control_in_time():
    assert await ControlLock().wait_taken("b1", timeout=0.05) is False


async def test_wait_taken_only_listens_to_its_own_bot():
    lock = ControlLock()
    waiting = asyncio.create_task(lock.wait_taken("b1", timeout=0.1))
    await asyncio.sleep(0.01)
    lock.take("b2")
    assert await waiting is False


async def test_a_wait_after_a_give_back_starts_fresh():
    """The hold is over: a later wait does not see the old take."""
    lock = ControlLock()
    lock.take("b1")
    lock.give_back("b1")
    assert await lock.wait_taken("b1", timeout=0.05) is False
    lock.take("b1")
    assert await lock.wait_taken("b1", timeout=0.05) is True


async def test_a_give_back_with_no_hold_does_not_hide_a_later_take_from_a_waiting_call():
    lock = ControlLock()
    waiting = asyncio.create_task(lock.wait_taken("b1", timeout=5.0))
    await asyncio.sleep(0.01)
    lock.give_back("b1")                      # nothing was held: the waiter is still waiting for a take
    lock.take("b1")
    assert await asyncio.wait_for(waiting, timeout=1.0) is True


def test_take_is_idempotent_and_keeps_when_the_hold_began():
    ticks = iter((100.0, 200.0))
    lock = ControlLock(clock=lambda: next(ticks))
    first = lock.take("b1")
    assert lock.take("b1") == first and lock.held("b1").since == 100.0


def test_holds_are_per_bot_and_forget_releases_one():
    lock = ControlLock()
    lock.take("b1")
    assert lock.held("b2") is None
    lock.forget("b1")
    assert lock.held("b1") is None


def test_a_new_lock_starts_free():
    """A restart builds a new lock: no hold survives it."""
    lock = ControlLock()
    lock.take("b1")
    assert ControlLock().held("b1") is None


async def test_wait_released_returns_at_once_when_free():
    await asyncio.wait_for(ControlLock().wait_released("b1"), timeout=0.5)


async def test_wait_released_waits_for_the_give_back():
    lock = ControlLock()
    lock.take("b1")
    waiting = asyncio.create_task(lock.wait_released("b1"))
    await asyncio.sleep(0.01)
    assert not waiting.done()
    lock.give_back("b1")
    await asyncio.wait_for(waiting, timeout=0.5)


def test_epoch_counts_takes():
    lock = ControlLock()
    assert lock.epoch("b1") == 0
    lock.take("b1")
    lock.take("b1")                  # a second click is the same hold
    assert lock.epoch("b1") == 1
    lock.give_back("b1")
    assert lock.epoch("b1") == 1     # giving back is not a take
    lock.take("b1")
    assert lock.epoch("b1") == 2 and lock.epoch("b2") == 0
