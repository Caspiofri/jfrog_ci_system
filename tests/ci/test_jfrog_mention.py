"""D77: the JFrog mention snippet, from the stored text with the mentions_jfrog pattern."""
import pytest

from ci import demo, jfrog_mention
from ci.api.app import JfrogMentionOut

LONG = "word " * 200


def test_found_in_text_with_context_and_at_most_280_chars():
    raw = {"title": "A release", "text": LONG + "Teams compare it with JFrog Artifactory for caching. " + LONG,
           "text_status": "full"}
    m = jfrog_mention.mention(raw, True)
    assert m["status"] == "found" and m["found_in"] == "text"
    assert "JFrog Artifactory" in m["snippet"]
    assert len(m["snippet"]) <= 280 and m["snippet"].startswith("…") and m["snippet"].endswith("…")


def test_text_first_then_title():
    assert jfrog_mention.find({"title": "JFrog news", "text": "it uses artifactory"})["found_in"] == "text"
    assert jfrog_mention.find({"title": "JFrog news", "text": "nothing here"}) == \
        {"snippet": "JFrog news", "found_in": "title"}


def test_short_text_is_returned_whole_without_ellipsis():
    assert jfrog_mention.find({"title": "", "text": "  Frogbot   opened a PR. "})["snippet"] == "Frogbot opened a PR."


def test_a_url_or_domain_is_not_a_mention_as_in_the_flag():
    raw = {"title": "x", "text": "See https://jfrog.com/blog/post and jfrog.io for details."}
    assert jfrog_mention.find(raw) is None
    assert jfrog_mention.mention(raw, True) == {"status": "not_in_stored_text", "snippet": None, "found_in": None}


def test_junk_text_reads_the_teaser_like_the_flag():
    raw = {"title": "x", "text": "menu JFrog menu", "teaser": "no mention", "text_status": "junk"}
    assert jfrog_mention.find(raw) is None


def test_flag_false_gives_no_field():
    assert jfrog_mention.mention({"title": "JFrog", "text": "JFrog"}, False) is None


def test_snapshot_match_is_used_over_the_cut_text():
    raw = {"title": "x", "text": "an excerpt without it",
           jfrog_mention.RAW_KEY: {"snippet": "…said JFrog…", "found_in": "text"}}
    assert jfrog_mention.mention(raw, True) == {"status": "found", "snippet": "…said JFrog…", "found_in": "text"}
    assert jfrog_mention.mention({**raw, jfrog_mention.RAW_KEY: None}, True)["status"] == "not_in_stored_text"


def test_snapshot_raw_keeps_the_match_from_the_full_text():
    raw = {"id": "a", "title": "x", "text": LONG + "with JFrog Xray " + LONG, "text_status": "full"}
    out = demo.snapshot_raw(raw)
    assert "JFrog Xray" in out[jfrog_mention.RAW_KEY]["snippet"] and "JFrog" not in out["text"]


def test_api_model_caps_the_snippet():
    JfrogMentionOut.model_validate({"status": "found", "snippet": "a" * 280, "found_in": "text"})
    with pytest.raises(ValueError):
        JfrogMentionOut.model_validate({"status": "found", "snippet": "a" * 281, "found_in": "text"})
