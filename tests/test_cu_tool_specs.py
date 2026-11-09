"""The screen tools are offered only to Linux-computer bots, never to helpers (C3 Task 11)."""

from __future__ import annotations

import json
from dataclasses import replace

from roost.bots.models import Avatar, Bot, BotStatus
from roost.computer_use.tool_specs import CU_TOOL_DEFS, cu_tools_for
from roost.computer_use.models import OpenAppIn
from roost.constants import CU_ACT_TOOLS, CU_FREE_ACT_TOOLS, CU_OPEN_APPS, CU_TOOLS
from roost.talk.instructions import build_instructions
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import EVERY_BOT_TOOLS, helper_tool_names, run_tool_names, tool_specs_for

_BOT = Bot(id="b1", user_id="u1", name="Scout", job="browses", instructions="", avatar=Avatar("round", "#22c55e", "none"),
           template_id=None, status=BotStatus.RESTING, model_override=None,
           created_at="2026-10-22T00:00:00+00:00", updated_at="2026-10-22T00:00:00+00:00", computer="mac_brave")


def test_linux_bots_get_fifteen_tools_mac_brave_none():
    linux = replace(_BOT, computer="linux")
    # the full computer adds open_app, B1 the tab tools, fast pages read_text and read_pdf, use_saved_login,
    # send_screenshot and use_vault_password
    assert cu_tools_for(linux) == frozenset(CU_TOOLS) and len(CU_TOOLS) == 15
    assert cu_tools_for(_BOT) == frozenset()
    assert frozenset(CU_TOOLS) <= run_tool_names(linux, team=True)
    assert not frozenset(CU_TOOLS) & run_tool_names(_BOT, team=True)
    names = {spec.name for spec in tool_specs_for(linux, team=False)}
    assert frozenset(CU_TOOLS) <= names
    assert not frozenset(CU_TOOLS) & EVERY_BOT_TOOLS


def test_helpers_never_get_screen_tools():
    linux = replace(_BOT, computer="linux")
    assert not frozenset(CU_TOOLS) & helper_tool_names(run_tool_names(linux, team=True))


def test_the_kinds_are_read_and_act():
    kinds = {tool.name: tool.kind for tool in CU_TOOL_DEFS}
    assert kinds == {"look": "read", "wait_ready": "read", "scroll": "read",
                     "click": "act", "type": "act", "press_key": "act", "open_app": "act",
                     "list_tabs": "read", "switch_tab": "act", "close_tab": "act", "read_text": "read",
                     "read_pdf": "read", "use_saved_login": "act", "send_screenshot": "read",
                     "use_vault_password": "act"}
    assert all(CATALOG[name].kind == kinds[name] for name in CU_TOOLS)
    assert {n for n, k in kinds.items() if k == "act"} == CU_ACT_TOOLS | CU_FREE_ACT_TOOLS


def test_no_cu_tool_name_has_control_and_no_description_has_role():
    for tool in CU_TOOL_DEFS:
        assert "control" not in tool.name
        assert " role" not in json.dumps(tool.spec.description) and " role" not in json.dumps(tool.spec.input_schema)
        assert "role" not in json.dumps(tool.spec.input_schema.get("properties", {}))


def test_click_schema_offers_target_or_point_and_expect():
    click = next(t for t in CU_TOOL_DEFS if t.name == "click").spec.input_schema
    assert set(click["properties"]) == {"target", "index", "x", "y", "expect", "owner_words"} and click["required"] == ["expect"]
    typed = next(t for t in CU_TOOL_DEFS if t.name == "type").spec.input_schema
    assert typed["properties"]["source"]["properties"]["from"]["enum"] == ["message", "card", "note", "document"]


def test_instructions_mention_expect_and_facts_from_text():
    linux = build_instructions(replace(_BOT, computer="linux"))
    assert "expect" in linux and "facts" in linux and "from the page text" in linux
    assert "One screen action per step" in linux
    assert "cannot type, click" not in linux
    assert "linux" not in linux.lower()
    mac = build_instructions(_BOT)
    assert "expect" not in mac and "cannot type, click, submit, buy or send anything on a page yet" in mac
    assert "run_program" in linux and "run commands yet" not in linux


def test_open_app_takes_a_fixed_app_or_a_package_name_and_a_reason():
    spec = next(t for t in CU_TOOL_DEFS if t.name == "open_app").spec
    assert spec.input_schema["required"] == ["app"] and set(spec.input_schema["properties"]) == {"app", "why"}
    assert all(app in spec.description for app in CU_OPEN_APPS)
    assert OpenAppIn.model_validate({"app": "files"}).app == "files"
    assert OpenAppIn.model_validate({"app": "geany", "why": "edit the notes"}).why == "edit the notes"
    for bad in ({"app": "Files"}, {"app": "../sh"}, {"app": "files", "x": 1}, {}, {"app": "a"},
                {"app": "files", "why": "x" * 300}):
        try:
            OpenAppIn.model_validate(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_open_app_says_browser_opens_the_browser_when_none_is_open():
    from roost.computer_use.tool_specs import OPEN_APP_SPEC
    assert "opens your browser" in OPEN_APP_SPEC.description


def test_instructions_say_the_whole_computer_is_yours():
    linux = build_instructions(replace(_BOT, computer="linux"))
    assert "The computer is yours" in linux and "open_app" in linux
    assert "whole screen" in linux and "The browser's rules are unchanged" in linux
    # D5: the computer starts with an empty desktop; the bot opens the browser when it needs one, and tidies tabs.
    assert "starts with an empty desktop" in linux and "close_tab" in linux
    mac = build_instructions(_BOT)
    assert "open_app" not in mac


def test_the_prompt_says_a_bot_may_type_its_own_text_and_the_send_card_shows_it():
    # Owner, 2026-11-03: Gigs refused to fill an Upwork proposal ("I can only type your own words"); the gate allows it.
    from roost.computer_use.tool_specs import CLICK_SPEC, TYPE_SPEC
    linux = build_instructions(replace(_BOT, computer="linux"))
    for text in (linux, TYPE_SPEC.description):
        assert "your own text" in text
        assert "Type only the user's own words" not in text and "Any other text must be" not in text
    assert "Send · Don't send · Change it" in linux and "fill the form yourself" in linux
    assert "never ask the user to paste your text back" in linux
    assert "After Don't send, stop and wait" in linux
    assert "your own text" in CLICK_SPEC.description and "always shows" in CLICK_SPEC.description
    assert "optional" in TYPE_SPEC.input_schema["properties"]["source"]["description"].lower()
