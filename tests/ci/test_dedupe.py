"""URL normalization, the seen-URL store and embedding dedupe, offline (fake embedding function)."""
import hashlib

import numpy as np

from ci.dedupe import EmbeddingDeduper, SeenUrls, normalize_url, resolve_duplicates, url_dedupe
from ci.packet import Packet, packet_id


def fake_embed(texts):
    """Same leading word -> same vector: a stand-in for 'same story' that needs no model."""
    out = []
    for t in texts:
        seed = int(hashlib.md5(t.split()[0].lower().encode()).hexdigest()[:8], 16)
        out.append(np.random.default_rng(seed).normal(size=16).tolist())
    return out


def pkt(url, title="t", text="", status="snippet", resolved=True, original=None, run_id="r1"):
    p = Packet(source="hackernews", origin="q", competitor="snyk", title=title, url=url,
               original_url=original or url, url_resolved=resolved, text=text, text_status=status)
    return p.model_copy(update={"id": packet_id(url), "run_id": run_id})


def test_normalize_url():
    assert normalize_url("https://Example.COM/a/b/?utm_source=x&id=3&ref=hn&source=rss#frag") == \
        "https://example.com/a/b?id=3"
    assert normalize_url("https://a.com/x/") == normalize_url("https://a.com/x")
    assert normalize_url("https://news.ycombinator.com/item?id=123") == "https://news.ycombinator.com/item?id=123"


def test_url_dedupe_within_run_prefers_resolved():
    unresolved = pkt("https://news.google.com/rss/articles/abc", resolved=False)
    resolved = pkt("https://pub.com/story", original="https://news.google.com/rss/articles/abc")
    twin = pkt("https://pub.com/story/?utm_medium=rss")
    kept, dropped = url_dedupe([unresolved, resolved, twin], seen=None)
    assert kept == [resolved]
    assert {d[0].url for d in dropped} == {unresolved.url, twin.url}
    assert all(d[2] == resolved.id for d in dropped)


def test_url_dedupe_against_history(tmp_path):
    seen = SeenUrls(tmp_path / "seen.sqlite")
    old = pkt("https://pub.com/story", run_id="run-old")
    seen.add([old])
    seen.close()
    seen = SeenUrls(tmp_path / "seen.sqlite")  # persisted across instances
    kept, dropped = url_dedupe([pkt("https://pub.com/story#x", run_id="r2"), pkt("https://pub.com/new")], seen)
    assert [p.url for p in kept] == ["https://pub.com/new"]
    assert dropped[0][2] == old.id and "run-old" in dropped[0][1]
    assert url_dedupe([pkt("https://pub.com/story")], None)[0]  # no store (--fresh): kept
    seen.close()


def test_embedding_dedupe_keeps_richer_copy(tmp_path):
    d = EmbeddingDeduper(tmp_path / "chroma", fake_embed)
    snippet = pkt("https://a.com/1", title="Breach at Snyk", status="snippet")
    full = pkt("https://b.com/1", title="Breach at Snyk", text="long text", status="full")
    other = pkt("https://c.com/1", title="Unrelated news")
    kept, dropped = d.dedupe([snippet, full, other])
    assert {p.url for p in kept} == {full.url, other.url}
    assert [(p.url, dup) for p, _, dup in dropped] == [(snippet.url, full.id)]
    assert d._col is not None and d._col.count() == 0  # nothing stored until remember()


def test_embedding_dedupe_against_history_and_fresh(tmp_path):
    first = EmbeddingDeduper(tmp_path / "chroma", fake_embed)
    old = pkt("https://a.com/1", title="Breach at Snyk", run_id="run-old")
    first.remember(first.dedupe([old])[0])

    second = EmbeddingDeduper(tmp_path / "chroma", fake_embed)
    again = pkt("https://b.com/1", title="Breach reported", status="full", run_id="r2")
    kept, dropped = second.dedupe([again])
    assert kept == [] and dropped[0][2] == old.id and "run-old" in dropped[0][1]
    assert second.dedupe([again], use_history=False)[0] == [again]


def test_client_is_lazy(tmp_path):
    d = EmbeddingDeduper(tmp_path / "chroma", fake_embed)
    assert d._col is None and not (tmp_path / "chroma").exists()
    assert d.dedupe([]) == ([], [])
    assert d._col is None


def angle_embed(texts):
    """Title "sim 0.83 ..." embeds at cosine 0.83 to the base vector [1, 0]; any other title is the base."""
    out = []
    for t in texts:
        s = float(t.split()[1]) if t.startswith("sim ") else 1.0
        out.append([s, (1 - s * s) ** 0.5])
    return out


def test_embedding_threshold_boundary(tmp_path):
    d = EmbeddingDeduper(tmp_path / "chroma", angle_embed)
    base = pkt("https://a.com/base", title="Base story", status="full")
    above = pkt("https://a.com/above", title="sim 0.83 above")
    below = pkt("https://a.com/below", title="sim 0.81 below")
    kept, dropped = d.dedupe([base, above, below], use_history=False)
    assert {p.url for p in kept} == {base.url, below.url}
    assert [(p.url, dup) for p, _, dup in dropped] == [(above.url, base.id)]


def test_resolve_duplicates_follows_chain_to_survivor():
    a, b, c = pkt("https://a.com"), pkt("https://b.com"), pkt("https://c.com")
    drops = [(a, "url", b.id), (b, "emb", c.id), (pkt("https://d.com"), "history", "old-run-id")]
    resolved = resolve_duplicates(drops, kept_ids={c.id})
    assert [dup for _, _, dup in resolved] == [c.id, c.id, "old-run-id"]
