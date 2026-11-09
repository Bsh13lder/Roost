"""Owner, 2026-11-01: the ``type`` tool takes up to 5000 characters (Upwork's cover letter limit) with line breaks
and tabs (``\\n``, ``\\t``); any other control character, a carriage return included, is refused. The
keeper's and roost-input's key-by-key path keeps refusing every control character (there a line break would
press Enter), and every cap mirrors ``CU_TYPE_MAX_CHARS``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from roost.computer_use.models import TypeIn
from roost.computer_use.tool_specs import TYPE_SPEC
from roost.constants import CU_BOX_TEXT_MAX_CHARS, CU_TYPE_MAX_CHARS
from roost.keeper.computer_input import TypeAction

_ROOST_INPUT = Path(__file__).resolve().parents[1] / "docker" / "computer" / "roost_input.py"


def _roost_input():
    spec = importlib.util.spec_from_file_location("roost_input_caps", _ROOST_INPUT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["roost_input_caps"] = module     # a dataclass looks its module up while it is built
    spec.loader.exec_module(module)
    return module


def _type(text: str) -> TypeIn:
    return TypeIn.model_validate({"text": text, "expect": "typed"})


def test_the_cap_is_upworks_cover_letter_limit():
    assert CU_TYPE_MAX_CHARS == 5000 and CU_BOX_TEXT_MAX_CHARS >= CU_TYPE_MAX_CHARS
    assert len(_type("a" * CU_TYPE_MAX_CHARS).text) == CU_TYPE_MAX_CHARS
    with pytest.raises(ValidationError):
        _type("a" * (CU_TYPE_MAX_CHARS + 1))
    assert TYPE_SPEC.input_schema["properties"]["text"]["maxLength"] == CU_TYPE_MAX_CHARS


def test_line_breaks_and_tabs_are_allowed():
    assert _type("Hello,\n\nI can start.\n\tGela").text == "Hello,\n\nI can start.\n\tGela"


@pytest.mark.parametrize("bad", ["one\r\ntwo", "ring\x07", "esc\x1b[1m", "nul\x00", "del\x7f", "\x0b", "\x0c"])
def test_other_control_characters_are_refused(bad):
    with pytest.raises(ValidationError):
        _type(bad)


def test_the_tool_says_line_breaks_are_fine():
    assert "line break" in TYPE_SPEC.description


def test_the_key_by_key_path_still_refuses_line_breaks():
    with pytest.raises(ValidationError):
        TypeAction.model_validate({"verb": "type", "text": "one\ntwo"})
    assert TypeAction.model_validate({"verb": "type", "text": "x" * CU_TYPE_MAX_CHARS}).text


def test_roost_input_mirrors_the_cap():
    assert _roost_input().MAX_TEXT_CHARS == CU_TYPE_MAX_CHARS
