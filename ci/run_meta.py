"""What a run or an eval ran with (D53, D54): the three fingerprints, the capability sheet's hash, the model names and
call settings, one combined fingerprint over all of those, and the git commit of the code.

Not frozen and in no fingerprint itself: it only records. The three fingerprints stay exactly as they are
(classify_rank = ci.eval_golden.fingerprint, lens, insights); the capability sheet and the model feed the lens, the
insights and the eval but are in none of them, so `combined` is the one value to compare two records by. The commit
says which code ran; `dirty` is true when tracked files differed from that commit (untracked files are ignored).
Every field is best-effort: a value that can't be read is None, never an exception.
"""
import hashlib
import json
import logging
import subprocess
from pathlib import Path

from ci import eval_golden, insights, lens, llm
from modules import llm_clients

log = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
SHEET_PATH = lens.SHEET_PATH  # config/jfrog_capabilities.md
SHA_CHARS = 12
# Every deliberate fingerprint change, old -> new, with the evidence for it; copied into every record so a report on
# the new value can be traced to the old one. Not part of `combined`.
FINGERPRINT_CHANGES = (
    {"fingerprint": "insights", "old": "9ec366312774", "new": "e99d23e4edcf", "date": "2026-11-01",
     "decision": "D51 (2)", "change": "insights prompt: item_text tags defanged in any case, article text marked as "
     "data (a prompt change, reported as hardening, not as an improvement)"},
    {"fingerprint": "classify_rank", "old": "c837f4fdaf70", "new": "99b79890ceea", "date": "2026-11-01",
     "decision": "D51 (1)", "change": "ci.classify.delimited_items defangs item_text tags in any case (shared by "
     "classify, rank and lens); no prompt wording or rule changed",
     "prompt_diff": {"method": "every classify, rank and lens prompt rendered with the old and the new code, "
                               "one item at a time and as one batch per set; golden items built by "
                               "eval_golden.rebuild_item",
                     "store_items": 351, "golden_rows": 107, "prompts_compared": 3 * (351 + 107),
                     "differences": 0, "batches_identical": True, "control_poisoned_prompt_differs": True},
     "lens_unchanged": "1692c04ba7df"},
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:SHA_CHARS]


def sheet_sha(path: Path = SHEET_PATH) -> str | None:
    try:
        return _sha(path.read_bytes())
    except OSError:
        return None


def call_settings() -> dict:
    """How every Gemini call is made (ci.llm.GeminiLLM and the shared client factory)."""
    return {"temperature": llm.TEMPERATURE, "response_mime_type": llm.RESPONSE_MIME_TYPE,
            "max_attempts": llm.MAX_ATTEMPTS, "request_timeout_s": llm_clients.GEMINI_TIMEOUT_S}


def models(model: str | None = None) -> dict:
    return {"llm": model or llm.model_name(), "embedding": eval_golden.EMBED_MODEL_TAG}


def git_commit(repo: Path = REPO) -> dict:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=5,
                              check=True).stdout.strip()
    try:
        sha = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("git commit not recorded: %s", e)
        return {"sha": None, "dirty": None}
    return {"sha": sha, "dirty": dirty}


def combine(fingerprints: dict, sheet: str | None, model_names: dict, settings: dict) -> str:
    parts = {"fingerprints": fingerprints, "sheet_sha": sheet, "models": model_names, "call_settings": settings}
    return _sha(json.dumps(parts, sort_keys=True).encode())


def collect(*, fingerprints: dict | None = None, model: str | None = None, cfg=None, repo: Path = REPO,
            sheet_path: Path = SHEET_PATH) -> dict:
    """The metadata block. fingerprints: the run's own, when it has them; missing ones are computed here."""
    fps = dict(fingerprints or {})
    for key, fn in (("classify_rank", lambda: eval_golden.fingerprint(cfg)), ("lens", lens.fingerprint),
                    ("insights", insights.fingerprint)):
        if not fps.get(key):
            try:
                fps[key] = fn()
            except Exception as e:  # a record must never take the run down
                log.warning("fingerprint %s not recorded: %s", key, e)
                fps[key] = None
    fps = {k: fps[k] for k in ("classify_rank", "lens", "insights")}
    sheet, names, settings = sheet_sha(sheet_path), models(model), call_settings()
    return {"fingerprints": fps, "sheet_sha": sheet, "models": names, "call_settings": settings,
            "combined": combine(fps, sheet, names, settings), "commit": git_commit(repo),
            "fingerprint_changes": list(FINGERPRINT_CHANGES)}


def safe_collect(**kw) -> dict:
    """collect(), or {"error": ...} if even that fails: the metadata never fails the run that records it."""
    try:
        return collect(**kw)
    except Exception as e:
        log.exception("run metadata not collected")
        return {"error": f"{type(e).__name__}: {e}"}
