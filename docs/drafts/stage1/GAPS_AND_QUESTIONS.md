# Gaps and questions (DRAFT, 2 Nov 2026)

Checked against `docs/specs/PRD.md` (up to D66) and the repo at `main` ae8fbb5, read only. Owners follow the PRD:
Ofri, BE (backend agent), UI (frontend agent). Dates follow the Closing plan (D59): Tue 3 Nov verification, Wed 4 Nov
docs and submission, Thu 5 Nov buffer.

---

## a. Missing assets

### Screenshots

None exist yet for Stage 1 (only `docs/demo_1.png` and `docs/demo_2.png`, which predate Jessi's name and are not
checked here). All need the demo day chosen first (question d1).

| # | Screen | State to capture | Owner · when | Blocked by |
| --- | --- | --- | --- | --- |
| S1 | Daily Brief | The chosen demo day, "Demo snapshot <date>" badge visible; summary block (published, held by preliminary score); at least one published item scored 4+; the experimental insights section with its measured line (D61) | Ofri · Wed | Demo day (d1). D59: "no Brief day yet has both a published 4+ item and an insight" |
| S2 | Item card / drawer | One item with its three rows: What happened (≤ 280-char excerpt), "Closest JFrog capability" with the sheet line, Evidence with "Feed date" and text basis (D44, D45, D58) | Ofri · Wed | S1 |
| S3 | Held-item drawer (Review queue) | A held item with its hold reason, e.g. teaser-only high score at Strict; the action buttons; the level control showing Strict | Ofri · Wed | Demo day |
| S4 | Item history | An item whose actions show Dismiss then Reopen (D62; Ofri's reopen of d3e44c95ac969e9f) | Ofri · Wed | Whether the reopen is in the snapshot |
| S5 | Competitors overview | All six cards: items today / 7 days, threat level, category mix, Mentions JFrog count | Ofri · Wed | — |
| S6 | Competitor profile | Head-to-head table vs JFrog, source and as-of date per cell; 30-day activity; latest items. The "this week" summary returns `not_built` (question d9) | Ofri · Wed | d9 |
| S7 | Log | Filters, a dropped item with the stage it stopped at, colour-coded statuses | Ofri · Wed | — |
| S8 | Health | Run history with ok / degraded / failed markers; funnel; extraction per source (the three Cloudflare sites); the test-split eval with n, date and fingerprint | Ofri · Wed | [PENDING: test-split eval] |
| S9 | Roadmap tab (optional) | Concept cards marked "Concept, sample data" (D35). The page expects `frontend/public/roadmap/<slug>.png`; the folder is empty at ae8fbb5, so the tab shows no images today | Ofri adds images (Tue, optional per Closing plan); UI owns `frontend/` | Low priority (Closing plan) |

### Other assets

| Asset | What it must show | Owner · when | Status |
| --- | --- | --- | --- |
| Architecture diagram (image) | The three lanes into one store, API and UI; source can be the Mermaid in STAGE1_OVERVIEW.md §b | Ofri + Claude · Wed | Mermaid draft exists; no image |
| AWS production diagram | The PROPOSAL table of STAGE1_OVERVIEW.md §g as a picture; marked "proposal, not built, not load-tested" | Ofri + Claude · Tue (Closing plan: outline Tue, slide Wed) | Not started |
| Demo video script | Part b below, timed to 10 minutes | Ofri · Wed | Draft in part b |
| Demo video | Recorded on the frozen snapshot | Ofri · Wed | Not started |
| ARCHITECTURE.md | Flow, what each component does, data model (Remaining work, Docs and delivery). Proposed source: STAGE1_OVERVIEW.md §b and §g | Ofri + Claude · Wed | Not written (D59, Closing plan) |
| DECISIONS.md | Key decisions, each with what, why, what else was considered. Proposed source: STAGE1_OVERVIEW.md §c plus every D-ID the README cites. Needed because `docs/specs/` (the PRD) is gitignored and is not in the repo a reviewer clones | Ofri + Claude · Wed | Not written |
| Demo snapshot in the repo | `demo/snapshot/` from the chosen day; `docker-compose.yml` says it is "committed", but at ae8fbb5 `demo/` holds only README.md | BE · after d1 (D59 said Mon evening) | Not committed |

### README sections still to write

The README at ae8fbb5 has a short Jessi part (run the demo, what is built, architecture in short, insight window,
injection defense, known issues, future) followed by the newsletter agent's README.

1. **Evaluation table** with n next to every number (Closing plan, "We insist on" (6)), including both reliability
   checks and the D66 deviation stated next to them. [PENDING: test-split eval] [PENDING: repeat check of 2 Nov]
   [PENDING: held-out coverage]
2. **Single-labeler statement** (D17) and that production would use analyst labels with inter-rater agreement.
3. **Now vs future** list including every 1 Nov deferral (Closing plan "Not now").
4. **Challenges and pitfalls** (the PRD list; STAGE1_OVERVIEW.md §f).
5. **The demo day** presented as a selected run with its published and held counts (Closing plan).
6. **Live mode setup**: a live run needs a paid key or Vertex (Remaining work); the free-tier quota is 20 requests per
   day (Pitfalls).
7. **How to check the numbers**: the repro pack command, and where fingerprints are recorded.
8. **Screenshots**, linked.
9. **Remove or move the newsletter-agent sections** that a reviewer would read as Jessi (Tech stack, Setup with Gmail
   auth, Monitoring with LangSmith); see c14. Keep the credit to `newsletter_agent` (D8).
10. **Brief-to-repo map**: the brief's four asks, each with where it is answered.

---

## b. Demo story and slide outline

Based on D22 ("a day of an analyst"), updated by D44 (Brief hierarchy, chart removed), D58 (lens shows the closest
capability, not the relation) and D61 (insights marked experimental). **⚠ NEEDS REAL DATA** marks a step the data
does not support today.

### 10-minute demo

| Min | Step | What to show | Data status |
| --- | --- | --- | --- |
| 0:00–1:00 | Problem | The analyst's question, the six competitors and the Industry channel; "Demo snapshot <date>" badge | — |
| 1:00–3:00 | Daily Brief | Summary block: published vs held by preliminary score. An item card: what happened, closest JFrog capability, evidence with "Feed date". The experimental insights section: read the measured line aloud, open one claim and its source | **⚠ NEEDS REAL DATA:** a day with a published 4+ item and an insight (D59: none yet). Proposed but not decided: 1 Nov, by Ofri approving its held score-4 item before the freeze (Status Mon 2 Nov) |
| 3:00–5:00 | Competitors | Overview cards → one profile → head-to-head table with source and as-of date; explain how a tracked-page change would re-extract a cell and hold it | **⚠ NEEDS REAL DATA:** a changed head-to-head cell. 0 of 42 cells changed (Closing plan). Do not stage one; say it has not happened yet |
| 5:00–6:30 | Review and Log | A held item and its reason (the 1 Nov teaser-only score 4, held at Strict, is the item that failed the reliability check and never reached the Brief, D55). The three levels and what each holds. The Log: a dropped item and its stage | **⚠** D22 wants the level "moved live", but demo mode refuses every write (contract §12.2, `demo_read_only`). Needs live mode or a description (question d3) |
| 6:30–8:30 | Health | Run history and markers; extraction per source (the Cloudflare sites); the test-split eval with n; both reliability checks; the lens and insight checks | **⚠ NEEDS REAL DATA:** [PENDING: test-split eval], [PENDING: repeat check of 2 Nov] |
| 8:30–10:00 | Architecture, now vs future, pitfalls | One architecture slide, the now/future table, two pitfalls (the failed check; the lens relation) | [PENDING: held-out coverage] if quoted |

### Slide outline (9 slides)

1. **Jessi in one sentence**: the answer to the brief; the analyst's question.
2. **Two needs, five screens**: Daily Brief and Competitors; Review, Log, Health as the quality loop.
3. **How it works**: the architecture diagram (three lanes, one store).
4. **Trust controls**: autonomy levels and always-held reasons; prompt-injection layers and what stays open.
5. **How JFrog compares**: capability sheet, head-to-head per competitor, the lens; why the relation is hidden (0 of
   8, D58).
6. **What we measured**: the evaluation table with n and status. [PENDING: test-split eval] [PENDING: repeat check of
   2 Nov] [PENDING: held-out coverage]
7. **What went wrong and what we did**: the failed 1 Nov check, the firewall miss, insights that overstate and are
   rewritten daily.
8. **Built now vs future**: the table from STAGE1_OVERVIEW.md §d.
9. **Production path (proposal)**: the AWS mapping, marked "not built, not load-tested".

---

## c. Contradictions and stale text

Quotes are exact. Nothing here was resolved by this draft.

**c1. Faithfulness judge: listed as in scope, not in the code.**
- D17: "Metrics: classifier accuracy by competitor and category, noise precision/recall, ranker precision@k, summary
  faithfulness (Claude judge)".
- Success metrics, Correct row: "faithfulness judge from a different model family" with "In this submission: Yes".
- Scope table, Quality: "60-item golden set, test-split metrics, Claude judge, run funnel (D17)".
- Remaining work, Mon 2 Nov: "[ ] BE: insights faithfulness judge (Claude, D17)" (unticked).
- Repo: `ci/eval_golden.py` has no judge (the only match for "judge" is the variable `judged`). The Claude judge in the
  README is the newsletter agent's `modules/trace_judge.py`.

**c2. Golden-set size.**
- Scope table: "60-item golden set"; D17: "Golden set: 60 items"; Open questions: "→ 60 items, Ofri labels on Saturday
  (D17)"; Schedule: "60-item golden set".
- D57: "351 stored items, 107 golden rows". D40: "After the first train eval (78 items …)".

**c3. Schedule lines that predate D47, D55 and D66.**
- Schedule, item 6: "the test-split eval on Sun afternoon, after the reliability check of the 06:00 run".
- D47: "The test-split eval runs Sun afternoon".
- Remaining work, Mon 2 Nov: "BE: run the 26 held\_out items through the pipeline (the single test-split eval, logged
  with fingerprint, moved to Sun afternoon, D23, D47)".
- Later: D55 "moved to Mon morning"; D66 runs it on 2 Nov without waiting for the repeat-check marks.
- Schedule, item 4: "move development to k8" vs Remaining work: "Dropped from this submission: … the move to k8".
- Schedule, item 1: "coverage check (recall 96%)" vs D26: the after-fix recall "is optimistic and is reported only as
  'the fix works'".

**c4. Test-split size.** Remaining work says "the 26 held\_out items". The golden set grew to 107 rows (D57) with a
75/25 split (D17). The PRD does not state the test split's n at ae8fbb5.

**c5. Duplicate decision IDs.** D61 appears twice (insights marking refinement; insights display) and D60 appears twice
(marking guide; insights results). The log also runs D63, D62, D61, D60, D61, D60, D59, not strictly newest first.
Citing "D60" or "D61" is ambiguous.

**c6. Competitor "this week" summary.**
- Product table and D20: "Profile: AI-written 'this week' summary citing items".
- Remaining work: "the meaning layer (insights, JFrog lens, competitor 'this week' summary from D20, not yet built)".
- Repo: `ci/api/competitors.py` returns `"summary": {"status": "not_built"}`.

**c7. Product table, Daily Brief, predates D61.** "3–5 insights at the top, each citing the items it rests on" vs D61:
the section is "Experimental: cross-item patterns", with "0 of 4" fully correct.

**c8. Hiring signals.** Scope table: "Hiring signals | Stretch: open roles by function per competitor (D12)" vs
Remaining work: "Dropped from this submission: hiring signals".

**c9. Changes page.** D13: "publish the old-vs-new difference as an item on the Changes page". The UI at ae8fbb5 has no
Changes route (`frontend/src/app`: brief, capabilities, competitors, health, log, review, roadmap). The UI also has a
`capabilities` page that the PRD's screen list does not mention.

**c10. Glossary.** "Ranker | Scores item importance 1–5 against the D14 rubric" vs rubric v2 (D29) supersedes D14's
scale. "Item status | auto-published, awaiting review, approved, flagged, or dismissed" leaves out "Dropped" (Item
lifecycle, Statuses).

**c11. AWS scope.** D10: "AWS CodeArtifact for the cloud vendors" vs the rubric anchor "Amazon ECR replication
backfill | aws" and the product words "Amazon ECR, Amazon Inspector". `config/tracked_pages.yaml` notes a cell left
untracked because a page "scans ECR, not CodeArtifact".

**c12. Closing plan, insights row, stale after D60.** "Insights eval found 1 of 4 expected patterns, partially (n = 4
patterns) … The 12 claims of the 1 Nov run are not marked yet" vs D60: "0 fully found, 3 partially found, 1 not
found", and the 12 claims marked.

**c13. Lens denominators.** D58: "axis 10 of 10, capability quote 5 of 9, relation 0 of 8 where a relation was claimed,
not\_related 6 of 6". The Lens reference for the same day: "15 lenses: 14 ok, 1 rejected … All 8 lenses with a gap or
shared relation carry a quote". The PRD does not say which 9 items the quote count covers, or which 10 the axis count
covers, when 8 relations were claimed.

**c14. README vs PRD and repo.**
- README "Tech stack" lists Gemini 2.5 Flash, "Claude Haiku 4.5" as trace judge, "Email | Gmail API" and LangSmith
  "One `digest_run` trace per day"; README "Setup" has "First run — Gmail auth". These describe the newsletter agent.
  D7 drops Gmail from the demo; D57 defers LangSmith daily tracing; D59 found "README still describes the newsletter
  agent".
- README "Run the demo" and `docker-compose.yml` ("demo/snapshot, committed") vs the repo: `demo/` has only
  README.md at ae8fbb5. Not run here (no servers allowed), so whether a fresh clone shows empty screens is not
  checked.
- README numbers not in the PRD: "5 of the 351 stored items are flagged", "207 of the 351 stored items come from
  Google News", the feed-date evidence "(n = 2 …)", and "7 synthetic poisoned articles". These were not used in the
  drafts.

**c15. Demo story vs demo mode.** D22: "the autonomy threshold moved live … the autonomy threshold is a UI control, not
only config" vs D59 (2): demo mode has "writes disabled", and the contract §12.2 refuses any PUT with
`demo_read_only`.

**c16. Changed head-to-head cell.** D22: "The demo snapshot must contain one hot competitor with a changed cell" vs
Closing plan: "0 changed cells, so D22's 'changed head-to-head cell' demo step has no real example … none is staged".

**c17. LangSmith.** D48 lists "LangSmith tracing of every LLM call" as Sun 1 Nov work; D57 defers it ("LangSmith daily
tracing (not built)"). D48's row is not marked as updated.

**c18. Insight continuity (D63).** The Handoff says: if not built, "it goes to the README as future work". Status Mon
2 Nov asked BE to "merge release/insight-continuity-20261101 if it touches nothing fingerprinted (UI badges time-boxed
to 13:00)". At ae8fbb5 the branch is not merged, and the PRD does not record the outcome.

**c19. Order of the check and the eval (declared, not hidden).** D55 and D59 put the repeat check before the test
eval; D66 runs the eval without waiting, and says so. Not a contradiction, but the README must state it next to both
checks (D66).

**c20. Tagging rules as of an older commit.** "As of main a7a758e (30 Oct), from ci/classify.py" and product words "As
of main 9c3aa9c". ci/classify.py changed since (D57 guard fix); D57 says the prompts did not change, but the section
was not re-checked against ae8fbb5.

**c21. The brief's wording.** PRD Problem & context: "It must be good, accurate and scalable." The brief as quoted for
this draft does not contain that sentence. The Closing plan has rows for "Good and accurate" and "Scalable".

---

## d. Open questions for Ofri

Ordered by how much they block. Each can be answered in one line.

1. **Demo day:** 1 Nov (approving its held score-4 item, shown as an analyst release) or another day? Blocks the
   snapshot, every screenshot and the video.
2. **Snapshot in the repo:** will the real `demo/snapshot/` be committed before submission, so `docker compose up` on a
   fresh clone shows data?
3. **Autonomy level in the demo:** show the change in live mode, or describe it, since demo mode refuses writes (c15)?
4. **Changed cell:** drop D22's changed-cell step, or keep it as "explained, no real example yet" (c16)?
5. **Status of the test-split result:** PROVEN (data the tuning never saw) or EXPERIMENTAL (single labeler)? This draft
   classes every labelled result EXPERIMENTAL.
6. **DECISIONS.md:** since `docs/specs/` is gitignored, should DECISIONS.md carry every D-ID the README cites?
7. **Faithfulness judge (c1):** mark it future in D17 and Success metrics, or is it planned before submission?
8. **Insight continuity (c18):** merged, or README future work?
9. **"This week" summary (c6):** show the profile with it marked not built, or hide the block in screenshots?
10. **Test-split n (c4):** what is it at ae8fbb5?
11. **Lens denominators (c13):** which items do "5 of 9" and "10 of 10" count?
12. **Duplicate D60 and D61 (c5):** renumber, or cite them with a suffix?
13. **README-only numbers (c14):** add them to the PRD, or may the drafts cite the README?
14. **"Industry competitor errors (0.63, n=19)" (D41):** an accuracy or an error rate?
15. **The `capabilities` page (c9):** include it in the screen list and screenshots?
16. **"Good, accurate and scalable" (c21):** part of the official brief, or the PRD's paraphrase?
