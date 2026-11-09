"""C3 Task 7: while the lease is held, the bot's browser keeps to the job's sites, with no downloads, uploads,
prompts or popups. A fake CDP client records every command; nothing starts a browser."""

from __future__ import annotations

import asyncio

import pytest

from roost.computer_use.fence import SiteFence
from roost.desk.browser_guards import BLOCKED_REASON, DENIED_PERMISSIONS, BrowserGuards, fence_allows
from roost.desk.cdp import CdpClientError, CdpReplyError, CdpTimeoutError

FENCE = SiteFence(frozenset({"wikipedia.org"}))


class GuardCdp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str | None]] = []
        self.listeners: list[tuple[frozenset[str], asyncio.Queue]] = []
        self.fail: set[str] = set()

    async def send(self, method, params=None, session_id=None):
        self.calls.append((method, params or {}, session_id))
        if method in self.fail:
            raise CdpReplyError(f"{method} failed")
        if method == "Page.getFrameTree":
            return {"result": {"frameTree": {"frame": {"id": "MAIN"}}}}
        if method == "Target.getTargets":
            return {"result": {"targetInfos": [{"targetId": "OWN", "type": "page"}, {"targetId": "YOURS", "type": "page"}]}}
        return {"result": {}}

    def listen(self, methods):
        queue: asyncio.Queue = asyncio.Queue()
        self.listeners.append((methods, queue))
        return queue

    def unlisten(self, queue):
        self.listeners = [(m, q) for m, q in self.listeners if q is not queue]

    def sent(self, method):
        return [(params, sid) for name, params, sid in self.calls if name == method]


def _paused(url, frame="MAIN", request_id="R1"):
    return {"method": "Fetch.requestPaused", "sessionId": "S",
            "params": {"requestId": request_id, "request": {"url": url}, "frameId": frame, "resourceType": "Document"}}


async def _armed():
    client = GuardCdp()
    guards = BrowserGuards(client, "S", "OWN")
    await guards.arm(FENCE)
    return client, guards


async def test_fence_blocks_a_top_level_navigation_off_the_fence():
    client, guards = await _armed()
    await guards.handle(_paused("https://evil.example/login"))
    assert client.sent("Fetch.failRequest") == [({"requestId": "R1", "errorReason": BLOCKED_REASON}, "S")]
    assert guards.blocked_last() == "evil.example"
    await guards.handle(_paused("https://en.wikipedia.org/wiki/Roost", request_id="R2"))
    assert client.sent("Fetch.continueRequest") == [({"requestId": "R2"}, "S")]
    await guards.handle(_paused("http://127.0.0.1:18800/api", request_id="R3"))     # never a local address
    await guards.handle(_paused("file:///etc/passwd", request_id="R4"))
    assert [p["requestId"] for p, _ in client.sent("Fetch.failRequest")] == ["R1", "R3", "R4"]
    await guards.disarm()


async def test_fence_lets_subresources_through():
    client, guards = await _armed()
    (enable, sid), = client.sent("Fetch.enable")
    assert enable == {"patterns": [{"resourceType": "Document", "requestStage": "Request"}]} and sid == "S"
    await guards.handle(_paused("https://js.payments.example/frame", frame="CHILD"))
    assert client.sent("Fetch.continueRequest") == [({"requestId": "R1"}, "S")]
    assert guards.blocked_last() == ""
    await guards.disarm()


async def test_downloads_are_denied_while_armed_and_restored():
    client, guards = await _armed()
    assert client.sent("Browser.setDownloadBehavior") == [({"behavior": "deny"}, None)]
    await guards.disarm()
    assert client.sent("Browser.setDownloadBehavior")[-1] == ({"behavior": "default"}, None)
    assert client.sent("Fetch.disable") == [({}, "S")]
    assert client.listeners == [] and not guards.armed


async def test_the_file_chooser_never_opens():
    client, guards = await _armed()
    assert client.sent("Page.setInterceptFileChooserDialog") == [({"enabled": True}, "S")]
    assert not guards.chooser_opened()
    await guards.handle({"method": "Page.fileChooserOpened", "params": {"mode": "selectSingle"}})
    assert guards.chooser_opened()
    assert client.sent("Page.handleFileChooser") == []
    await guards.disarm()
    assert client.sent("Page.setInterceptFileChooserDialog")[-1] == ({"enabled": False}, "S")


async def test_permissions_are_denied():
    client, guards = await _armed()
    denied = [params["permission"]["name"] for params, _ in client.sent("Browser.setPermission")]
    assert denied == list(DENIED_PERMISSIONS)
    assert {params["setting"] for params, _ in client.sent("Browser.setPermission")} == {"denied"}
    await guards.disarm()


async def test_a_popup_is_closed_and_its_url_kept():
    client, guards = await _armed()
    await guards.handle({"method": "Target.targetCreated", "params": {"targetInfo": {
        "targetId": "POP", "type": "page", "url": "https://ads.example/win"}}})
    await guards.handle({"method": "Target.targetCreated", "params": {"targetInfo": {
        "targetId": "BLANK", "type": "page", "url": "about:blank"}}})
    for kept in ("OWN", "YOURS"):                         # the bot's tab and pages open before arming stay
        await guards.handle({"method": "Target.targetCreated", "params": {"targetInfo": {
            "targetId": kept, "type": "page", "url": "https://x.example/"}}})
    await guards.handle({"method": "Target.targetCreated", "params": {"targetInfo": {
        "targetId": "W", "type": "service_worker", "url": "https://x.example/sw.js"}}})
    assert [p["targetId"] for p, _ in client.sent("Target.closeTarget")] == ["POP", "BLANK"]
    assert guards.closed_targets() == ("https://ads.example/win",)
    assert client.sent("Target.setDiscoverTargets") == [({"discover": True}, None)]
    await guards.disarm()
    assert client.sent("Target.setDiscoverTargets")[-1] == ({"discover": False}, None)


async def test_arm_is_idempotent_and_swaps_the_fence():
    client, guards = await _armed()
    await guards.arm(SiteFence(frozenset({"evil.example"})))
    assert len(client.sent("Fetch.enable")) == 1 and len(client.listeners) == 1
    await guards.handle(_paused("https://evil.example/"))
    assert client.sent("Fetch.continueRequest") and not client.sent("Fetch.failRequest")
    await guards.disarm()
    await guards.disarm()
    assert len(client.sent("Fetch.disable")) == 1


async def test_the_pump_handles_queued_events_and_survives_a_failed_reply():
    client, guards = await _armed()
    client.fail.add("Fetch.failRequest")
    (_, queue), = client.listeners
    queue.put_nowait(_paused("https://evil.example/", request_id="A"))
    queue.put_nowait(_paused("https://en.wikipedia.org/", request_id="B"))
    for _ in range(10):
        await asyncio.sleep(0)
    assert [p["requestId"] for p, _ in client.sent("Fetch.continueRequest")] == ["B"]
    client.fail.add("Fetch.disable")
    await guards.disarm()                                  # a failed step while disarming is only a warning
    assert client.sent("Browser.setDownloadBehavior")[-1] == ({"behavior": "default"}, None)


@pytest.mark.parametrize("dead", [CdpTimeoutError("timed out"), CdpClientError("not connected")])
async def test_disarm_stops_at_the_first_step_a_dead_browser_does_not_answer(dead):
    # Log 2026-11-07 21:14: a hung browser made each of the four steps wait its whole 30 s timeout in turn.
    client, guards = await _armed()

    async def hung(method, params=None, session_id=None):
        client.calls.append((method, params or {}, session_id))
        raise dead

    client.send, client.calls = hung, []
    await guards.disarm()
    assert [name for name, _, _ in client.calls] == ["Fetch.disable"]


@pytest.mark.parametrize(("url", "allowed"), [
    ("about:blank", True), ("https://wikipedia.org/", True), ("https://en.wikipedia.org/x", True),
    ("https://wikipedia.org.evil.io/", False), ("data:text/html,hi", False), ("javascript:alert(1)", False),
    ("http://[::1]/", False),
])
def test_fence_allows(url, allowed):
    assert fence_allows(FENCE, url) is allowed


async def test_the_cdp_client_queues_every_listened_event_until_unlisten():
    from roost.desk.cdp import CdpClient

    client = CdpClient("ws://127.0.0.1:1/unused", "t")
    queue = client.listen(frozenset({"Fetch.requestPaused"}))
    client._route({"method": "Fetch.requestPaused", "params": {"requestId": "1"}})
    client._route({"method": "Page.loadEventFired", "params": {}})
    client._route({"method": "Fetch.requestPaused", "params": {"requestId": "2"}})
    assert [queue.get_nowait()["params"]["requestId"] for _ in range(2)] == ["1", "2"]
    client.unlisten(queue)
    client._route({"method": "Fetch.requestPaused", "params": {"requestId": "3"}})
    assert queue.empty()


# --- B1 (2026-10-23): a sign-in popup, or one on the fence, stays open as a tab ---------------------------------

def _created(target_id, url, opener=""):
    info = {"targetId": target_id, "type": "page", "url": url, **({"openerId": opener} if opener else {})}
    return {"method": "Target.targetCreated", "params": {"targetInfo": info}}


def _changed(target_id, url):
    return {"method": "Target.targetInfoChanged",
            "params": {"targetInfo": {"targetId": target_id, "type": "page", "url": url}}}


async def test_a_sign_in_popup_and_a_fence_popup_are_kept_as_tabs():
    client, guards = await _armed()
    await guards.handle(_created("G", "https://accounts.google.com/o/oauth2/auth?x=1", opener="OWN"))
    await guards.handle(_created("W", "https://en.wikipedia.org/wiki/Socks", opener="OWN"))
    await guards.handle(_created("AD", "https://ads.example/win", opener="OWN"))
    assert [p["targetId"] for p, _ in client.sent("Target.closeTarget")] == ["AD"]
    assert guards.kept_targets() == ("https://accounts.google.com/o/oauth2/auth?x=1",
                                     "https://en.wikipedia.org/wiki/Socks")
    assert guards.closed_targets() == ("https://ads.example/win",)


async def test_a_blank_popup_from_the_bots_tab_waits_for_its_address():
    client, guards = await _armed()
    await guards.handle(_created("G", "about:blank", opener="OWN"))
    await guards.handle(_created("X", "", opener="OWN"))
    assert client.sent("Target.closeTarget") == []
    await guards.handle(_changed("G", "https://appleid.apple.com/auth"))
    await guards.handle(_changed("X", "https://evil.example/"))
    await guards.handle(_changed("G", "https://evil.example/later"))       # decided once, never again
    assert [p["targetId"] for p, _ in client.sent("Target.closeTarget")] == ["X"]
    assert guards.kept_targets() == ("https://appleid.apple.com/auth",)
