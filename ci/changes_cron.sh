#!/usr/bin/env bash
# Cron entry for daily change detection (python -m ci.changes --live), chained after the 06:00 collection:
#   0 6 * * * /path/to/agent_backbone/ci/daily_cron.sh; /path/to/agent_backbone/ci/changes_cron.sh
# Appends the run to output/logs/ci_changes.log between a start line and an end line with the exit code (FAILED on
# 1 = every page failed, or 2 = another change-detection run holds the lock), and logs how many cells changed, so a
# changed head-to-head cell (D22 needs one in the demo) is visible the morning it appears.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/output/logs/ci_changes.log"
mkdir -p "$(dirname "$LOG")"
{
  echo "=== $(date -Iseconds) start ci.changes --live"
  cd "$ROOT" && "$ROOT/.venv/bin/python" -m ci.changes --live "$@"
  status=$?
  if [ "$status" -eq 0 ]; then
    label="ok"
    found=$("$ROOT/.venv/bin/python" -c 'import json,pathlib; p=max(pathlib.Path("output/changes").glob("*.report.json"), key=lambda p: p.stat().st_mtime); r=json.loads(p.read_text()); print(r.get("changes", 0))' 2>/dev/null || echo "?")
    echo "=== changes found: ${found} (changed head-to-head cells await review)"
  else
    label="FAILED"
  fi
  echo "=== $(date -Iseconds) end ci.changes: $label (exit $status)"
} >>"$LOG" 2>&1
exit "$status"
