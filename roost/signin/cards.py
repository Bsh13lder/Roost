"""Which block opens a Sign-in card: a sign-in page, ``request_sign_in`` or ``ask_for_help`` naming a sign-in, on a
bot's **Linux** computer with a site to sign in on. Mac Brave bots keep today's Stuck card. Pure."""

from __future__ import annotations

from dataclasses import replace

from roost.desk.stuck import Block


def sign_in_block_for(block: Block, computer: str) -> tuple[Block, bool]:
    """The block the card is opened from, and whether it is a Sign-in card (its reason then reads ``login``)."""
    wants = block.reason == "login" or block.sign_in
    if computer != "linux" or not block.host or not wants:
        return block, False
    return replace(block, reason="login", sign_in=True), True
