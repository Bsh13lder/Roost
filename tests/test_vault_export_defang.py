"""Defanging web-made text before the Obsidian export writes it (pure)."""

from __future__ import annotations

from roost.vault_export.defang import body, defang, heading, label, markdown_body


def test_defang_leaves_no_image_embed_html_or_fence():
    out = defang('![a](http://x.test/i.png) ![[Secret]] <img src=x> ```dataviewjs\n\\![b](y)')
    assert out.startswith("\\!\\[a\\](`http://x.test/i.png)`")
    assert "![" not in out and "<" not in out and "```" not in out and "\\\\\\!" in out


def test_labels_and_headings_stay_on_one_line():
    assert label("a]] [[b|c\n<i>#x") == "a)) ((b/c ‹i›♯x"
    assert heading("Plan\n# Boom [x]") == "Plan # Boom \\[x\\]"


def test_only_web_made_text_changes():
    assert body("![a](https://x.test)", False) == "![a](https://x.test)"
    assert markdown_body("![a](https://x.test)", False) == "![a](https://x.test)"
    assert markdown_body("<b>", True) == "&lt;b&gt;"
    assert markdown_body("---\nunclosed <b>", True) == "---\nunclosed &lt;b&gt;"
    assert markdown_body("---\na: [1]\n---\n[x]", True) == "---\na: [1]\n---\n\\[x\\]"
