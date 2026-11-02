# Evidence table (DRAFT, 2 Nov 2026)

Every number used in `STAGE1_OVERVIEW.md` and `GAPS_AND_QUESTIONS.md`, one row each, taken from `docs/specs/PRD.md`
only. Numbers that appear only in the README are not used.

**Status.** PROVEN: measured on data the tuning never saw. EXPERIMENTAL: measured, but small n, single labeler, or
the tuning data. PENDING: planned, not run yet. FUTURE: not built.

**Rule applied here.** Every golden-set, reliability, lens and insight mark is by one labeler (Ofri), so no labelled
quality result is PROVEN in this draft. PROVEN is used only for mechanical checks that need no label. Single-run
operational counts are EXPERIMENTAL (n = 1 run). How to class the test-split result once it exists is an open question
(GAPS_AND_QUESTIONS.md, part d).

## 1. Measurements

| # | Value | n | What it measures | Source | Status | Measured on |
| --- | --- | --- | --- | --- | --- | --- |
| **Operations** | | | | | | |
| 1 | 26 new items, 15 scored, 3 published, 12 held at Strict (unvetted source) | 1 run (20261101T0400Z-e9cae4) | Daily run output, 1 Nov | Closing plan; D54 | EXPERIMENTAL | 1 Nov 2026 |
| 2 | 11 further items were noise | same run | Noise count of the 1 Nov run | D54 | EXPERIMENTAL | 1 Nov 2026 |
| 3 | 13 new, 7 noise, 6 scored, 1 published (score 3), 5 held (unvetted), 0 scored 4+ | 1 run (20261102T0400Z-bed018) | Daily run output, 2 Nov | Status Mon 2 Nov | EXPERIMENTAL | 2 Nov 2026 |
| 4 | Lens 6 of 6 ok; insights 4 produced, 12 claims, 0 rejected | same run | Step outcomes of the 2 Nov run | Status Mon 2 Nov | EXPERIMENTAL | 2 Nov 2026 |
| 5 | Strict held 84; Balanced held 28 | 228 non-noise items, 14 publication days | Review load per autonomy level | D34 | EXPERIMENTAL | 31 Oct 2026 |
| 6 | Strict holds a median 2.5 per day (max 24) | same 228 items | Daily review load at Strict | D34 | EXPERIMENTAL | 31 Oct 2026 |
| 7 | 71% of items extracted | 325 items | Full-text extraction success | D39 | EXPERIMENTAL | 31 Oct 2026 |
| 8 | 0 of 15 extracted | 15 items from 3 sites | Sites behind a Cloudflare challenge | D39 | EXPERIMENTAL | 31 Oct 2026 |
| 9 | 0 differences | 1,374 prompts (351 stored items, 107 golden rows) | Classify guard fix changed no rendered prompt | D57 | PROVEN (mechanical) | 1 Nov 2026 |
| 10 | 0 advisories in the store; 0 of 325 classified items would flip | 351 items / 325 items | Effect of vetting security advisories | D57 | EXPERIMENTAL | 1 Nov 2026 |
| 11 | 1,189 Python tests pass, plus the UI tests | test suite | Merged code at ae8fbb5 | Closing plan (merge order; Status Mon 2 Nov) | PROVEN (mechanical) | 1–2 Nov 2026 |
| 12 | Pack recompute: every number back, 0 different | numbers in the repro pack (count not stated) | Reproducibility pack | Closing plan (merge order) | PROVEN (mechanical) | 1 Nov 2026 |
| 13 | 79 items → 79 stories; 0 of 37 labelled same-event pairs reach the insights window at Strict | 79 items; 37 pairs | Story grouping under Strict routing | D45 | EXPERIMENTAL | 31 Oct 2026 |
| 14 | 21 of 35 same-event pairs grouped; 1 of 5 different pairs merged (at 0.821) | 35 / 5 pairs | Story grouping at 0.82 | D45 | EXPERIMENTAL | 31 Oct 2026 |
| 15 | 7 of 9 multi-item events are one event, 2 mixed | 9 events, 26 items | Hand review of clusters, before the CVE veto | D38 | EXPERIMENTAL | 31 Oct 2026 |
| 16 | 7 of 12 near-miss pairs the same event, 5 different | 12 pairs (0.75–0.82) | Whether a looser 0.75 link would help | D38 | EXPERIMENTAL | 31 Oct 2026 |
| **Classification and ranking, train split (tuning data)** | | | | | | |
| 17 | Category accuracy 0.66 | 59 | Run 3 on train | D41 | EXPERIMENTAL | 31 Oct 2026 |
| 18 | Noise precision 0.88 / recall 0.74 | 16 / 19 | Run 3 on train | D41 | EXPERIMENTAL | 31 Oct 2026 |
| 19 | Score within 1 point: 1.00 | 57 | Run 3 on train | D41 | EXPERIMENTAL | 31 Oct 2026 |
| 20 | Mean score error +0.11 (was +0.22) | not stated | Run 3 on train | D41 | EXPERIMENTAL | 31 Oct 2026 |
| 21 | Labeled 2, predicted 3: 7 of 23 (was 9 of 20) | 23 | Run 3 on train | D41 | EXPERIMENTAL | 31 Oct 2026 |
| 22 | Industry competitor errors 0.63 | 19 | Diagnosed, not fixed (D41 gives the figure without saying whether it is an accuracy or an error rate) | D41 | EXPERIMENTAL | 31 Oct 2026 |
| 23 | Category accuracy 0.65; 37 of 55 scores exact; mean error +0.22; 3-vs-4 errors 3 of 25; Security→Product 9 items | 60 / 55 / 25 | First train eval (78 items) | D40 | EXPERIMENTAL | 31 Oct 2026 |
| 24 | Noise pre-filter precision 1.00, 0 relevant dropped | 5 | Shadow mode on the golden set | D41 | EXPERIMENTAL | 31 Oct 2026 |
| 25 | Noise pre-filter noise recall 0.16 | 32 | Shadow mode | Remaining work, Pipeline fixes | EXPERIMENTAL | before 31 Oct (date not stated) |
| 26 | 28 of 60 golden labels are noise | 60 | Share of noise in the input | D25 | EXPERIMENTAL | 30 Oct 2026 |
| 27 | 107 golden rows | — | Size of the golden set | D57 | (count) | 1 Nov 2026 |
| 28 | 1 test label scored 4+ | test split | Why important-item P/R on test is uninformative | D59 | EXPERIMENTAL | 1 Nov 2026 |
| **Classification and ranking, test split** | | | | | | |
| 29 | [PENDING: test-split eval] | [PENDING: test-split eval] | Competitor, category, noise, score on the test split, once, on ae8fbb5 | D23, D66 | PENDING | started 2 Nov 2026 (D66) |
| **Reliability checks of daily runs** | | | | | | |
| 30 | Competitor wrong 0 of 15; category wrong 1 of 15 | 15 scored items | 1 Nov check (unsure counts as wrong) | D55 | EXPERIMENTAL | 1 Nov 2026 |
| 31 | Items scored 4: 1 of 2 wrong → check failed | 2 | 1 Nov check, high-score condition | D55 | EXPERIMENTAL | 1 Nov 2026 |
| 32 | Pass line: at most 1 wrong competitor or category, no 4+ item wrong | planned n = 20, applied to 15 | Line set before marks | D52, D54 | (setting) | 31 Oct 2026 |
| 33 | [PENDING: repeat check of 2 Nov] | 6 scored items, none 4+ | 2 Nov repeat check, same line and rule | D55, D66 | PENDING | 2 Nov 2026 run |
| 34 | 21 | 15 + 6 | The two checks together, each day reported apart | Status Mon 2 Nov | PENDING (second half) | 1–2 Nov 2026 |
| **Lens** | | | | | | |
| 35 | Axis right 10 of 10 | 10 | 1 Nov check | D58 | EXPERIMENTAL | 1 Nov 2026 |
| 36 | Capability quote right 5 of 9 | 9 | 1 Nov check | D58 | EXPERIMENTAL | 1 Nov 2026 |
| 37 | Relation right 0 of 8 where a relation was claimed | 8 | 1 Nov check | D58 | EXPERIMENTAL | 1 Nov 2026 |
| 38 | not_related right 6 of 6 | 6 | 1 Nov check | D58 | EXPERIMENTAL | 1 Nov 2026 |
| 39 | 5 of the 8 wrong relations had no fitting value; 3 were a wrong choice | 8 | Taxonomy gap | D58 | EXPERIMENTAL | 1 Nov 2026 |
| 40 | 15 lenses: 14 ok, 1 rejected; improves_shared 7, not_related 6, closes_gap 1, opens_gap 0 | 15 | First daily run with the lens, 1 Nov | Item lifecycle, Lens reference | EXPERIMENTAL | 1 Nov 2026 |
| 41 | Quote check 5 of 5; 14 of 14 lenses kept | 5 / 14 | First real run | D45 | EXPERIMENTAL | 31 Oct 2026 |
| **Insights** | | | | | | |
| 42 | Claims supported 11 of 12 | 12 claims, 4 insights | 1 Nov 06:00 Brief, fingerprint 9ec366312774 | D60 | EXPERIMENTAL | 1 Nov 2026 |
| 43 | Cited items correct 12 of 12 | 12 | same | D60 | EXPERIMENTAL | 1 Nov 2026 |
| 44 | Quotes 9 of 12 (4 of the 9 partial) | 12 | same | D60 | EXPERIMENTAL | 1 Nov 2026 |
| 45 | Pattern type 4 of 4; title 1 of 4; summary 0 of 4; why it matters 1 of 4 | 4 | same | D60 | EXPERIMENTAL | 1 Nov 2026 |
| 46 | Insights with every field right: 0 of 4 | 4 | same | D60, D61 | EXPERIMENTAL | 1 Nov 2026 |
| 47 | Recall: 0 fully, 3 partly, 1 not found | 4 expected patterns | After D51 hardening, window 16–30 Oct, fingerprint e99d23e4edcf | D60 | EXPERIMENTAL | 1 Nov 2026 |
| 48 | Recall 1 of 4, partial; 3 of 4 generated insights match no pattern | 4 patterns | Before any generator change, fingerprint 9ec366312774 | D43 | EXPERIMENTAL | 31 Oct 2026 |
| 49 | 3 produced, 1 rejected | 1 re-run | Insights after D51 hardening | Closing plan | EXPERIMENTAL | 1 Nov 2026 |
| **Comparison with JFrog** | | | | | | |
| 50 | 35 of 42 competitor head-to-head cells hold a value with source and as-of date (1 stale); 7 empty | 42 cells | Competitors screen on real data | Closing plan (UI status report, 1 Nov) | EXPERIMENTAL | 1 Nov 2026 |
| 51 | JFrog column 7 of 7 | 7 cells | same | Closing plan | EXPERIMENTAL | 1 Nov 2026 |
| 52 | 0 changed cells | 42 cells | Change detection has produced no real changed cell | Closing plan | EXPERIMENTAL | 1 Nov 2026 |
| **Coverage** | | | | | | |
| 53 | 6 of 8 important events (75%) | 8 | Dev list, before the fix | D26 | EXPERIMENTAL | 30 Oct 2026 |
| 54 | 25 of 26; 11 of 11 important | 26 / 11 | Dev list, after the fix (fixes tuned on this list) | D26 | EXPERIMENTAL | 30 Oct 2026 |
| 55 | [PENDING: held-out coverage] | [PENDING: held-out coverage] | Held-out list, events 31 Oct–2 Nov, measured once | D26, D47 | PENDING | planned Tue 3 Nov |
| **Single cases (demo stories and known issues)** | | | | | | |
| 56 | Firewall caught as a 92-character snippet, scored 4 not 5 | 1 event | Coverage miss | D36; demo stories | EXPERIMENTAL | 30 Oct 2026 |
| 57 | 10 entries | 1 feed | GitHub changelog feed returns only its newest entries | Pitfalls | EXPERIMENTAL | 30 Oct 2026 |
| 58 | 10,438 → 652 characters | 1 article | Effect of the favor_precision setting | Demo stories | EXPERIMENTAL | date not stated |
| 59 | 2,145 → 885 characters | 1 item | Cloudsmith "Other logs" after stripping | Demo stories | EXPERIMENTAL | date not stated |
| 60 | Mentions JFrog bonus raised a score judged too high: 2 items | 2 | Known issue | D62 | EXPERIMENTAL | 1 Nov 2026 |
| 61 | 20 requests per day | — | Free-tier Gemini quota | Pitfalls | (external limit) | date not stated |
| 62 | 3 review rounds | 1 case | GitHub company vs place | D24; demo stories | EXPERIMENTAL | 30 Oct 2026 |
| 64 | 2 analyst writes on 1 Nov (1 Edit, 1 mistaken Dismiss) | 2 | First real analyst session | D62 | EXPERIMENTAL | 1 Nov 2026 |
| **Not built** | | | | | | |
| 65 | — | — | Faithfulness judge (Claude) | D17 | FUTURE (listed as built in Success metrics; see gaps) | — |
| 66 | — | — | Capture–recapture coverage estimate; "Missed event" button | Scope table; talking points | FUTURE | — |

The size of the injection regression set is not in the PRD (D51 says it is "reported with n"), so it is not used
here; see GAPS_AND_QUESTIONS.md, part c.

## 2. Settings and identifiers (not measurements)

These are design values, not results; the four-way status does not apply.

| Value | What it is | Source |
| --- | --- | --- |
| 06:00 Israel time | Daily run | D21 |
| 6 competitors + Industry | Scope | D10 |
| 7 categories | Taxonomy | D11 |
| 7 axes; 6 × 7 = 42 competitor cells (49 with JFrog) | Head-to-head | D13 |
| 1–5 + Noise | Rubric v2 | D29 |
| 3+ | Score shown in the Brief | D44 |
| 0.82 | Story similarity rule | D33 |
| 0.8 | Low-confidence hold (Strict and Balanced) | D36 |
| 0.85 | Fixed confidence of rule-settled items | Tagging rules B7; D34 |
| 7 days (14 if fewer than 15 stories) | Insights window | D37 |
| at least 2 stories | Per insight | D37 |
| 280 characters | Maximum excerpt | D36 |
| 6,000 characters | Stored text per item | D57 |
| 1,500 characters | Text the classifier sees per item | `ci/classify.py` (`LLM_TEXT_CHARS`) |
| 2,500 characters | Text the ranker sees per item | `ci/rank.py` (`LLM_TEXT_CHARS`) |
| +1, capped at 5 | Mentions JFrog bonus | D14; `ci/rank.py` (`JFROG_BONUS`) |
| 4 | Snippet cap (was 3 before 30 Oct) | `ci/rank.py` (`SNIPPET_SCORE_CAP`); value not in the PRD (gaps c24) |
| ×3 | A title mention counts as 3 text mentions when comparing competitors | Tagging rules B3; `ci/classify.py` (`TITLE_WEIGHT`) |
| under 25 words | Ranker reason length | `ci/rank.py` prompt |
| 1,500 characters; batches of 10 | Lens input | Lens reference |
| ≥ 6 characters; 1–200 characters | Lens quote and why checks | Lens reference |
| ~1 h; ~26 h | Stale and overdue run thresholds | D48 |
| 3+ approvals, 0 dismissals | Trust-this-source suggestion | D36 |
| 75/25 | Train/test split | D17 |
| 99b79890ceea; e04716a2a1d6; 1692c04ba7df; e99d23e4edcf; e7f13e0b3456 | classify_rank (legacy); portable; lens; insights; sheet_sha | D66; Status Mon 2 Nov |
