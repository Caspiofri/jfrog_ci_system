"""The architecture review's failure scenarios, end to end where feasible, all offline (fake fetch, embedding, LLM)."""
import json
import sys
import types

import pytest

from ci import eval_golden, pipeline
from ci.classify import Classifier, MentionCounter
from ci.config import CIConfig, Competitor
from ci.llm import FakeLLM, GeminiLLM, LLMError
from ci.packet import CollectorResult, Packet, utc_now
from ci.rank import Ranker
from tests.ci.test_dedupe import fake_embed

CFG = CIConfig(window_days=7, competitors=[
    Competitor(key="sonatype", name="Sonatype"), Competitor(key="snyk", name="Snyk"),
    Competitor(key="github", name="GitHub"), Competitor(key="gitlab", name="GitLab"),
    Competitor(key="aws_codeartifact", name="AWS CodeArtifact"), Competitor(key="industry", name="Industry")])
PAGE = "Hyphenate, the finance startup, said the round was led by Nexus. " * 40


def _pkt(url, title, text="teaser", source="google_news", competitor="industry", **kw):
    return Packet(source=source, origin="q", competitor=competitor, title=title, url=url, original_url=url,
                  published_at=utc_now(), text=text, **kw)


def _registry(monkeypatch, collectors: dict) -> dict:
    reg = {}
    for source, fn in collectors.items():
        mod = types.ModuleType(f"fake_scenario_{source}")
        mod.collect = fn
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
        reg[source] = mod.__name__
    return reg


def _run(tmp_path, registry, fetch):
    return pipeline.run(CFG, registry=registry, runs_dir=tmp_path / "runs", data_dir=tmp_path / "data",
                        embed_fn=fake_embed, fetch=fetch, fresh=True, collector_timeout=5)


# (a) conflicting duplicate announcements ---------------------------------------------------------------------------

def test_a_conflicting_duplicates_keep_the_richer_copy_and_leave_the_other_inspectable(tmp_path, monkeypatch):
    def collect(cfg, since):
        return CollectorResult(source="google_news", packets=[
            _pkt("https://wire.example/hyphenate", "Hyphenate raises $45M Series B", "Hyphenate raised $45M."),
            _pkt("https://blog.example/hyphenate", "Hyphenate raises $50M to automate finance", "It raised $50M.")])

    fetch = {"https://blog.example/hyphenate": "Hyphenate raises $50M. " + PAGE}.get  # only one page readable
    res = _run(tmp_path, _registry(monkeypatch, {"google_news": collect}), fetch)
    [kept] = res.kept
    assert kept.url == "https://blog.example/hyphenate" and kept.text_status == "full"  # the richer copy
    dropped = [json.loads(x) for x in (tmp_path / "runs" / f"{res.run_id}.dropped.jsonl").read_text().splitlines()]
    [other] = dropped
    assert other["duplicate_of"] == kept.id and other["drop_stage"] == "embedding_dedupe"
    assert "$45M" in other["text"] and "$45M" in other["title"]  # the conflicting number is still there to inspect


# (b) competitor aliases ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("title,key", [
    ("Amazon CodeArtifact adds Cargo package support", "aws_codeartifact"),
    ("AWS's CodeArtifact now supports Swift packages", "aws_codeartifact"),
    ("Sonatype Nexus Repository 3.80 released", "sonatype"),
    ("GitHub Dependabot now supports uv lockfiles", "github"),
    ("GitLab Duo agents learn from your codebase", "gitlab"),
])
def test_b_aliases_resolve_to_the_right_competitor(title, key):
    counts, _ = MentionCounter(CFG)(title)
    assert max(counts, key=counts.get) == key and counts[key] >= 1
    result, why = Classifier(FakeLLM(), CFG, runs_dir=None).apply_rules(
        {"id": "x", "title": title, "competitor": key, "text": "", "source": "google_news"})
    assert result is not None and result.competitor == key, why


# (c) an irrelevant, heavily mentioned company ---------------------------------------------------------------------

@pytest.mark.parametrize("prefilled,title,text", [
    ("sonatype", "Nexus Venture Partners leads $30M round in a payments startup",
     "Nexus said ... Nexus partner ... Nexus fund " * 20),
    ("snyk", "Snake River Capital backs Idaho dairy cooperative", "Snake River ... Snake ... Snake " * 20),
])
def test_c_a_confusable_company_is_never_rules_settled(prefilled, title, text):
    item = {"id": "x", "title": title, "competitor": prefilled, "text": text, "source": "google_news"}
    c = Classifier(FakeLLM(lambda p, s: {"items": []}), CFG, runs_dir=None)
    assert c.apply_rules(item)[0] is None
    (out,) = c.classify([item])
    assert out.method != "rules" and len(c.llm.calls) == 1  # it went to the LLM


# (d) inaccessible full text -------------------------------------------------------------------------------------

def test_d_unreadable_page_stays_a_snippet_capped_at_4_and_in_review():
    p = pipeline.read_full_text(_pkt("https://paywalled.example/x", "Snyk acquires Invariant Labs",
                                     competitor="snyk"), lambda url: None)
    assert p.text_status == "snippet"
    item = {**p.model_dump(mode="json"), "id": "x"}
    cls = Classifier(FakeLLM(), CFG, runs_dir=None).classify([item])
    llm = FakeLLM([{"items": [{"id": "x", "score": 5, "reason": "acquisition", "why_it_matters": "M&A"}]}])
    (r,) = Ranker(llm).rank([item], cls)
    assert (r.raw_score, r.score) == (5, 4) and r.needs_review
    assert "snippet-only item scored >= 4" in r.review_reasons and not r.auto_publishable


# (e) model outage -----------------------------------------------------------------------------------------------

def test_e_a_model_outage_degrades_every_item_into_review_and_the_report_counts_them(tmp_path):
    rows = [{"id": f"i{n}", "run_id": "r", "competitor": comp, "category": "Security", "score": 3, "noise": False,
             "item": {"title": title, "text": "body " * 200, "source": "google_news", "competitor": comp}}
            for n, (comp, title) in enumerate([("snyk", "Snyk patches critical vulnerability"),
                                               ("industry", "Malicious npm packages found"),
                                               ("gitlab", "Some GitLab story")])]
    labels = tmp_path / "golden.jsonl"
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def down():
        raise LLMError("503 model overloaded")

    llm = GeminiLLM(model="m", client_factory=down, sleep=lambda s: None)
    report = eval_golden.run(split="all", live=True, labels_path=labels, runs_dir=tmp_path / "runs", out_dir=None,
                             llm=llm, cfg=CFG, allow_fallback=True, embed_fn=lambda: fake_embed,
                             split_path=tmp_path / "sides.json")
    assert not report["aborted"] and report["n"] == 3  # the run completes
    preds = [it["pred"] for it in report["items"]]
    assert all(p["score"] is None and p["degraded"] and p["needs_review"] for p in preds)
    assert report["fallbacks"]["rank"] == 3 and report["metrics"]["score"]["missing"] == 3
    assert report["fallbacks"]["classify"] == 2  # the rules still settled the Snyk item; the other two degraded


# (f) a source failure is never a silent loss ----------------------------------------------------------------------

def test_f_a_failed_source_is_reported_even_when_others_succeed(tmp_path, monkeypatch):
    def news(cfg, since):
        return CollectorResult(source="google_news", packets=[_pkt("https://a.example/1", "Some industry story")])

    def vendor(cfg, since):  # where "Sonatype acquires X" would have come from
        raise ConnectionError("sonatype.com feed unreachable")

    res = _run(tmp_path, _registry(monkeypatch, {"google_news": news, "vendor_feed": vendor}), lambda url: None)
    assert res.report["status"] == "ok"  # the run itself still succeeded
    assert "ConnectionError" in res.report["sources"]["vendor_feed"]["errors"][0]
    assert res.report["totals"]["errors"] == 1
    assert "! vendor_feed:" in pipeline.format_report(res.report)
