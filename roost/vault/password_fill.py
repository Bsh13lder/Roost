"""Typing a saved login into the page's own boxes (owner, 2026-11-08, docs/plans/2026-11-08-roost-vault-passwords.md
V6, V8).

``fill_login`` checks the page is the login's own site (``host_serves``), finds the one password box of the top page
(never one inside another site's frame), types the user name into the sign-in box the bot named (when there is one
and it doesn't already hold it; read back), then the password into the password box (focus checked first). It
presses nothing: the bot clicks Sign in. Values stay in this call's arguments: never logged, stored or put in an
event. Errors are ``FillRefused`` with fixed words."""

from __future__ import annotations

from typing import Any, Final

from roost.computer_use.models import PageTarget
from roost.desk import ScreenInput
from roost.desk.page_geometry import viewport_to_screen
from roost.desk.stuck import host_of_url
from roost.vault.passwords import LoginSecret, host_serves

WRONG_SITE_TEXT: Final = "The page is not the saved login's own site, so I didn't type it."
NO_BOX_TEXT: Final = "This page has no password box Roost can type into."
MANY_BOXES_TEXT: Final = "This page has more than one password box, so I didn't type it. Take control to sign in."
NOT_TYPED_TEXT: Final = "The login didn't go into the page's boxes. Look again, or take control to sign in."


class FillRefused(Exception):
    """Nothing more was typed, and ``detail`` says why in fixed words."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _password_box(target: PageTarget) -> bool:
    return target.secret_field and not target.card_field and not target.cross_origin_frame


async def _site_check(page: Any, login: LoginSecret) -> None:
    if not host_serves(login.host, host_of_url(await page.url())):
        raise FillRefused(WRONG_SITE_TEXT)


async def _the_password_box(page: Any) -> PageTarget:
    boxes = [target for target in await page.targets() if _password_box(target)]
    if not boxes:
        raise FillRefused(NO_BOX_TEXT)
    if len(boxes) > 1:
        raise FillRefused(MANY_BOXES_TEXT)
    return boxes[0]


async def _focus(page: Any, desk: Any, box: PageTarget, login: LoginSecret) -> Any:
    """Click the box, check the focus is that same box and the page is still the login's site; select its text."""
    geo = await page.geometry()
    x, y = viewport_to_screen(box.box.center(), geo)
    await desk.send_input(ScreenInput("move", x, y, window=geo.window_rect))
    await desk.send_input(ScreenInput("click", x, y, window=geo.window_rect))
    now = await page.focused()
    if now is None or now.node_id != box.node_id:
        raise FillRefused(NOT_TYPED_TEXT)
    await _site_check(page, login)                 # a redirect between boxes: type nothing more
    await page.select_box(box.node_id)
    return geo


async def _type_user_name(page: Any, desk: Any, box: PageTarget | None, login: LoginSecret) -> None:
    if box is None or box.secret_field or not login.username:
        return
    if (await page.box_text(box.node_id) or "").strip() == login.username:
        return
    geo = await _focus(page, desk, box, login)
    await desk.send_input(ScreenInput("type", text=login.username, window=geo.window_rect))
    if (await page.box_text(box.node_id) or "").strip() != login.username:
        raise FillRefused(NOT_TYPED_TEXT)


async def fill_login(page: Any, desk: Any, user_box: PageTarget | None, login: LoginSecret) -> None:
    """The user name into ``user_box`` (the box the bot named; ``None`` for a page that asks for the password
    alone), then the password into the page's one password box. ``FillRefused`` and nothing more typed otherwise."""
    await _site_check(page, login)
    password_box = await _the_password_box(page)
    await _type_user_name(page, desk, user_box, login)
    geo = await _focus(page, desk, password_box, login)
    await desk.send_input(ScreenInput("type", text=login.password, window=geo.window_rect))
