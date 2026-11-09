from roost.bots.limits import fits_on_one_line


def test_plain_text_and_emoji_fit_on_one_line():
    assert fits_on_one_line("HiMap SEO · v2 🐦")


def test_line_breaks_and_control_characters_do_not():
    for bad in ("a\nb", "a\rb", "a\tb", "a\x00b", "a\x85b", "a b", "a b", "a\x7fb"):
        assert not fits_on_one_line(bad), repr(bad)
