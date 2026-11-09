"""``send_screenshot`` (owner, 2026-11-05, "the bot should take a screenshot and send it to me"): in a run of your
own chat, the page as ``look`` takes it (every text box painted grey) goes to the chat as a bot message with the
picture attached. A routine, handoff or room run gets a plain refusal; the picture is never logged."""

from __future__ import annotations

import io
from typing import Any, Awaitable, Callable, Mapping

from PIL import Image

from roost.computer_use.look import look
from roost.computer_use.models import ScreenshotIn
from roost.computer_use.outcome import CuOutcome
from roost.constants import SCREENSHOT_DEFAULT_CAPTION
from roost.media.process import CleanPicture
from roost.media.store import ChatMediaStore
from roost.talk.owner_chat import owner_chat_run
from roost.talk.store import TalkStore, message_out
from roost.talk.verdict import GateContext

OUTSIDE_TEXT = "Not sent: I send you my screen only in our own chat, when you're there to see it."
NO_PICTURE_TEXT = "Not sent: the screen didn't give a picture. Look again, then try once more."
SENT_TEXT = "Sent your screen to the chat."


class _Plain:
    """``look`` reads only the expect line here; a screenshot checks nothing."""
    expect = ""
    typed: Mapping[str, str] = {}


def _sized(jpeg: bytes) -> CleanPicture:
    with Image.open(io.BytesIO(jpeg)) as image:
        return CleanPicture(jpeg, image.width, image.height)


async def send_screen(run: Any, page: Any, events: Any, args: ScreenshotIn, ctx: GateContext,
                      arm: Callable[[], Awaitable[str | None]]) -> CuOutcome:
    """Post the screen to ``run``'s chat; ``arm`` is the loop's own lease and control check."""
    if run.thread_id is None or not owner_chat_run(ctx):
        return CuOutcome(OUTSIDE_TEXT)
    refusal = await arm()
    if refusal is not None:
        return CuOutcome(refusal)
    result = await look(page, _Plain(), picture=True)
    if result.image is None:
        return CuOutcome(NO_PICTURE_TEXT)
    caption = (args.caption or "").strip() or SCREENSHOT_DEFAULT_CAPTION
    message = await TalkStore(run.config).add_message(run.user_id, run.thread_id, "bot", caption,
                                                       tainted=ctx.tainted, author_bot_id=run.bot_id)
    media = await ChatMediaStore(run.config).add(run.user_id, run.thread_id, _sized(result.image), source="bot",
                                                 message_id=message.id)
    await events.publish(run.user_id, {"type": "message", "thread_id": run.thread_id,
                                       "message": message_out(message, (media,))})
    return CuOutcome(SENT_TEXT)
