# Jessi

**JFrog's Engine for Strategic Signals & Intelligence.** Jessi keeps JFrog's competitive-intelligence team updated
every day on what six competitors (Cloudsmith, Sonatype, GitHub, GitLab, Snyk, AWS) and the wider industry ship and
say, and shows how JFrog compares. It is a GenAI pipeline with fixed steps, validation and human review. Every item
and every insight links to its source, and every number in this README is reported with its n.

[Screenshot placeholder: Daily Brief, top of the page — `docs/screenshots/brief.png`]

**Video:** [placeholder: demo video link]

Contents: [Run the demo](#run-the-demo-no-api-key) · [The writable demo](#the-writable-demo-and-how-it-resets) ·
[Frozen insights](#insights-are-frozen-in-the-demo) · [Snapshot and live system](#the-demo-is-a-snapshot-the-live-system-keeps-running) ·
[Screens](#screens) · [How it works](#how-it-works) · [Evaluation](#evaluation) · [Pitfalls](#pitfalls-and-known-limits) ·
[Now vs future](#now-vs-future) · [Origin, legacy code](#origin-legacy-code) · [Repository](#repository)

## Run the demo (no API key)

You need Git and Docker (on Windows and macOS: Docker Desktop, and it must be running). Ports **3000** (UI) and
**8011** (API) must be free.

```bash
git clone <this repo> jessi && cd jessi
docker compose up --build
```

This README describes the frozen commit `fbc9677` (D115). Open **http://127.0.0.1:3000**. The API is on http://127.0.0.1:8011/api/v1 (contract: `docs/api-contract.md`).

- The first build takes a few minutes: 7:21 min on a Windows clean clone of `d4e219b`, the earlier freeze.
- No `.env` and no key are needed. The demo calls no model.
- On Windows the image user defaults to uid 1000. If you set it anyway, in CMD it is `set APP_UID=1000`, in
  PowerShell `$env:APP_UID=1000`.
- If a port is taken, set `UI_PORT` or `API_PORT` before `docker compose up`.

Without Docker: `pip install -r requirements.txt`, then `python -m ci.api --demo demo/snapshot --port 8011`, and the
UI from `frontend/` with `npm install && CI_API_URL=http://127.0.0.1:8011 npm run dev`.

## The writable demo and how it resets

The demo is a real system on a real day's data, and you can act on it (D111).

- **Every action works:** Approve, Dismiss with a reason, Edit, Flag, Re-open, trusting a source, and changing the
  autonomy level.
- **Your changes stay in your copy.** Each start copies the snapshot stores (`demo/snapshot/ci.sqlite`,
  `changes.sqlite`) to a fresh temporary folder inside the container. Every action writes only there.
- **A restart resets everything.** `docker compose down && docker compose up` starts again from the snapshot. The
  screen says this in a line under the header.
- **The snapshot itself is never written.** `demo/snapshot/` stays byte-identical, and the live store is never
  opened in demo mode.
- **A startup guard** proves that opening the copy changed 0 rows. If it cannot, the demo serves the snapshot
  read-only instead.
- **Health and evaluation numbers never move.** They read the snapshot's saved summaries (`demo/snapshot/health/`),
  so your clicks change the Brief, Review and Log counts in your copy, and nothing that was measured.
- **Read-only mode** is still available: `CI_DEMO_READ_ONLY=1 docker compose up`. Every write then answers
  `403 demo_read_only`.

Full article text is never in the snapshot: items keep a field allowlist and a 280-character excerpt (D34).

## Insights are frozen in the demo

Insights need a live LLM, so the demo makes no model call even when a key is present. Refresh insights is disabled,
and the Brief states:

> Insights are frozen in this demo: generating new ones needs a live LLM connection and API key. They do not reflect
> changes made here.

Any other action that needs a model is disabled with a plain message. The insights you see are the ones the 1 Nov
06:00 run produced, and they are the ones measured in [Evaluation](#evaluation).

## The demo is a snapshot; the live system keeps running

The demo serves the **1 Nov 2026 Brief** (run `20261101T0400Z-e9cae4`, D69). Under the header:
"Demo snapshot of 1 Nov 2026. The live system keeps running daily at 06:00." (D106).

Two analyst actions made after that Brief, on items of that day, are kept in the snapshot and listed in
`demo/snapshot/snapshot.json` with their time (D69): the release of a held score-4 item by an analyst, and the
reopening of an item dismissed by mistake (D62).

**Real daily runs, up to submission day** (from the `run_metrics` table; D74, D79, D106):

| Date | Run | Status | New items | Published | Held for review |
| --- | --- | --- | --- | --- | --- |
| 30 Oct | 20261030T1312Z-389e71 (14-day import) | ok, reconstructed | 282 | | |
| 31 Oct | 20261031T1345Z-802913 | ok, reconstructed | 43 | | |
| 1 Nov (demo day) | 20261101T0400Z-e9cae4 | ok | 26 | 4 | 11 |
| 2 Nov | 20261102T0400Z-bed018 | ok | 13 | 1 | 5 |
| 3 Nov | 20261103T0400Z-d03c41 | ok | 44 | | |
| 4 Nov | 20261104T0400Z-20da28 | ok | 46 | | |

- 30 and 31 Oct rows are reconstructed once from the per-item log, marked "Reconstructed from the item log" on
  screen, and leave empty what the stored items cannot prove (D74). Published and held are empty there because
  routing did not exist at those runs.
- 1 Nov: 239 fetched, 11 removed as noise. 2 Nov: 237 fetched, 7 removed as noise (D74).
- 1 Nov: at run time 3 items were published and 12 held at Strict; an analyst approved 1 held item afterwards, so
  the Brief shows 4 published and 11 held (D69).
- 30 Oct had two collections: the 14-day import `389e71` that entered the product, and a 7-day labelling collection
  `5d06a9` that was never imported. 3 of the 29 test-split items came only from `5d06a9` (26 skipped in `389e71`
  + 3 = 29) (D79).

**The demo's Health shows the 1 Nov run's fingerprint `c837f4fdaf70`.** The prompt-injection fix of D51 changed the
classify_rank fingerprint to `99b79890ceea` later that day, with 0 differences in 1,374 rendered prompts (D57). Every
later run and the test-split eval use `99b79890ceea`.

### Run the live system with your own key

A live run collects real news and calls Gemini. The free tier allows 20 requests a day, which a daily run exceeds, so
use a paid key or Vertex AI.

```bash
export APP_UID=$(id -u)
mkdir -p output data && touch evals/golden_set.jsonl
cp repro/split_assignments.json evals/   # the frozen split; do not run ci.eval_golden to make a new one
cp .env.example .env                     # then set GOOGLE_API_KEY in .env, before the first run
docker compose --profile pipeline build ci
docker compose --profile pipeline run --rm --entrypoint python ci -m ci.daily
```

- **Do not run the plain `ci` service first.** It only collects and marks every URL as seen, so a daily run after it
  finds 0 new items and still reports ok.
- **What was checked.** Without an API key, we checked these steps on a clean clone only through collecting and
  storing articles (169 collected, 135 stored, Linux with Docker). Without a key the run does not stop: it writes
  fallback rows, marked degraded, and ends with status degraded (exit 3). Classification, ranking and insights need
  a key, so they were not run on a clean clone. The live system runs them every day.
- **Insights are off on a fresh store.** To turn them on, run this from the repo root after the setup commands,
  before the daily run:

  ```bash
  docker compose --profile pipeline run --rm --entrypoint python ci -c "from ci.store import Store; Store().set_setting('insights_enabled', 'true')"
  ```

  This command was checked on a scratch store. Insights generation after it was not run on a clean clone, because
  that needs a key.
- **Open the UI on the live store:** [TODO BE: commands to start the API and the UI on the live store].
- The split file keeps the golden-set test items away from the model (D23). The scheduled run is
  `ci/daily_cron.sh` at 06:00 Israel time.

## Screens

Everything is in English (D18). Two primary screens answer the brief's two needs; three supporting screens keep the
system accurate and measurable (D15, D21).

| Screen | Answers | What it shows |
| --- | --- | --- |
| **Daily Brief** | What happened since yesterday? | Insights first, each claim with its quote and source; "Items in this Brief"; the published items scored 3+ found since the previous Brief, filterable by competitor and category; past Briefs by date (D31, D44, D113) |
| **Competitors** | Where does each competitor stand against JFrog? | A competitor-by-category heatmap with a Total row; one card per competitor (highest score, awaiting review, mentions JFrog, a sparkline, top items); a profile per competitor; JFrog vs competitors, an interim view (D112, D113) |
| **Review queue** | Is this item right, and does it belong? | Items held by the routing rules, each with its reason; Approve, Dismiss with a reason, Edit, Flag, Re-open; the autonomy level (D9, D16, D34) |
| **Log** | What was collected, and where did it stop? | Every collected item, dropped ones included, with status, reason and the stage it stopped at (D21) |
| **Health** | Does the system work? | Run history, the funnel, extraction per source, the test-split eval and held-out coverage, each with n and "Measured on" (D48, D80, D83) |
| **Roadmap** | What comes next? | 7 concept images, each labelled "Concept, sample data" (D105) |

[Screenshot placeholder: Competitors — `docs/screenshots/competitors.png`]

[Screenshot placeholder: Review queue — `docs/screenshots/review.png`]

[Screenshot placeholder: Log — `docs/screenshots/log.png`]

[Screenshot placeholder: Health — `docs/screenshots/health.png`]

[Screenshot placeholder: Roadmap — `docs/screenshots/roadmap.png`]

## How it works

A daily run calls fixed steps in order, in plain Python (`run_daily()` in `ci/daily.py`). The model answers inside
those steps; it does not choose them. The full picture is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how Jessi works today (flow, components, data
model) and the AWS production design, which is design only and not built.

```
collectors (Google News, vendor blogs and changelogs, GitHub releases, Hacker News)
  -> dedupe (URL, then embedding similarity, with a CVE-ID veto)  -> full text + extraction check
  -> classify (rules for safe cases, Gemini for the rest: competitor, category, noise)
  -> rank (Gemini, rubric v2: score 1-5)  -> validate (schema + rules)  -> route (hold reasons x autonomy level)
  -> lens (closest JFrog capability, quote checked against the sheet)  -> insights (claims quote their source)
  -> SQLite store  -> FastAPI (ci/api)  -> Next.js UI (frontend/)
```

- **Importance.** Rubric v2 (`config/rubric_v2.md`, D29) scores competitive impact on JFrog, not the size of the
  competitor's change. The Brief shows 3+; 1-2 go to the competitor profile and timeline; noise stays in the Log.
- **Routing.** One autonomy control, Strict (default), Balanced or Relaxed, decides auto-publish vs review. Pricing,
  M&A, Mentions JFrog and model failures are held at every level (D9, D34, D36).
- **Flag** marks an item as important and nothing else: it does not approve, publish or dismiss it (D107, D108).
- **Lens.** Each non-noise item gets the closest JFrog capability, with a phrase quoted word for word from
  `config/jfrog_capabilities.md`. The UI shows the capability, not the claimed relation (D42, D58).
- **Insights** connect several stories over a 7-day window (14 with fewer than 15 stories). Every claim must quote
  its cited article word for word, checked in code (D37). On screen: one AI icon, "AI-generated — check the cited
  sources" (D73).
- **Prompt-injection defense** in layers: delimited article text, defanged tags, schema-checked output, quotes
  checked in code, human review, and a regression set. It narrows what a poisoned article can do; it does not solve
  the problem (D32, D51).
- **Head-to-head values** were extracted by an AI model from linked public pages, are not covered by the evaluation,
  and are captioned as such on screen (D88). One manual check is reported below.

## Evaluation

Every measurement was taken once, on the frozen system, and is reported as it came out (D23, D99). Small n is stated,
not hidden. The tables below are copied from stored reports and the decision log; the reproducibility pack recomputes
the eval numbers from saved reports with no model call: `python -m ci.repro recompute repro`.

| Area | Measure | Result | n | Data | Source |
| --- | --- | --- | --- | --- | --- |
| **Classification** (test split, once) | Competitor accuracy | 0.92 (aws 1 of 3) | 24 | Test split, never used in tuning | D67 |
| | Category accuracy, harness definition | 0.71 | 24 | Test split | D67 |
| | Category accuracy, a noise prediction counted wrong | 0.58 (14 of 24) | 24 | Test split | D67 |
| | Category settled by rules / by the LLM | 0.33 (3 of 9) / 0.93 (14 of 15) | 9 / 15 | Test split | D67, D70 |
| | Competitor settled by rules | 9 of 9 | 9 | Test split | D70 |
| | Noise precision / recall | 0.50 (3 of 6) / 0.60 (3 of 5) | 6 / 5 | Test split | D67 |
| | Score exact / within 1 point | 0.76 / 0.95 | 21 | Test split, items neither side called noise | D67 |
| | Score mean absolute error / signed error | 0.29 / -0.10 | 21 | Test split | D67 |
| | Important items (4+) precision / recall | 1.00 / 1.00, uninformative | 1 | Test split | D67 |
| | Mentions JFrog | not measurable | 0 | Test split | D67 |
| **Classification** (tuning data, context only) | Category accuracy | 0.66 | 59 | Train split, tuned on | D41, D67 |
| | Score within 1 point | 1.00 | 57 | Train split | D41 |
| | Noise precision / recall | 0.88 / 0.74 | 16 / 19 | Train split | D41 |
| **Daily runs** (field-by-field marks) | 1 Nov check: failed. Competitor wrong / category wrong | 0 of 15 / 1 of 15 | 15 | Run e9cae4 | D55 |
| | 1 Nov check: items scored 4 that were wrong | 1 of 2 (held by routing, never in the Brief) | 2 | Run e9cae4 | D55 |
| | 2 Nov check: passed, high-score condition not exercised. Competitor / category / score right | 5 of 6 / 6 of 6 / 4 of 6 | 6 | Run bed018 | D68 |
| **Insights** (1 Nov Brief) | Claims supported / cited items correct | 11 of 12 / 12 of 12 | 12 claims | 4 insights | D60 |
| | Quotes support the claim | 9 of 12 (4 of the 9 partial) | 12 | 4 insights | D60 |
| | Pattern / title / summary / why it matters right | 4 of 4 / 1 of 4 / 0 of 4 / 1 of 4 | 4 | 4 insights | D60 |
| | Insights with every field right | 0 of 4 | 4 | 4 insights | D60 |
| | Expected patterns found: fully / partly / not | 0 / 3 / 1 | 4 patterns | Window 16-30 Oct | D60 |
| **Lens** (1 Nov) | Axis right / capability quote right | 10 of 10 / 5 of 9 | 10 / 9 | 15 items | D58 |
| | Relation right where one was claimed / not_related right | 0 of 8 / 6 of 6 | 8 / 6 | 15 items | D58 |
| **Coverage** (did we collect what happened?) | Held-out events captured | 3 of 4 (feed 2 of 2, external 1 of 2) | 4 | Held-out list, 31 Oct-2 Nov | D102 |
| | Dev list before the fix, important events | 6 of 8 (75%) | 8 | Dev list | D26 |
| | Dev list after the fix (tuned on this list, optimistic) | 25 of 26; important 11 of 11 | 26 / 11 | Dev list | D26 |
| **Head-to-head** (checked manually, 3 Nov 2026) | Extracted values: correct / partial / wrong | 38 / 2 / 2 | 42 | Cells with a value | D95 |
| | Empty cells where the information exists on another page | 7 | 49 | All cells | D95 |
| | Stored quotes found on the page (not a check of the value) | 32 of 32 | 32 | Audit | D88 |
| **Mechanical** | Rendered prompts changed by the injection fix | 0 differences | 1,374 prompts | 351 items, 107 golden rows | D57 |
| | Writable demo (`d6fdeed`) vs the read-only demo (`d4e219b`), live-store copy | 1 difference (`demo_writable` in /meta) | 589 responses | Before merge | 14:10 handoff |

**Held-out check: 3 of 4 events captured (n = 4, weekend, no 4+ event), indication only.** (D103) The list came from
a web search and has no 4+ event, so it says nothing about important events. The missed event (VOLTA) was not covered
by any followed source (D101, D102).

**Which category number to read.** The lead number is **0.71** (n = 24), the harness's definition, the same one the
train reports use: it compares the predicted category with the label on every non-noise test item, including the 3
items the model predicted as noise. Beside it, **0.58** (14 of 24) counts a noise prediction as a wrong category
(D67).

**The clearest finding.** Rules were meant to settle only safe cases (D24, D25). For competitor they did (9 of 9);
for category they did not (3 of 9), almost always setting Security or AI & Agents to Product & Features. The fix is
known: rules settle the competitor only, and the LLM always decides the category. It was not applied, because the
test split is spent and the fix could not be measured before submission (D70).

**Insights: facts right, conclusions overstated.** The evidence layer holds (11 of 12 claims supported, 12 of 12
citations right), and the synthesis overstates: "escalating" without a trend, a vendor added to a convergence it is
not part of. The lens shows the same split. The UI says so, and nothing was tuned on it (D60, D61, D73).

**Fingerprints of the measured system.** classify_rank `99b79890ceea` (the eval report shows `9c39b7d25f65` because
it also hashes one mention side file; both are quoted), portable `e04716a2a1d6`, lens `1692c04ba7df`, insights
`e99d23e4edcf`, capability sheet `e7f13e0b3456`; `gemini-3.6-flash`, temperature 0; measured on `ae8fbb5` (D67). In a clean clone the legacy
classify_rank differs, because it hashes absolute paths; the portable fingerprint is the one that matches (D59).

**Process notes a reviewer may ask about.**
- The test-split eval ran on 2 Nov without waiting for the second daily check, a deliberate change of order decided
  before any result was seen: the prompts were frozen, so there was nothing to fix (D66).
- A tolerance that would have turned the 1 Nov fail into a pass was proposed after the marks and not applied (D55).
- Not measured: ranking precision@k (not in this harness) and the faithfulness judge (D17, not built).
- All marks are by one labeler.

**Tests.** 1,239 Python tests and 275 frontend tests pass at `fbc9677` (BE, 4 Nov 19:33). [TODO BE: update for the
final commit.]

## Pitfalls and known limits

What went wrong, what we found, and what stays open. Each is left as it is on purpose unless it says fixed: the
freeze keeps the measured system unchanged (D99).

**Collection and extraction**
- **The GitHub changelog feed returns only its newest 10 entries.** The coverage check found that the most important
  event of the window, GitHub's package firewall, was caught only as a 92-character snippet, tagged industry and scored
  4 instead of 5. We now poll the changelog page.
- **Sites we trust but cannot read** (D39). The Hacker News, Visual Studio Magazine and Security Boulevard block every
  fetch with a Cloudflare challenge: 0 of 15 extracted. We chose not to bypass it. Their items reached the Brief scored
  on the headline alone, and nobody noticed until Health measured extraction per source. They are now held as
  teaser-only.
- **Prices rendered by JavaScript** (GitLab, Snyk, AWS) cannot be read by the fetcher. The manual check found GitLab
  and Snyk pricing cells wrong for this reason, so the screen says "price not captured" (D95, D97).
- **Neighbouring content leaks in.** Cloudsmith's "Other logs" entries leaked into an item (2,145 → 885 characters
  after stripping). A stricter extraction setting cut real articles (10,438 → 652 characters), so it stays off.
- **Google News dates are the feed's date, not the publisher's.** An old article can look recent (n = 2 checked:
  stored 27 Oct vs published 11 Aug 2026; stored 29 Oct vs published 6 Feb 2025). Not fixed, because the date decides
  the insights window; the UI labels it "Feed date" (D57).
- **Cold start.** Follow-up coverage looks new until history builds up.

**Classification and scoring**
- **Rule-settled category is weak on test** (3 of 9, above). Fix known, not applied (D70).
- **Pattern rules are brittle.** A fix for one title can silently re-break another; "GitHub as a company" vs "GitHub
  as a place" took three review rounds. Every misfire is pinned as a regression test (D24).
- **Ambiguous names.** The Sonatype query returned a story about the VC firm Nexus; it was correctly tagged noise.
  New players outside the list (Socket, Aikido) are not tracked.
- **"Mentions JFrog" can come from page text the model never sees.** The match runs over the whole fetched page, but
  only 6,000 characters are stored. A match in a nav link or footer holds the item and adds +1 to its score (D57).
- **The +1 Mentions JFrog bonus raised scores an analyst judged too high** (n = 2, D62), and it inflates JFrog's own
  news (a JFrog customer-award story went from 3 to 4). Future fix: no bonus on JFrog's own news.
- **A pricing change skipped review** (D41). "Copilot included in GitHub Enterprise" was classified AI & Agents, so it
  auto-published instead of being held as Pricing. Routing is only as safe as the category it rests on.
- **A funding story with no fitting score** (2 Nov). AIR Security's $50M seed for an AI-agent firewall is not a
  tracked competitor, and the Industry column of the rubric has no cell for an adjacent startup's funding. The cause is
  the rubric, not the labeler. A candidate for the next golden set.

**Lens and insights**
- **The lens relation is wrong where it matters most** (0 of 8). 5 of the 8 had no fitting value in the taxonomy (an
  attack, or an existing capability with no change). The UI hides the relation and shows only the capability (D58).
- **The lens covers part of the items.** In the 1 Nov snapshot 88 of 110 held items have no lens result; the "Why it
  matters to JFrog" block is then hidden (D73).
- **Insights are rewritten every day** (D63). The generator has no memory and two days' windows overlap by 6 of 7
  days, so yesterday's pattern returns under a new title. The Brief marks insights new, continuing or strengthened by
  shared cited stories; "strengthened" means a newly cited story, not more evidence.
- **Insights merge patterns that mean different things.** Copilot Fusion and the GitHub package firewall were found
  but merged into one insight (D60).
- **Insight claims rarely quote the capability sheet:** 2 of 33 claims across 31 Oct, 1 Nov and 2 Nov, 0 of 12 on the
  demo day.
- **An insight cites items outside today's Brief,** because a pattern needs more than one day. The card tags them
  "not in this Brief" (D37, D44, D50).

**Prompt injection (open)**
- A planted sentence passes the quote check: it proves the words are in the article, not that they are true.
- Ignoring an instruction is up to the model; code cannot verify it. Schema checks, quote checks and review limit the
  damage.
- Nothing detects or strips injected text before the prompt (D51).

**Product and UI**
- **Flag approved held items** (fixed). Ofri's screen review found that Flag on a held item also approved it, so it
  could reach the Brief without a decision. Flag now only marks an item as important. 0 flagged items existed in the
  live store and the snapshot, so no reported number was affected (D107, D108).
- **Head-to-head values are unverified** beyond the one manual check of 3 Nov; the system has no ongoing verification
  (D88, D95).
- **Edits show field by field in the item drawer,** not in Log rows.

## Now vs future

| Area | Built now | Future |
| --- | --- | --- |
| Scope | 6 competitors + Industry, from `config/competitors.yaml` (D10) | Auto-discovery of new entrants (Socket, Aikido) |
| Sources | Public news search, vendor blogs and changelogs, GitHub releases, Hacker News | Paid feeds, earnings calls, G2, patents, an analyst-forwarding inbox; a headless browser for JavaScript sites |
| Classification | Competitor, 7 categories, Mentions JFrog; rules first, LLM for the rest (D11) | Rules settle the competitor only; a learned classifier from analyst feedback; a new test set |
| Importance | Rubric v2, 1-5 + noise (D29) | Weights tuned on flags and dismissals; no JFrog bonus on JFrog's own news |
| Daily Brief | Insights + items, daily at 06:00, kept by date | Insights with a lifecycle (created once, updated, closed); email and Slack delivery |
| Competitors | Heatmap, cards, profiles, an interim JFrog vs competitors view with unverified values (D88, D113) | The Roadmap's market views; extraction from fixed pages with measured accuracy and human-checked sources; battlecards |
| Lens | Closest JFrog capability, quote-checked (D42) | Redesign: competitor or external event, capability match, evidence, "relevant, impact undetermined"; wider coverage |
| Review and Log | Routing by autonomy level, analyst actions, full Log (D9, D16) | Per-analyst queues, SLAs |
| Quality | Golden set with a frozen split, held-out coverage, daily checks, a reproducibility pack | A faithfulness judge (D17); ranking precision@k; continuous eval from analyst actions; capture–recapture coverage; a "Missed event" button; JFrog's own blog as a "self" source (D43) |
| Observability | `run_metrics`, run status, Health | LangSmith tracing of the daily run (off now, D48, D57) |
| Readers | CI analysts | Role-based digests, an internal MCP server (D19) |
| Infra | Docker Compose, SQLite, ChromaDB, one daily scheduler, a writable demo | Not built: RDS when more than one API instance or a smaller loss window is needed; a bigger instance for more sources; hourly collection after its own check; Amazon Bedrock, subject to JFrog's policies (D116, D117); see ARCHITECTURE.md |
| Agents | — | Not built: add agents for small, bounded processes inside the pipeline (D118) |
| Fixes known, not applied | — | Publisher dates instead of feed dates; JFrog mention from stored text only; hiring signals (D12, dropped) |
| Screen speed (not measured) | — | Competitors takes about a second to appear by eye on the Windows demo, and the Review page makes one item request per decided row |

## Origin, legacy code

Jessi is based on `newsletter_agent`, a personal daily digest pipeline (D8). What Jessi reused is code and ideas: the
reader, the LLM clients, the models and the ranking funnel. It did not reuse the newsletter's LangGraph orchestration:
Jessi's pipeline in `ci/` is plain Python (D117).

Jessi still imports a few files from the origin code: `modules/reader.py` (page fetch and text extraction),
`modules/llm_clients.py` (LLM clients) and `evals/rank_split.py` (the split percentage).

The rest of the newsletter code is **origin, legacy code**: `main.py`, the LangGraph graph in `modules/graph.py` and
the other newsletter files in `modules/`, and the ranking-label tools in `evals/` (`rank_eval.py`, `label_hub.py`,
`import_labels.py` and their helpers). That legacy path is not part of Jessi, does not run in the demo or the daily
run, and is not covered by the evaluation above. It stays until after submission so the frozen commit hashes do not change.

## Repository

```
ci/             Jessi: collectors, pipeline, classify, rank, route, lens, insights, store, API (ci/api), evals, demo
frontend/       Next.js UI
config/         competitors, rubric v2, the JFrog capability sheet, vetted sources, tracked pages
demo/snapshot/  the frozen 1 Nov snapshot the demo serves
repro/          reproducibility pack: labels without article text, the split, saved reports
tests/          Python tests (pytest)
tools/          lock_check.py (fingerprints of the measured system), demo_snapshot.py
docs/           api-contract.md, docker.md, ARCHITECTURE.md, DECISIONS.md
main.py, modules/   origin code: mostly legacy; Jessi uses modules/reader.py and modules/llm_clients.py (see above)
```

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): how Jessi works today, and the AWS production design (design only,
  not built)
- `docs/DECISIONS.md`: the main decisions, each with why and what else was considered
- `docs/api-contract.md`: endpoints per screen
- `docs/docker.md`: every Compose command

**Trademarks.** Company names and logos are trademarks of their owners. The Roadmap concept images show real company
names and logos with sample data; nothing on them is a finding, and no affiliation or endorsement is implied (D105).
