"""Noise pre-filter: chatter and review-site patterns, event protection (title and full text), shadow vs on."""
import pytest

from ci import eval_golden, prefilter
from ci.classify import Classifier
from ci.config import CIConfig, Competitor
from ci.llm import FakeLLM

CFG = CIConfig(competitors=[Competitor(key="gitlab", name="GitLab"), Competitor(key="snyk", name="Snyk"),
                            Competitor(key="industry", name="Industry")])
BODY = "The company reported quarterly numbers and analysts commented on the shares. " * 5


def _item(i, title, text=BODY, competitor="gitlab", **kw):
    return {"id": f"i{i}", "title": title, "text": text, "competitor": competitor, "source": "google_news",
            "origin": "q", "text_status": "full", "url": f"https://news.example/{i}", "publisher": "News", **kw}


@pytest.mark.parametrize("title,pattern", [
    ("BofA Securities Adjusts Gitlab Price Target to $64 From $54", "price target"),
    ("GitLab Reaches $56.28, a Fresh 52-Week High", "52-week high/low"),
    ("GitLab hits a new 52-week low", "52-week high/low"),
    ("26,983 GitLab Inc. $GTLB Shares Sold by Taylor Frigon Capital", "fund share trade"),
    ("Vanguard Group buys 120,000 shares of GitLab", "fund share trade"),
    ("Is GitLab Stock a Buy Now?", "is it a buy"),
    ("Is It Time To Consider Buying GitLab? Is GitLab stock a buy", "is it a buy"),
    ("Jane Street lowers its stake in GitLab Inc.", "stake"),
    ("Cetera Advisors trims holdings in GitLab", "holdings"),
    ("GitLab gets an analyst upgrade from Morgan Stanley", "analyst rating"),
    ("GitLab (GTLB) Short Interest & Short Float | Updated Oct 2026", "short interest"),
    ("Institutional investors own 87% of GitLab", "institutional investor"),
])
def test_each_chatter_pattern_flags_the_title(title, pattern):
    assert prefilter.check(_item(1, title), BODY) == f"stock chatter: {pattern}"


@pytest.mark.parametrize("url,publisher", [
    ("https://www.g2.com/products/snyk/reviews", "News"),
    ("https://reviews.capterra.com/x", "News"),
    ("https://news.example/x", "Software Advice"),
    ("https://news.example/x", "G2"),
])
def test_review_sites_are_flagged(url, publisher):
    assert prefilter.check(_item(1, "Snyk reviews and ratings", url=url, publisher=publisher), BODY).startswith(
        "review site")


@pytest.mark.parametrize("title", [
    "Snyk shares jump after $300M funding round",  # a chatter word, but a funding event
    "GitLab stock falls after critical vulnerability disclosed",
    "GitLab price target raised as GitLab launches Orbit",
    "Analyst upgrade follows GitLab acquisition of Oxeye",
    "GitLab short interest grows after outage",
])
def test_an_event_word_in_the_title_protects_the_item(title):
    assert prefilter.check(_item(1, title), BODY) is None


def test_protection_found_only_in_the_full_text():
    text = BODY + " Separately, the company announced the general availability of its new agent platform."
    item = _item(1, "BofA Securities Adjusts Gitlab Price Target to $64 From $54", text=text)
    assert prefilter.check(item, text) is None
    assert prefilter.check(item, BODY) is not None


def test_a_patterns_own_words_do_not_protect_it():
    assert prefilter.check(_item(1, "1,000 GitLab shares acquired by Example Capital"), BODY) is not None


def test_a_plain_story_is_never_flagged():
    assert prefilter.check(_item(1, "GitLab ships a new merge train UI"), BODY) is None


def _llm():
    return FakeLLM(lambda p, s: {"items": [{"id": i, "competitor": "gitlab", "category": "Customers & Market",
                                            "noise": False, "confidence": 0.8}
                                           for i in s["properties"]["items"]["items"]["properties"]["id"]["enum"]]})


ITEMS = [_item(1, "BofA Securities Adjusts Gitlab Price Target to $64 From $54"),
         _item(2, "GitLab Inc. Estimates and earnings call recap"),
         _item(3, "Snyk shares jump after $300M funding round", competitor="snyk")]


def test_shadow_mode_changes_nothing_but_records_the_decision():
    llm_plain, llm_shadow = _llm(), _llm()
    plain = Classifier(llm_plain, CFG, runs_dir=None, prefilter_mode="shadow").classify(ITEMS)
    assert [c.shadow_prefilter for c in plain] == ["stock chatter: price target", "", ""]
    stripped = [c.model_copy(update={"shadow_prefilter": ""}) for c in plain]
    again = Classifier(llm_shadow, CFG, runs_dir=None, prefilter_mode="shadow").classify(ITEMS)
    assert [c.model_copy(update={"shadow_prefilter": ""}) for c in again] == stripped
    assert plain[0].method != "prefilter" and not plain[0].noise  # the LLM still decided
    assert len(llm_plain.calls[0][1]["properties"]["items"]["items"]["properties"]["id"]["enum"]) == 3


def test_on_mode_marks_noise_and_skips_the_llm_for_that_item():
    llm = _llm()
    out = Classifier(llm, CFG, runs_dir=None, prefilter_mode="on").classify(ITEMS)
    assert (out[0].method, out[0].noise, out[0].competitor, out[0].category) == ("prefilter", True, "gitlab", None)
    assert out[0].reason == "prefilter: stock chatter: price target"
    sent = [i for _, s in llm.calls for i in s["properties"]["items"]["items"]["properties"]["id"]["enum"]]
    assert "i1" not in sent and {"i2", "i3"} <= set(sent)


def test_on_mode_with_every_item_filtered_makes_no_llm_call():
    llm = FakeLLM()
    out = Classifier(llm, CFG, runs_dir=None, prefilter_mode="on").classify(ITEMS[:1])
    assert out[0].method == "prefilter" and llm.calls == []


def test_the_default_mode_is_shadow():
    assert prefilter.PREFILTER_MODE == "shadow"
    with pytest.raises(ValueError):
        Classifier(FakeLLM(), CFG, runs_dir=None, prefilter_mode="maybe")


def test_patterns_and_mode_are_in_the_eval_fingerprint(monkeypatch):
    base = eval_golden.fingerprint(CFG)
    monkeypatch.setattr(prefilter, "PREFILTER_MODE", "on")
    assert eval_golden.fingerprint(CFG) != base
    monkeypatch.undo()
    monkeypatch.setattr(prefilter, "REVIEW_DOMAINS", (*prefilter.REVIEW_DOMAINS, "trustradius.com"))
    assert eval_golden.fingerprint(CFG) != base


def test_eval_reports_the_prefilter_against_labels():
    from tests.ci.test_eval_golden import _label, _ranked

    labels = [_label("a", "gitlab", noise=True), _label("b", "gitlab", "Security", 4)]
    cls = Classifier(_llm(), CFG, runs_dir=None).classify(
        [_item("x", "GitLab Price Target Raised to $70") | {"id": "a"}, _item("y", "GitLab ships") | {"id": "b"}])
    m = eval_golden.evaluate(labels, cls, [_ranked("a", 1), _ranked("b", 4)])
    assert m["prefilter"] == {"flagged": 1, "noise_caught": 1, "labeled_noise": 1, "precision": 1.0,
                              "precision_n": 1, "recall": 1.0, "recall_n": 1, "relevant_flagged": []}
