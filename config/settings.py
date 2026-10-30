"""Central paths and environment loading. Every module imports locations from here, never from the cwd."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
EVALS_DIR = ROOT / "evals"

CHROMA_PATH = DATA_DIR / "chroma_db"
GOLDEN_SET_PATH = EVALS_DIR / "golden_set.json"

# The old funnel (python main.py) until the competitors config drives it (migration task 10). Each default can be
# overridden in .env; HN_QUERIES is comma-separated.
DEFAULT_SUBJECT = ("JFrog's competitors and the software supply chain: artifact management, package registries, "
                   "DevSecOps and CI/CD")
DEFAULT_AUDIENCE = "a competitive-intelligence analyst at JFrog"
DEFAULT_EXPERIENCE = "expert"
DEFAULT_TOP_K = 10
DEFAULT_HN_QUERIES = ["Sonatype", "Snyk", "Cloudsmith", "GitLab", "GitHub Advanced Security", "CodeArtifact",
                      "software supply chain"]
STORE_PROFILE = "jfrog_ci"  # article-store collection the funnel's dedupe checks against


def reader_profile() -> dict[str, str]:
    """Who the shortlist and ranker prompts write for (main.py and evals.rank_eval), from env or the defaults."""
    return {"subject": os.getenv("SUBJECT") or DEFAULT_SUBJECT,
            "target_audience": os.getenv("AUDIENCE") or DEFAULT_AUDIENCE,
            "experience_level": os.getenv("EXPERIENCE") or DEFAULT_EXPERIENCE}


HN_MIN_POINTS = 20
COLLECTOR_MAX_AGE_DAYS = 2

# Ranking pipeline: how many candidates per source reach the reader/ranker, and the minimum ranker score to be included.
SHORTLIST_QUOTA = {"hackernews": 6}
READ_MAX_CHARS = 6000
RANK_TEXT_CHARS = 6000  # characters of each article the ranker reads (was a hard-coded 2500)
SHORTLIST_TEASER_CHARS = 300  # characters of each article the title screen sees as a teaser (was none)
RANK_MIN_SCORE = 5
DEDUPE_NEAR_MISS_MIN = 0.70  # cosine similarity; dedupe matches at or above this are reported in the trace
SNIPPET_SCORE_CAP = 6  # an article we could only read a teaser of cannot score above this

# Model names (PRD D5), each overridable in .env. Gemini writes and ranks, on the API-key and the Vertex route alike
# (modules.llm_clients); gemini-3.6-flash is Ofri's Oct 30 choice. Rank baselines measured on 2.5-flash need a rerun.
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.6-flash"
# LLM judge models (Claude, so the judge is not the same family as the ranker and writer)
JUDGE_MODEL_DAILY = os.getenv("JUDGE_MODEL_DAILY") or "claude-haiku-4-5"  # per-run trace judge: cheap, every run
JUDGE_MODEL_EVAL = os.getenv("JUDGE_MODEL_EVAL") or "claude-sonnet-5-5"  # golden-set evals: stronger, on demand
