#!/usr/bin/env bash
# Cron entry for the daily CI run (python -m ci.daily). Crontab line, on a host whose clock is Asia/Jerusalem:
#   0 6 * * * /path/to/agent_backbone/ci/daily_cron.sh
# Appends the whole run to output/logs/ci_daily.log between a start line and an end line that carries the exit code;
# a non-zero exit is logged as FAILED (1, 2) or DEGRADED (3) and returned to cron.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/output/logs/ci_daily.log"
mkdir -p "$(dirname "$LOG")"
{
  echo "=== $(date -Iseconds) start ci.daily"
  cd "$ROOT" && "$ROOT/.venv/bin/python" -m ci.daily "$@"
  status=$?
  case $status in
    0) label="ok" ;;
    3) label="DEGRADED" ;;
    *) label="FAILED" ;;
  esac
  echo "=== $(date -Iseconds) end ci.daily: $label (exit $status)"
} >>"$LOG" 2>&1
exit "$status"
