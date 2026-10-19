#!/usr/bin/env bash
# Launch COUNT rollouts of one arm in Docker. Uses your provider key from .env, so this costs money unless the
# config's provider is `mock`.
#
#   deploysim/scripts/launch_ds.sh ARM COUNT --batch NAME [--max-concurrent N] [--dry-run] [key=value overrides ...]
#   e.g. deploysim/scripts/launch_ds.sh DS-D 20 --batch mymodel agent.model=<openrouter-model-id> agent.provider_preferences=null
#   ARM: any config in deploysim/configs/ (DS-G graded episode, DS-D deployment, DS-D-NOPUSH, ablations, ...)
#   Results go to results/deploysim/NAME/ARM; condition.batch=NAME is stamped into every run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
[ $# -ge 2 ] || { sed -n '2,8p' "$0"; exit 2; }
ARM="$1"; COUNT="$2"; shift 2
CFG="deploysim/configs/$ARM.yaml"
[ -f "$CFG" ] || { echo "unknown arm '$ARM' (no $CFG)"; ls deploysim/configs/*.yaml | sed 's#.*/##; s#\.yaml$##' | tr '\n' ' '; echo; exit 2; }
MAX_CONCURRENT=15; DRY_RUN=""; BATCH=""; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --max-concurrent) MAX_CONCURRENT="$2"; shift 2 ;;
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --batch) BATCH="$2"; shift 2 ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done
[ -n "$BATCH" ] || { echo "--batch NAME is required (e.g. --batch uptake)"; exit 2; }
PY="${PYTHON:-$REPO_ROOT/.venv/bin/python}"; [ -x "$PY" ] || PY=python3
RESULTS_DIR="$REPO_ROOT/results/deploysim/$BATCH/$ARM"
echo "arm=$ARM config=$CFG count=$COUNT batch=$BATCH max_concurrent=$MAX_CONCURRENT results=$RESULTS_DIR ${DRY_RUN:+(dry run)}"
"$PY" deploysim/scripts/run_ds.py "$CFG" --count "$COUNT" --max-concurrent "$MAX_CONCURRENT" \
  --results-dir "$RESULTS_DIR" --no-judge --overrides "condition.batch=$BATCH" $DRY_RUN ${EXTRA[@]+"${EXTRA[@]}"}
echo
echo "Next:  $PY deploysim/analysis/gate_check.py results/deploysim/$BATCH"
