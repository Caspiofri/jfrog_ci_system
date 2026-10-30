"""Extraction quality detector: real articles pass; consent/nav walls and pages about something else fail."""
from ci.extraction_quality import BOILERPLATE_MAX_RATIO, TITLE_MIN_COVERAGE, assess, title_coverage

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


def test_a_cookie_and_nav_page_fails_on_boilerplate():
    q = assess("Sonatype launches Nexus Repository Pro+ for AI model screening", CONSENT_WALL)
    assert not q.ok and q.boilerplate_ratio > BOILERPLATE_MAX_RATIO
    assert any("boilerplate" in r for r in q.reasons)


def test_a_page_about_something_else_fails_on_title_coverage():
    q = assess("LiteLLM supply chain attack started with an exposed master key", HEADLINE_LIST)
    assert not q.ok and q.title_coverage < TITLE_MIN_COVERAGE
    assert any("title words missing" in r for r in q.reasons)


def test_a_short_legitimate_release_note_is_not_junk():
    q = assess("cloudsmith-cli Release v1.30.1", RELEASE_NOTE)
    assert q.ok, q.reasons


def test_tiny_js_walls_fail_on_boilerplate_even_without_title_signal():
    q = assess("Roku developer repositories moved from GitHub to GitLab",
               "Please enable JavaScript in your browser to use this website.\nReload Page")
    assert not q.ok


def test_title_coverage_matches_word_forms_and_ignores_stopwords():
    assert title_coverage("GitLab launches Orbit", "gitlab launched the orbit graph") == 1.0
    assert title_coverage("Is it here?", "anything") is None  # no content words: no signal
