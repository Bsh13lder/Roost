"""Owner, 2026-10-31: "when it hits an error, just reload the page". Upwork's job page answered 500 ("We'll be right
back") and the bot gave up at once. ``open_page`` now waits and loads the page again on a server error (5xx), a few
times, and says plainly when the site stays down. No real browser."""

from __future__ import annotations

from roost.constants import SERVER_ERROR_RELOAD_WAITS_S
from roost.desk import PageText
from roost.talk.server_error import (
    SERVER_ERROR_ACTIVITY, SERVER_ERROR_DOWN_TEXT, SERVER_ERROR_PLAIN_ACTIVITY, reload_on_server_error,
)


def _page(status: int | None) -> PageText:
    return PageText(url="https://www.upwork.com/jobs/~1", title="Job", text="body", truncated=False, status=status)


class Rig:
    def __init__(self, statuses: list[int | None]) -> None:
        self.statuses = statuses
        self.fetches = 0
        self.slept: list[float] = []
        self.said: list[str] = []

    async def fetch(self) -> PageText:
        self.fetches += 1
        return _page(self.statuses[self.fetches - 1])

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    async def announce(self, words: str) -> None:
        self.said.append(words)

    async def run(self, first: int | None, plain: list[int | None] | None = None) -> PageText:
        page, self.used = await reload_on_server_error(
            _page(first), self.fetch, plain=self._plain(plain) if plain is not None else None,
            sleep=self.sleep, announce=self.announce)
        return page

    def _plain(self, statuses: list[int | None]):
        self.plain_fetches = 0

        async def fetch() -> PageText:
            self.plain_fetches += 1
            return _page(statuses[self.plain_fetches - 1])
        return fetch


async def test_a_good_page_is_never_loaded_again():
    for status in (200, 404, 403, None):
        rig = Rig([])
        assert (await rig.run(status)).status == status and rig.fetches == 0


async def test_a_server_error_is_loaded_again_until_it_works():
    rig = Rig([200])
    page = await rig.run(500)
    assert page.status == 200 and page.notice is None
    assert rig.fetches == 1 and rig.slept == [SERVER_ERROR_RELOAD_WAITS_S[0]]
    assert rig.said == [SERVER_ERROR_ACTIVITY]


async def test_every_kind_of_server_error_counts():
    for status in (500, 502, 503, 504, 522):
        rig = Rig([200])
        assert (await rig.run(status)).status == 200


async def test_a_site_that_stays_down_says_so_after_the_last_try():
    rig = Rig([503] * len(SERVER_ERROR_RELOAD_WAITS_S))
    page = await rig.run(500)
    assert rig.fetches == len(SERVER_ERROR_RELOAD_WAITS_S)
    assert rig.slept == list(SERVER_ERROR_RELOAD_WAITS_S)
    tries = len(SERVER_ERROR_RELOAD_WAITS_S) + 1
    assert page.notice == SERVER_ERROR_DOWN_TEXT.format(status=503, tries=tries)
    assert "www.upwork.com" not in page.notice     # fixed words only


async def test_a_failing_reload_keeps_the_page_there_was():
    class Broken(Rig):
        async def fetch(self) -> PageText:
            raise RuntimeError("gone")

    rig = Broken([])
    page = await rig.run(500)
    assert page.status == 500 and page.notice is not None


# -- the plain address first (owner, 2026-11-01: Upwork's list popup answers 500, its job page 200) ---------------

async def test_the_plain_address_is_tried_first_with_no_wait():
    rig = Rig([])
    page = await rig.run(500, plain=[200])
    assert page.status == 200 and rig.fetches == 0 and rig.slept == []
    assert rig.said == [SERVER_ERROR_PLAIN_ACTIVITY]
    assert rig.used is not rig.fetch            # later repeats load the plain address, not the broken one


async def test_a_failing_plain_address_falls_back_to_reloading():
    rig = Rig([200])
    page = await rig.run(500, plain=[500])
    assert page.status == 200 and rig.plain_fetches == 1 and rig.fetches == 1
    assert rig.used == rig.fetch


async def test_the_notice_never_claims_the_site_is_down_for_sure():
    rig = Rig([500] * len(SERVER_ERROR_RELOAD_WAITS_S))
    page = await rig.run(500)
    assert "may" in page.notice and "main page" in page.notice
