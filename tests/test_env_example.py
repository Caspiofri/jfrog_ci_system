""".env.example lists exactly the variables the code reads: none missing, none stale."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = [ROOT / "main.py", *(p for d in ("config", "modules", "evals", "ci") for p in (ROOT / d).rglob("*.py"))]

# Read by a library, not by our code, and still part of the setup a user fills in.
LIBRARY_VARS = {
    "ANTHROPIC_API_KEY": "anthropic SDK",
    "LANGSMITH_TRACING": "langsmith SDK",
    "GOOGLE_APPLICATION_CREDENTIALS": "google-auth, on the Vertex AI route",
}
ENV_HELPER = re.compile(r"^_?env_")  # small helpers like main._env_list(name, ...) take the variable name first


def _is_os_env_read(node: ast.Call) -> bool:
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr == "getenv":
        return isinstance(f.value, ast.Name) and f.value.id == "os"
    return (isinstance(f, ast.Attribute) and f.attr == "get" and isinstance(f.value, ast.Attribute)
            and f.value.attr == "environ")


def _literal(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def code_env_reads() -> tuple[set[str], list[str]]:
    """(variable names read, places that read a computed name outside an _env_ helper)."""
    names, dynamic = set(), []
    for path in CODE:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        helpers = {n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and ENV_HELPER.match(n.name)}
        in_helper = {id(n) for h in helpers for n in ast.walk(h)}
        for node in ast.walk(tree):
            key = None
            if isinstance(node, ast.Call) and (_is_os_env_read(node) or (
                    isinstance(node.func, ast.Name) and ENV_HELPER.match(node.func.id))):
                key = node.args[0] if node.args else None
            elif (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
                  and node.value.attr == "environ"):
                key = node.slice
            if key is None:
                continue
            name = _literal(key)
            if name is not None:
                names.add(name)
            elif id(node) not in in_helper:
                dynamic.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return names, dynamic


def example_vars() -> list[str]:
    """Variables in .env.example, set (NAME=...) or shown commented out with their default (# NAME=...)."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return re.findall(r"^(?:# )?([A-Z][A-Z0-9_]*)=", text, re.M)


def test_the_scan_finds_the_known_reads():
    names, _ = code_env_reads()
    assert {"GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GEMINI_MODEL", "HN_QUERIES", "LANGSMITH_API_KEY"} <= names


def test_no_env_variable_name_is_computed():
    _, dynamic = code_env_reads()
    assert dynamic == [], "read env variables by literal name, so .env.example can be checked"


def test_every_variable_the_code_reads_is_in_env_example():
    names, _ = code_env_reads()
    assert names - set(example_vars()) == set()


def test_env_example_has_no_stale_or_duplicate_variables():
    listed = example_vars()
    names, _ = code_env_reads()
    assert set(listed) - names - set(LIBRARY_VARS) == set()
    assert len(listed) == len(set(listed))


def test_env_example_holds_no_secret_values():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in ("GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        assert re.search(rf"^{name}=$", text, re.M), f"{name} must be an empty placeholder"
