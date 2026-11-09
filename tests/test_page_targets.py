"""C3 Task 6: the bot's page lists its controls with their labels, forms and boxes over CDP.

Every page is a fixture (``tests/fixtures/cu_ax_*.json``) served by ``FakeCdp``; nothing starts a browser."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from cu_page_helpers import FakeCdp, load_fixture, session_of

from roost.computer_use.commit_words import commit_class
from roost.computer_use.models import Box
from roost.desk import PageText
from roost.desk.browser import DeskBrowserPage
from roost.desk.page_targets import CdpPageDriver, box_from_quad, same_label, target_from_ax, visible_part


async def _no_facts() -> PageText:
    return PageText(url="", title="", text="", truncated=False)


def _driver(name: str) -> tuple[CdpPageDriver, FakeCdp]:
    client = FakeCdp(load_fixture(name))
    return CdpPageDriver(session_of(client), _no_facts), client


def _by_text(targets, text):
    return next(t for t in targets if t.text == text)


async def test_targets_lists_only_interactive_nodes_in_view():
    driver, _ = _driver("login")
    targets = await driver.targets()
    texts = [t.text for t in targets]
    assert texts == ["Email", "Password", "Sign in", "Forgot password?", "Digits", "One-time code", "Verify",
                     "Zip", "New password"]
    assert "Footer link" not in texts            # below the viewport
    assert "Hidden" not in texts                 # ignored by the accessibility tree
    assert "Welcome back" not in texts           # static text is not a control
    sign_in = _by_text(targets, "Sign in")
    assert (sign_in.kind, sign_in.tag, sign_in.box) == ("button", "button", Box(400, 300, 100, 36))
    assert _by_text(targets, "Forgot password?").link_host == "shop.example"


async def test_find_by_text_and_kind_with_nth():
    driver, _ = _driver("search")
    second = await driver.find("read more", "link", 2)
    assert second is not None and second.link_host == "news.example"
    assert (await driver.find("Read more", "any", 1)).link_host == "wiki.example"
    assert await driver.find("Read more", "button", 1) is None
    assert await driver.find("Read more", "link", 3) is None


async def test_find_is_exact_text_not_substring():
    driver, _ = _driver("search")
    found = await driver.find("Submit", "button", 1)
    assert found is not None and found.text == "Submit"
    assert await driver.find("Submit", "button", 2) is None
    assert await driver.find("Subm", "any", 1) is None
    assert same_label("Read  more", "read more") and not same_label("Submit", "Submit later")


async def test_node_at_climbs_to_the_button():
    driver, client = _driver("dialog")
    target = await driver.node_at(650, 415)       # the span inside "No thanks"
    assert target is not None and (target.text, target.kind) == ("No thanks", "button")
    assert target.in_dialog == "Join our newsletter"
    assert await driver.node_at(10, 600) is None  # plain words: nothing to click
    assert await driver.node_at(5, 5) is None     # the browser places nothing there
    assert ("DOM.getNodeForLocation", {"x": 650, "y": 415, "includeUserAgentShadowDOM": True,
                                       "ignorePointerEventsNone": False}) in client.calls


async def test_the_hit_test_is_what_a_real_click_reaches():
    """A see-through layer (pointer-events: none, as WhatsApp lays over its filter tabs) never covers a control:
    the browser hit-tests as a click would, skipping such layers. True would hit the layer and say "something"."""
    driver, client = _driver("dialog")
    targets = await driver.targets()
    assert await driver.covering(_by_text(targets, "Save")) == ""
    hits = [params for method, params in client.calls if method == "DOM.getNodeForLocation"]
    assert hits and all(params["ignorePointerEventsNone"] is False for params in hits)


async def test_a_dialog_over_the_button_is_reported():
    driver, _ = _driver("dialog")
    targets = await driver.targets()
    assert await driver.covering(_by_text(targets, "Delete")) == "Join our newsletter"
    assert await driver.covering(_by_text(targets, "Save")) == ""
    assert await driver.covering(_by_text(targets, "No thanks")) == ""


async def test_a_centre_nothing_answers_counts_as_covered():
    driver, _ = _driver("cookie")
    targets = await driver.targets()
    assert await driver.covering(_by_text(targets, "Next story")) == "something"


async def test_password_and_one_time_code_are_secret_fields():
    driver, _ = _driver("login")
    targets = await driver.targets()
    secret = {t.text: t.secret_field for t in targets}
    assert secret["Password"] and secret["One-time code"] and secret["New password"]
    assert secret["Digits"]                        # numeric, 6 long, in a form that mentions a code
    assert not secret["Zip"]                       # numeric, 5 long, but the form never mentions a code
    assert not secret["Email"]
    assert all(t.editable for t in targets if t.kind == "field")


async def test_form_method_and_default_submit_are_read():
    driver, _ = _driver("checkout")
    targets = await driver.targets()
    holder, coupon = _by_text(targets, "Card holder"), _by_text(targets, "Apply coupon")
    place, later = _by_text(targets, "Place order"), _by_text(targets, "Pay later")
    assert (holder.form_method, holder.form_submit_text, holder.is_form_submit) == ("post", "Place order", False)
    assert not coupon.is_form_submit and place.is_form_submit and later.is_form_submit
    assert commit_class(holder, key="Enter") == "spend"
    assert _by_text(targets, "Order details").expands and _by_text(targets, "Order details").form_method == ""
    search, _ = _driver("search")
    go = _by_text(await search.targets(), "Go")
    assert (go.form_method, go.searchish, commit_class(go)) == ("get", True, "browsing")


async def test_cookie_banner_buttons_are_in_consent():
    driver, _ = _driver("cookie")
    targets = await driver.targets()
    reject = _by_text(targets, "Reject all")
    assert reject.in_consent and reject.in_dialog == "We use cookies"
    assert commit_class(reject) == "consent" and commit_class(_by_text(targets, "Accept all")) == "accept"
    assert not _by_text(targets, "Next story").in_consent


async def test_cross_origin_iframe_is_marked():
    driver, _ = _driver("iframe")
    targets = await driver.targets()
    frame = _by_text(targets, "Secure card payment input frame")
    assert frame.cross_origin_frame and frame.kind == "frame" and commit_class(frame) == "unknown"
    assert not _by_text(targets, "Help").cross_origin_frame
    assert all(t.text != "Shop widget" for t in targets)     # a same-origin frame is not a control itself
    hit = await driver.node_at(300, 130)
    assert hit is not None and hit.cross_origin_frame
    inner = await driver.node_at(140, 225)
    assert inner is not None and inner.text == "Help" and not inner.cross_origin_frame


def _input_with_inner_editor(shadow_type: str) -> dict:
    """WhatsApp's search box (2026-10-27): an <input> whose user-agent shadow root holds Chromium's inner editor,
    a generic editable the accessibility tree lists and the hit test reaches."""
    return {
        "url": "https://web.whatsapp.com/", "viewport": [800, 600],
        "dom": {"id": 1, "tag": "html", "children": [{"id": 2, "tag": "body", "children": [
            {"id": 541, "tag": "input", "attrs": {"type": "text", "aria-label": "Search or start a new chat"},
             "shadow": {"id": 1847, "type": shadow_type, "children": [{"id": 1257, "tag": "div"}]}}]}]},
        "ax": [{"role": "textbox", "name": "Search or start a new chat", "backend": 541,
                "props": {"focusable": True, "editable": "plaintext", "focused": True}},
               {"role": "generic", "name": "", "backend": 1257, "props": {"editable": "plaintext"}}],
        "boxes": {"541": [133, 76, 420, 20], "1257": [133, 76, 420, 20]},
        "hits": {"343,86": 1257},
    }


async def test_an_inputs_inner_editor_is_the_input_itself():
    client = FakeCdp(_input_with_inner_editor("user-agent"))
    driver = CdpPageDriver(session_of(client), _no_facts)
    fields = [t for t in await driver.targets() if t.kind == "field"]
    assert [(t.node_id, t.text) for t in fields] == [(541, "Search or start a new chat")]
    hit = await driver.node_at(343, 86)
    assert hit is not None and (hit.node_id, hit.text) == (541, "Search or start a new chat")
    focused = await driver.focused()
    assert focused is not None and focused.node_id == 541


async def test_a_pages_own_shadow_root_keeps_its_controls():
    client = FakeCdp(_input_with_inner_editor("open"))
    driver = CdpPageDriver(session_of(client), _no_facts)
    hit = await driver.node_at(343, 86)
    assert hit is not None and hit.node_id == 1257          # a web component's own editable is a real control


async def test_text_box_values_are_never_read():
    for name in ("login", "search"):
        driver, _ = _driver(name)
        dumped = json.dumps([asdict(t) for t in await driver.targets()])
        focused = await driver.focused()
        dumped += json.dumps(asdict(focused)) if focused else ""
        for secret in ("hunter2", "me@private.example", "my secret query", "my secret draft", "rich secret"):
            assert secret not in dumped


async def test_focused_is_the_focused_field():
    driver, _ = _driver("login")
    focused = await driver.focused()
    assert focused is not None and focused.text == "Password" and focused.secret_field
    none_focused, _ = _driver("checkout")
    assert await none_focused.focused() is None


async def test_dom_is_switched_off_after_each_read():
    driver, client = _driver("login")
    await driver.targets()
    assert client.methods()[-1] == "DOM.disable"


async def test_url_screenshot_and_geometry_use_the_session():
    driver, client = _driver("login")
    assert await driver.url() == "https://shop.example/login"
    assert (await driver.screenshot())[:2] == b"\xff\xd8"
    probe = await driver.screenshot(probe=True)
    from io import BytesIO

    from PIL import Image
    with Image.open(BytesIO(probe)) as image:
        assert image.size == (160, 100)
    assert ("Page.captureScreenshot", {"format": "jpeg", "quality": 60, "captureBeyondViewport": False}) in client.calls
    assert (await driver.facts()).url == ""


def test_target_from_ax_is_pure():
    node = {"role": {"value": "tab"}, "name": {"value": "  Prices\n tab "}, "backendDOMNodeId": 7}
    target = target_from_ax(node, Box(1, 2, 3, 4), {"tag": "div"})
    assert (target.kind, target.text, target.expands, target.node_id) == ("tab", "Prices tab", True, 7)
    assert box_from_quad([10, 20, 30, 20, 30, 50, 10, 50]) == Box(10, 20, 20, 30)
    assert visible_part(Box(-10, 0, 20, 10), Box(0, 0, 100, 100)) == Box(0, 0, 10, 10)
    assert visible_part(Box(200, 0, 20, 10), Box(0, 0, 100, 100)) is None


class _GeoCdp(FakeCdp):
    def _Browser_getWindowForTarget(self, params):
        return {"windowId": 1, "bounds": {"left": 0, "top": 0, "width": 1280, "height": 800, "windowState": "normal"}}

    def _Page_getFrameTree(self, params):
        return {"frameTree": {"frame": {"id": "F"}}}

    def _Page_createIsolatedWorld(self, params):
        return {"executionContextId": 9}

    def _Runtime_evaluate(self, params):
        return {"result": {"value": [1280, 800, 1280, 690]}}


async def test_geometry_brings_the_tab_up_first():
    client = _GeoCdp(load_fixture("login"))
    driver = CdpPageDriver(session_of(client), _no_facts)
    geo = await driver.geometry()
    assert (geo.inner_w, geo.inner_h) == (1280, 690)
    assert client.methods()[0] == "Page.bringToFront"


class _TabCdp(FakeCdp):
    def _Target_createTarget(self, params):
        return {"targetId": "T"}

    def _Target_attachToTarget(self, params):
        return {"sessionId": "S9"}

    def _Page_getFrameTree(self, params):
        return {"frameTree": {"frame": {"id": "F"}}}


async def test_the_browser_page_hands_out_its_client_and_session():
    async def no_wait(_seconds: float) -> None:
        return None

    client = _TabCdp(load_fixture("search"))
    page = DeskBrowserPage(client, sleep=no_wait)   # type: ignore[arg-type]
    assert await page.page_session() == (client, "S9")
    driver = page.page_driver()
    assert isinstance(driver, CdpPageDriver)
    assert await driver.url() == "https://wiki.example/"


@pytest.mark.parametrize("name", ["login", "checkout", "search", "cookie", "dialog", "iframe", "chat"])
async def test_every_fixture_reads(name):
    driver, _ = _driver(name)
    assert await driver.targets()


def test_a_linux_keeper_desk_has_a_page_driver_and_mac_brave_has_none(tmp_path):
    from roost.config import RoostConfig
    from roost.desk.client import KeeperDesk

    config = RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "d", desks_dir=tmp_path / "k",
                         keeper_secret="k" * 32)
    assert isinstance(KeeperDesk(config, "b", computer="linux").page(), CdpPageDriver)
    assert KeeperDesk(config, "b", computer="mac_brave").page() is None


def _of(targets, text, kind):
    return next(t for t in targets if t.text == text and t.kind == kind)


async def test_a_form_with_no_method_is_not_a_search_form():
    # Security review (a): scripted chat forms rarely say method="post"; their boxes are not search boxes.
    driver, _ = _driver("chat")
    targets = await driver.targets()
    message = _of(targets, "Message", "field")
    assert message.form_method == "get" and not message.searchish
    assert message.form_submit_text == "Send" and commit_class(message, key="Enter") == "send"
    find = _of(targets, "Find", "field")
    assert find.searchish and commit_class(find, key="Enter") == "browsing"   # an explicit method="get"


async def test_a_role_or_an_aria_label_cannot_hide_a_buy_button():
    driver, _ = _driver("chat")
    targets = await driver.targets()
    fake_box = _of(targets, "Buy now", "field")
    assert fake_box.tag == "button" and commit_class(fake_box) == "spend"
    pay = _of(targets, "Next page", "link")
    assert pay.visible_text == "Pay now" and commit_class(pay) == "spend"
    assert _of(targets, "Jobs", "link").visible_text == ""        # named by its own words: nothing extra
    assert all(t.visible_text == "" for t in targets if t.kind == "field" and t.tag != "button")


async def test_a_search_landmark_makes_its_box_searchish():
    driver, _ = _driver("search")
    box = _of(await driver.targets(), "Search", "field")
    assert box.searchish


def _ax(role: str, name: str, focusable: bool) -> dict:
    props = [{"name": "focusable", "value": {"type": "boolean", "value": True}}] if focusable else []
    return {"role": {"value": role}, "name": {"value": name}, "backendDOMNodeId": 7, "properties": props}


@pytest.mark.parametrize("role", ["gridcell", "row", "treeitem"])
def test_a_focusable_list_row_is_a_row_you_can_click(role):
    """WhatsApp's chats are focusable grid cells (2026-10-25): a click on one must find it, as browsing."""
    target = target_from_ax(_ax(role, "Francis Friday Photo", focusable=True), Box(0, 0, 300, 72), {"tag": "div"})
    assert target.kind == "row"
    assert commit_class(target) == "browsing"


@pytest.mark.parametrize("role", ["gridcell", "row", "cell"])
def test_a_plain_table_row_is_not_a_control(role):
    target = target_from_ax(_ax(role, "Totals 120", focusable=False), Box(0, 0, 300, 20), {"tag": "td"})
    assert target.kind == "any"


def test_a_row_that_says_an_action_still_commits():
    target = target_from_ax(_ax("gridcell", "Pay now", focusable=True), Box(0, 0, 300, 72), {"tag": "div"})
    assert commit_class(target) == "spend"


async def test_target_for_reads_a_numbered_control_again_and_marks_its_focus():
    """Fast pages: a look's number is a backend node; it is read again live, and gone or out of view is None."""
    driver, _ = _driver("login")
    targets = await driver.targets()
    password = _by_text(targets, "Password")
    assert password.focused and not _by_text(targets, "Email").focused
    again = await driver.target_for(password.node_id)
    assert again is not None and again.text == "Password" and again.focused
    footer = next(n["backend"] for n in load_fixture("login")["ax"] if n.get("name") == "Footer link")
    assert await driver.target_for(footer) is None              # below the viewport
    assert await driver.target_for(999_999) is None              # gone


async def test_link_url_is_the_links_full_address_and_empty_for_anything_else():
    """Fast pages, slice 5: read_pdf fetches the address a numbered link goes to, read from the DOM."""
    driver, _ = _driver("search")
    first = await driver.find("Read more", "link", 1)
    second = await driver.find("Read more", "link", 2)
    assert await driver.link_url(first.node_id) == "https://wiki.example/a"
    assert await driver.link_url(second.node_id) == "https://news.example/b"
    submit = await driver.find("Submit", "button", 1)
    assert await driver.link_url(submit.node_id) == ""


# Owner, 2026-11-04: Upwork's "Yes, I understand." checkbox is an sr-only 1x1 input inside its label, with a drawn
# box beside it. Every click said the dialog covered it, or found nothing at the drawn box.
async def test_a_visually_hidden_checkbox_aims_at_its_label():
    driver, _ = _driver("terms")
    targets = await driver.targets()
    agree, news = _by_text(targets, "Yes, I understand."), _by_text(targets, "Send me news")
    assert (agree.kind, agree.node_id, agree.box) == ("checkbox", 31, Box(287, 463, 685, 21))
    assert news.box == Box(287, 500, 200, 21)                 # a label tied by for= counts too
    assert agree.in_dialog == "3 things you need to know"
    assert commit_class(agree) != "unknown"


async def test_a_hidden_checkbox_in_the_open_dialog_is_not_covered():
    driver, _ = _driver("terms")
    targets = await driver.targets()
    assert await driver.covering(_by_text(targets, "Yes, I understand.")) == ""
    assert await driver.covering(_by_text(targets, "Send me news")) == ""
    assert await driver.covering(_by_text(targets, "Continue")) == ""


async def test_a_click_on_the_drawn_box_or_the_label_is_the_checkbox():
    driver, _ = _driver("terms")
    drawn = await driver.node_at(297, 473)                    # the fake box's icon inside the label
    assert drawn is not None and (drawn.node_id, drawn.kind, drawn.text) == (31, "checkbox", "Yes, I understand.")
    assert drawn.box == Box(287, 463, 685, 21)
    by_for = await driver.node_at(387, 510)
    assert by_for is not None and by_for.node_id == 38
    assert (await driver.target_for(31)).box == Box(287, 463, 685, 21)


async def test_a_click_on_the_hidden_checkbox_resolves_to_a_browsing_click_nothing_refuses():
    from roost.computer_use.models import ClickIn
    from roost.computer_use.resolve import resolve_click
    driver = CdpPageDriver(session_of(_GeoCdp(load_fixture("terms"))), _no_facts)
    url = "https://www.upwork.com/nx/proposals/job/~1/apply/"
    by_point = await resolve_click(driver, ClickIn(x=297, y=473, expect="the box is ticked"), url)
    by_index = await resolve_click(driver, ClickIn(index=1, expect="the box is ticked"), url,
                                   aimed=await driver.target_for(31))
    for r in (by_point, by_index):
        assert r.target is not None and r.target.node_id == 31
        assert (r.covered_by, r.refusal, r.commit) == ("", "", "browsing")
    assert by_index.point == (630, 474)                       # the label's middle, where a person clicks


# Owner, 2026-11-04: Wizz Air's "No thanks" is a 13 px see-through radio in its label, inside a web component; its
# centre hits the drawn circle, a ::after pseudo-element. Pseudo-elements weren't indexed, so every click said covered.
def test_a_pseudo_element_counts_as_part_of_the_element_it_draws():
    from roost.desk.page_dom import DomIndex
    after = {"backendNodeId": 7, "nodeType": 1, "nodeName": "::after", "localName": "::after", "pseudoType": "after"}
    radio = {"backendNodeId": 5, "nodeType": 1, "nodeName": "INPUT", "localName": "input",
             "attributes": ["type", "radio", "id", "none"], "pseudoElements": [after]}
    label = {"backendNodeId": 4, "nodeType": 1, "nodeName": "LABEL", "localName": "label",
             "attributes": ["for", "none"], "children": [radio]}
    host = {"backendNodeId": 2, "nodeType": 1, "nodeName": "HTS-FLIGHTS", "localName": "hts-flights",
            "shadowRoots": [{"backendNodeId": 3, "nodeType": 11, "nodeName": "#document-fragment", "children": [label]}]}
    index = DomIndex.build({"backendNodeId": 1, "nodeType": 9, "nodeName": "#document", "children": [host]}, "x")
    assert index.node(7) is not None
    assert index.is_inside(7, 4) and index.label_of_toggle(5) == 4
