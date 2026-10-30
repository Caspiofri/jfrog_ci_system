"""Every module imports with no API keys or credentials, and importing builds no client (lazy init)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# every variable that could hand a client a key or credentials
SECRET_VARS = ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
               "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_GENAI_USE_VERTEXAI", "LANGSMITH_API_KEY",
               "LANGCHAIN_API_KEY", "CLOUDSDK_CONFIG")

# Runs in a fresh interpreter: .env loading is switched off (a developer's .env would hand out keys), then every
# module of the three packages is imported. Modules named __main__ are skipped, since importing one runs it.
SCRIPT = """
import importlib, pkgutil, sys
import dotenv
dotenv.load_dotenv = lambda *a, **k: False

failed = []
names = []
for pkg in ("modules", "evals", "ci"):
    mod = importlib.import_module(pkg)
    names.append(pkg)
    names += [m.name for m in pkgutil.walk_packages(mod.__path__, pkg + ".") if not m.name.endswith("__main__")]
for name in names:
    try:
        importlib.import_module(name)
    except Exception as e:
        failed.append(f"{name}: {type(e).__name__}: {e}")

from modules import article_store, llm_clients
built = [f.__name__ for f in (llm_clients.gemini_client, llm_clients.anthropic_client, llm_clients.langsmith_client,
                              article_store._client, article_store._embed_fn) if f.cache_info().currsize]
print("IMPORTED", len(names))
for line in failed:
    print("FAILED", line)
for name in built:
    print("BUILT", name)
sys.exit(1 if failed or built else 0)
"""


def test_every_module_imports_without_keys_and_builds_no_client(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in SECRET_VARS}
    env["HOME"] = str(tmp_path)  # no gcloud application-default credentials from the real home
    proc = subprocess.run([sys.executable, "-W", "error", "-c", SCRIPT], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    imported = int(next(line.split()[1] for line in proc.stdout.splitlines() if line.startswith("IMPORTED")))
    assert imported > 30, out  # the walk really found the packages
