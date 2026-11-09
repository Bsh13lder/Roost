"""Helpers for the approval tests (not a test module): set a bot's approval mode, build a card rig."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roost.approvals.executor import ApprovedCalls
from roost.approvals.service import ApprovalService
from roost.approvals.sessions import SessionOks
from roost.approvals.store import ApprovalStore
from roost.approvals.wiring import ApprovalWiring
from roost.choices.decisions import DecisionBook
from roost.memory.service import MemoryService
from roost.memory.store import MemoryStore
from roost.approvals.models import BotApproval
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.talk.domain_tools import build_domain_tools
from roost.talk.gate import Gate
from roost.talk.new_site import PageOpens
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore

ORIGIN = {"Origin": "http://127.0.0.1:18800"}


async def set_mode(target: Any, bot_id: str, mode: str, topics=(), *, user_id: str | None = None) -> None:
    """Set a bot's approval mode. ``target`` is a logged-in ``httpx.AsyncClient``/``TestClient`` (it uses
    the route), or an app (it uses the store, and then ``user_id`` is needed)."""
    if hasattr(target, "put"):
        response = target.put(f"/api/bots/{bot_id}/approval", json={"mode": mode, "ask_topics": list(topics)},
                              headers=ORIGIN)
        if hasattr(response, "__await__"):
            response = await response
        assert response.status_code == 200, response.text
        return
    assert user_id is not None, "set_mode on an app needs user_id"
    assert await target.state.bots.set_approval(user_id, bot_id, BotApproval(mode, frozenset(topics))) is not None


@dataclass(frozen=True)
class CardRig:
    runner: TurnRunner
    bots: BotStore
    talk: TalkStore
    events: EventHub
    store: ApprovalStore
    sessions: SessionOks
    service: ApprovalService
    model: Any
    wiring: ApprovalWiring
    decisions: Any = None
    desks: Any = None


def make_card_rig(cfg, model, *, mac_files=None, grants=None, limits=None) -> CardRig:
    """A ``TurnRunner`` with approvals wired, and the service that answers its cards. With ``mac_files`` and
    ``grants`` the bots also have the Mac tools."""
    bots, talk, events, desks = BotStore(cfg), TalkStore(cfg), EventHub(cfg), DeskFactory(cfg)
    store, sessions = ApprovalStore(cfg), SessionOks()
    wiring = ApprovalWiring(store, sessions, limits, grants)
    domain = build_domain_tools(cfg, events, mac_files=mac_files, grants=grants, sessions=sessions, limits=limits,
                                desks=desks)
    decisions = DecisionBook(MemoryService(MemoryStore(cfg), events))
    runner = TurnRunner(cfg, bots, talk, events, desks, model, ActivityBoard(), approvals=wiring, domain=domain,
                        decisions=decisions)
    executor = ApprovedCalls(runner.domain, Gate(cfg), talk, events, pages=PageOpens(bots, desks))
    service = ApprovalService(store, talk, events, runner, executor, sessions, decisions=decisions)
    return CardRig(runner, bots, talk, events, store, sessions, service, model, wiring, decisions, desks)
