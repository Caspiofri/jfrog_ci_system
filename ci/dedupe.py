"""Dedupe for the CI run: normalized-URL matching (sqlite seen-URL store) and embedding similarity (ChromaDB)."""
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
_DROP_PARAMS = {"ref", "source"}  # plus every utm_* param

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
    return ({"full": 0, "partial": 1, "snippet": 2}[p.text_status], 0 if p.url_resolved else 1)


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

    def _history_matches(self, emb: np.ndarray) -> list[tuple[str, str, float] | None]:
        """Per packet: (earlier id, earlier run_id, similarity) of the closest earlier item within threshold."""
        col = self._collection()
        if col.count() == 0:
            return [None] * len(emb)
        res = col.query(query_embeddings=emb.tolist(), n_results=1, include=["distances", "metadatas"])
        out = []
        for ids, dists, metas in zip(res["ids"], res["distances"], res["metadatas"], strict=True):
            hit = ids and dists[0] <= 1 - self._threshold
            out.append((ids[0], metas[0].get("run_id", "?"), 1 - dists[0]) if hit else None)
        return out

    def dedupe(self, packets: list[Packet], use_history: bool = True) -> tuple[list[Packet], list[Drop]]:
        """History first (so a repeat of an old story never survives through its in-run twin), then within the run,
        visiting richer copies first so the copy kept has full text and a resolved URL when any copy does."""
        if not packets:
            return [], []
        order = sorted(range(len(packets)), key=lambda i: richness(packets[i]))
        packets = [packets[i] for i in order]
        emb = self._embed(packets)
        dropped: list[Drop] = []
        history = self._history_matches(emb) if use_history else [None] * len(packets)
        kept_idx: list[int] = []
        for i, p in enumerate(packets):
            if history[i]:
                old_id, old_run, sim = history[i]
                dropped.append((p, f"similar ({sim:.2f}) to item from run {old_run}", old_id))
                continue
            if kept_idx:
                sims = emb[kept_idx] @ emb[i]
                j = int(np.argmax(sims))
                if sims[j] >= self._threshold:
                    dropped.append((p, f"similar ({sims[j]:.2f}) to item in this run", packets[kept_idx[j]].id))
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
            metadatas=[{"run_id": p.run_id, "url": p.url, "title": p.title} for p in packets],
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
