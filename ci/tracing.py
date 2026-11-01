"""LangSmith tracing switch (D48, D51). The one place that decides whether a run may send traces.

Tracing sends item text and predictions to a third party, so it is off in every eval run, whatever the environment
says, and off by default elsewhere: only the daily run may turn it on, with CI_LANGSMITH_TRACING=true (the global
LANGSMITH_* variables belong to the newsletter project and are never read as a yes). No ci module imports
langsmith except through here; tests/ci/test_tracing.py checks that.

Today no ci code sends traces at all (the D48 tracing of the daily run is not built); this module makes sure an eval
can't start sending them when it is.
"""
import os
from contextlib import contextmanager

ENV_VAR = "CI_LANGSMITH_TRACING"
DAILY = "daily"
EVAL_KINDS = frozenset({"eval", "eval_golden", "insights_eval"})
# Variables the langsmith / langchain SDKs read to switch tracing on by themselves
SDK_VARS = ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING")

_eval_depth = 0  # > 0 while an eval runs in this process


def enabled(kind: str, env: dict[str, str] | None = None) -> bool:
    """May a run of this kind send traces? Never during an eval; for the daily run only when CI_LANGSMITH_TRACING."""
    if _eval_depth or kind in EVAL_KINDS or kind != DAILY:
        return False
    value = os.environ.get("CI_LANGSMITH_TRACING", "") if env is None else env.get("CI_LANGSMITH_TRACING", "")
    return value.strip().lower() == "true"


@contextmanager
def off_for_eval():
    """Wrap every eval run: tracing.enabled() is False inside, and the SDK variables are forced off so no library
    can trace on its own. The environment is restored afterwards."""
    global _eval_depth
    saved = _env_force_off()
    _eval_depth += 1
    try:
        yield
    finally:
        _eval_depth -= 1
        _env_restore(saved=saved)


def _env_force_off() -> dict[str, str | None]:
    names = (*SDK_VARS, ENV_VAR)
    saved = {k: os.environ.get(k) for k in names}
    for k in names:
        os.environ[k] = "false"
    return saved


def _env_restore(saved: dict[str, str | None]) -> None:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
