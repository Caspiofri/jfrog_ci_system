"""The run pipeline end to end with fake collectors, a fake fetcher and a fake embedding function (offline)."""
import json
import sqlite3
import sys
import threading
import types
from datetime import timedelta

import pytest

from ci import pipeline
from ci.config import CIConfig
from ci.dedupe import EmbeddingDeduper
from ci.packet import CollectorResult, Packet, utc_now
from tests.ci.test_dedupe import fake_embed

CFG = CIConfig(window_days=7, competitors=[])
LONG = "word " * 400  # 2000 chars: a full page
release = threading.Event()


def pkt(source, url, title, hours_ago=None, **kw):
    published = utc_now() - timedelta(hours=hours_ago) if hours_ago is not None else None
    return Packet(source=source, origin="q", competitor="snyk", title=title, url=url,
                  original_url=kw.pop("original_url", url), published_at=published, text="teaser", **kw)


def _hn(cfg, since):
    return CollectorResult(source="hackernews", errors=["query 'Snyk' failed: 503"], packets=[
        pkt("hackernews", "https://pub.com/a", "Alpha launch", hours_ago=2),
        pkt("hackernews", "https://pub.com/a/?utm_source=hn", "Alpha launch", hours_ago=2),  # URL dup
        pkt("hackernews", "https://short.com/b", "Beta story", hours_ago=48),
    ])


def _gnews(cfg, since):
    assert since < utc_now() - timedelta(days=2)  # --days 3 reaches the collector
    return CollectorResult(source="google_news", packets=[
        pkt("google_news", "https://news.google.com/rss/articles/x", "Gamma news", url_resolved=False),
        pkt("google_news", "https://other.com/alpha", "Alpha reported elsewhere", hours_ago=30),  # embedding dup
    ])


def _boom(cfg, since):
    raise RuntimeError("feed parser exploded")


def _hang(cfg, since):
    release.wait(10)
    return CollectorResult(source="github_releases")


def _fetch(url):
    return {"https://pub.com/a": LONG, "https://short.com/b": "x" * 500, "https://other.com/alpha": None}.get(url)


@pytest.fixture
def registry(monkeypatch):
    for name, fn in [("hn", _hn), ("gnews", _gnews), ("boom", _boom), ("hang", _hang)]:
        mod = types.ModuleType(f"fake_ci_{name}")
        mod.collect = fn
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    release.clear()
    yield {"hackernews": "fake_ci_hn", "google_news": "fake_ci_gnews", "vendor_feed": "fake_ci_boom",
           "github_releases": "fake_ci_hang", "missing": "fake_ci_does_not_exist"}
    release.set()  # let the abandoned thread finish


def _run(tmp_path, registry, **kw):
    return pipeline.run(CFG, registry=registry, runs_dir=tmp_path / "runs", data_dir=tmp_path / "data",
                        embed_fn=fake_embed, fetch=_fetch, collector_timeout=1, days=3, **kw)


def test_run_end_to_end(tmp_path, registry):
    res = _run(tmp_path, registry)
    assert pipeline.format_report(res.report)  # printable
    src = res.report["sources"]

    # failures are isolated and recorded per source
    assert "RuntimeError" in src["vendor_feed"]["errors"][0]
    assert "timed out" in src["github_releases"]["errors"][0]
    assert "ModuleNotFoundError" in src["missing"]["errors"][0]
    assert src["hackernews"]["errors"] == ["query 'Snyk' failed: 503"]

    assert src["hackernews"] | {"errors": [], "duration_s": 0} == {
        "collected": 3, "in_24h": 2, "unresolved_urls": 0, "dup_url": 1, "dup_embedding": 0, "kept": 2,
        "full": 1, "partial": 1, "snippet": 0, "contaminated": 0, "contaminated_ids": [], "errors": [],
        "duration_s": 0}
    assert src["google_news"]["unresolved_urls"] == 1 and src["google_news"]["dup_embedding"] == 1
    assert res.report["totals"]["collected"] == 5 and res.report["totals"]["kept"] == 3

    kept = {p.url: p for p in res.kept}
    assert set(kept) == {"https://pub.com/a", "https://short.com/b", "https://news.google.com/rss/articles/x"}
    assert kept["https://pub.com/a"].text_status == "full" and kept["https://pub.com/a"].in_24h
    assert len(kept["https://pub.com/a"].text) == len(LONG)
    gnews = kept["https://news.google.com/rss/articles/x"]
    assert gnews.text == "teaser" and gnews.text_status == "snippet" and not gnews.in_24h
    assert all(p.run_id == res.run_id and p.id and p.collected_at for p in res.kept)

    lines = res.paths["kept"].read_text().splitlines()
    assert len(lines) == 3 and Packet.model_validate_json(lines[0])
    dropped = [json.loads(x) for x in res.paths["dropped"].read_text().splitlines()]
    assert {d["drop_stage"] for d in dropped} == {"url_dedupe", "embedding_dedupe"}
    alpha = kept["https://pub.com/a"].id
    assert all(d["duplicate_of"] == alpha and d["drop_reason"] for d in dropped)
    assert json.loads(res.paths["report"].read_text())["run_id"] == res.run_id


def test_second_run_dedupes_against_history_unless_fresh(tmp_path, registry):
    sources = ["hackernews", "google_news"]
    first = _run(tmp_path, registry, sources=sources)
    second = _run(tmp_path, registry, sources=sources)
    assert second.run_id != first.run_id
    assert second.kept == [] and second.report["totals"]["dup_url"] == 5
    fresh = _run(tmp_path, registry, sources=sources, fresh=True)
    assert len(fresh.kept) == 3


def test_text_is_capped_and_unknown_source_rejected(tmp_path, registry):
    p = pipeline.read_full_text(pkt("hackernews", "https://pub.com/a", "t"), lambda u: "y" * 9000)
    assert len(p.text) == pipeline.TEXT_MAX_CHARS and p.text_status == "full"
    with pytest.raises(ValueError):
        _run(tmp_path, registry, sources=["nope"])


def test_run_id_format():
    rid = pipeline.new_run_id()
    stamp, short = rid.split("-")
    assert len(stamp) == len("20261030T0915Z") and stamp.endswith("Z") and len(short) == 6


def _single(monkeypatch, fn) -> dict[str, str]:
    mod = types.ModuleType(f"fake_ci_{fn.__name__}")
    mod.collect = fn
    monkeypatch.setitem(sys.modules, mod.__name__, mod)
    return {"hackernews": mod.__name__}


def _seen_rows(tmp_path) -> int:
    with sqlite3.connect(tmp_path / "data" / "seen_urls.sqlite") as db:
        return db.execute("SELECT COUNT(*) FROM seen").fetchone()[0]


def _chroma_count(tmp_path) -> int:
    return EmbeddingDeduper(tmp_path / "data" / "chroma", fake_embed)._collection().count()


def test_embedding_failure_keeps_items_and_writes_outputs(tmp_path, monkeypatch):
    def broken_embed(texts):
        raise OSError("model download failed")

    res = pipeline.run(CFG, registry=_single(monkeypatch, _hn), runs_dir=tmp_path / "runs",
                       data_dir=tmp_path / "data", embed_fn=broken_embed, fetch=_fetch)
    assert len(res.kept) == 2  # everything that passed URL dedupe
    assert "OSError: model download failed" in res.report["pipeline_errors"][0]
    assert "OSError" in pipeline.format_report(res.report)
    assert all(p.exists() for p in res.paths.values())
    assert json.loads(res.paths["report"].read_text())["pipeline_errors"] == res.report["pipeline_errors"]
    assert _seen_rows(tmp_path) > 0 and _chroma_count(tmp_path) == 0  # no embeddings remembered


def test_remember_failure_is_reported_not_raised(tmp_path, monkeypatch):
    def fail(self, packets):
        raise RuntimeError("disk full")

    monkeypatch.setattr(EmbeddingDeduper, "remember", fail)
    res = pipeline.run(CFG, registry=_single(monkeypatch, _hn), runs_dir=tmp_path / "runs",
                       data_dir=tmp_path / "data", embed_fn=fake_embed, fetch=_fetch)
    assert res.kept and "history write failed (embeddings)" in res.report["pipeline_errors"][0]
    assert "disk full" in res.paths["report"].read_text()


def test_failed_run_leaves_history_untouched(tmp_path, monkeypatch):
    def broken_fetch(url):
        raise RuntimeError("bug in fetch")

    with pytest.raises(RuntimeError):
        pipeline.run(CFG, registry=_single(monkeypatch, _hn), runs_dir=tmp_path / "runs",
                     data_dir=tmp_path / "data", embed_fn=fake_embed, fetch=broken_fetch)
    assert _seen_rows(tmp_path) == 0 and _chroma_count(tmp_path) == 0
    assert not (tmp_path / "runs").exists()


def test_duplicate_of_points_at_survivor(tmp_path, monkeypatch):
    def chain(cfg, since):  # A is a URL dup of B; B is an embedding dup of C (C has the full text)
        return CollectorResult(source="hackernews", packets=[
            pkt("hackernews", "https://b.com/x", "Alpha one"),
            pkt("hackernews", "https://b.com/x?utm_source=z", "Alpha one"),
            pkt("hackernews", "https://full.com/x", "Alpha two"),
        ])

    res = pipeline.run(CFG, registry=_single(monkeypatch, chain), runs_dir=tmp_path / "runs",
                       data_dir=tmp_path / "data", embed_fn=fake_embed, fetch=lambda u: LONG if "full" in u else None)
    assert [p.url for p in res.kept] == ["https://full.com/x"]
    assert len(res.dropped) == 2 and all(d["duplicate_of"] == res.kept[0].id for d in res.dropped)


def test_github_releases_skip_embedding_dedupe(tmp_path, monkeypatch):
    def releases(cfg, since):
        return CollectorResult(source="github_releases", packets=[
            pkt("github_releases", f"https://github.com/snyk/cli/releases/tag/v1.{i}", "cli v1.preview")
            for i in (1, 2)])

    reg = {"github_releases": _single(monkeypatch, releases)["hackernews"]}
    res = pipeline.run(CFG, registry=reg, runs_dir=tmp_path / "runs", data_dir=tmp_path / "data",
                       embed_fn=fake_embed, fetch=lambda u: None)
    assert len(res.kept) == 2 and res.report["sources"]["github_releases"]["dup_embedding"] == 0


def test_naive_published_at_counts_as_utc():
    naive = (utc_now() - timedelta(hours=2)).replace(tzinfo=None)
    p = pipeline.stamp(pkt("hackernews", "https://a.com", "t").model_copy(update={"published_at": naive}),
                       "rid", utc_now())
    assert p.in_24h and p.published_at.tzinfo is not None
    assert not pipeline.stamp(pkt("hackernews", "https://a.com", "t"), "rid", utc_now()).in_24h  # no date


MENTION_CFG = CIConfig(competitors=[{"key": "sonatype", "name": "Sonatype"}, {"key": "snyk", "name": "Snyk"},
                                    {"key": "industry", "name": "Industry"}])


def test_top5_list_counts_a_competitor_named_only_past_the_cap():
    from ci.classify import MentionCounter

    page = "Top 5 SCA tools. 1. Snyk is popular. " + "filler " * 1200 + "5. Sonatype Nexus Lifecycle. JFrog too."
    assert page.index("Sonatype") > pipeline.TEXT_MAX_CHARS
    p = pipeline.read_full_text(pkt("google_news", "https://hackernoon.com/top5", "Top 5 SCA tools"),
                                lambda u: page, count=MentionCounter(MENTION_CFG))
    assert len(p.text) == pipeline.TEXT_MAX_CHARS and "Sonatype" not in p.text
    assert p.mentions == {"sonatype": 1, "snyk": 1} and p.mentions_jfrog is True
    assert p.mentions_config == MentionCounter(MENTION_CFG).config_hash


def test_snippet_mentions_are_counted_over_the_teaser():
    from ci.classify import MentionCounter

    teaser = pkt("google_news", "https://a.com/x", "Sonatype news").model_copy(
        update={"text": "Sonatype and Snyk said"})
    p = pipeline.read_full_text(teaser, lambda u: None, count=MentionCounter(MENTION_CFG))
    # the title ("Sonatype news") is not counted: the classifier weights title mentions itself
    assert p.text_status == "snippet" and p.mentions == {"sonatype": 1, "snyk": 1} and not p.mentions_jfrog


def test_old_runs_without_mentions_still_load():
    old = {"source": "hackernews", "origin": "q", "competitor": "snyk", "title": "t", "url": "https://a",
           "original_url": "https://a"}
    p = Packet.model_validate(old)
    assert p.mentions == {} and p.mentions_jfrog is False


def test_report_counts_items_holding_another_items_title():
    from ci.packet import CollectorResult

    def mk(i, source, title, text):
        return Packet(source=source, origin="o", competitor="acme", title=title, url=f"https://a/{i}",
                      original_url=f"https://a/{i}", text=text, id=f"id{i}")

    kept = [mk(1, "vendor_feed", "npm installs are now faster", "Faster npm. Other logs: Set exact usage limits with "
               "numerical inputs. Deprecating password authentication for the API."),
            mk(2, "vendor_feed", "Set exact usage limits with numerical inputs", "Sliders are gone."),
            mk(3, "vendor_feed", "Deprecating password authentication for the API", "Use API keys."),
            mk(4, "hackernews", "Show HN: cli", "we talk about set exact usage limits with numerical inputs"),
            mk(5, "hackernews", "v1.30", "nothing")]  # short titles are never probes
    collected = {"vendor_feed": (CollectorResult(source="vendor_feed"), 1.0),
                 "hackernews": (CollectorResult(source="hackernews"), 1.0)}
    report = pipeline.build_report("r", collected, kept, kept, [],
                                   {"window_days": 7, "fresh": False, "duration_s": 1.0})
    assert report["sources"]["vendor_feed"]["contaminated"] == 1
    assert report["sources"]["vendor_feed"]["contaminated_ids"] == ["id1"]
    assert report["sources"]["hackernews"]["contaminated"] == 1 and report["totals"]["contaminated"] == 2
    table = pipeline.format_report(report)
    assert "contaminated" in table.splitlines()[1] and "~ vendor_feed: text holds another item's title: id1" in table


def test_same_story_titles_never_count_as_contamination():
    from ci import contamination

    items = [{"id": "a", "title": "GitLab patches critical RCE today", "text": "GitLab patches critical RCE today!"},
             {"id": "b", "title": "GitLab patches critical RCE today", "text": "GitLab patches critical RCE today"}]
    assert contamination.find(items) == {}


def test_short_titles_are_not_probes_even_when_punctuation_splits_them():
    from ci import contamination

    items = [{"id": "a", "title": "cli v1.1308.3", "text": "release notes"},
             {"id": "b", "title": "Announcing Snyk CLI v1.1308.3", "text": "We shipped cli v1.1308.3 today"}]
    assert contamination.find(items) == {}  # "cli v1.1308.3" is 2 words as written


def test_dropped_items_titles_are_probes():
    from ci import contamination

    items = [{"id": "a", "source": "vendor_feed", "title": "npm installs are now faster",
              "text": "Faster npm. Other logs: Set exact usage limits with numerical inputs"}]
    dropped = [{"id": "z", "title": "Set exact usage limits with numerical inputs"}]
    assert contamination.find(items) == {}
    assert contamination.find(items, dropped) == {"a": ["z"]}
    assert contamination.by_source(items, dropped)["vendor_feed"]["worst"] == ["a"]


def test_a_run_where_every_source_failed_writes_only_a_failed_report(tmp_path, registry):
    res = _run(tmp_path, registry, sources=["vendor_feed", "missing"])  # one crashes, one cannot be imported
    assert res.failed and res.report["status"] == "failed" and res.kept == []
    runs = tmp_path / "runs"
    assert not (runs / f"{res.run_id}.jsonl").exists() and not (runs / f"{res.run_id}.dropped.jsonl").exists()
    assert json.loads((runs / f"{res.run_id}.report.json").read_text())["status"] == "failed"
    assert "FAILED" in pipeline.format_report(res.report)


def test_a_partly_failing_or_quiet_run_is_ok(tmp_path, registry):
    res = _run(tmp_path, registry, sources=["hackernews", "vendor_feed"])
    assert not res.failed and res.report["status"] == "ok" and (tmp_path / "runs" / f"{res.run_id}.jsonl").exists()


def test_ci_run_exits_nonzero_and_prints_failed(tmp_path, registry, monkeypatch, capsys):
    from ci import run as run_cli

    monkeypatch.setattr(run_cli, "run", lambda cfg, **kw: _run(tmp_path, registry, sources=["vendor_feed"]))
    monkeypatch.setattr(run_cli.config, "load", lambda: CFG)
    with pytest.raises(SystemExit) as exc:
        run_cli.main([])
    assert exc.value.code == 1 and "FAILED" in capsys.readouterr().out


def test_a_dropped_duplicate_of_the_item_itself_is_not_contamination():
    from ci import contamination

    items = [{"id": "a", "title": "GitLab ships Orbit to everyone", "text": "GitLab Orbit is GA: agents get cheaper "
              "today. As reported, gitlab orbit is ga agents get cheaper today"}]
    dropped = [{"id": "z", "title": "GitLab Orbit is GA: agents get cheaper today", "duplicate_of": "a"},
               {"id": "y", "title": "GitLab Orbit is GA: agents get cheaper today", "duplicate_of": "z"}]  # chain
    assert contamination.find(items, dropped) == {}
    stranger = [{"id": "q", "title": "GitLab Orbit is GA: agents get cheaper today", "duplicate_of": "other"}]
    assert contamination.find(items, stranger) == {"a": ["q"]}


def test_a_dropped_row_never_overwrites_a_kept_items_probe():
    from ci import contamination

    items = [{"id": "a", "title": "Snyk raises a big new round", "text": "x"},
             {"id": "b", "title": "unrelated", "text": "we heard snyk raises a big new round"}]
    dropped = [{"id": "a", "title": "Completely different headline here"}]
    assert contamination.find(items, dropped) == {"b": ["a"]}


def test_contamination_check_is_fast_on_thousands_of_items():
    import random
    import time

    from ci import contamination

    rng = random.Random(0)
    vocab = [f"w{i}" for i in range(3000)]
    items = [{"id": f"i{n}", "title": " ".join(rng.choices(vocab, k=7)),
              "text": " ".join(rng.choices(vocab, k=400))} for n in range(2000)]
    items[5]["text"] += " " + items[7]["title"]
    start = time.perf_counter()
    hits = contamination.find(items)
    assert time.perf_counter() - start < 3.0
    assert hits.get("i5") == ["i7"]
