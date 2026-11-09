"""Whether a password box on the page holds anything (owner, 2026-11-05, ``use_saved_login``).

Run in an **isolated world** (``roost-login``), so the page's own script cannot redefine ``value``. It returns one
boolean: never the password, its length or which box held it, so nothing secret reaches Roost, a log or the model."""

from __future__ import annotations

from roost.desk.cdp import CdpReplyError
from roost.desk.page_geometry import CdpSender

LOGIN_WORLD = "roost-login"
_FILLED = ("Array.from(document.querySelectorAll('input[type=password]'))"
           ".some(box => typeof box.value === 'string' && box.value.length > 0)")


async def password_filled(client: CdpSender, session_id: str) -> bool:
    """True only when the page's main frame has a password box that holds text."""
    try:
        tree = await client.send("Page.getFrameTree", {}, session_id=session_id)
        frame_id = (((tree.get("result") or {}).get("frameTree") or {}).get("frame") or {}).get("id")
        if not isinstance(frame_id, str) or not frame_id:
            return False
        world = await client.send("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": LOGIN_WORLD},
                                  session_id=session_id)
        context_id = (world.get("result") or {}).get("executionContextId")
        if not isinstance(context_id, int):
            return False
        reply = await client.send("Runtime.evaluate", {"expression": _FILLED, "contextId": context_id,
                                                       "returnByValue": True}, session_id=session_id)
    except CdpReplyError:
        return False
    result = reply.get("result") or {}
    return not result.get("exceptionDetails") and (result.get("result") or {}).get("value") is True
