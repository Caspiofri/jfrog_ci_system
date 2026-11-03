// Response types for the CI API v1 (docs/plans/2026-10-31-api-contract.md and ci/api/app.py as built).
// Every string here may come from a site we don't control (D32): render as text only.

export type Level = "strict" | "balanced" | "relaxed";
export type Badge = "new" | "late";
export type Status =
  | "auto_published"
  | "awaiting_review"
  | "approved"
  | "dismissed"
  | "flagged"
  | "dropped"
  | "held_out"
  | "unclassified";

export interface ApiMeta {
  mode: "live" | "demo";
  now: string;
  api_version: string;
  snapshot?: { date: string } | null; // demo mode: the day the snapshot was taken (not served yet)
}

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface HoldReason {
  code: string;
  detail: string;
  held_at: Level[];
}

/** Why lens is null: "rejected" (its checks failed) or "failed" (the call failed); null means never analyzed. */
export type LensStatus = "ok" | "rejected" | "failed";

// Contract §10.5. axis and capability_quote are null for not_related.
export interface Lens {
  axis: string | null;
  capability_quote: string | null;
  relation: "closes_gap" | "opens_gap" | "improves_shared" | "not_related" | string;
  why_it_matters: string;
  /** @deprecated same text as why_it_matters */
  why?: string;
  source_url?: string | null; // request 3d, not built
  source_label?: string | null;
}

// Contract §10.5 (D39).
export interface TextBasis {
  status: "full" | "partial" | "snippet" | "junk" | string;
  source: "page" | "feed" | "teaser" | string;
  label: string;
  reason: string | null;
  reason_detail: string | null;
  chars_used_for_scoring: number;
}

export interface RubricLine {
  score: number;
  label: string;
  competitor: string;
  industry: string;
}

export interface Item {
  item_id: string;
  title: string;
  url: string;
  excerpt: string;
  source: string;
  publisher: string;
  publisher_host: string;
  competitor: string;
  classified: boolean;
  category: string | null;
  noise: boolean;
  score: number | null;
  urgency: string | null;
  confidence: number | null;
  mentions_jfrog: boolean;
  jfrog_mention?: JfrogMention | null; // D77: where JFrog is mentioned; null when mentions_jfrog is false
  reason: string;
  why_it_matters: string;
  published_at: string | null;
  date_precision: "time" | "day" | string;
  published_at_source?: string | null; // §10.6: the source's date when it was after our collection
  scheduled_for?: string | null; // §10.6: published_at_source while still in the future
  discovered_at: string | null;
  discovery_lag_hours: number | null;
  badge: Badge | null;
  status: Status;
  hold_reasons: HoldReason[];
  edited: Record<string, unknown> | null;
  flagged: boolean;
  version: number;
  run_id: string | null;
  fingerprint: string | null;
  event_id: string | null;
  lens?: Lens | null; // D42: only when its quote check passed
  lens_status?: LensStatus | null; // null: no lens row yet (not served yet)
  text_basis?: TextBasis | null; // contract §10.5
}

export interface Competitor {
  key: string;
  name: string;
  is_industry: boolean;
}

export interface Meta {
  competitors: Competitor[];
  categories: string[];
  levels: Level[];
  default_level: Level;
  statuses: Status[];
  dismiss_reasons: string[];
  hold_reasons: string[];
  level: Level;
  latest_brief_date: string | null;
  latest_run_id: string | null;
  insights_enabled: boolean;
  rubric?: RubricLine[]; // request 3f
  meta: ApiMeta;
}

// ---- Brief ----

export interface BriefRow {
  date: string;
  anchor_run_id: string;
  anchor_kind?: string; // requested in BACKEND_REQUESTS.md #1
  backfill?: boolean; // requested in BACKEND_REQUESTS.md #1 (either name)
  published?: number; // §10.2
  published_high?: number;
  held?: number;
  held_high?: number;
  /** @deprecated §10.2 */
  items: number;
  found_late: number;
  awaiting_review: number;
}

export interface Claim {
  text: string;
  item_ids: string[];
  quote: string;
  quote_item_id: string;
  jfrog_quote?: string; // D42: verbatim from the JFrog capability sheet, when the claim is about JFrog
  jfrog_axis?: string | null; // not served today: the capability the quote comes from, if the generator ever stores it
  axis?: string | null;
}

export interface Insight {
  insight_id: string;
  pattern: string;
  title: string;
  summary: string;
  why_it_matters: string;
  claims: Claim[];
  item_ids: string[];
  story_ids: string[];
  max_score: number | null;
  window?: Record<string, unknown>;
  axis: string | null;
  jfrog_cell: Record<string, unknown> | null;
  baseline_note: string;
  jfrog_quotes?: string[];
  /** Contract §10.4 (D50): one row per cited item, claim order. in_brief false = not in this Brief's list. */
  cited_items?: CitedItemRow[];
  /** Contract §14: absent on older data. */
  continuity?: InsightContinuity | null;
}

export interface InsightContinuity {
  status: "new" | "continuing" | "strengthened" | string;
  since: string | null; // the previous Brief's date
  new_stories: number | null;
  matched?: string[];
}

export interface PreviousInsights {
  date: string | null;
  status: string | null;
  insights: number;
  unmatched: number;
  unmatched_ids?: string[];
}

export interface CitedItemRow {
  item_id: string;
  title: string;
  score: number | null;
  url: string;
  status: string;
  in_brief: boolean;
}

export interface BriefInsights {
  /** Contract §10.4: the state the UI shows. */
  status: "disabled" | "refreshing" | "failed" | "none_passed" | "ok" | "not_run" | "missing" | string;
  generator_status?: string; // ok | partial | none | failed
  enabled?: boolean;
  generated_at?: string;
  trigger?: string;
  level?: string;
  model?: string;
  window?: { from?: string; to?: string; days?: number; items?: number; stories?: number };
  rejected?: number; // a count (§10.4)
  items: Insight[];
  previous?: PreviousInsights | null; // contract §14: absent on older data
  mock?: boolean; // dev mock scenarios only
}

export interface Kpi {
  key: "items" | "important" | "found_late" | "mentions_jfrog";
  value: number;
  prev: number | null;
}

// Contract §10.2: the Brief window's counts, from the same query as the item list.
export interface BriefSummary {
  brief_min_score: number;
  published: number;
  published_high: number;
  published_below: number;
  held: number;
  held_high: number;
  held_by_preliminary_score: Record<string, number>;
  level: string;
  mock?: boolean; // dev mock scenarios only
}

export interface Brief {
  date: string;
  status: "ok" | "partial" | "missing";
  window: {
    prev_anchor: string;
    anchor: string;
    anchor_run_id: string;
    anchor_kind?: string;
    backfill?: boolean;
    hours: number;
    tz: string;
  } | null;
  counts: {
    items: number;
    new: number;
    found_late: number;
    awaiting_review: number;
    important: number;
    mentions_jfrog: number;
  } | null;
  kpis: Kpi[];
  summary?: BriefSummary; // contract §10.2; absent only for a missing Brief
  brief_min_score?: number;
  insights: BriefInsights;
  intensity: { days: number; by: string; series: { date: string; score: number; items: number }[] } | null;
  level?: Level;
  items: Page<Item>;
  meta: ApiMeta;
}

// ---- Item drawer ----

export interface ItemDetail {
  item: Item;
  classification: { method?: string; reason?: string; degraded?: boolean; competitor_confirmed?: boolean } | null;
  ranking: { raw_score?: number | null; adjustments?: unknown; degraded?: boolean } | null;
  sightings: { item_id: string; run_id: string; seen_at?: string }[];
  rejections: string[];
  skip: string | null;
  actions: ItemAction[];
}

/** §13.2: one per field an edit changed. Older edit actions have no changes, only payload.before. */
export interface FieldChange {
  field: "competitor" | "category" | "score" | string;
  old: string | number | null;
  new: string | number | null;
  note: string | null;
}

export interface ItemAction {
  action: string;
  at: string;
  reason?: string | null;
  note?: string | null;
  payload?: { changes?: FieldChange[]; status_before_dismiss?: string | null; reopens_action_id?: number | null } | null;
}

// ---- Review ----

export interface LevelCount {
  level: Level;
  held: number;
  published: number;
  n: number;
}

export interface TrustInfo {
  host: string;
  approved: number;
  dismissed: number;
  suggest: boolean;
  vetted?: boolean;
  trusted?: boolean;
}

export interface ReviewItemRow {
  kind: "item";
  item: Item;
  held_since: string | null;
  trust_source: TrustInfo | null;
}

export interface TierChange {
  tier: string;
  change: "added" | "removed" | "changed" | "renamed" | string;
  old: string;
  new: string;
  old_name?: string;
}

export interface ReviewChangeRow {
  kind: "change";
  change_id: string;
  run_id: string;
  competitor: string | null;
  axis: string | null;
  axis_label?: string;
  old_value: string | null;
  new_value: string | null;
  old_evidence?: string;
  new_evidence?: string;
  tier_changes?: TierChange[];
  diff?: string;
  page_url?: string;
  note?: string;
  held_since?: string;
  hold_reasons: HoldReason[];
}

export interface Review extends Page<ReviewItemRow | ReviewChangeRow> {
  level: Level;
  levels: LevelCount[];
  counts_by_reason: Record<string, number>;
  scope?: { date_from?: string | null; date_to?: string | null; competitor?: unknown; brief?: string | null; window?: { prev_anchor: string; anchor: string } };
  backlog_total?: number; // §10.3: every undecided held item at this level, unfiltered
  meta: ApiMeta;
}

export interface SourceRow {
  host: string;
  items?: number;
  held?: number;
  approved?: number;
  dismissed?: number;
  suggest?: boolean;
  group?: string;
}

export interface TrustResult {
  host: string;
  released: { total: number; item_ids: string[] };
  still_held: { total: number; item_ids: string[] };
}

// ---- Log ----

export interface LogRow {
  item_id: string | null;
  run_id: string | null;
  title: string;
  url: string | null;
  source: string | null;
  publisher: string | null;
  competitor: string | null;
  category: string | null;
  score: number | null;
  published_at: string | null;
  collected_at: string | null;
  discovered_at: string | null;
  status: Status;
  stage: string | null;
  reason: string;
  dismiss_reason?: string | null; // §3.5: the latest dismiss action's reason, null on every other row
  flagged?: boolean; // D107: the analyst's flag, a marker only
  duplicate_of: string | null;
  text_status: string | null;
}

export interface Log extends Page<LogRow> {
  counts: { status: Record<string, number>; stage: Record<string, number> };
  meta: ApiMeta;
}

// ---- Competitors (contract §9) ----

export interface CompetitorCard {
  key: string;
  name: string;
  is_industry: boolean;
  items_today: number;
  items_7d: number;
  items_prev_7d: number;
  trend: { delta: number; direction: "up" | "down" | "flat" };
  threat: number | null;
  pending_review: number;
  pending_max_score: number | null;
  tracked_changes: number | null;
  head_to_head_changes: number | null;
  mentions_jfrog: number;
  category_mix: { category: string; count: number }[];
  top_item: { item_id: string; title: string; score: number | null; published_at: string | null; badge?: Badge | null } | null;
  last_activity_at: string | null;
  summary: { status: string; text?: string };
}

export interface Deal {
  item_id: string;
  title: string;
  url: string;
  competitor: string;
  published_at: string | null;
  source: string;
  publisher: string;
  status: Status;
  score: number | null;
}

export interface Competitors {
  date: string;
  level: Level;
  week: { start: string; end: string };
  counted_by: string;
  total: number;
  items: CompetitorCard[];
  deals: Page<Deal> & { category: string };
  meta: ApiMeta;
}

export interface CellChange {
  change_id: string;
  old_value: string;
  new_value: string;
  tier_changes: TierChange[];
  detected_at: string;
  status: string;
}

export interface Cell {
  state: "value" | "stale" | "not_stated" | "not_tracked";
  value: string | null;
  reason?: string;
  evidence?: string;
  tiers?: { name: string; price: number | null; currency: string; period: string; unit: string }[];
  source_url?: string;
  page_key?: string;
  as_of?: string;
  checked_at?: string;
  confidence?: number;
  note?: string;
  stale_reason?: string;
  needs_review?: boolean;
  review_reason?: string;
  change: CellChange | null;
}

export interface H2HAxis {
  axis: string;
  label: string;
  competitor: Cell;
  jfrog: Cell;
  changed: boolean;
}

export interface CompetitorProfile {
  key: string;
  name: string;
  date: string;
  card: CompetitorCard;
  summary: { status: string; text?: string };
  head_to_head: { jfrog_name: string; axes: H2HAxis[] } | null;
  activity: { days: number; bucket: string; total: number; series: { date: string; items: number; max_score: number | null }[] };
  deals: Deal[];
  latest_items: Page<Item>;
  meta: ApiMeta;
}

export interface CellHistoryRow {
  value: string;
  as_of: string;
  confidence: number;
  source_url: string;
  run_id: string;
  event: string;
  change_id: string;
}

// ---- Health (contract §9) ----

export interface RunInfo {
  run_id: string;
  kind: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  fingerprint: string | null;
  model: string | null;
  llm_calls: number | null;
  error?: string | null;
  errors?: unknown[];
  /** Contract §11.2: on /runs rows. stale = still running more than 1 h after it started. */
  marker?: RunMarker;
}

export type RunMarker = "ok" | "degraded" | "failed" | "running" | "stale";

// Contract §11.2 (D48).
export interface Liveness {
  state: RunMarker | "overdue" | "none";
  latest_run_id: string | null;
  latest_status: string | null;
  hours_since_latest: number | null;
  stale_run_ids: string[];
  stale_after_hours: number;
  overdue_after_hours: number;
}

// Contract §11.1: only the parts Health shows.
export interface RunStep {
  step: string;
  status: "ok" | "degraded" | "failed" | "skipped" | string;
  seconds?: number | null;
  llm_calls?: number | null;
  errors?: unknown[];
  item_ids?: string[];
  reason?: string;
}

export interface RunMetrics {
  run_id: string;
  status: string;
  items?: { collected?: number; kept?: number; new?: number; [k: string]: unknown } | null; // contract §11.1
  items_after_actions?: { published?: number | null; held?: number | null; [k: string]: unknown } | null; // §11.2, D74
  reconstructed?: { decision?: string; at?: string; label?: string; sources?: Record<string, string>; empty?: Record<string, string> } | null; // D74
  error?: string | null;
  steps: RunStep[];
  fingerprints?: Record<string, string | null> | null;
  metadata?: { commit?: string | null; [k: string]: unknown } | null;
}

// Contract §11.3: the test-split eval. status "none" until it has run.
export interface TestEval {
  status: "ok" | "none" | string;
  note?: string;
  report?: string;
  created_at?: string;
  split?: string;
  fingerprint?: string;
  model?: string;
  n?: number;
  test_runs?: number;
  cards?: EvalCard[];
}

export type FunnelRow = Record<string, number | string | unknown[]> & { source: string };

export interface ExtractionRow {
  key: string;
  extracted: number;
  n: number;
  rate: number | null;
  by_status: { full: number; partial: number; snippet: number; junk: number };
  fetch?: Record<string, number>;
}

export interface ExtractionBlock {
  run_id?: string;
  extracted: number;
  n: number;
  rate: number | null;
  fetch?: Record<string, number>;
  by_source: ExtractionRow[];
  by_publisher: ExtractionRow[];
}

export interface EvalCard {
  metric: string;
  value: number | null;
  n: number;
  untested: boolean;
  weak: boolean;
  note: string;
}

export interface Health {
  run: RunInfo | null;
  liveness?: Liveness | null;
  run_metrics?: RunMetrics | null;
  test_eval?: TestEval | null;
  funnel: { run_id: string; level: Level; sources: FunnelRow[]; totals: Record<string, number> } | null;
  silent_sources: {
    runs_so_far: number;
    label: string;
    insufficient_history: boolean;
    rule: string;
    items: { source: string; last_item: string | null; hours_silent: number | null; collected_last_run: number; errors_last_run: unknown[]; status: string }[];
  } | null;
  extraction: { definition: string; run: ExtractionBlock | null; all: ExtractionBlock | null } | null;
  eval: {
    status: string;
    report?: string;
    created_at?: string;
    split?: string;
    live?: boolean;
    fingerprint?: string;
    model?: string;
    n?: number;
    labels?: { total: number; non_noise: number; important: number; funding_m_and_a: number };
    test_eval_run?: boolean;
    cards: EvalCard[];
  } | null;
  coverage: {
    status: string;
    measured_on?: string | null; // when the coverage check was measured (BE, D82)
    run_id?: string;
    list?: string;
    window?: { first: string; last: string };
    overall?: { captured: number; n: number };
    important?: { captured: number; n: number; min_score: number };
    by_source_kind?: Record<string, { captured: number; n: number }>;
    missed?: { id: string; title: string; competitor: string; expected_importance: number; official_url: string }[];
  } | null;
  change_detection: {
    run_id?: string;
    started_at?: string;
    live?: boolean;
    status: string;
    pages?: number;
    fetched?: number;
    changes?: number;
    failures?: { competitor?: string; page?: string; reason?: string; error?: string }[];
    unconfirmed?: { competitor: string; page: string; axes: string[]; reasons: Record<string, string> }[];
    needs_review?: unknown[];
    age_hours?: number;
  } | null;
  meta: ApiMeta;
}

/** Contract (3 Nov, D77): read-only, a mention and not a comparison. */
export interface JfrogMention {
  status: "found" | "not_in_stored_text";
  snippet: string | null; // at most 280 characters around the first match; null when not in the stored text
  found_in: "text" | "title" | null;
}
