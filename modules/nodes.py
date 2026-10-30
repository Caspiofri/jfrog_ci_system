import json
import re
from datetime import date

from langsmith import run_helpers, traceable
from langsmith.utils import ContextThreadPoolExecutor as ThreadPoolExecutor  # copies trace context into workers
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from config import settings
from modules import article_store, link_utils, llm_clients, ranking_report, reader
from modules.article_text import article_text
from modules.card_resolver import resolve_cards
from modules.collectors import hackernews
from modules.models import Article, NewsletterData
from modules.state import DigestState


def _gemini_usage(response) -> dict | None:
    """Gemini token counts in LangSmith's usage shape; thinking tokens are billed as output, so they count there."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    prompt = usage.prompt_token_count or 0
    thoughts = usage.thoughts_token_count or 0
    output = (usage.candidates_token_count or 0) + thoughts
    return {"input_tokens": prompt, "output_tokens": output, "total_tokens": usage.total_token_count or prompt + output,
            "output_token_details": {"reasoning": thoughts}}


@traceable(run_type="llm", name="gemini")
# a missing key is not transient: no retry; reraise=True surfaces the original error, not tenacity's RetryError
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
       retry=retry_if_not_exception_type(llm_clients.MissingCredentials), reraise=True)
def _call_gemini(contents: str, config: dict | None = None) -> str:
    response = llm_clients.gemini_client().models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=contents,
        config=config or {},
    )
    rt = run_helpers.get_current_run_tree()  # None when LANGSMITH_TRACING is off
    usage = _gemini_usage(response)
    if rt is not None:
        rt.add_metadata({"ls_provider": "google_genai", "ls_model_name": settings.GEMINI_MODEL})
        if usage:
            rt.set(usage_metadata=usage)
    return response.text


def _pick_by_ids(items: list, pool: list[Article], limit: int) -> list[Article]:
    """Map the LLM's ids to articles: ints in range only, LLM order, no duplicates, at most `limit`."""
    picked, seen = [], set()
    for i in items:
        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(pool) and i not in seen:
            seen.add(i)
            picked.append(pool[i])
    return picked[:limit]


def fillter_articles(state: DigestState) -> dict:
    articles = state["articles"]
    if not articles:
        return {"top_articles": []}

    top_k = int(state["top_k"])
    subject = state["subject"]
    # Prefer stories with a working link; fall back to the full pool only if there are too few.
    good = [a for a in articles if a.link_status == "ok"]
    if len(good) >= top_k:
        articles = good
    articles_meta = [
        {"id": i, "name": a.name, "author": a.author, "published_at": str(a.published_at),
         "teaser": article_text(a, settings.SHORTLIST_TEASER_CHARS)}
        for i, a in enumerate(articles)
    ]
    prompt = f"""You are a newsletter writer for a digest about {subject}.
    From these articles {json.dumps(articles_meta, ensure_ascii=False)}, select up to {top_k}
    that are GENUINELY on the subject of {subject}.
    Each article has a short "teaser" (the start of its text). It is only a hint: judge relevance on the
    title and teaser together; an empty teaser means none is available.
    EXCLUDE any article that is off-topic or only tangentially related — it is better to
    return fewer articles (or none at all) than to include irrelevant ones.
    If NONE of the articles are relevant to {subject}, return an empty array [].
    please return ONLY a JSON array of the selected article ids, no extra text,
    for example [2, 0], or [] if none:
    """
    text = _call_gemini(prompt)
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in filter response: {text!r}")
    top_articles = _pick_by_ids(json.loads(match.group()), articles, top_k)
    return {"top_articles": top_articles}



def _sanitize_ids(parsed: dict) -> dict:
    """Null any card/brief id that is not a real int (str, bool, float, missing) so resolve_cards drops it."""
    for key in ("cards", "brief_items"):
        for item in parsed.get(key) or []:
            if isinstance(item, dict) and (isinstance(item.get("id"), bool) or not isinstance(item.get("id"), int)):
                item["id"] = None
    return parsed


def summraize(state: DigestState):
    subject = state["subject"]
    target_audience = state["target_audience"]
    top_k = state["top_k"]
    articles = state["top_articles"]
    experience_level = state["experience_level"]

    # The model refers to articles by list index; resolve_cards maps each id back to the real URL.
    articles_for_prompt = [
        {"id": i, "title": a.name, "author": a.author, "signal": a.signal, "origin": a.origin,
         "read_status": a.read_status, "text": article_text(a)}
        for i, a in enumerate(articles)
    ]

    prompt = f"""You are a Senior Technical Newsletter Editor specializing in {subject}.
Your reader: {target_audience} ({experience_level}) — a Junior Software Engineer transitioning to an AI Engineer role, focused on practical implementation, RAG architectures, and Multi-Agent Systems.

TASK: Analyze the articles and return a JSON object with newsletter content. Return ONLY valid JSON — no markdown wrappers, no commentary.

STEP 1 — SCORE each article internally (0-10) for relevance to: AI engineering, Multi-Agent pipelines, RAG, practical coding tools. Do not output scores.
STEP 2 — CATEGORIZE (all {top_k} articles must appear):
  - Score ≥ 6 → full entry in "cards"
  - Score < 6 → one-line entry in "brief_items"
STEP 3 — WRITE each card:
  - "brief": 1-2 sentences. Factual. What happened / what was launched. Zero fluff, no "game-changer".
  - "personalization": 2-3 sentences. Concrete. Connect to LangGraph, RAG, or daily dev workflow. Coach the reader directly.
STEP 4 — WRITE "actions": 1-2 specific actions grounded in today's articles.

RULES:
- Hebrew prose only. Technical terms (LangGraph, RAG, LLM, API, etc.) stay in English.
- All {top_k} articles must appear (either as a card or brief_item).
- Provide 1-2 items in "actions".

OUTPUT FORMAT:
{{
  "cards": [
    {{
      "title": "[EMOJI] [HEBREW TITLE]",
      "source": "[SOURCE NAME]",
      "brief": "[1-2 sentence factual summary in Hebrew]",
      "personalization": "[2-3 sentences connecting to the reader's context in Hebrew]",
      "id": <int, the "id" of the input article>
    }}
  ],
  "brief_items": [
    {{
      "summary": "[1-sentence Hebrew summary]",
      "id": <int, the "id" of the input article>
    }}
  ],
  "actions": [
    "[Specific action 1 in Hebrew]",
    "[Specific action 2 in Hebrew]"
  ]
}}

INPUT ARTICLES (use each article's "id" exactly as given):
{json.dumps(articles_for_prompt, ensure_ascii=False)}"""  # noqa: E501 (prompt text)

    text = _call_gemini(prompt, config={
        "max_output_tokens": 8000,
        "thinking_config": {"thinking_budget": 4000},
    })

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in newsletter response: {text!r}")
    data = resolve_cards(NewsletterData(**_sanitize_ids(json.loads(match.group()))), articles)
    stats = {**state.get("run_stats", {}), "cards": len(data.cards), "brief_items": len(data.brief_items)}
    return {"newsletter_data": data, "run_stats": stats}


def dedupe_articles(state: DigestState) -> dict:
    """Drop stories already sent in the last few days, before they can take a shortlist slot."""
    profile = state["digest_name"].lower().replace(" ", "_")
    unseen, matches = article_store.filter_seen_detailed(state["articles"], profile)
    dropped = len(state["articles"]) - len(unseen)
    if dropped:
        print(f"[dedupe] Dropped {dropped} article(s) already sent (same URL, or a similar story in the last "
              f"{article_store.DEDUPE_DAYS} days).")
    hits = [m for m in matches if m["dropped"]]
    by_url = [m for m in hits if m.get("matched_by") == "url"]
    stats = {**state.get("run_stats", {}), "after_dedupe": len(unseen), "dedupe_dropped": dropped,
             "dedupe_matches": len(hits), "dedupe_url_matches": len(by_url),
             "dedupe_near_misses": len(matches) - len(hits),
             "dedupe_batch_duplicates": max(0, dropped - len(hits)),
             "dedupe_max_similarity": round(max((m["similarity"] for m in hits if m not in by_url), default=0.0), 3)}
    return {"articles": unseen, "dedupe_drops": matches, "run_stats": stats}


def source_error(source: str, stage: str, error: Exception) -> dict:
    """One failed source, as recorded in state["source_errors"] and the run summary."""
    print(f"[warn] {stage}: source '{source}' failed and is skipped: {type(error).__name__}: {error}")
    return {"source": source, "stage": stage, "error": f"{type(error).__name__}: {error}"}


def shortlist_articles(state: DigestState) -> dict:
    """Title screen run separately per source, so one noisy source cannot crowd out the others.

    A source whose screen fails (the LLM call, or its reply) is logged and recorded, and its articles are left out
    of this run; the other sources go on. Missing credentials are not a source failure: they fail the run.
    """
    articles = state["articles"]
    origins = sorted({a.origin for a in articles})

    def screen(origin: str) -> tuple[list[Article], dict | None]:
        group = [a for a in articles if a.origin == origin]
        quota = settings.SHORTLIST_QUOTA.get(origin, 5)
        try:
            return fillter_articles({**state, "articles": group, "top_k": quota})["top_articles"], None
        except llm_clients.MissingCredentials:
            raise
        except Exception as e:
            return [], source_error(origin, "shortlist", e)

    with ThreadPoolExecutor(max_workers=max(len(origins), 1)) as pool:
        results = list(pool.map(screen, origins))
    candidates = [a for group, _ in results for a in group]
    errors = [err for _, err in results if err is not None]
    print(f"[shortlist] {len(candidates)} of {len(articles)} candidates: "
          f"{ {o: sum(c.origin == o for c in candidates) for o in origins} }")
    stats = {**state.get("run_stats", {}), "shortlisted": len(candidates), "shortlist_failures": len(errors)}
    return {"candidates": candidates, "source_errors": errors, "run_stats": stats}


def read_articles(state: DigestState) -> dict:
    candidates = reader.read_articles(state["candidates"], max_chars=settings.READ_MAX_CHARS)
    stats = {s: sum(a.read_status == s for a in candidates) for s in ("full", "partial", "snippet")}
    print(f"[reader] read status: {stats}")
    run_stats = {**state.get("run_stats", {}), **{f"read_{s}": n for s, n in stats.items()}}
    return {"candidates": candidates, "run_stats": run_stats}


_SOURCE_DESCRIPTIONS = {
    "hackernews": "Hacker News front-page style submission voted by engineers",
}


def _final_scores(scored: list, candidates: list[Article], snippet_cap: int) -> dict[int, float]:
    """id -> score. Unknown ids and malformed rows are ignored; snippet-only articles are capped."""
    best: dict[int, float] = {}
    for row in scored:
        if not isinstance(row, dict) or not isinstance(row.get("id"), int):
            continue
        if 0 <= row["id"] < len(candidates) and isinstance(row.get("score"), (int, float)):
            best[row["id"]] = max(best.get(row["id"], 0), row["score"])
    return {i: min(sc, snippet_cap) if candidates[i].read_status == "snippet" else sc for i, sc in best.items()}


def _select_top(scored: list, candidates: list[Article], top_k: int, min_score: int,
                snippet_cap: int = 10) -> list[Article]:
    """Best-first articles with final score >= min_score."""
    final = _final_scores(scored, candidates, snippet_cap)
    ranked = sorted((i for i, sc in final.items() if sc >= min_score), key=lambda i: -final[i])
    return [candidates[i] for i in ranked[:top_k]]


def build_rank_prompt(candidates: list[Article], subject, target_audience, experience_level,
                      top_k: int, text_chars: int) -> str:
    """The ranker prompt: every candidate with its source and the first text_chars of its text."""
    items = [
        {
            "id": i,
            "title": a.name,
            "source": _SOURCE_DESCRIPTIONS.get(a.origin, a.origin) + (f" ({a.signal})" if a.signal else ""),
            "text_available": a.read_status,
            "text": article_text(a, text_chars),
        }
        for i, a in enumerate(candidates)
    ]
    return f"""You are the editor of a daily digest about {subject}.
Reader: {target_audience} ({experience_level}).

Score each candidate article 0-10 for how much this reader would value reading it, judging the TEXT, not just the title.
Reward: concrete engineering substance, primary sources (releases, papers, engineering blogs), novel results, practical techniques for RAG / agents / LLM systems.
Penalize: beginner tutorials, listicles, self-promotion, vague hype, thin teasers with no substance, off-topic items.
"text_available" tells how much text you have: "full", "partial", or "snippet" (teaser only). Do not reward a good title when the text is empty of substance.
Calibration: 9-10 = must-read; 7-8 = clearly worth the reader's time; 5-6 = acceptable filler; 3-4 = skip; 0-2 = off-topic or junk.
Be strict: on a typical day only about {top_k} candidates deserve 7 or above, and most should land in 3-6.

Return ONLY a JSON array, no commentary: [{{"id": 0, "score": 7, "reason": "short reason"}}]

CANDIDATES:
{json.dumps(items, ensure_ascii=False)}"""  # noqa: E501 (prompt text)


def _parse_rank_reply(text: str) -> list:
    match = re.search(r'\[.*\]', text or "", re.DOTALL)
    try:
        scored = json.loads(match.group()) if match else []
    except json.JSONDecodeError:
        scored = []
    if not scored:
        raise ValueError(f"No usable scores in ranker response: {text!r}")
    return scored


def score_candidates(candidates: list[Article], subject, target_audience, experience_level, top_k: int,
                     text_chars: int, snippet_cap: int | None = None, call=None) -> dict[int, float]:
    """id -> final score from one ranker call, exactly as rank_articles scores (used by evals.rank_eval).

    call defaults to _call_gemini, looked up at call time so tests can patch it. Raises ValueError on an
    unusable reply, including one where no row has a valid id and score.
    """
    prompt = build_rank_prompt(candidates, subject, target_audience, experience_level, top_k, text_chars)
    scored = _parse_rank_reply((call or _call_gemini)(prompt))
    final = _final_scores(scored, candidates, settings.SNIPPET_SCORE_CAP if snippet_cap is None else snippet_cap)
    if not final:
        raise ValueError(f"No valid id/score rows in ranker response: {scored!r}")
    return final


def rank_articles(state: DigestState) -> dict:
    """One LLM call scores every candidate on its content and source; the best top_k become top_articles."""
    candidates = state["candidates"]
    if not candidates:
        return {"top_articles": [], "rank_scores": [],
                "run_stats": {**state.get("run_stats", {}), "ranked": 0, "picked": 0}}
    top_k = int(state["top_k"])
    prompt = build_rank_prompt(candidates, state["subject"], state["target_audience"], state["experience_level"],
                               top_k, settings.RANK_TEXT_CHARS)
    scored = _parse_rank_reply(_call_gemini(prompt))
    final = _final_scores(scored, candidates, settings.SNIPPET_SCORE_CAP)
    top = _select_top(scored, candidates, top_k, settings.RANK_MIN_SCORE, settings.SNIPPET_SCORE_CAP)
    reasons = {r["id"]: r.get("reason", "") for r in scored if isinstance(r, dict) and isinstance(r.get("id"), int)}
    picked = {id(a) for a in top}
    for i in sorted(final, key=lambda i: -final[i]):
        a = candidates[i]
        mark = "*" if id(a) in picked else " "
        print(f"[rank]{mark}{final[i]:>4}  {a.origin:<10} {a.read_status:<7} {a.name[:55]} — {reasons.get(i, '')[:60]}")
    try:  # the labeling report is a by-product; it must never break a run
        profile = state["digest_name"].lower().replace(" ", "_")
        rows = ranking_report.build_rows(
            candidates, final, reasons, top, state["articles"], seed=str(date.today()),
            read_sample=lambda arts: reader.read_articles(arts, max_chars=settings.READ_MAX_CHARS))
        print(f"[rank] Ranking report for labeling: {ranking_report.save(profile, rows)}")
    except Exception as e:
        print(f"[rank] could not write ranking report: {e}")
    rank_scores = [
        {"title": candidates[i].name, "origin": candidates[i].origin, "read_status": candidates[i].read_status,
         "score": final[i], "reason": reasons.get(i, ""), "picked": id(candidates[i]) in picked}
        for i in sorted(final, key=lambda i: -final[i])
    ]
    stats = {**state.get("run_stats", {}), "ranked": len(final), "picked": len(top)}
    return {"top_articles": top, "rank_scores": rank_scores, "run_stats": stats}


def store_picks(state: DigestState) -> dict:
    """Remember the run's picks in the article store, so the next runs' dedupe drops the same stories."""
    profile = state["digest_name"].lower().replace(" ", "_")
    try:
        article_store.store_articles(state["top_articles"], profile)
    except Exception as e:
        print(f"[warn] Failed to store articles in ChromaDB: {e}")
    return {"email_status": "success"}


def isolated_collector(source: str, collect):
    """A collector node that never fails the run: an exception in `collect(state)` is logged and recorded in
    state["source_errors"], and the source contributes no articles; the other collectors go on."""
    def node(state: DigestState) -> dict:
        try:
            return {"extra_articles": list(collect(state))}
        except llm_clients.MissingCredentials:
            raise
        except Exception as e:
            return {"extra_articles": [], "source_errors": [source_error(source, "collect", e)]}
    node.__name__ = f"collect_{source}"
    return node


COLLECTOR_SOURCES = ("hackernews",)  # one per collector node wired into modules.graph


def every_source_failed(result: dict) -> bool:
    """True when the run had nothing to work with: every collector failed, or every source that reached the
    shortlist failed there. Such a run is reported as failed, not as an empty day."""
    errors = result.get("source_errors", [])
    collect_failed = {e["source"] for e in errors if e["stage"] == "collect"}
    if set(COLLECTOR_SOURCES) <= collect_failed:
        return True
    shortlist_failed = {e["source"] for e in errors if e["stage"] == "shortlist"}
    screened = {a.origin for a in result.get("articles", [])}
    return bool(screened) and screened <= shortlist_failed


collect_hackernews = isolated_collector("hackernews", lambda state: hackernews.collect(
    state["hn_queries"], state["subject"], settings.COLLECTOR_MAX_AGE_DAYS, settings.HN_MIN_POINTS))


def merge_sources(state: DigestState) -> dict:
    """Join point for all collectors: de-duplicate by URL, resolve every link to its canonical URL (and
    de-duplicate again), swap bad links for direct ones."""
    pool = list(state["articles"]) + list(state["extra_articles"])
    by_url = {}
    for a in pool:
        by_url.setdefault(a.url, a)
    articles = list(by_url.values())

    resolved = link_utils.resolve_links([a.url for a in articles])
    canon, checked, seen = 0, [], set()
    for a in articles:
        status, final = resolved[a.url]
        url = link_utils.canonical_url(a.url, final)
        canon += url != a.url
        if url in seen:  # two redirects (or tracking variants) of one article: keep the first
            continue
        seen.add(url)
        checked.append(a.model_copy(update={"url": url, "link_status": status}))
    collapsed = len(articles) - len(checked)
    if canon or collapsed:
        print(f"[merge] {canon} URL(s) canonicalised, {collapsed} article(s) collapsed into a duplicate.")
    bad_before = sum(a.link_status != "ok" for a in checked)
    upgraded = article_store.upgrade_bad_links(checked)
    bad_after = sum(a.link_status != "ok" for a in upgraded)

    per_source = {o: sum(a.origin == o for a in upgraded) for o in sorted({a.origin for a in upgraded})}
    print(f"[merge] {len(upgraded)} articles by source: {per_source}")
    if bad_before:
        print(f"[merge] {bad_before} article(s) had a dead/unverifiable link; "
              f"{bad_before - bad_after} replaced by a direct link, {bad_after} remain.")
    failed = sorted({e["source"] for e in state.get("source_errors", []) if e["stage"] == "collect"})
    if failed:
        print(f"[merge] collectors that failed this run: {failed}")
    return {"articles": upgraded, "run_stats": {"merged": len(upgraded), "collect_failures": len(failed)}}


def no_content(state: DigestState) -> dict:
    return {"email_status": "no_content"}
