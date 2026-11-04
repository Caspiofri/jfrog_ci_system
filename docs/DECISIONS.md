# Decisions

The main design decisions behind Jessi, each with what was decided, why, and what else was considered. The full log
(D1 to D128, newest first, with dates) is the PRD's decision log; numbers here are copied from it. IDs match the PRD,
so a reader can look each one up.

BE is the coding agent that ran the checks and reported these results.

Sections: [Product](#product) · [Routing and analyst actions](#routing-and-analyst-actions) ·
[Classification and scoring](#classification-and-scoring) · [The JFrog comparison](#the-jfrog-comparison) ·
[Pipeline and safety](#pipeline-and-safety) · [Insights](#insights) · [Evaluation](#evaluation) ·
[Demo and delivery](#demo-and-delivery) · [Screens](#screens) · [Stage 2](#stage-2)

## Product

**Two primary screens, one per need in the brief (D15, D21).**
- **What:** the Daily Brief answers "what happened since yesterday?"; Competitors answers "how does JFrog compare?".
  Review, Log and Health support them.
- **Why:** the brief says "news and insights": synthesis across items is what separates this from an RSS reader, so
  the Brief opens with insights. The review queue is the quality mechanism, not the stated need.
- **Considered:** leading with the review queue; rejected, because it would demo a work tool instead of what was
  asked.

**The competitor is the unit of navigation (D20).**
- **What:** a card and a profile per competitor, instead of one 7-axis × 7-company matrix.
- **Why:** competitors do not compete in the same places (Snyk is security only, Cloudsmith artifacts only), so one
  matrix is mostly empty cells. Analysts think per competitor.
- **Considered:** the single matrix of D13.

**A Brief covers everything found since the previous Brief, not a fixed 24 hours (D31).**
- **What:** membership uses discovery time; late discoveries appear in the list with a badge.
- **Why:** a fixed 24-hour window silently loses a missed day. Missing an important event is worse than showing an
  old one.
- **Considered:** a separate "late discovery" section (D27), replaced by the badge.

**Readers beyond analysts get nothing built now (D19).**
- **Why:** keeps scope on the brief's two needs. Future: role-based digests built from flagged items, and an internal
  MCP server so anyone can ask "what did Cloudsmith ship this month?".

## Routing and analyst actions

**Confidence-based routing with one autonomy control (D9, D34).**
- **What:** each item is auto-published or held for review. Three levels: Strict (default), Balanced, Relaxed.
  Pricing, M&A, Mentions JFrog and model failures are held at every level.
- **Why:** reviewing every item burns analyst time; publishing everything risks wrong claims. Autonomy is earned:
  start strict, relax as measured precision rises. At Strict the 14-day import held a median 2.5 items a day (max 24,
  n = 228 non-noise items over 14 days), so Strict is affordable.
- **Considered:** a confidence slider. Rejected: classifier confidence takes only four values and rule-settled items
  sit at a fixed 0.85, so a slider mostly toggled the rule items.
- **Open:** the default level is a question for the hiring manager.

**Analyst actions are signals (D16, D62).**
- **What:** Approve, Dismiss with a reason, Edit, Flag, Re-open. Edits become candidate labels, field by field.
  Actions are append-only; Re-open returns an item to its exact earlier state.
- **Why:** every action is also a measurement: a dismiss reason names the stage that failed, an edit becomes a
  label, a Flag on a low-scored item exposes a ranking miss. The first real session produced a mistaken Dismiss that could
  not be undone, which led to Re-open.

**Flag only marks an item as important (D107, D108).**
- **What:** Flag does not approve, publish, dismiss or rescore. Dismiss and Re-open do not touch the flag.
- **Why:** a code read found that Flag on a held item also approved it, so it could reach the Brief without a
  decision. Two actions must mean two things.
- **Considered:** keeping the old behaviour; rejected, since "today's behaviour" was not a reason.

## Classification and scoring

**Rules settle only safe cases; the default is the LLM (D24, D25).**
- **What:** rules decide the competitor when certain; anything ambiguous goes to the LLM, with a hint. Every rule
  misfire becomes a regression test.
- **Why:** no rule discards an item outright, so a missed pattern costs an LLM call, not a lost event.
- **Result:** on the test split rules settled the competitor right 9 of 9, but the category only 3 of 9 (D67, D70).
  The fix (rules settle the competitor only) is known and not applied, because it could not be measured before
  submission.

**Rubric v2: importance is competitive impact on JFrog (D14, D29).**
- **What:** 1-5 plus Noise. Type sets the default; content can raise it. 3 = a competitor improves something it
  already had; 4 = it opens or closes a gap against JFrog; 5 = significant scale against a core product.
- **Why:** labelling showed real items with no fitting level: routine patch releases inflated 2-3, and industry
  items cannot be scored by a competitor-gap test. Separating Noise from 1 maps to a product decision: drop from the
  feed vs keep in the competitor's timeline. Fewer levels label more consistently than a 0-10 scale (D14).
- **Considered:** Noise counted as 1 (D28), reversed by D29.

**Model split: Gemini writes and ranks, Claude judges (D5, corrected by D116 and D117).**
- **Why:** already proven in the origin project; a judge from another family does not grade its own work.
- **Corrected:** D5 said Bedrock or an LLM gateway is a config change for production. The AWS design (D116) finds a
  switch touches four files, and D117 replaces D5's future infra list with D116's growth triggers: no Kubernetes,
  queues or workers.
- **Note:** the faithfulness judge was not built for this submission (D17).

**Stack: Next.js UI, FastAPI backend, Docker Compose (D3, corrected by D117).**
- **What:** Next.js with Tailwind, shadcn/ui and Recharts for the UI; FastAPI for the API; Docker Compose for the
  demo.
- **Corrected:** D3 said "FastAPI over the LangGraph pipeline". The `ci/` pipeline is plain Python: `run_daily()`
  calls the steps in order, with thread pools during collection. LangGraph is imported only in `modules/graph.py`,
  used by the legacy newsletter path (per BE on `fbc9677`, D117). No reason for building it this way is recorded.

## The JFrog comparison

**The lens is an explanation layer, not a score input (D42, D58).**
- **What:** after ranking, each non-noise item gets the closest JFrog capability, quoted word for word from the
  capability sheet and checked in code. It never changes a score.
- **Why:** the eval showed a capability baseline did not improve scores (D40), but the brief asks how JFrog compares.
  The lens adds that meaning without touching what was measured.
- **Result and display:** one manual check of one daily run (1 Nov, n = 15 items): axis right 10 of 10, capability quote right 5 of 9,
  not_related right 6 of 6, relation right 0 of 8 where claimed. The UI shows the capability and hides the relation, so
  the capability shown can still be wrong.
- **Limits:** this is a small, single-day check, an indication and not a rate. The lens has no golden-set labels,
  because axis and gap labels need product experts (future work, D31). The code check proves a quote exists on the
  capability sheet, not that it is the right capability. The prompts were frozen before the check, so no fix followed
  it (D57, D58).

**Head-to-head values stay, captioned as unverified (D87, D88, D95).**
- **What:** values extracted by an AI model from linked public pages, shown with a caption that no person reviewed
  them and that the evaluation does not cover them. One manual check on 3 Nov: 38 of 42 values correct, 2 partial,
  2 wrong; 7 of 49 cells empty where the information exists elsewhere.
- **Why:** the gap was verification, not provenance: the values come from a real running pipeline. Stating the gap
  keeps the comparison the brief asks for and stays honest.
- **Considered:** removing the comparison (D87), reversed the same evening.

## Pipeline and safety

**Article text is untrusted input (D32, D51).**
- **What:** guards in layers, each built with the code it protects: output validation (score, competitor, category
  and item ids checked, rejects routed to review); article text in delimited tags, with case-insensitive escaping;
  HTML escaping in the UI; insight citations checked against the stored text. Synthetic poisoned articles are pinned
  as regression tests.
- **Why:** pages we do not control feed the LLM, and a page can hide instructions that inflate a score or plant a
  false claim. JFrog sells AI-agent security, so this will come up. The LLM has no tools, so the worst case is wrong
  output, not an action; review routing is the backstop.
- **Stated openly:** the quote check proves a quote exists in the stored text, not that it is true, so a planted
  sentence passes it. The problem is narrowed, not solved.

**One event, one story: 0.82 similarity with a CVE-ID veto (D33, D38).**
- **What:** items about the same event link at the 0.82 rule. Two items that name different CVE IDs never merge.
- **Why:** a manual review of the 14-day import found 2 of 9 multi-item events mixed, both GitLab security releases
  with different CVEs that embeddings could not tell apart. Merging two vulnerabilities hides one from the Brief.
- **Considered:** a looser 0.75 link. Dropped: it did not fix the case it was meant for, and it would have been wrong
  on 5 of 12 near-miss pairs.

**Vetted means trusted, not readable (D39, D53).**
- **What:** sites that block our fetcher (0 of 15 items extracted) stay vetted. We never get around a challenge.
  Their important items are held as teaser-only, and every item records why its text is missing. On vetted hosts
  only releases, tags, code and changelog pages are vetted; issues and pull requests are not.
- **Why:** mixing trust with readability would hold reputable items for the wrong reason. A repository on a vetted
  host can be anyone's. Unvetted means held for review, not dropped, so narrowing vetting costs review time, not
  coverage.

**Observability lives in the repo (D48).**
- **What:** a `run_metrics` row per run, including degraded and failed runs; stale and overdue detection; the API
  log on disk; Health shows run history and the eval with n. LangSmith tracing of the daily run is not built (D57);
  tracing is forced off in every eval run, enforced in code with a test (D51).
- **Why:** a run that never started looked like yesterday's success. Reviewers run without our accounts, so
  everything they must see is in the repo and on Health.

## Insights

**Insights cite stories, and every claim quotes its source (D37).**
- **What:** at least 2 different stories per insight; each claim carries a quote checked against the stored text;
  any failed quote rejects the insight. Insights read only published items, over a 7-day window (14 with fewer than
  15 stories) plus anything found since the previous Brief.
- **Why:** near-duplicates in the data would turn one story into "momentum". Insights on unreviewed items could
  spread a wrong claim.

**Expected patterns are written before the generator runs (D43, D60).**
- **What:** four patterns in `evals/expected_insights_389e71.yaml`, written by the author from a neutral listing and
  checked by a second reader. Any later generator change is tuning on this file and is reported as such.
- **Why:** a recall number needs a reference the generator never shaped. Result on 1 Nov: 0 of 4 found fully, 3
  partly, 1 not found; two patterns were found only by being merged.

**Continuity from shared sources, not wording (D63).**
- **What:** each insight is marked new, continuing or strengthened by the stories it shares with the previous
  Brief's insights, with no LLM call.
- **Why:** the generator starts fresh every morning on windows that overlap by 6 of 7 days, so the same pattern came
  back under a new title. Matching on shared sources is deterministic and checkable.
- **Future:** insights with a lifecycle, created once and updated, which changes the generator.

**Insights lead the Brief, labelled as AI-generated (D61, D73).**
- **What:** insights stay first. One AI icon, "AI-generated — check the cited sources", with the measurement in the
  hover.
- **Why:** insights are what turns a news feed into intelligence. Leading with the least reliable part is acceptable
  only because the screen says how far to trust it.
- **Considered:** an "Experimental" label. Removed: it read as "not reliable" for the whole section, more than 11 of
  12 supported claims shows.

## Evaluation

**Tune on train, report test, once (D17, D23, D66).**
- **What:** a 60-item golden set with deliberate noise, a 75/25 split locked per story, every test run fingerprinted.
  The test split ran once on the locked code; it is now spent.
- **Why:** tuning never sees the test set, and the fingerprint proves it.
- **Deviation, stated:** the test eval ran before the second daily check was marked. Decided before any result was
  seen: the prompts were frozen, so there was nothing to fix (D66).

**Coverage has a dev list and a held-out list (D26, D101, D102).**
- **What:** the dev list found the GitHub changelog misses and was tuned on, so its 25 of 26 is reported only as "the
  fix works". The held-out list (n = 4) was measured once: 3 of 4.
- **Why:** measuring on the list used to find misses is tuning on the test set.

**Pass lines are set before the marks (D52, D55, D68).**
- **What:** daily reliability checks use a line and a counting rule (unsure counts as wrong) fixed in advance. 1 Nov
  failed (n = 15); 2 Nov passed with the high-score condition not exercised (n = 6). Both are reported apart.
- **Considered:** a tolerance proposed after the 1 Nov marks; not applied, because it would have turned the fail into
  a pass.

**Everything measured stays what was measured (D99).**
- **What:** from 3 Nov, prompts, rules, rubric, labels, stored rows, eval reports and the demo snapshot are frozen.
  Each exception is a named decision with a proof (D107, D111).
- **Why:** a change after measurement leaves every reported number describing an older version.

## Demo and delivery

**The demo is a frozen real day, writable on a copy (D2, D69, D106, D111).**
- **What:** the 1 Nov 2026 Brief, with the two analyst actions made later kept and dated. Each start copies the
  snapshot; actions write only there and reset on restart. Insights are frozen. The README lists the real runs up to
  submission day.
- **Why:** a reviewer must see the product in one command, without a key. Read-only "does not look good and the
  system cannot really be experienced" (the author, 4 Nov); the copy is isolated, so actions cannot pollute measured data.
- **Considered:** read-only (D110), reversed the same day under a time box with `d4e219b` as the fallback. It was frozen at `fbc9677` (D115).
- **Conditions:** allowed only with proofs: a guard showing that startup changes 0 rows on the copy, no write
  leaving the copy, live behaviour unchanged, and Health and evaluation numbers reading saved summaries.

**Build first, then verify the exact system that is submitted (D47, D57).**
- **What:** build days ended with a code freeze, a clean-clone test and a demo snapshot freeze. After that: fixes
  found in verification, docs, screenshots and video. No new features, and no change to classify, rank, lens or
  insights prompts and rules.
- **Why:** with the test eval one day away, finishing and verifying was worth more than any further change.

**A portable fingerprint beside the legacy one (D59).**
- **What:** the legacy classify_rank fingerprint hashes absolute paths, so a fresh clone gets a different value. A
  portable fingerprint hashes content only: rubric, config, capability sheet, model and call settings. Both are
  reported; no recorded fingerprint changed.
- **Why:** a reviewer must be able to check the evidence on a clone. A reproducibility pack recomputes every
  reported number from saved reports with no LLM call, kept separate from rerunning the evaluation.

**Freeze at a checked commit (D109).**
- **What:** tagged after every planned check passed on the bundle a reviewer would clone: review actions, a Windows
  clean clone, LOCK OK. From then: documents, the repro pack and cleanup that touches nothing measured, each followed
  by tests and lock_check.
- **Why:** freeze what was checked, on the artifact that will be submitted.
- Cleanup (D120): personal details and local paths were removed from the current published files where no frozen file changes. Frozen and measured files and git history were left as they are.
- Next.js upgrade (D123, D124): `jf audit` found 3 Applicable findings in next 15.5.4, one of them Critical. We made one exception to the code freeze and upgraded next to 15.5.28, which also closes the next findings the scanner could not decide on. Only `frontend/package.json` and `frontend/package-lock.json` changed, and nothing fingerprinted.
  - Why: the UI binds to 127.0.0.1, so the practical risk today is low, but the production design exposes it behind an ALB.
- UI base image (D125): we moved the UI image from node:22-slim to node:22-trixie-slim, changing only `docker/ui.Dockerfile`. Findings in the UI image: Critical 4 to 1, High 75 to 87, total 257 to 227, Applicable 4 to 2, with 18 new finding IDs.
  - Why: it removes two Applicable system-package findings, including a Critical one, at the cost of more High findings. The API image already uses the same Debian release, and the client files are identical.
- Final code freeze (D128): `22b45b6`, tag `freeze-20261105`, a normal merge of `4a82f28`, with an identical tree. 1,239 pytest and 275 frontend tests pass; LOCK OK with classify_rank `99b79890ceea`; 7 snapshot files identical; repro recomputes with 0 differences. The Windows check of `4a82f28` passed. Earlier freezes: `fbc9677` (D115), `017e26b` (D122), `f73b549` (D127). Only documents change from here.

**No AWS for the submission (D4).**
- **Why:** credentials block reviewers from running it. The production design is in
  [ARCHITECTURE.md](ARCHITECTURE.md).

**AWS production design, design only, none of it built (D116).**
- **What:** size S is one EC2 instance with SQLite and ChromaDB on its disk and an hourly AWS Backup of the whole
  disk. Access through an ALB with a Cognito login, an HTTPS certificate and a domain name; the server in a private
  subnet with a NAT gateway. Keys in Parameter Store, shell through Session Manager. A failed or degraded run alerts at
  once; a 26-hour missing-metric alarm covers a run that never started or finished and the whole instance going down.
  Deploy: build once, scan with Xray, push to Artifactory, the server pulls and runs. Cutover after a 7-day shadow
  run, with the Pi kept as rollback for one more week. RDS when more than one API instance or a smaller loss window
  is needed.
- **Why:** each service carries what it does and why it beat the simpler option, so every choice can be defended in
  plain words. Artifactory and Xray follow from the requirement that everything running has been scanned; this has
  not been built for Jessi, and the scan and push were run in Stage 2 on the forked app.
- **Stated openly:** about one hour of possible loss, and the single instance is a single point of failure. Size S
  needs the configuration and script changes listed in ARCHITECTURE.md, none built. The cost of about $125 a month is
  an unverified estimate. Running the design against the code showed that "no change to the app code" was not true as
  first written, so the list states the real changes.
- **Considered:** Kubernetes, ECS and Step Functions; left out because they could not be defended.
- **Renamed:** in the approved design, "step 1" is now "Size S" under "Moving to production", and "step 2" is
  "Size M"; the design adds sizes S, M and L and "Serving more teams" (ARCHITECTURE.md).

**Product name Jessi (D46).** JFrog's Engine for Strategic Signals & Intelligence.

**The documents describe what was built (D117).**
- **What:** the documents state that `ci/` is plain Python and does not use LangGraph, and the future infra list
  follows D116's growth triggers.
- **Why:** a reviewer opening the code would see that the earlier claim was false. Neither git nor the docs record
  why `ci/` was built without LangGraph, so no reason is stated.

**Video on Thu 5 Nov at 08:00, submission after it (D119).**
- **What:** tonight: documents, the docs-only merge, a last clean clone and a push with the repo still Private.
  Thu: check the 06:00 run, back up, record the video on the live system, add the video link and the 5 Nov run row
  (docs only), a last clean clone, push without force, make the repo Public, run the final check, send both links.
  The one approved item in the video comes from the Thu 5 Nov run, which is in no measurement (updates D106).
- **Why:** recording tomorrow shows the first 06:00 run on the frozen commit and leaves Thursday with only the video
  and the submission. A Private push tonight keeps a safe copy on GitHub.

**Jessi is a GenAI pipeline, not an agent (D118).**
- **What:** fixed steps, validation and human review. The freeze stays, and the submission goes ahead as built. The
  documents say what was reused from the newsletter agent: code and ideas, not the LangGraph orchestration.
- **Future, not built:** add agents for small, bounded processes inside the pipeline.
- **Why:** the brief asks for a working GenAI tool, not an agent. Moving to an agent now would reopen the freeze, and
  the checks would no longer describe what is submitted.

**The README states a vision, not built and with no date (D126).**
- **What:** from a daily feed to an analysis partner: a chat assistant for analysts that uses the collected items,
  citations and JFrog comparison. The first step is to learn the analysts' pain points; the assistant also needs
  protection against prompt injection. No screen or code change.
- **Why:** the submission should not read as if the system stays as it is. No analysts have been interviewed, so
  the direction is stated as a vision, not as a validated need.

## Screens

Each UI round changed display only; nothing measured moved.

- **D44, D45:** the Brief separates what is known (published items scored 3+), what is pending (held items, shown
  only as counts) and what cannot be concluded yet (insight states, evidence basis).
- **D72:** an outside review: tiles on the Brief, explanations moved to hover, continuity badges, one link convention
  (the title opens the drawer, an icon opens the article), letter avatars instead of logos, a heatmap of where
  competitor activity lands.
- **D89:** the author's review of the merged demo: new articles marked as new, fewer repeated labels.
- **D104:** no raw errors, no false affordances, no duplicate panels; concept images labelled "Concept, sample data".
- **D112:** Competitors cards answer what happened and what is waiting; the heatmap already answers how much, so it
  gets a Total row and the cards lose the repeated counts. "+N vs previous 7 days" removed, because collection started
  on 30 Oct and it read as a surge.
- **D113:** from an outside reader: "Items in this Brief" instead of "Today in numbers" (wrong on a past Brief),
  "Cumulative insights" instead of "Weekly", JFrog vs competitors marked as an interim view, "Checked manually" with
  its date.
- **D114:** the four "Items in this Brief" tiles share one box so labels and numbers line up; no text or number
  changed.

## Stage 2

**Fix lodash, not moment (D30).**
- **What:** remediate lodash CVE-2018-16487 (4.17.4 to 4.17.21), not moment CVE-2022-31129. Each of the two
  applicable Highs is High on one scale only.
- **Why:** lodash: an unauthenticated route passes unvalidated input into `_.merge`, and prototype pollution was
  shown over a real HTTP request; one upgrade also closes CVE-2020-28500. moment: every flagged call is in a function
  that is never called, so no user input reaches it. Contextual Analysis marking dead code Applicable is a talking
  point: Applicable narrows, it does not prove.

**Harden the app on top of the upgrade (D64).**
- **What:** the update route builds from an allowed-field list with type checks, and a middleware rejects JSON
  bodies with `__proto__`, `constructor` or `prototype` keys at any depth. Each guard was tested with the vulnerable
  lodash, alone and together.
- **Why:** the upgrade fixes only that version's CVEs; the guards stop prototype pollution on this route whatever
  the library version.

**Publish with the JFrog CLI, not GitHub Actions with OIDC (D65).**
- **What:** the image is pushed with `jf docker push` and Build Info published with `jf rt build-publish`. The image
  is linux/arm64, built on the Pi. The adapted workflow stays in the repo, described as prepared, not run.
- **Why:** the brief allows the CLI. A blocked UI login stopped the OIDC setup; OIDC stays the production
  recommendation.

**Stage 2 is finalized on the fork's main at `7e9d10b` (D121).**
