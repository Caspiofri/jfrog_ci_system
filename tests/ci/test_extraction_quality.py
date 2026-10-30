"""Extraction quality detector: real articles pass; consent/nav walls and pages about something else fail."""
import pytest

from ci.extraction_quality import (
    BOILERPLATE_MAX_RATIO,
    BOILERPLATE_MIN_CHARS,
    TITLE_MIN_COVERAGE,
    assess,
    boilerplate_ratio,
    title_coverage,
)

ARTICLE = """Sonatype on Tuesday launched Nexus Repository Pro+, adding AI model screening to its repository manager.
The new tier scans models pulled from Hugging Face for malicious pickles and licence problems before they reach
developers, the company said.
Screening runs inside the repository, so teams that already proxy npm and PyPI through Nexus get the checks without
a new tool. Pricing was not disclosed.
Sonatype said early customers had blocked several poisoned models in the first weeks of the preview."""

CONSENT_WALL = """Skip to main content
Menu
Home
News
Security
We value your privacy
We use cookies to improve your experience. By clicking Accept all you consent to our use of cookies.
Accept all
Reject all
Manage preferences
Sign in
Subscribe to our newsletter
Follow us on LinkedIn
© 2026 Example Media. All rights reserved."""

HEADLINE_LIST = "\n".join(
    f"- Story {i}: Oracle wants to bill you for every AI task, and AWS installs accelerators every few seconds "
    f"while Microsoft faces a vote on emissions" for i in range(8))

RELEASE_NOTE = """What's Changed
- fix: put the release Docker credential helper on PATH
- feat: add --json output to `cloudsmith ls`
Full Changelog: v1.30.0...v1.30.1"""


def test_a_real_article_passes():
    q = assess("Sonatype launches Nexus Repository Pro+ for AI model screening", ARTICLE)
    assert q.ok and q.reasons == [] and q.title_coverage >= 0.8 and q.boilerplate_ratio < 0.1


def test_a_short_cookie_and_nav_page_fails_on_its_wall_phrase():
    assert len(CONSENT_WALL) < BOILERPLATE_MIN_CHARS
    q = assess("Sonatype launches Nexus Repository Pro+ for AI model screening", CONSENT_WALL)
    assert not q.ok and "page wall ('we value your privacy')" in q.reasons


def test_a_long_cookie_and_nav_page_fails_on_boilerplate():
    wall = CONSENT_WALL + "\n" + "\n".join(f"Section {i}" for i in range(30))
    assert len(wall) >= BOILERPLATE_MIN_CHARS
    q = assess("Sonatype launches Nexus Repository Pro+ for AI model screening", wall)
    assert not q.ok and q.boilerplate_ratio > BOILERPLATE_MAX_RATIO
    assert any("boilerplate" in r for r in q.reasons)


def test_a_page_about_something_else_fails_on_title_coverage():
    q = assess("LiteLLM supply chain attack started with an exposed master key", HEADLINE_LIST)
    assert not q.ok and q.title_coverage < TITLE_MIN_COVERAGE
    assert any("title words missing" in r for r in q.reasons)


def test_a_short_legitimate_release_note_is_not_junk():
    q = assess("cloudsmith-cli Release v1.30.1", RELEASE_NOTE)
    assert q.ok, q.reasons


# the three short pages that the boilerplate ratio flagged as junk (78-100%) before BOILERPLATE_MIN_CHARS
SHORT_REAL = {
    "release note": ("cloudsmith-cli Release v1.31.0", "v1.31.0\nHighlights\nFaster uploads\nNew `cloudsmith whoami`\n"
                     "Bug fixes\n- retry on 502 from the API\nFull Changelog: v1.30.1...v1.31.0"),
    "changelog entry": ("Secret scanning now covers npm tokens", "Changelog\nOctober 29, 2026\nImprovement\n"
                        "Security\nnpm\nSecret scanning covers npm tokens."),
    "sso news": ("GitLab adds SSO sign in for self-managed instances",
                 "GitLab adds SSO sign in for self-managed instances\nSign in with your identity provider\n"
                 "Admins can require SSO for every sign in to the instance."),
}


@pytest.mark.parametrize("name", list(SHORT_REAL))
def test_short_real_pages_are_not_junk(name):
    title, text = SHORT_REAL[name]
    assert boilerplate_ratio(text) > BOILERPLATE_MAX_RATIO  # what flagged them before
    q = assess(title, text)
    assert q.ok, q.reasons


@pytest.mark.parametrize("text", [
    "Please enable JavaScript in your browser to use this website.\nReload Page",
    "M\nmali-pagecache-root\nLoading",
    "Verifying your browser before proceeding...\nIncident ID:\nd548d34c-bsff-4369-b9dd-83432f06706c",
    "We use cookies to give you the best experience.\nAccept all\nReject all",
    "404\nPage not found\nThe page you are looking for does not exist.\nGo home",
    "Page Not Found\nSorry, we couldn't find that page.",
    "You need to enable JavaScript to run this app.",
    "Skip to content\nProducts\nPricing\n404\nPage not found\nThe page you are looking for does not exist.\nGo home",
])
def test_tiny_walls_fail_on_their_wall_phrase_even_without_title_signal(text):
    q = assess("Roku developer repositories moved from GitHub to GitLab", text)
    assert not q.ok and any(r.startswith("page wall") for r in q.reasons)


def test_title_coverage_matches_word_forms_and_ignores_stopwords():
    assert title_coverage("GitLab launches Orbit", "gitlab launched the orbit graph") == 1.0
    assert title_coverage("Is it here?", "anything") is None  # no content words: no signal


NAV_MENU = ("Skip to content\nProducts\nSolutions\nPricing\nDocs\nBlog\nSign in\nGet started\nContact sales\n"
            "About us\nCareers\nPress")


def test_a_short_nav_menu_still_fails_on_boilerplate():
    assert len(NAV_MENU) < BOILERPLATE_MIN_CHARS
    q = assess("GitLab ships Orbit to every tier", NAV_MENU)
    assert not q.ok and any("boilerplate" in r for r in q.reasons)


@pytest.mark.parametrize(("title", "text"), [
    ("CVE-2026-1234: captcha bypass in Example Login", "CVE-2026-1234: an attacker can bypass the captcha and reach "
     "the login form; requests then fail with access denied only after the lockout. Fixed in 2.3.1."),
    ("example-cli v2.3.1", "v2.3.1\n- fix: the cookie settings dialog no longer resets on reload in the web UI\n"
     "- chore: bump deps"),
    ("example-cli v2.3.2", "v2.3.2\n- fix: cookie settings now persist\nUpgrade with `pip install -U example-cli`."),
    ("Login hardening", "Login hardening\nThe new captcha flow is now on for every tenant by default."),
    ("Artifacts API retries", "404 errors on the artifacts API are now retried."),
    ("SSO fix", "Access denied errors for SSO users are fixed."),
    ("Login protection", "CAPTCHA is now required after five failed attempts."),
    ("Usage dashboard", "GitLab shipped a usage dashboard for CI minutes this week.\nEnable JavaScript to see the "
     "interactive chart.\nThe dashboard breaks usage down by project and runner."),
    ("Registry stats", "Cloudsmith published its registry statistics for October.\nLoading...\nDownloads grew 12% "
     "month over month, led by npm and Docker."),
])
def test_wall_words_inside_content_sentences_are_not_walls(title, text):
    assert len(text) < BOILERPLATE_MIN_CHARS
    q = assess(title, text)
    assert q.ok, q.reasons

