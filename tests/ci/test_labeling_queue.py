"""Stratified labeling queue: bucket sizes and fills, one bucket per item, seeded order, labeled items, storage."""
import json
import random

import pytest
from fastapi.testclient import TestClient

from ci.config import CIConfig, Competitor, Feed
from ci.labeling import stratified
from ci.labeling.app import create_app

CFG = CIConfig(competitors=[Competitor(key="snyk", name="Snyk"), Competitor(key="sonatype", name="Sonatype"),
                            Competitor(key="industry", name="Industry")])


def _item(id_: str, competitor: str, title: str, source: str = "vendor_feed", text: str = "") -> dict:
    return {"id": id_, "run_id": "r1", "source": source, "origin": "q", "competitor": competitor, "title": title,
            "url": f"https://a.com/{id_}", "original_url": f"https://a.com/{id_}", "url_resolved": True,
            "published_at": None, "text": text or title, "text_status": "snippet", "publisher": "", "in_24h": True}


def _run(n_snyk=10, n_sonatype=2, n_industry=10, n_noise=30) -> list[dict]:
    items = [_item(f"snyk{i}", "snyk", f"Snyk launches feature {i}") for i in range(n_snyk)]
    items += [_item(f"sona{i}", "sonatype", f"Sonatype launches Nexus feature {i}") for i in range(n_sonatype)]
    items += [_item(f"ind{i}", "industry", f"Malicious npm packages {i}", "google_news") for i in range(n_industry)]
    items += [_item(f"noise{i}", "snyk", f"Snyk stock rally {i}", "google_news") for i in range(n_noise)]
    return items


def _sizes(q: dict) -> dict[str, int]:
    return {b["name"]: b["target"] for b in q["buckets"]}


def test_noise_signal_beats_the_prefilled_competitor():
    clf = stratified.Classifier(None, CFG)
    nexus = _item("x", "sonatype", "Hyphenate raises $45M led by Nexus", "google_news", "a fintech round")
    assert stratified.bucket_of(nexus, clf)[0] == stratified.NOISE
    assert stratified.bucket_of(_item("y", "snyk", "Snyk shares fall after earnings"), clf)[0] == stratified.NOISE
    assert stratified.bucket_of(_item("z", "snyk", "Snyk launches feature"), clf) == ("snyk", "prefilled snyk")
    assert stratified.bucket_of(_item("w", "none", "Something else"), clf)[0] == stratified.REST


def test_short_bucket_is_filled_from_noise():
    q = stratified.build_queue("r1", _run(n_noise=50), set(), CFG)
    # two competitors leave noise 40; sonatype has 2 of 6, so noise also takes the 4-item gap
    assert _sizes(q) == {"snyk": 6, "sonatype": 2, "industry": 8, "noise": 44, "rest": 0}
    assert len(q["entries"]) == stratified.TARGET


def test_gap_falls_to_the_rest_when_noise_runs_dry():
    q = stratified.build_queue("r1", _run(n_noise=5), set(), CFG)
    # gap 4 + 39 missing noise, but only 4 snyk + 2 industry are left over
    assert _sizes(q) == {"snyk": 6, "sonatype": 2, "industry": 8, "noise": 5, "rest": 6}
    rest = {e["id"] for e in q["entries"] if e["bucket"] == "rest"}
    assert rest == {f"snyk{i}" for i in range(10)} - {e["id"] for e in q["entries"] if e["bucket"] == "snyk"} \
        | {f"ind{i}" for i in range(10)} - {e["id"] for e in q["entries"] if e["bucket"] == "industry"}


def test_real_target_sizes_with_six_competitors():
    keys = ["cloudsmith", "sonatype", "github", "gitlab", "snyk", "aws"]
    names = {k: k.title() for k in keys} | {"aws": "Amazon ECR"}  # a bare "AWS" is not an alias, its products are
    cfg = CIConfig(competitors=[Competitor(key=k, name="AWS" if k == "aws" else names[k],
                                           aliases=["Amazon ECR"] if k == "aws" else []) for k in keys]
                   + [Competitor(key="industry", name="Industry")])
    items = [_item(f"{k}{i}", k, f"{names[k]} launches feature {i}") for k in keys for i in range(9)]
    items += [_item(f"ind{i}", "industry", f"Supply chain attack {i}", "google_news") for i in range(12)]
    items += [_item(f"n{i}", "gitlab", f"Gitlab stock price target {i}", "google_news") for i in range(20)]
    q = stratified.build_queue("r1", items, set(), cfg)
    assert sum(_sizes(q).values()) == stratified.TARGET == 60
    assert _sizes(q) == {**dict.fromkeys(keys, 6), "industry": 8, "noise": 16, "rest": 0}


def test_each_item_in_exactly_one_bucket():
    q = stratified.build_queue("r1", _run(n_noise=5), set(), CFG)
    ids = [e["id"] for e in q["entries"]]
    assert len(ids) == len(set(ids))
    noise = {e["id"] for e in q["entries"] if e["bucket"] == "noise"}
    assert all(i.startswith("noise") for i in noise)  # stock chatter never lands in the snyk bucket
    assert not any(e["id"].startswith("noise") for e in q["entries"] if e["bucket"] != "noise")


def test_seed_gives_a_stable_order():
    items = _run()
    a = stratified.build_queue("r1", items, set(), CFG)
    shuffled = items[:]
    random.Random(7).shuffle(shuffled)
    assert stratified.build_queue("r1", shuffled, set(), CFG) == a  # input order does not matter
    assert [e["id"] for e in stratified.build_queue("r2", items, set(), CFG)["entries"]] != \
        [e["id"] for e in a["entries"]]  # another run gets its own shuffle


def test_already_labeled_items_count_toward_their_bucket():
    items = _run()
    default = {e["id"] for e in stratified.build_queue("r1", items, set(), CFG)["entries"] if e["bucket"] == "snyk"}
    labeled = {f"snyk{i}" for i in range(10)} - default  # the 4 the seed left out
    q = stratified.build_queue("r1", items, labeled, CFG)
    picked = {e["id"] for e in q["entries"] if e["bucket"] == "snyk"}
    assert labeled <= picked and len(picked) == 6
    prog = stratified.with_progress(q, {i: {} for i in labeled})
    assert next(b for b in prog["buckets"] if b["name"] == "snyk")["labeled"] == 4 and prog["labeled"] == 4


@pytest.fixture
def client(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "r1.jsonl").write_text("".join(json.dumps(it) + "\n" for it in _run()), encoding="utf-8")
    return TestClient(create_app(runs_dir=runs, labels_path=tmp_path / "golden_set.jsonl", cfg=CFG)), runs


def test_queue_api_is_stored_reused_and_not_a_run(client):
    c, runs = client
    q = c.get("/api/runs/r1/queue").json()
    assert q["total"] == 52 and q["labeled"] == 0  # 6 + 2 + 8 + all 30 noise + 6 rest
    assert (runs / "r1.queue.json").exists()
    assert [r["run_id"] for r in c.get("/api/runs").json()] == ["r1"]
    assert c.get("/api/meta").json()["runs"] == ["r1"]
    # reused, not rebuilt: a hand edit to the stored file shows through
    stored = json.loads((runs / "r1.queue.json").read_text())
    stored["seed"] = "edited"
    (runs / "r1.queue.json").write_text(json.dumps(stored))
    assert c.get("/api/runs/r1/queue").json()["seed"] == "edited"
    assert c.get("/api/runs/nope/queue").status_code == 404


def test_queue_api_counts_labels_per_bucket(client):
    c, _ = client
    first = c.get("/api/runs/r1/queue").json()["entries"][0]
    body = {"id": first["id"], "run_id": "r1", "competitor": "snyk", "noise": True, "basis": "full"}
    assert c.post("/api/labels", json=body).status_code == 200
    q = c.get("/api/runs/r1/queue").json()
    assert q["labeled"] == 1
    assert next(b for b in q["buckets"] if b["name"] == first["bucket"])["labeled"] == 1


def _cfg(n: int) -> CIConfig:
    return CIConfig(competitors=[Competitor(key=f"c{i}", name=f"Vendor{i}") for i in range(n)]
                    + [Competitor(key="industry", name="Industry")])


@pytest.mark.parametrize("n, per, noise", [(4, 6, 28), (6, 6, 16), (9, 5, 7)])
def test_targets_sum_to_target_for_any_number_of_competitors(n, per, noise):
    quotas, noise_quota = stratified.quotas_for([f"c{i}" for i in range(n)])
    assert sum(quotas.values()) + noise_quota == stratified.TARGET
    assert quotas["c0"] == per and quotas["industry"] == 8 and noise_quota == noise
    items = [_item(f"c{k}-{i}", f"c{k}", f"Vendor{k} launches feature {i}") for k in range(n) for i in range(8)]
    items += [_item(f"ind{i}", "industry", f"Malicious npm packages {i}", "google_news") for i in range(10)]
    items += [_item(f"n{i}", "c0", f"Vendor0 stock rally {i}", "google_news") for i in range(40)]
    q = stratified.build_queue("r1", items, set(), _cfg(n))
    assert len(q["entries"]) == stratified.TARGET and _sizes(q)["noise"] == noise


def test_first_party_means_the_competitors_own_feed():
    snyk = Competitor(key="snyk", name="Snyk", feeds=[Feed(url="https://snyk.io/blog/feed/")])
    cfg = CIConfig(competitors=[snyk, *CFG.competitors[1:]])
    clf = stratified.Classifier(None, cfg)
    own = {**_item("a", "snyk", "Python 3.15 support"), "origin": "https://snyk.io/blog/feed/"}
    other = {**_item("b", "snyk", "Python 3.15 support"), "origin": "https://example.com/feed"}
    assert stratified.noise_signal(own, clf) is None  # its own blog need not repeat its name
    assert stratified.noise_signal(other, clf) == "Snyk never named: ambiguous name or generic match"


def test_stale_queue_is_flagged_but_never_rebuilt_on_its_own(client):
    c, runs = client
    first = c.get("/api/runs/r1/queue").json()
    assert first["stale"] is False and first["rules_hash"] == stratified.rules_hash(CFG)
    # a queue saved before hashing (like the live one) or with other rules: kept as is, flagged
    stored = json.loads((runs / "r1.queue.json").read_text())
    del stored["rules_hash"]
    stored["entries"] = stored["entries"][::-1]
    (runs / "r1.queue.json").write_text(json.dumps(stored))
    again = c.get("/api/runs/r1/queue").json()
    assert again["stale"] is True and again["entries"] == stored["entries"]
    assert stratified.rules_hash(_cfg(2)) != stratified.rules_hash(CFG)
    # only the explicit rebuild replaces it, and it keeps labeled items
    labeled_id = next(e["id"] for e in first["entries"] if e["bucket"] == "snyk")
    c.post("/api/labels", json={"id": labeled_id, "run_id": "r1", "competitor": "snyk", "noise": True,
                                "basis": "partial"})
    rebuilt = c.post("/api/runs/r1/queue/rebuild").json()
    assert rebuilt["stale"] is False and rebuilt["labeled"] == 1
    assert labeled_id in {e["id"] for e in rebuilt["entries"]}
    assert json.loads((runs / "r1.queue.json").read_text())["rules_hash"] == stratified.rules_hash(CFG)
