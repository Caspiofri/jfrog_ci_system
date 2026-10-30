import operator
from typing import Annotated, TypedDict

from modules.models import Article, NewsletterData


class DigestState(TypedDict):
    subject: str
    target_audience: str
    experience_level: str
    digest_name: str  # names the article-store collection that dedupe checks against
    top_k: int
    hn_queries: list[str]
    articles: list[Article]
    candidates: list[Article]  # per-source shortlist, read and ranked into top_articles
    # written in parallel by the collector nodes; combined with `articles` in merge_sources
    extra_articles: Annotated[list[Article], operator.add]
    top_articles: list[Article]
    # evidence for the trace; each node after merge writes {**state.get("run_stats", {}), ...}
    run_stats: dict[str, float]
    dedupe_drops: list[dict]
    rank_scores: list[dict]
    # one {"source", "stage", "error"} per source that failed in a collector or the shortlist (the run went on)
    source_errors: Annotated[list[dict], operator.add]
    newsletter_data: NewsletterData | None  # written by summraize, which is not wired into the graph
    email_status: str  # "success" once the picks are stored, "no_content" on an early exit
