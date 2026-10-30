"""Mentions backfill and its side file, offline: a fake fetch stands in for reader.fetch_text."""
import json
import re
from datetime import UTC, datetime

from ci.backfill_mentions import backfill
from ci.classify import Classifier
from ci.config import CIConfig, Competitor
from ci.llm import FakeLLM
from ci.mentions import attach

CFG = CIConfig(competitors=[Competitor(key="sonatype", name="Sonatype"), Competitor(key="snyk", name="Snyk"),
                            Competitor(key="gitlab", name="GitLab"), Competitor(key="industry", name="Industry")])
RUN = "20261030T0836Z-abc123"


def _row(i, title, text, competitor="industry", **kw):
    return {"id": f"id{i}", "run_id": RUN, "source": "google_news", "origin": "q", "competitor": competitor,
            "title": title, "url": f"https://pub.com/{i}", "original_url": f"https://pub.com/{i}", "text": text,
            "text_status": "partial", "publisher": "", **kw}


def _run(tmp_path, rows):
    runs = tmp_path / "runs"
    runs.mkdir()
    path = runs / f"{RUN}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return runs, path


def test_backfill_writes_a_side_file_and_never_touches_the_run(tmp_path):
    stored = "Top 5 SCA tools. 1. Snyk. " + "x" * 200
    pages = {"https://pub.com/1": stored + " ... 5. Sonatype Nexus. Also JFrog Artifactory.",
             "https://pub.com/2": None}

    def fetch(url):
        if url == "https://pub.com/3":
            raise TimeoutError("slow site")
        return pages.get(url)

    runs, run_path = _run(tmp_path, [_row(1, "Top 5 SCA tools", stored), _row(2, "Snyk news", "Snyk said"),
                                     _row(3, "GitLab story", "GitLab GitLab")])
    before = run_path.read_bytes()
    summary = backfill(RUN, runs, fetch=fetch, cfg=CFG, workers=2, now=datetime(2026, 10, 30, 12, tzinfo=UTC))
    assert run_path.read_bytes() == before
    side = json.loads((runs / f"{RUN}.mentions.json").read_text(encoding="utf-8"))
    from ci.classify import MentionCounter

    assert side["id1"] == {"mentions": {"sonatype": 1, "snyk": 1, "gitlab": 0}, "mentions_jfrog": True,
                           "fetched": True, "skipped": False, "config": MentionCounter(CFG).config_hash,
                           "counted_on": "2026-10-30"}
    assert side["id2"]["fetched"] is False and side["id2"]["mentions"]["snyk"] == 1  # stored text, not the title
    assert side["id3"]["fetched"] is False and side["id3"]["mentions"]["gitlab"] == 2
    assert summary["gained"] == {"id1": ["sonatype"]} and summary["gained_items"] == 1
    assert summary["fetched"] == 1 and summary["jfrog_gained"] == 1 and summary["counted_on"] == "2026-10-30"


def test_classifier_reads_the_side_file(tmp_path):
    runs, _ = _run(tmp_path, [])
    (runs / f"{RUN}.mentions.json").write_text(json.dumps(
        {"id1": {"mentions": {"sonatype": 6, "snyk": 1, "gitlab": 0}, "mentions_jfrog": True, "fetched": True}}),
        encoding="utf-8")
    llm = FakeLLM(lambda prompt, schema: {"items": []})
    item = _row(1, "Snyk patches critical vulnerability", "Snyk short text", competitor="snyk")
    (c,) = Classifier(llm, CFG, runs_dir=runs).classify([item])
    assert c.method == "fallback" and c.mentions_jfrog  # Sonatype dominates the full page -> LLM, not rules
    payload = json.loads(re.search(r"Items \(JSON\):\n(.*)", llm.calls[0][0], re.S).group(1))
    assert payload[0]["full_text_mentions"] == "sonatype×6, snyk×1"
    (plain,) = Classifier(FakeLLM(), CFG, runs_dir=None).classify([item])  # no side file: stored text, rules
    assert plain.method == "rules" and not plain.mentions_jfrog


def test_an_items_own_counts_beat_the_side_file(tmp_path):
    runs, _ = _run(tmp_path, [])
    (runs / f"{RUN}.mentions.json").write_text(json.dumps({"id1": {"mentions": {"snyk": 9}, "fetched": True}}),
                                               encoding="utf-8")
    own = {**_row(1, "t", ""), "mentions": {"snyk": 1}}
    assert attach([own], runs)[0]["mentions"] == {"snyk": 1}
    assert attach([_row(1, "t", "")], runs)[0]["mentions"] == {"snyk": 9}
    assert attach([_row(2, "t", "")], runs)[0].get("mentions") is None  # not in the side file


def test_labeling_page_does_not_list_the_side_file(tmp_path):
    from fastapi.testclient import TestClient

    from ci.labeling.app import create_app

    runs, _ = _run(tmp_path, [_row(1, "t", "x")])
    (runs / f"{RUN}.mentions.json").write_text("{}", encoding="utf-8")
    client = TestClient(create_app(runs_dir=runs, labels_path=tmp_path / "labels.jsonl", competitors=["snyk"]))
    assert [r["run_id"] for r in client.get("/api/runs").json()] == [RUN]


def test_backfill_skips_what_production_skips(tmp_path):
    fetched = []

    def fetch(url):
        fetched.append(url)
        return "Sonatype " * 50

    gnews = "https://news.google.com/rss/articles/abc"
    capped = "Snyk " + "x" * 6000  # stored text cut at the pipeline's cap: the page goes on
    rows = [_row(1, "already full", "Snyk Snyk", text_status="full"),
            _row(2, "unresolved", "Snyk teaser", url=gnews, original_url=gnews, url_resolved=False),
            _row(3, "snippet", "Snyk teaser", text_status="snippet"),
            _row(4, "full but capped", capped[:6000], text_status="full")]
    runs, _ = _run(tmp_path, rows)
    summary = backfill(RUN, runs, fetch=fetch, cfg=CFG, workers=1)
    side = json.loads((runs / f"{RUN}.mentions.json").read_text(encoding="utf-8"))
    assert sorted(fetched) == ["https://pub.com/3", "https://pub.com/4"]
    assert not side["id4"]["skipped"]
    assert side["id1"]["skipped"] and side["id1"]["mentions"]["snyk"] == 2  # stored text counted
    assert side["id2"]["skipped"] and not side["id2"]["fetched"]
    assert side["id3"]["fetched"] and side["id3"]["mentions"]["sonatype"] == 50
    assert summary["skipped"] == 2


def test_backfill_cli_says_when_the_pages_were_fetched(tmp_path, monkeypatch, capsys):
    import ci.backfill_mentions as mod

    runs, _ = _run(tmp_path, [_row(1, "t", "Snyk")])
    monkeypatch.setattr(mod, "_default_fetch", lambda url: None)
    monkeypatch.setattr(mod.ci_config, "load", lambda: CFG)
    monkeypatch.setattr(mod, "backfill", lambda *a, **k: backfill(*a, fetch=lambda u: None, cfg=CFG, **k))
    assert mod.main([RUN, "--runs-dir", str(runs)]) == 0
    assert "counts come from pages re-fetched on" in capsys.readouterr().out


def test_backfill_fetches_with_the_shared_reader_extraction(monkeypatch):
    import ci.backfill_mentions as mod
    from modules import reader

    seen = []
    monkeypatch.setattr(reader, "fetch_text", lambda url: seen.append(url) or "page")
    assert mod._default_fetch("https://a/1") == "page" and seen == ["https://a/1"]


def test_feed_sourced_items_are_left_out(tmp_path):
    fetched = []
    body = "Snyk " + "x" * 6000
    runs, _ = _run(tmp_path, [_row(1, "feed entry", body[:6000], text_status="full", text_source="feed",
                                   source="vendor_feed")])
    summary = backfill(RUN, runs, fetch=lambda u: fetched.append(u), cfg=CFG, workers=1)
    side = json.loads((runs / f"{RUN}.mentions.json").read_text(encoding="utf-8"))
    assert fetched == [] and "id1" not in side and summary["left_out_feed"] == 1  # the pipeline's counts stand
