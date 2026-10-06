#!/usr/bin/env bash
# Launch COUNT rollouts of one DS arm locally in Docker. PAID: Olivia launches these herself (CLAUDE.md).
#
#   deploysim/scripts/launch_ds.sh ARM COUNT --batch NAME [--max-concurrent N] [--dry-run] [extra run.py args]
#   ARM: DS-G | DS-D | DS-G-NONOTE
#   --batch NAME is required: results go to results/deploysim/NAME/ARM and condition.batch=NAME is
#   stamped into every run, so the uptake batch and any later batch are never pooled.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
[ $# -ge 2 ] || { sed -n '2,8p' "$0"; exit 2; }
ARM="$1"; COUNT="$2"; shift 2
case "$ARM" in
  DS-G|DS-D|DS-G-NONOTE|DS-D-NOPUSH|DS-D-NOPRIOR|DS-D-BAREREPO|DS-D-EXAMTEXT|DS-D-AGENTSYS|DS-G+REPO|DS-G+REPO+PUSH|DS-G+REPO+PUSH+SYS) CFG="deploysim/configs/$ARM.yaml" ;;
  *) echo "unknown arm '$ARM'"; exit 2 ;;
esac
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
