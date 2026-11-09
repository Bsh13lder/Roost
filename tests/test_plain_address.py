"""Owner, 2026-11-01 ("gigs still problem"): Upwork answered 500 to ``/nx/search/jobs/details/~ID`` every time, the
search list's popup, which never opens on its own, while the job's plain page ``/jobs/~ID`` answered 200. On a server
error ``open_page`` tries the page's plain address first. Pure, no browser."""

from __future__ import annotations

from roost.talk.plain_address import plain_address

_ID = "~022116311312546022189"


def test_an_upwork_list_popup_becomes_the_jobs_plain_page():
    for path in (f"/nx/search/jobs/details/{_ID}", f"/nx/find-work/best-matches/details/{_ID}/",
                 f"/nx/search/jobs/saved/details/{_ID}?pageTitle=Job"):
        assert plain_address(f"https://www.upwork.com{path}") == f"https://www.upwork.com/jobs/{_ID}"


def test_an_address_with_no_plain_form_has_none():
    for url in (f"https://www.upwork.com/jobs/{_ID}", "https://www.upwork.com/nx/find-work/",
                f"https://evil.example/nx/search/jobs/details/{_ID}", f"http://www.upwork.com/nx/search/jobs/details/{_ID}",
                "not a url", ""):
        assert plain_address(url) is None


def test_the_plain_address_never_leaves_the_host():
    assert plain_address(f"https://upwork.com/nx/search/jobs/details/{_ID}") == f"https://upwork.com/jobs/{_ID}"


def test_the_bot_is_told_an_old_tab_never_proves_a_site_is_down():
    from roost.talk import instructions
    text = " ".join(v for v in vars(instructions).values() if isinstance(v, str))
    assert "Before you say a site is down, load the page again with open_page" in text


def test_an_upwork_job_page_names_its_apply_form():
    from roost.talk.plain_address import apply_address
    assert apply_address(f"https://www.upwork.com/jobs/{_ID}") == (
        f"https://www.upwork.com/nx/proposals/job/{_ID}/apply/")
    assert apply_address(f"https://www.upwork.com/jobs/Build-receptionist_{_ID}/") == (
        f"https://www.upwork.com/nx/proposals/job/{_ID}/apply/")
    for url in (f"https://www.upwork.com/nx/search/jobs/details/{_ID}", "https://www.upwork.com/nx/find-work/",
                f"https://evil.example/jobs/{_ID}", f"http://www.upwork.com/jobs/{_ID}"):
        assert apply_address(url) is None
