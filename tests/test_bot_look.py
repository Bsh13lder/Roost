"""Bot avatars (avatars v7, the Lensbots): eighteen Lensbot shapes, every old shape (the ten ghosts,
the six Boxbot heads and the S1.6 birds) still accepted, the screen style still accepted though no
longer drawn, an optional role (the job's emblem), and a colour no teammate wears for a new bot. The
gateway stores a shape as sent; the web draws it, so the web's one table must give every accepted
shape a Lensbot."""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from roost.bots.look import avatar_dict, next_bot_color
from roost.bots.models import Avatar, AvatarScreen, AvatarShape, BotRole
from roost.constants import (
    AVATAR_SHAPES, BOT_DEFAULT_COLORS, BOT_ROLES, DEFAULT_LENSBOT_SHAPE, GHOST_SHAPES, LEGACY_AVATAR_SHAPES,
    LENSBOT_SHAPES, ROBOT_HEADS, ROBOT_SCREENS,
)
from roost.gateway.app import create_app

ROOT = Path(__file__).resolve().parents[1]
WEB_LOOK = ROOT / "web" / "src" / "components" / "robot" / "look.ts"
WEB_PALETTE = ROOT / "web" / "src" / "components" / "robot" / "palette.ts"
O = {"Origin": "http://127.0.0.1:18800"}
OLD_BIRD_SHAPES = ("round", "tall", "wide", "egg", "pear", "plump", "crest")   # S1.6


def _web_list(text: str, name: str) -> list[str]:
    block = re.search(rf"{name}[^=]*=\s*\[(.*?)\];", text, re.DOTALL)
    assert block, f"{name} not found"
    return re.findall(r'"([^"]+)"', block.group(1))


def _web_table(text: str, name: str) -> dict[str, str]:
    block = re.search(rf"{name}[^=]*=\s*\{{(.*?)\}};", text, re.DOTALL)
    assert block, f"{name} not found"
    return dict(re.findall(r'(\w+):\s*"(\w+)"', block.group(1)))


def _client() -> TestClient:
    client = TestClient(create_app())
    assert client.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"},
                       headers=O).status_code == 201
    return client


LENSBOTS = ("mochi", "loaf", "gumdrop", "pebble", "bun", "acorn", "marsh", "dumpling", "muffs", "squish", "cub",
            "sprout", "cheeky", "tower", "helmet", "bell", "puck", "pod")


def test_the_shape_lists_are_one_list():
    assert LENSBOT_SHAPES == LENSBOTS
    assert DEFAULT_LENSBOT_SHAPE == "mochi"
    assert GHOST_SHAPES == ("dome", "tall", "wide", "round", "droopy", "spire", "comet", "cape", "puff", "hooded")
    assert get_args(AvatarShape) == AVATAR_SHAPES
    assert AVATAR_SHAPES[:18] == LENSBOT_SHAPES
    assert AVATAR_SHAPES[18:28] == GHOST_SHAPES
    assert len(set(AVATAR_SHAPES)) == len(AVATAR_SHAPES)   # "tall", "wide" and "round" are listed once
    assert set(ROBOT_HEADS) | set(LEGACY_AVATAR_SHAPES) | set(GHOST_SHAPES) | set(LENSBOT_SHAPES) == set(AVATAR_SHAPES)
    assert get_args(AvatarScreen) == ROBOT_SCREENS
    assert set(OLD_BIRD_SHAPES) <= set(AVATAR_SHAPES)   # every S1.6 value stays valid


def test_the_roles_are_one_list():
    assert BOT_ROLES == ("general", "tasks", "code", "seo", "money", "social", "research", "writer")
    assert get_args(BotRole) == BOT_ROLES
    assert _web_list(WEB_LOOK.read_text(encoding="utf-8"), "BOT_ROLES") == list(BOT_ROLES)


def test_every_shape_the_gateway_accepts_has_a_lensbot_on_the_web():
    look = WEB_LOOK.read_text(encoding="utf-8")
    lensbots = _web_list(look, "LENSBOT_SHAPES")
    table = _web_table(look, "LEGACY_SHAPE_TO_LENSBOT")
    assert lensbots == list(LENSBOT_SHAPES)
    assert list(table) == [shape for shape in AVATAR_SHAPES if shape not in LENSBOT_SHAPES]   # the one table, in order
    assert set(table.values()) <= set(LENSBOT_SHAPES)
    assert [shape for shape in AVATAR_SHAPES if shape not in lensbots and shape not in table] == []
    assert _web_list(look, "ROBOT_SCREENS") == list(ROBOT_SCREENS)


def test_the_web_and_the_gateway_share_the_default_colours():
    assert _web_list(WEB_PALETTE.read_text(encoding="utf-8"), "BOT_DEFAULT_COLORS") == list(BOT_DEFAULT_COLORS)


def test_a_new_bot_takes_the_first_colour_no_teammate_wears():
    assert next_bot_color([]) == "#8b5cf6"
    assert next_bot_color(["#8B5CF6", "#22c55e"]) == "#3b82f6"
    assert next_bot_color(list(BOT_DEFAULT_COLORS)) == BOT_DEFAULT_COLORS[0]
    assert next_bot_color([*BOT_DEFAULT_COLORS, "#ffffff"]) == BOT_DEFAULT_COLORS[1]


def test_an_avatar_on_the_wire_names_its_screen():
    assert avatar_dict(Avatar("egg", "#14b8a6", "none")) == {
        "shape": "egg", "color": "#14b8a6", "badge": "none", "screen": "glow"}


def test_an_avatar_on_the_wire_names_its_role_only_when_it_has_one():
    assert avatar_dict(Avatar("mochi", "#14b8a6", "none", role="seo")) == {
        "shape": "mochi", "color": "#14b8a6", "badge": "none", "screen": "glow", "role": "seo"}
    assert "role" not in avatar_dict(Avatar("mochi", "#14b8a6", "none"))


def test_a_role_is_stored_and_read_back_and_an_old_avatar_has_none():
    client = _client()
    made = client.post("/api/bots", headers=O, json={"name": "Coder", "job": "writes code", "instructions": "",
                                                     "avatar": {"shape": "marsh", "color": "#3b82f6", "role": "code"}})
    assert made.status_code == 201
    assert made.json()["avatar"]["role"] == "code"
    bot_id = made.json()["id"]
    assert client.get(f"/api/bots/{bot_id}", headers=O).json()["avatar"]["role"] == "code"
    changed = client.patch(f"/api/bots/{bot_id}", headers=O,
                           json={"avatar": {"shape": "marsh", "color": "#3b82f6", "role": "writer"}})
    assert changed.json()["avatar"]["role"] == "writer"
    cleared = client.patch(f"/api/bots/{bot_id}", headers=O, json={"avatar": {"shape": "marsh", "color": "#3b82f6"}})
    assert "role" not in cleared.json()["avatar"]   # no role: it counts as general


def test_a_shared_template_file_carries_the_role():
    client = _client()
    made = client.post("/api/bots", headers=O, json={"name": "Ledger", "job": "keeps the budget", "instructions": "",
                                                     "avatar": {"shape": "bun", "color": "#22c55e", "role": "money"}})
    file = client.get(f"/api/bots/{made.json()['id']}/template", headers=O).json()
    assert file["avatar"]["role"] == "money"
    checked = client.post("/api/templates/check", headers=O, json={"file": file})
    assert checked.status_code == 200
    assert checked.json()["avatar"]["role"] == "money"
    plain = {**file, "avatar": {"shape": "bun", "color": "#22c55e"}}   # a file from before the roles
    assert "role" not in client.post("/api/templates/check", headers=O, json={"file": plain}).json()["avatar"]


def test_every_role_is_accepted_and_an_unknown_role_is_refused():
    client = _client()
    for number, role in enumerate(BOT_ROLES):
        body = {"name": f"Role {number}", "job": "works", "instructions": "",
                "avatar": {"shape": "pod", "color": "#3b82f6", "role": role}}
        made = client.post("/api/bots", headers=O, json=body)
        assert made.status_code == 201, role
        assert made.json()["avatar"]["role"] == role
    for bad in ("hacker", "", "SEO", 3):
        body = {"name": "Nope", "job": "works", "instructions": "",
                "avatar": {"shape": "pod", "color": "#3b82f6", "role": bad}}
        assert client.post("/api/bots", headers=O, json=body).status_code == 422, bad


def test_a_ghost_shape_is_stored_and_an_old_bird_shape_is_still_accepted():
    client = _client()
    made = client.post("/api/bots", headers=O, json={"name": "Scout", "job": "finds", "instructions": "",
                                                     "avatar": {"shape": "hooded", "color": "#3b82f6", "screen": "pixel"}})
    assert made.status_code == 201
    assert made.json()["avatar"] == {"shape": "hooded", "color": "#3b82f6", "badge": "none", "screen": "pixel",
                                     "picture": None}
    old = client.patch(f"/api/bots/{made.json()['id']}", headers=O,
                       json={"avatar": {"shape": "egg", "color": "#14b8a6", "badge": "none"}})
    assert old.status_code == 200
    assert old.json()["avatar"] == {"shape": "egg", "color": "#14b8a6", "badge": "none", "screen": "glow",
                                    "picture": None}


def test_every_shape_the_gateway_has_ever_taken_is_stored_as_sent_with_no_badge_or_screen():
    client = _client()
    for number, shape in enumerate(AVATAR_SHAPES):
        body = {"name": f"Bot {number}", "job": "works", "instructions": "",
                "avatar": {"shape": shape, "color": "#3b82f6"}}   # an old client: no badge, no screen
        made = client.post("/api/bots", headers=O, json=body)
        assert made.status_code == 201, shape
        assert made.json()["avatar"] == {"shape": shape, "color": "#3b82f6", "badge": "none", "screen": "glow",
                                         "picture": None}
        kept = client.get(f"/api/bots/{made.json()['id']}", headers=O).json()["avatar"]
        assert kept["shape"] == shape and kept["screen"] == "glow", shape


def test_an_unknown_shape_or_screen_is_refused():
    client = _client()
    for avatar in ({"shape": "hexagon", "color": "#3b82f6"}, {"shape": "classic", "color": "#3b82f6", "screen": "neon"}):
        body = {"name": "Scout", "job": "finds", "instructions": "", "avatar": avatar}
        assert client.post("/api/bots", headers=O, json=body).status_code == 422


def test_the_templates_wear_robot_heads_and_all_three_screens():
    client = _client()
    looks = [template["avatar"] for template in client.get("/api/templates").json()]
    assert [(look["shape"], look["screen"]) for look in looks] == [
        ("classic", "glow"), ("soft", "pixel"), ("monitor", "signal")]


def test_the_bot_tools_offer_the_lensbot_shapes_and_the_roles_and_still_accept_the_old_shapes():
    from roost.talk.team_tools import CreateBotArgs, SuggestBotArgs
    from roost.talk.tool_catalog import CREATE_BOT_SPEC, SUGGEST_BOT_SPEC

    for spec in (CREATE_BOT_SPEC, SUGGEST_BOT_SPEC):
        assert spec.input_schema["properties"]["shape"]["enum"] == list(LENSBOT_SHAPES), spec.name
        assert spec.input_schema["properties"]["role"]["enum"] == list(BOT_ROLES), spec.name
        assert "role" not in spec.input_schema["required"], spec.name
    made = CreateBotArgs.model_validate({"name": "Coder", "job": "j", "instructions": "i", "role": "code"})
    assert made.draft([]).avatar.role == "code"
    assert made.draft([]).avatar.shape == DEFAULT_LENSBOT_SHAPE
    assert CreateBotArgs.model_validate({"name": "Plain", "job": "j", "instructions": "i"}).draft([]).avatar.role is None
    assert SuggestBotArgs.model_validate({"name": "Ads", "job": "j", "role": "social"}).card([])["avatar"]["role"] == "social"
    with pytest.raises(ValidationError):
        CreateBotArgs.model_validate({"name": "X", "job": "j", "instructions": "i", "role": "hacker"})
    for old in ("dome", "hooded", "classic", "soft", "cube", "monitor", "egg", "pear", "plump", "crest"):
        assert CreateBotArgs.model_validate(
            {"name": "Old", "job": "j", "instructions": "i", "shape": old}).shape == old
        assert SuggestBotArgs.model_validate({"name": "Old", "job": "j", "shape": old}).shape == old
