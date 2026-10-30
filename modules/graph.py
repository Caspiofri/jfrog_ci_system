from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from modules import nodes
from modules.state import DigestState


def check_merge(state: DigestState) -> str:
    """Exit early if no collector found anything."""
    if len(state["articles"]) == 0:
        return "no_content"
    return "dedupe"


def check_dedupe(state: DigestState) -> str:
    """Exit early if everything collected was already picked in an earlier run."""
    if len(state["articles"]) == 0:
        return "no_content"
    return "shortlist"


def check_rank(state: DigestState) -> str:
    """Exit early if the ranker found nothing worth keeping."""
    if len(state["top_articles"]) == 0:
        return "no_content"
    return "store_picks"


# collectors -> merge -> dedupe -> shortlist -> reader -> rank. summraize stays in modules.nodes (its ID-citation
# logic is reused for Brief insights later) but is not wired into the graph.
graph_builder = StateGraph(DigestState)
graph_builder.add_node("collect_hackernews", nodes.collect_hackernews)
graph_builder.add_node("merge", nodes.merge_sources)
graph_builder.add_node("dedupe", nodes.dedupe_articles)
graph_builder.add_node("shortlist", nodes.shortlist_articles)
graph_builder.add_node("reader", nodes.read_articles)
graph_builder.add_node("rank", nodes.rank_articles)
graph_builder.add_node("store_picks", nodes.store_picks)
graph_builder.add_node("no_content", nodes.no_content)

# Collectors run in parallel from START and join in `merge`.
graph_builder.add_edge(START, "collect_hackernews")
graph_builder.add_edge(["collect_hackernews"], "merge")
graph_builder.add_conditional_edges("merge", check_merge, ["dedupe", "no_content"])
graph_builder.add_conditional_edges("dedupe", check_dedupe, ["shortlist", "no_content"])
graph_builder.add_edge("shortlist", "reader")
graph_builder.add_edge("reader", "rank")
graph_builder.add_conditional_edges("rank", check_rank, ["store_picks", "no_content"])
graph_builder.add_edge("store_picks", END)
graph_builder.add_edge("no_content", END)

graph = graph_builder.compile(checkpointer=InMemorySaver())
