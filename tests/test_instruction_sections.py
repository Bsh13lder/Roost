"""Structured bot instructions (replies track, part 2): free text becomes five Markdown sections in a fixed order."""

from __future__ import annotations

from roost.bots.instruction_sections import parse_sections, structure_instructions
from roost.constants import INSTRUCTION_SECTIONS, MAX_BOT_INSTRUCTIONS_LENGTH

HEADS = [f"## {title}" for title in INSTRUCTION_SECTIONS]


def _heads(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def test_the_five_sections_in_order():
    assert INSTRUCTION_SECTIONS == ("Who you are and context", "What you do", "Rules", "Tone", "Team")


def test_free_text_goes_under_what_you_do_and_every_section_is_there():
    out = structure_instructions("Read the news every morning.\nSum it up in five bullets.", name="Scout",
                                 job="reads the news")
    assert _heads(out) == HEADS
    sections = parse_sections(out)
    assert sections["what"] == "Read the news every morning.\nSum it up in five bullets."
    assert sections["who"] == "You are Scout. Your job: reads the news."
    assert sections["rules"] and sections["tone"] and sections["team"]


def test_rule_lines_move_to_rules():
    out = structure_instructions("Check prices.\n- Never buy anything.\nDon't post for me.\nAlways say the source.")
    sections = parse_sections(out)
    assert sections["what"] == "Check prices."
    assert sections["rules"] == "- Never buy anything.\nDon't post for me.\nAlways say the source."


def test_known_headings_and_labels_are_sorted_into_place():
    text = ("# Tone\nWarm and brief.\n\n### Rules\n- Never spend money.\n\nContext: the user runs a bakery.\n"
            "Teammates:\nAsk Ledger about money.\n\n## Job\nAnswer customer mail.")
    sections = parse_sections(structure_instructions(text))
    assert sections["tone"] == "Warm and brief."
    assert sections["rules"] == "- Never spend money."
    assert sections["who"] == "the user runs a bakery."
    assert sections["team"] == "Ask Ledger about money."
    assert sections["what"] == "Answer customer mail."


def test_an_unknown_heading_stays_as_bold_text_in_its_section():
    sections = parse_sections(structure_instructions("## Rules\nNever post.\n## Sources\nUse BBC."))
    assert sections["rules"] == "Never post.\n**Sources**\nUse BBC."


def test_a_code_fence_is_left_alone():
    text = "Run this:\n```\n# Rules\nnot a heading\n```"
    assert parse_sections(structure_instructions(text))["what"] == text


def test_structuring_twice_changes_nothing():
    once = structure_instructions("Do X.\nNever do Y.\nTone: calm", name="Ada", job="does X")
    assert structure_instructions(once, name="Ada", job="does X") == once
    assert structure_instructions(once) == once


def test_empty_text_gets_a_skeleton_from_the_job():
    sections = parse_sections(structure_instructions("", name="Penny", job="keeps the books"))
    assert sections["what"] == "keeps the books"
    assert _heads(structure_instructions("")) == HEADS


def test_it_never_passes_the_limit():
    long = "Answer mail. " * ((MAX_BOT_INSTRUCTIONS_LENGTH - 40) // 13)
    out = structure_instructions(long, name="Scout", job="answers mail")
    assert len(out) <= MAX_BOT_INSTRUCTIONS_LENGTH
    assert "Answer mail." in out
    full = "x" * MAX_BOT_INSTRUCTIONS_LENGTH
    assert structure_instructions(full) == full


def test_defaults_go_first_when_it_is_too_long():
    text = "What: " + "w" * (MAX_BOT_INSTRUCTIONS_LENGTH - 200)
    out = structure_instructions(text)
    assert len(out) <= MAX_BOT_INSTRUCTIONS_LENGTH
    assert _heads(out) == ["## What you do"]


def test_a_never_or_always_label_keeps_its_word():
    for text in ("Never: share the client list", "**Always:** cite the source",
                 "Don'ts: post for me", "Dos and don'ts: ask before you spend"):
        rules = parse_sections(structure_instructions(text))["rules"]
        assert rules == text, text


def test_a_never_heading_keeps_its_word_over_its_lines():
    out = structure_instructions("Check prices.\n\n## Never\n\n- share the client list\n- buy anything")
    rules = parse_sections(out)["rules"]
    assert "Never" in rules
    assert rules.index("Never") < rules.index("- share the client list")
    assert structure_instructions(out) == out


def test_a_never_label_on_its_own_line_keeps_its_word():
    out = structure_instructions("Never:\n- share the client list")
    rules = parse_sections(out)["rules"]
    assert rules.startswith("Never:") and "- share the client list" in rules
    assert structure_instructions(out) == out
