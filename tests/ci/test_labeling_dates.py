"""The labeling page's fmtDate, run under node: a day-only date shows its UTC day and no made-up time."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).parents[2] / "ci" / "labeling" / "page.html"
NODE = shutil.which("node")  # resolved once, from the caller's PATH (nvm installs it outside /usr/bin)
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def fmt_date(value, day_only: bool, tz: str = "America/Los_Angeles") -> str:
    source = re.search(r"^function fmtDate\(.*?^}", PAGE.read_text(encoding="utf-8"), re.S | re.M).group(0)
    script = f"{source}\nprocess.stdout.write(fmtDate({json.dumps(value)}, {json.dumps(day_only)}));"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True, timeout=30,
                         env={"TZ": tz, "LANG": "en_US.UTF-8", "PATH": "/usr/bin:/bin"})
    return out.stdout


def test_day_only_shows_the_utc_day_without_a_time():
    # 00:30 UTC on the 28th is still the 27th in Los Angeles; the listing said the 28th
    shown = fmt_date("2026-10-28T00:30:00+00:00", True)
    assert "28" in shown and ":" not in shown


def test_exact_time_keeps_the_local_time():
    shown = fmt_date("2026-10-28T16:30:00+00:00", False)
    assert "28" in shown and ":" in shown


def test_missing_date():
    assert fmt_date(None, True) == "no date"
