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
}

export interface Kpi {
  key: "items" | "important" | "found_late" | "mentions_jfrog";
  value: number;
  prev: number | null;
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

export interface ReviewChangeRow {
  kind: "change";
  change_id: number | string;
  run_id: string;
  competitor: string | null;
  axis: string | null;
  old_value: string | null;
  new_value: string | null;
  hold_reasons: HoldReason[];
}

export interface Review extends Page<ReviewItemRow | ReviewChangeRow> {
  level: Level;
  levels: LevelCount[];
  counts_by_reason: Record<string, number>;
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
