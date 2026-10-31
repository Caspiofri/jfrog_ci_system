"""Dedupe for the CI run: normalized-URL matching (sqlite seen-URL store) and embedding similarity (ChromaDB)."""
import logging
import re
import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np

from ci.packet import Packet

SIMILARITY_THRESHOLD = 0.82  # cosine similarity; chroma's cosine distance = 1 - similarity
MAX_DISTANCE = 1 - SIMILARITY_THRESHOLD
EMBED_TEXT_CHARS = 300
COLLECTION = "ci_items"
# D38 CVE veto: two items that both name CVE IDs with none in common are different events (and never duplicates of
# each other), however similar the text. Items naming no CVE behave as before. The IDs are read from the title and the
# whole stored text (the 300-char embedding text often misses them).
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
HISTORY_CANDIDATES = 5  # nearest earlier items checked, so a vetoed nearest one doesn't hide an allowed match
_DROP_PARAMS = {"ref", "source"}  # plus every utm_* param

# which copy of a story is kept: full text first; junk (the fetched page was not the article) holds less than a
# teaser, so it ranks below snippet
STATUS_RANK = {"full": 0, "partial": 1, "snippet": 2, "junk": 3}
UNKNOWN_STATUS_RANK = max(STATUS_RANK.values()) + 1
log = logging.getLogger(__name__)

EmbedFn = Callable[[list[str]], list]
Drop = tuple[Packet, str, str]  # (packet, reason, duplicate_of id)


def normalize_url(url: str) -> str:
    """Lowercase scheme and host, drop the fragment, tracking params (utm_*, ref, source) and the trailing slash."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in _DROP_PARAMS]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def url_keys(p: Packet) -> set[str]:
    """A packet matches another if either its resolved or its original URL does."""
    return {normalize_url(p.url), normalize_url(p.original_url or p.url)}


def richness(p: Packet) -> tuple[int, int]:
    """Sort key: full text first, then resolved URL."""
    rank = STATUS_RANK.get(p.text_status)
    if rank is None:  # a status added later must never disable dedupe (a KeyError here once kept every item)
        log.warning("unknown text_status %r on %s; ranked lowest for dedupe", p.text_status, p.id or p.url)
        rank = UNKNOWN_STATUS_RANK
    return (rank, 0 if p.url_resolved else 1)


class SeenUrls:
    """Persistent normalized URL -> packet id, so later runs drop stories already collected."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, id TEXT, run_id TEXT)")

    def lookup(self, url: str) -> tuple[str, str] | None:
        """(packet id, run_id) of the earlier item with this normalized URL, or None."""
        return self._db.execute("SELECT id, run_id FROM seen WHERE url = ?", (url,)).fetchone()

    def add(self, packets: Iterable[Packet]) -> None:
        rows = [(k, p.id, p.run_id) for p in packets for k in url_keys(p)]
        with self._db:
            self._db.executemany("INSERT OR IGNORE INTO seen VALUES (?, ?, ?)", rows)

    def close(self) -> None:
        self._db.close()


def url_dedupe(packets: list[Packet], seen: SeenUrls | None) -> tuple[list[Packet], list[Drop]]:
    """Drop packets whose URL repeats within the run or (when seen is given) an earlier run; resolved copies win."""
    kept, dropped, by_key = [], [], {}
    for p in sorted(packets, key=lambda p: not p.url_resolved):  # stable: resolved copies first
        keys = url_keys(p)
        dup = next((by_key[k] for k in keys if k in by_key), None)
        if dup:
            dropped.append((p, "same URL in this run", dup))
            continue
        earlier = next((hit for k in keys if seen and (hit := seen.lookup(k))), None)
        if earlier:
            dropped.append((p, f"URL seen in run {earlier[1]}", earlier[0]))
            continue
        by_key.update(dict.fromkeys(keys, p.id))
        kept.append(p)
    return kept, dropped


def cve_ids(text: str) -> frozenset[str]:
    return frozenset(m.upper() for m in CVE_RE.findall(text or ""))


def packet_cves(p: Packet) -> frozenset[str]:
    """CVE IDs in the title and the stored text (the teaser when the page text is junk, as content_text does)."""
    return cve_ids(f"{p.title}\n{p.teaser if p.text_status == 'junk' else p.text}")


def cve_veto(a: frozenset[str], b: frozenset[str]) -> bool:
    """True when both name CVE IDs and share none: never the same event (D38)."""
    return bool(a) and bool(b) and not (a & b)


def embed_text(p: Packet) -> str:
    return f"{p.title}. {p.text[:EMBED_TEXT_CHARS]}"


def default_embedding_fn() -> EmbedFn:
    """chromadb's bundled ONNX all-MiniLM-L6-v2 (no torch); the model downloads once on first use."""
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    return DefaultEmbeddingFunction()


class EmbeddingDeduper:
    """Near-duplicate stories by cosine similarity of title + teaser, within the run and against earlier runs."""

    def __init__(self, path: Path, embed_fn: EmbedFn | None = None, threshold: float = SIMILARITY_THRESHOLD):
        self._path = path
        self._embed_fn = embed_fn
        self._threshold = threshold
        self._col = None
        self._vectors: dict[str, np.ndarray] = {}  # packet id -> normalized embedding, reused by remember()

    def _collection(self):
        if self._col is None:  # lazy: chromadb is only touched when a run reaches this stage
            import chromadb
            from chromadb.config import Settings
            client = chromadb.PersistentClient(path=str(self._path), settings=Settings(anonymized_telemetry=False))
            # embeddings are always passed in, so the collection carries no embedding function of its own
            self._col = client.get_or_create_collection(
                COLLECTION, embedding_function=None, configuration={"hnsw": {"space": "cosine"}})
        return self._col

    def _embed(self, packets: list[Packet]) -> np.ndarray:
        if self._embed_fn is None:
            self._embed_fn = default_embedding_fn()
        emb = np.array(self._embed_fn([embed_text(p) for p in packets]), dtype=float)
        emb /= np.maximum(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9)
        self._vectors.update(zip((p.id for p in packets), emb, strict=True))
        return emb

    def _history_matches(self, emb: np.ndarray, cves: list[frozenset[str]]) -> list[tuple[str, str, float] | None]:
        """Per packet: (earlier id, earlier run_id, similarity) of the closest earlier item within threshold that the
        CVE veto allows. An earlier item stored before D38 has no "cves" metadata; its IDs are then read from the
        stored document (title + 300 chars), so run backfill_cves once to give old history the full-text IDs."""
        col = self._collection()
        count = col.count()
        if count == 0:
            return [None] * len(emb)
        res = col.query(query_embeddings=emb.tolist(), n_results=min(HISTORY_CANDIDATES, count),
                        include=["distances", "metadatas", "documents"])
        out = []
        for mine, ids, dists, metas, docs in zip(cves, res["ids"], res["distances"], res["metadatas"],
                                                 res["documents"], strict=True):
            hit = None
            for old_id, dist, meta, doc in zip(ids, dists, metas, docs, strict=True):
                if dist > 1 - self._threshold:
                    break
                theirs = frozenset(filter(None, meta["cves"].split(","))) if "cves" in meta else cve_ids(doc)
                if cve_veto(mine, theirs):
                    continue
                hit = (old_id, meta.get("run_id", "?"), 1 - dist)
                break
            out.append(hit)
        return out

    def backfill_cves(self, cves_by_id: dict[str, frozenset[str]]) -> int:
        """Set the "cves" metadata of earlier items (stored before D38) from their full text; returns how many."""
        col = self._collection()
        known = col.get(ids=list(cves_by_id), include=["metadatas"])
        if not known["ids"]:
            return 0
        col.update(ids=known["ids"], metadatas=[{**m, "cves": ",".join(sorted(cves_by_id[i]))}
                                                for i, m in zip(known["ids"], known["metadatas"], strict=True)])
        return len(known["ids"])

    def dedupe(self, packets: list[Packet], use_history: bool = True) -> tuple[list[Packet], list[Drop]]:
        """History first (so a repeat of an old story never survives through its in-run twin), then within the run,
        visiting richer copies first so the copy kept has full text and a resolved URL when any copy does."""
        if not packets:
            return [], []
        order = sorted(range(len(packets)), key=lambda i: richness(packets[i]))
        packets = [packets[i] for i in order]
        emb = self._embed(packets)
        cves = [packet_cves(p) for p in packets]
        dropped: list[Drop] = []
        history = self._history_matches(emb, cves) if use_history else [None] * len(packets)
        kept_idx: list[int] = []
        for i, p in enumerate(packets):
            if history[i]:
                old_id, old_run, sim = history[i]
                dropped.append((p, f"similar ({sim:.2f}) to item from run {old_run}", old_id))
                continue
            if kept_idx:
                sims = emb[kept_idx] @ emb[i]
                # the most similar kept item the CVE veto allows (D38)
                match = next((j for j in np.argsort(-sims) if sims[j] >= self._threshold
                              and not cve_veto(cves[i], cves[kept_idx[j]])), None)
                if match is not None:
                    dropped.append((p, f"similar ({sims[match]:.2f}) to item in this run",
                                    packets[kept_idx[match]].id))
                    continue
            kept_idx.append(i)
        return [packets[i] for i in kept_idx], dropped

    def remember(self, packets: list[Packet]) -> None:
        """Store survivors so later runs dedupe against them; call only after the run succeeded."""
        if not packets:
            return
        missing = [p for p in packets if p.id not in self._vectors]
        if missing:
            self._embed(missing)
        self._collection().upsert(
            ids=[p.id for p in packets],
            embeddings=[self._vectors[p.id].tolist() for p in packets],
            documents=[embed_text(p) for p in packets],
            metadatas=[{"run_id": p.run_id, "url": p.url, "title": p.title, "cves": ",".join(sorted(packet_cves(p)))}
                       for p in packets],
        )


def resolve_duplicates(drops: list[Drop], kept_ids: set[str]) -> list[Drop]:
    """Point duplicate_of at a survivor: A -> B where B was itself dropped as a dup of C becomes A -> C.
    An id that is neither kept nor dropped in this run belongs to an earlier run and is left as is."""
    parent = {p.id: dup for p, _, dup in drops if p.id not in kept_ids}
    out = []
    for p, reason, dup in drops:
        hops = set()
        while dup not in kept_ids and dup in parent and dup not in hops:
            hops.add(dup)
            dup = parent[dup]
        out.append((p, reason, dup))
    return out
