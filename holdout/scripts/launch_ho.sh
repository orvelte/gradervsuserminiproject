#!/usr/bin/env bash
# Launch COUNT holdout rollouts of one condition in Docker. Uses your provider key from .env: costs money unless
# the config's provider is mock.
#   holdout/scripts/launch_ho.sh COND COUNT --batch NAME [--max-concurrent N] [--dry-run] [key=value overrides ...]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
COND="$1"; COUNT="$2"; shift 2
CFG="holdout/configs/$COND.yaml"
[ -f "$CFG" ] || { echo "no config $CFG; available:"; ls holdout/configs | sed 's/.yaml$//'; exit 2; }
MAX_CONCURRENT=15; DRY_RUN=""; BATCH=""; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --batch) BATCH="$2"; shift 2 ;;
    --max-concurrent) MAX_CONCURRENT="$2"; shift 2 ;;
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done
[ -n "$BATCH" ] || { echo "--batch NAME is required"; exit 2; }
RESULTS_DIR="$REPO_ROOT/results/holdout/$BATCH/$(basename "$COND")"
echo "cond=$COND count=$COUNT batch=$BATCH max_concurrent=$MAX_CONCURRENT results=$RESULTS_DIR ${DRY_RUN:+(dry run)}"
"$PY" holdout/scripts/run_ho.py "$CFG" --count "$COUNT" --max-concurrent "$MAX_CONCURRENT" \
  --results-dir "$RESULTS_DIR" --no-judge --overrides "condition.batch=$BATCH" $DRY_RUN ${EXTRA[@]+"${EXTRA[@]}"}
