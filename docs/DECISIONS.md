# Decisions

The main design decisions behind Jessi, each with what was decided, why, and what else was considered. The full log
(D1 to D113, newest first, with dates) is the PRD's decision log; numbers here are copied from it. IDs match the PRD,
so a reader can look each one up.

[DRAFT, 4 Nov. Started from the PRD after D113. Still to add: the delivery decisions (D57, D59, D99, D109, D111) in
full, Stage 2 (D30, D64, D65), and a line per UI round (D72, D89, D104, D112, D113).]

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

**Model split: Gemini writes and ranks, Claude judges (D5).**
- **Why:** already proven in the origin project; a judge from another family does not grade its own work. A gateway
  such as Bedrock is a config change for production.
- **Note:** the faithfulness judge was not built for this submission (D17).

## The JFrog comparison

**The lens is an explanation layer, not a score input (D42, D58).**
- **What:** after ranking, each non-noise item gets the closest JFrog capability, quoted word for word from the
  capability sheet and checked in code. It never changes a score.
- **Why:** the eval showed a capability baseline did not improve scores (D40), but the brief asks how JFrog compares.
  The lens adds that meaning without touching what was measured.
- **Result and display:** axis right 10 of 10, relation right 0 of 8 where claimed (n = 15 items). The UI shows the
  capability and hides the relation.

**Head-to-head values stay, captioned as unverified (D87, D88, D95).**
- **What:** values extracted by an AI model from linked public pages, shown with a caption that no person reviewed
  them and that the evaluation does not cover them. One manual check on 3 Nov: 38 of 42 values correct, 2 partial,
  2 wrong; 7 of 49 cells empty where the information exists elsewhere.
- **Why:** the gap was verification, not provenance: the values come from a real running pipeline. Stating the gap
  keeps the comparison the brief asks for and stays honest.
- **Considered:** removing the comparison (D87), reversed the same evening.

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
  system cannot really be experienced" (Ofri, 4 Nov); the copy is isolated, so actions cannot pollute measured data.
- **Considered:** read-only (D110), reversed the same day under a time box with the frozen commit as the fallback.

**No AWS for the submission (D4).**
- **Why:** credentials block reviewers from running it. The production design is in ARCHITECTURE.md.

**Product name Jessi (D46).** JFrog's Engine for Strategic Signals & Intelligence.
