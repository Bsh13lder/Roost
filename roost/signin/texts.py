"""The Sign-in card's words: the bot's card line, your continue sentence, the tool results and the refusals.

User-facing and chat-facing text lives here in one place. Every line says plainly that Roost never sees your
password."""

from __future__ import annotations

NEVER_SEES_PASSWORD = "Roost never sees your password."
# A bot waiting on a Sign-in card is not "Stuck": its status line starts with this calm lead everywhere
# (the header, Home's rows, ``GET /api/bots``); the web reads the lead to draw the calm colour.
SIGN_IN_WAIT_LEAD = "Waiting for you to sign in"
LATER_LINE = "OK, I left {host} for later. Ask me again when you want to sign in."

# request_sign_in's results (model-facing).
SIGN_IN_REQUESTED_TEXT = "Asked: the user will sign in on {host} on your computer. Stop here."
BAD_SIGN_IN_ARGS_TEXT = "Refused: request_sign_in needs a site (a web address or a host) and a short why."
SITE_REFUSED_TEXT = "Refused: that isn't a site I can open for the user to sign in."
SITE_NOT_IN_SCOPE_TEXT = ("Refused: this run has read web content, so you may ask the user to sign in only on the "
                          "page you have open or a site the user named.")

# Route refusals (user-facing).
NOT_SIGN_IN_DETAIL = "This card isn't a sign-in."
KEEP_ANSWER_NEEDED_DETAIL = "Say whether to keep you signed in on this computer: Yes, keep me signed in, or No, this time."
SIGN_OUT_LINUX_ONLY_DETAIL = "Sign out works on a bot's Linux computer. Forget removes the account name only."
SIGN_OUT_BAD_SITE_DETAIL = "Roost can't sign out of that site."


def _clause(text: str) -> str:
    return " ".join(text.split()).rstrip(".")


def sign_in_line(host: str, note: str = "") -> str:
    """The bot's line on a Sign-in card: where, why (its own words, when it gave any), what to do, and the promise."""
    why = f" ({_clause(note)})" if note.strip() else ""
    return (f"{host}'s sign-in page is open on my computer{why}. Take control, type your email and password, "
            f"then press I'm done. {NEVER_SEES_PASSWORD}")


def sign_in_wait_line(host: str) -> str:
    """The status line of a bot waiting on a Sign-in card: "Waiting for you to sign in to accounts.google.com."."""
    return f"{SIGN_IN_WAIT_LEAD} to {host}." if host else f"{SIGN_IN_WAIT_LEAD}."


def not_signed_in_text(host: str) -> str:
    """I'm done on a Sign-in card while the computer doesn't look signed in yet: nothing was saved."""
    return f"You don't look signed in to {host} yet, so nothing was saved."


def kept_sentence(host: str, keep: bool) -> str:
    """Your answer to "Keep me signed in on this computer?", said in your continue line."""
    if keep:
        return f"Stay signed in on {host} on your computer."
    return f"Don't stay signed in on {host}: Roost signs your computer out of it after this task."
