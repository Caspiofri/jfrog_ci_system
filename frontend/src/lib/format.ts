// Display helpers. Labels and colors only: no data lives here.

export const TZ = "Asia/Jerusalem";

/** Shown where the API returns an empty excerpt. */
export const NO_TEXT = "Text couldn't be extracted";

/** One importance color scale (build notes: urgency dropped, the score is the only scale). */
export const SCORE_COLOR: Record<number, [string, string]> = {
  5: ["#9b1c1c", "#fff"],
  4: ["#e5483b", "#fff"],
  3: ["#f59e0b", "#fff"],
  2: ["#fcd34d", "#5b4400"],
  1: ["#cbd3df", "#44516a"],
  0: ["#eaeef4", "#6b7788"],
};

export const CATEGORY_COLOR: Record<string, string> = {
  "Product & Features": "#3f5b8f",
  "Pricing & Packaging": "#f59e0b",
  "AI & Agents": "#8b5cf6",
  Security: "#e5483b",
  "Funding/M&A/Partnerships": "#14b8a6",
  "Customers & Market": "#41be57",
  "Leadership & Org": "#9aa5b5",
};

export const STATUS_LABEL: Record<string, string> = {
  auto_published: "Cleared", // D94: passed routing (display only; the stored status is auto_published)
  awaiting_review: "Awaiting review",
  approved: "Cleared by analyst", // D94: cleared, by an analyst's approval
  flagged: "Flagged",
  dismissed: "Dismissed",
  dropped: "Dropped",
  held_out: "Held out (test split)",
  unclassified: "Not classified yet",
};

export const STATUS_COLOR: Record<string, string> = {
  auto_published: "#41be57",
  approved: "#14a085",
  awaiting_review: "#f59e0b",
  flagged: "#e5483b",
  dismissed: "#b45b5b",
  dropped: "#9aa5b5",
  held_out: "#8b5cf6",
  unclassified: "#cbd3df",
};

export const HOLD_LABEL: Record<string, string> = {
  unvetted_source: "Unvetted source",
  low_confidence: "Low confidence",
  teaser_high_score: "High score on a teaser",
  junk_extraction: "Junk extraction",
  pricing: "Pricing",
  m_and_a: "M&A / funding",
  mentions_jfrog: "Mentions JFrog",
  model_failure: "Model failure",
  invalid_output: "Invalid model output",
  changed_cell: "Changed head-to-head cell",
};

export const DISMISS_LABEL: Record<string, string> = {
  not_relevant: "Not relevant",
  wrong_competitor: "Wrong competitor",
  wrong_category: "Wrong category",
  duplicate: "Duplicate",
};

export const LEVEL_LABEL: Record<string, string> = { strict: "Strict", balanced: "Balanced", relaxed: "Relaxed" };

export const STAGE_LABEL: Record<string, string> = {
  url_dedupe: "URL dedupe",
  embedding_dedupe: "Embedding dedupe",
  test_skip: "Test split",
  classify: "Classify",
  rank: "Rank",
  validate: "Validate",
  route: "Route",
  analyst: "Analyst",
  pending: "Pending",
};

export const SOURCE_LABEL: Record<string, string> = {
  google_news: "News search",
  vendor_feed: "Vendor feed",
  github_releases: "GitHub releases",
  hackernews: "Hacker News",
};

export const PATTERN_LABEL: Record<string, string> = {
  competitor_momentum: "Competitor momentum",
  axis_convergence: "Convergence",
  shared_threat: "Shared threat",
};

export const label = (map: Record<string, string>, key: string | null | undefined) =>
  key ? (map[key] ?? key.replace(/_/g, " ")) : "—";

/** "Oct 31" or "Oct 31, 2025" when not this year. Israel date. */
export function fmtDate(iso: string | null | undefined, withYear = false): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(withYear ? { year: "numeric" } : {}), timeZone: TZ });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: TZ });
}

/** A YYYY-MM-DD Brief date as "Saturday, Oct 31, 2026". */
export function fmtLongDate(date: string): string {
  const d = new Date(`${date}T12:00:00Z`);
  return d.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

/** The item's date as the feed gave it (Google News, not the article page), with precision: day-precision says "date only". */
export function fmtPublished(iso: string | null, precision: string): string {
  if (!iso) return "unknown";
  return precision === "day" ? `${fmtDate(iso, true)} (date only)` : fmtDate(iso, true);
}

/** D94: the three terms, one name each, with their hover. Display only: API fields and stored statuses are unchanged. */
export const ARTICLE_DATE_TIP = "The date the publisher put on the article.";
export const COLLECTED_TIP = "When our pipeline found it.";
export const CLEARED_TIP = "Passed routing, or approved by an analyst.";

/** D94: the route's reason as the API stores it ("published at strict") reads "cleared at strict" on screen. Any other
 *  reason is shown as stored. Display only. */
export function routeReasonWords(reason: string | null | undefined): string {
  if (!reason) return "";
  return reason.replace(/^published at\b/, "cleared at");
}

/** The date line for an item, labeled "Article date" (D94; the API's published_at). A future article date reads as
 * scheduled (contract §10.6). Once it passes, the API clears scheduled_for. */
export function itemDateText(it: { published_at: string | null; date_precision: string; scheduled_for?: string | null; published_at_source?: string | null }): string {
  if (it.scheduled_for) return `Article date ${fmtDate(it.scheduled_for, true)} (scheduled, after we collected it)`;
  // An article date later than our collection is stored as the collection time; the article's own date is published_at_source.
  if (it.published_at_source) return `Article date ${fmtDate(it.published_at_source, true)}`;
  return `Article date ${fmtPublished(it.published_at, it.date_precision)}`;
}

/** Only http(s) links are clickable; anything else from a collected page is shown as text (D32). */
export function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

export function delta(value: number, prev: number | null): { text: string; cls: string } {
  if (prev === null || prev === undefined) return { text: "no previous Brief", cls: "text-mute" };
  const d = value - prev;
  if (d === 0) return { text: `same as previous Brief (${prev})`, cls: "text-mute" };
  return { text: `${d > 0 ? "+" : ""}${d} vs previous Brief (${prev})`, cls: "text-mute" };
}

// ---- D44: score labels, lens relations, text basis ----

/** Rubric v2 (config/rubric_v2.md, frozen under D29), copied word for word. Replaced by /meta rubric when served.
 * Only 3–5 have a label: the Brief shows 3+ (D44); never invent other severity words. */
export const RUBRIC: Record<number, { label: string; competitor: string; industry: string }> = {
  5: {
    label: "Strategic move",
    competitor: "Strategic move at significant scale against a JFrog core product (Artifactory, Xray, Curation) or its positioning; a material acquisition",
    industry: "A market-changing event (rare)",
  },
  4: {
    label: "Material change",
    competitor: "Material competitive change backed by evidence: a capability-level gap opened or closed, or a business/security event with direct competitive impact",
    industry: "A major event in JFrog's market: a broad supply-chain attack on a package or AI-tooling ecosystem, new regulation",
  },
  3: {
    label: "Relevant development",
    competitor: "Relevant development without a proven material change: improves an existing capability, a sub-feature, a partnership, a customer win, a security event with indirect impact",
    industry: "A relevant vulnerability or incident of limited scope",
  },
  // 2 and 1: named with the rubric v2 rows' own words (docs/specs/rubric_v2.md); shown on profiles and timelines
  2: {
    label: "Intelligence value",
    competitor: "No new event, but intelligence value: marketing, opinion, listicle, buyer's guide that reveals positioning or strategy",
    industry: "Commentary and research",
  },
  1: {
    label: "Routine update",
    competitor: "A routine operational event: patch release, version support, maintenance, deprecation of a minor feature, a default/config change",
    industry: "A routine operational event",
  },
};

export const RELATION_LABEL: Record<string, string> = {
  closes_gap: "Closes a gap: gains a capability JFrog already has",
  opens_gap: "Opens a gap: a capability JFrog doesn't have",
  improves_shared: "Improves a capability both already have",
};

/** Why the article text wasn't used (contract §10.5 `reason`), in words. http_<code> is handled below. */
const BASIS_REASON: Record<string, string> = {
  cloudflare_challenge: "the site blocks text extraction",
  timeout: "the page timed out",
  empty: "the page had no readable text",
  not_html: "the link isn't an article page",
  connection_error: "the site couldn't be reached",
  skipped_unresolved: "the news link couldn't be resolved to the article",
  shorter_than_teaser: "the page text was shorter than the teaser",
  failed: "the fetch failed",
  not_recorded: "why wasn't recorded for this older item",
};

function reasonWords(reason: string | null): string | null {
  if (!reason || reason === "not_article") return null; // the junk label already says so
  const http = reason.match(/^http_(\d{3})$/);
  if (http) return http[1] === "403" || http[1] === "401" ? "the site blocks text extraction" : `the site answered HTTP ${http[1]}`;
  return BASIS_REASON[reason] ?? reason.replace(/_/g, " ");
}

/** The text an item was scored from, in words (D39): the API's label, plus why when the article wasn't used. */
export function textBasisWords(b: { status: string; label: string; reason: string | null } | null | undefined): string | null {
  if (!b) return null;
  if (b.status === "full" || b.status === "partial") return b.label;
  const why = reasonWords(b.reason);
  return `Scored from ${b.label.charAt(0).toLowerCase()}${b.label.slice(1)}${why ? `; ${why}` : ""}`;
}

/** Head-to-head axis keys -> the capability sheet's row labels (the /capabilities page anchors on the key). */
export const AXIS_LABEL: Record<string, string> = {
  deployment: "Deployment",
  package_coverage: "Package coverage",
  security_scanning: "Security scanning",
  curation_gating: "Curation / gating",
  ai_mcp: "AI & MCP",
  cicd_integration: "CI/CD integration",
  pricing_model: "Pricing model",
};

/** D88: shown, never only on hover, wherever head-to-head or change-detection values appear. */
export const UNVERIFIED_VALUES =
  "Values are extracted by an AI model from the linked public pages. The system has no verification step for them, and our automated evaluation does not cover them. Check the source before relying on a value.";

/** D90: aggregators whose name says nothing about who wrote the article; the article's domain is shown instead. */
export const AGGREGATORS = ["hacker news", "google news", "news.ycombinator.com", "news.google.com"];

function hostOf(u: string | null | undefined): string | null {
  if (!u) return null;
  try {
    const h = new URL(u).hostname.toLowerCase();
    return h ? h.replace(/^www\./, "") : null;
  } catch {
    return null;
  }
}

/** D90: the name on an article's external link: the stored publisher; the article's domain when the publisher is
 *  missing, an aggregator, or itself a URL; null when there is neither (the link then says "Source"). Never invented. */
export function publisherName(publisher: string | null | undefined, url: string | null | undefined): string | null {
  const p = (publisher ?? "").trim();
  const isUrl = /^https?:\/\//i.test(p);
  if (p && !isUrl && !AGGREGATORS.includes(p.toLowerCase())) return p;
  return hostOf(url) ?? (isUrl ? hostOf(p) : null);
}
