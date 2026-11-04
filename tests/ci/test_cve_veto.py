"""D38 CVE veto, pinned on the two false merges of the manual cluster review (D24): events 6 and 8 of run 389e71.

The fake embedding gives texts that start with the same word the same vector (similarity 1.0), so only the veto can
keep these apart: exactly the case D38 is for (different GitLab CVEs, near-identical wording)."""
from datetime import UTC, datetime

from ci import insights
from ci.dedupe import EmbeddingDeduper, cve_ids, cve_veto
from ci.packet import Packet
from tests.ci.test_dedupe import fake_embed

# Event 6 (manual review: "different vulnerabilities and security releases despite shared GitLab regex-engine context")
E6 = [("6a7e0fe1cff862af", "GitLab RCE Hits CVSS 10.0, 7 Branches Patched [2026]",
       "GitLab fixed CVE-2026-110264 on October 21; an earlier flaw, CVE-2026-97229, was patched before."),
      ("1a425a273e291b93", "GitLab Patches Two Critical 9.9 RCE Flaws in Regex Engine",
       "GitLab patched CVE-2026-93577 and CVE-2026-89078 (CVSS 9.9) on September 23.")]
# Event 8 (manual review: "different security incidents, CVEs, release versions, and remediation actions")
E8 = [("9c3fe8f01f4a5c7a", "GitLab Critical Patch Release: 19.5.1, 19.4.3, 19.3.6, 19.2.9, 19.1.9, 19.0.10, 18.11.13",
       "This release fixes CVE-2026-110264, CVE-2026-105777 and CVE-2026-112212."),
      ("e30ab49652d6854c", "GitLab Patch Release and Security Update: 19.5.3, 19.4.5, 19.3.7, 19.2.10, 19.1.10, "
       "19.0.11, 18.11.1", "This update addresses CVE-2026-111943 (compromised eMudhra CA certificates).")]


def pkt(item_id, title, text, run_id="r1"):
    return Packet(source="google_news", origin="q", competitor="gitlab", title=title, url=f"https://x.example/{item_id}",
                  original_url=f"https://x.example/{item_id}", published_at=datetime(2026, 10, 29, tzinfo=UTC),
                  text=text, text_status="full", id=item_id, run_id=run_id)


def test_veto_needs_ids_on_both_sides_and_none_shared():
    a, b = cve_ids("fix for cve-2026-110264"), cve_ids("CVE-2026-111943")
    assert a == {"CVE-2026-110264"} and cve_veto(a, b)
    assert not cve_veto(a, cve_ids("CVE-2026-110264 and CVE-2026-1"))  # one shared ID: may merge
    assert not cve_veto(a, frozenset()) and not cve_veto(frozenset(), frozenset())  # no IDs: as before


def test_event_6_and_8_are_not_dropped_as_duplicates_within_a_run(tmp_path):
    for pair in (E6, E8):
        kept, dropped = EmbeddingDeduper(tmp_path / pair[0][0], fake_embed).dedupe([pkt(*x) for x in pair],
                                                                                   use_history=False)
        assert {p.id for p in kept} == {pair[0][0], pair[1][0]} and dropped == []


def test_without_the_cve_mismatch_the_same_pair_is_still_a_duplicate(tmp_path):
    shared = [pkt(E8[0][0], E8[0][1], "Fixes CVE-2026-110264."), pkt(E8[1][0], E8[1][1], "Also CVE-2026-110264.")]
    assert len(EmbeddingDeduper(tmp_path / "a", fake_embed).dedupe(shared, use_history=False)[1]) == 1
    plain = [pkt(E8[0][0], E8[0][1], "A patch release."), pkt(E8[1][0], E8[1][1], "Another patch release.")]
    assert len(EmbeddingDeduper(tmp_path / "b", fake_embed).dedupe(plain, use_history=False)[1]) == 1


def test_event_8_against_history_kept_and_old_history_backfilled(tmp_path):
    first = EmbeddingDeduper(tmp_path / "chroma", fake_embed)
    first.remember([pkt(*E8[0])])
    later = EmbeddingDeduper(tmp_path / "chroma", fake_embed)
    kept, dropped = later.dedupe([pkt(*E8[1], run_id="r2")])
    assert [p.id for p in kept] == [E8[1][0]] and dropped == []
    # history stored before D38 has no "cves" metadata; the backfill gives it the full-text IDs
    col = later._collection()
    col.update(ids=[E8[0][0]], metadatas=[{"run_id": "r1", "url": "u", "title": "t"}])
    assert later.backfill_cves({E8[0][0]: cve_ids(E8[0][2]), "unknown": frozenset()}) == 1
    assert col.get(ids=[E8[0][0]], include=["metadatas"])["metadatas"][0]["cves"] == \
        "CVE-2026-105777,CVE-2026-110264,CVE-2026-112212"


def item(item_id, title, text):
    return {"item_id": item_id, "title": title, "text": text, "source": "google_news", "text_status": "full",
            "url_resolved": True}


def test_event_6_and_8_split_in_story_grouping_and_a_cve_free_copy_still_joins():
    rows = [item(*x) for x in E6 + E8] + [item("plain0000000000a", "GitLab urges users to upgrade now", "No IDs.")]
    story_of = insights.stories(rows, fake_embed)
    assert len({story_of[x[0]] for x in E6}) == 2 and len({story_of[x[0]] for x in E8}) == 2
    assert story_of["plain0000000000a"] in {story_of[x[0]] for x in E6 + E8}  # no CVE IDs: joins as before
    assert len(set(insights.stories(rows, fake_embed, veto=False).values())) == 1  # without the veto: one story
