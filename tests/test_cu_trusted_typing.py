"""Owner, 2026-10-27: "if web page is trusted by me on that web page free actions ... why he asked about type".
On a site in the chat's fence (a host you named, or said Yes to on a new-site card), typing into an ordinary box
needs no card. Secrets and contact details still ask, and so does everything that sends: a Send click, Enter in a
box that isn't structurally a search box, a submit. A site outside the fence keeps the old rule."""

from __future__ import annotations

from roost.approvals.floor import floor_of
from roost.computer_use.commit_words import commit_class
from roost.computer_use.fence import SiteFence
from roost.computer_use.models import ActResolution, Box
from roost.desk.page_targets import target_from_ax

_BOX = Box(20, 70, 380, 36)
_EDITABLE = {"name": "editable", "value": {"value": "richtext"}}
_TRUSTED = SiteFence(frozenset({"whatsapp.com"}))


def _box(name: str):
    ax = {"role": {"value": "textbox"}, "name": {"value": name}, "backendDOMNodeId": 7, "properties": [_EDITABLE]}
    return target_from_ax(ax, _BOX, {"tag": "div"})


def _typing(target, *, host: str = "web.whatsapp.com", flags=frozenset()) -> ActResolution:
    return ActResolution("type", f"https://{host}/", host, target, (210, 88), "", "", "browsing",
                         text_ok=False, text_flags=flags)


def test_typing_on_a_trusted_site_needs_no_card():
    for box in (_box(""), _box("Type a message"), _box("Search or start a new chat")):
        assert floor_of(_typing(box), _TRUSTED, typed_chars=500) is None


def test_secrets_and_contact_details_still_ask_on_a_trusted_site():
    box = _box("")
    assert floor_of(_typing(box, flags=frozenset({"secret"})), _TRUSTED, typed_chars=8) == "secret"
    assert floor_of(_typing(box, flags=frozenset({"contact"})), _TRUSTED, typed_chars=8) == "contact"


def test_typing_off_the_trusted_sites_needs_no_card_either():
    """Owner, 2026-11-03: typing never asks; only what sends it does."""
    box = _box("Type a message")
    assert floor_of(_typing(box, host="evil.example"), _TRUSTED, typed_chars=5) is None
    assert floor_of(_typing(box, host="whatsapp.com.evil.example"), _TRUSTED, typed_chars=5) is None
    assert floor_of(_typing(box), None, typed_chars=5) is None


def test_enter_in_a_message_box_still_asks_on_a_trusted_site():
    composer = _box("Type a message")
    assert commit_class(composer, key="Enter") == "unknown"
    press = ActResolution("press_key", "https://web.whatsapp.com/", "web.whatsapp.com", composer, (210, 88), "", "",
                          commit_class(composer, key="Enter"))
    assert floor_of(press, _TRUSTED) == "commit_click"
