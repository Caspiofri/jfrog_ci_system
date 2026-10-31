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

export interface Lens {
  axis: string;
  capability_quote: string;
  relation: "closes_gap" | "opens_gap" | "improves_shared" | "not_related" | string;
  why: string;
  source_url?: string | null; // request 3d
  source_label?: string | null;
}

export interface TextBasis {
  status: "full" | "partial" | "snippet" | "junk" | string;
  source?: "page" | "feed" | "teaser" | string | null;
  reason?: string | null;
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
  reason: string;
  why_it_matters: string;
  published_at: string | null;
  date_precision: "time" | "day" | string;
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
  text_basis?: TextBasis | null; // D44 request 3c
  mock?: string[]; // dev mock mode only: the fields filled with stand-in values
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
}

export interface BriefInsights {
  status: string; // ok | partial | none | failed | not_generated | missing
  enabled?: boolean;
  generated_at?: string;
  trigger?: string;
  level?: string;
  model?: string;
  window?: { from?: string; to?: string; days?: number; items?: number; stories?: number };
  rejected?: number | unknown[];
  items: Insight[];
  mock?: boolean; // dev mock mode only
}

export interface Kpi {
  key: "items" | "important" | "found_late" | "mentions_jfrog";
  value: number;
  prev: number | null;
}

export interface BriefSummary {
  published: number;
  published_high: number | null;
  held: number;
  held_high: number | null;
  level?: string;
  mock?: string[]; // dev mock mode only
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
  summary?: BriefSummary | null; // D44, request 3a
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
  actions: { action: string; at: string; reason?: string | null; note?: string | null }[];
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
  scope?: { date_from?: string | null; date_to?: string | null; competitor?: unknown; brief?: string | null };
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
