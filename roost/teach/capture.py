"""One teach intent → one ``TeachStep`` read from the live page (Chromium's own AX names, never a field's value).

A press is turned from screen pixels into viewport pixels with the window geometry; a press above or beside the
page (the tab strip, the address bar) is a ``browser`` step. Typing and a paste name the focused field; a secret
field (password, one-time code) becomes a ``password`` step. Nothing here reads what was typed: there is nothing
to read, the socket's bytes never reach this module."""

from __future__ import annotations

from typing import Any

from roost.computer_use.models import PageTarget
from roost.desk.page_geometry import WindowGeometry
from roost.teach.input import Intent, NamedKey, Paste, Press, Typing
from roost.teach.models import TeachStep, url_parts

_KEYS = ("Enter", "Tab", "Escape")
_PASSWORD_TYPE = "password"


async def _where(page: Any) -> dict[str, str]:
    host, path = url_parts(await page.url())
    return {"host": host, "path": path, "title": await page.title() if host else ""}


def _viewport_point(x: int, y: int, geo: WindowGeometry) -> tuple[int, int] | None:
    vx, vy = x - (geo.left + geo.border), y - geo.page_top
    if 0 <= vx < geo.inner_w and 0 <= vy < geo.inner_h:
        return vx, vy
    return None


def _is_secret(target: PageTarget | None) -> bool:
    return target is not None and (target.secret_field or target.input_type == _PASSWORD_TYPE)


def _control(target: PageTarget | None) -> dict[str, str]:
    return {"role": target.kind, "label": target.text} if target is not None else {}


async def _press(page: Any, press: Press, geo: WindowGeometry) -> TeachStep:
    point = _viewport_point(press.x, press.y, geo)
    if point is None:
        return TeachStep(kind="browser")
    target = await page.node_at(*point)
    return TeachStep(kind="click", **await _where(page), **_control(target))


async def _into_field(page: Any, kind: str, address_bar: bool) -> TeachStep:
    if address_bar:
        return TeachStep(kind=kind)
    target = await page.focused()
    return TeachStep(kind="password" if _is_secret(target) else kind, **await _where(page), **_control(target))


async def capture(page: Any, intent: Intent, geo: WindowGeometry, *, address_bar: bool = False) -> TeachStep:
    """The step for ``intent``. ``address_bar``: the last press was outside the page, so typing went there."""
    if isinstance(intent, Press):
        return await _press(page, intent, geo)
    if isinstance(intent, Typing):
        return await _into_field(page, "type", address_bar)
    if isinstance(intent, Paste):
        return await _into_field(page, "paste", address_bar)
    assert isinstance(intent, NamedKey)
    key = intent.name if intent.name in _KEYS else ""
    return TeachStep(kind="key", key=key, **await _where(page))
