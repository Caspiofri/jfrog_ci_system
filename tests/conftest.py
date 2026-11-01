"""Suite-wide: FastAPI's TestClient sends `Host: testserver`; the servers' Host allowlist (ci.csrf, D59) accepts it
in tests only. tests/ci/test_csrf.py checks the real allowlist with explicit hosts."""
import os

os.environ.setdefault("CI_TRUSTED_HOSTS", "testserver")
