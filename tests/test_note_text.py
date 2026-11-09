"""The harvested note text helpers (M2 D1): wikilinks, front matter, tags, titles, folding."""

from __future__ import annotations

from roost.notes.frontmatter import parse_frontmatter
from roost.notes.text import capped_tags, fold, merge_tags, note_title
from roost.notes.wikilinks import extract_wikilinks, extract_wikilinks_full, normalize_page


def test_wikilinks_are_folded_deduplicated_and_code_is_skipped():
    md = "See [[Ana]] and [[ ana ]], [[Garden|my garden]] but not `[[code]]`."
    assert extract_wikilinks(md) == ["ana", "garden"]
    assert [(link.raw_target, link.display) for link in extract_wikilinks_full(md)] == [("Ana", ""), ("Garden", "my garden")]
    assert normalize_page("  Ana   García ") == "ana garcía"


def test_tags_merge_explicit_front_matter_and_hashtags_once():
    md = "---\ntags: [family, People]\n---\nAna likes #orchids and #Family"
    assert merge_tags(["#people"], md) == ["people", "family", "orchids"]


def test_tags_are_capped_in_count_and_length():
    many = [f"t{i}" for i in range(30)] + ["x" * 60]
    capped = capped_tags(many)
    assert len(capped) == 20 and all(len(tag) <= 40 for tag in capped)


def test_a_note_title_comes_from_the_first_line_after_front_matter():
    assert note_title(None, "---\ntags: [x]\n---\n# Ana\nlikes orchids") == "Ana"
    assert note_title("  Garden ", "body") == "Garden"
    assert note_title("", "   ") == "Untitled note"


def test_fold_ignores_case_and_accents():
    assert fold("Cumpleaños ORQUÍDEAS") == "cumpleanos orquideas"


def test_front_matter_is_split_from_the_body():
    props, body, has = parse_frontmatter("---\ntags: [a, b]\n---\nBody")
    assert (props["tags"], body, has) == (["a", "b"], "Body", True)
