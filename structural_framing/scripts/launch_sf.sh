#!/usr/bin/env bash
# Launch COUNT rollouts of one SF1 arm locally in Docker (paid; authorised only within sfbuildtask.md's stages).
#
#   structural_framing/scripts/launch_sf.sh ARM COUNT [--batch NAME] [--max-concurrent N] [--dry-run] [extra run.py args]
#   ARM: SF1-G-LAX | SF1-C-LAX | SF1-G-STRICT | SF1-C-STRICT | SF1-C-LAX-NOHORIZON | SF1-G-LAX-PRIYACHECK
#   --batch NAME: a fresh, separately analysed batch (PREREG.md): results go to results/structural_framing/batches/NAME/ARM
#                 and condition.batch=NAME is stamped into every run (never pooled with the pilot).
#
# Results: results/structural_framing/<ARM>/precommit_hook_sf/<model>/<timestamp>/run-N/ (gitignored).
# Concurrency default 15: the value measured for the pinned AkashML endpoint in the original 2x2.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
[ $# -ge 2 ] || { sed -n '2,8p' "$0"; exit 2; }
ARM="$1"; COUNT="$2"; shift 2
case "$ARM" in
  SF1-G-LAX|SF1-C-LAX|SF1-G-STRICT|SF1-C-STRICT|SF1-C-LAX-NOHORIZON|SF1-G-LAX-PRIYACHECK) CFG="structural_framing/configs/$ARM.yaml" ;;
  *) echo "unknown arm '$ARM'"; exit 2 ;;
esac
MAX_CONCURRENT=15; DRY_RUN=""; BATCH=""; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --max-concurrent) MAX_CONCURRENT="$2"; shift 2 ;;
    --max-concurrent=*) MAX_CONCURRENT="${1#*=}"; shift ;;
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --batch) BATCH="$2"; shift 2 ;;
    --batch=*) BATCH="${1#*=}"; shift ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done
PY="${PYTHON:-$REPO_ROOT/.venv/bin/python}"; [ -x "$PY" ] || PY=python3
if [ -z "$DRY_RUN" ] && { [ ! -f .env ] || ! grep -q '^OPENROUTER_API_KEY=.\+' .env; }; then
  echo "WARNING: .env has no OPENROUTER_API_KEY; the rollouts will fail at provider construction." >&2
fi
RESULTS_DIR="$REPO_ROOT/results/structural_framing/$ARM"
if [ -n "$BATCH" ]; then RESULTS_DIR="$REPO_ROOT/results/structural_framing/batches/$BATCH/$ARM"; EXTRA+=("--overrides" "condition.batch=$BATCH"); fi
echo "arm=$ARM config=$CFG count=$COUNT batch=${BATCH:-pilot} max_concurrent=$MAX_CONCURRENT results=$RESULTS_DIR ${DRY_RUN:+(dry run)}"
"$PY" structural_framing/scripts/run_sf.py "$CFG" --count "$COUNT" --max-concurrent "$MAX_CONCURRENT" \
  --results-dir "$RESULTS_DIR" --no-judge $DRY_RUN ${EXTRA[@]+"${EXTRA[@]}"}
echo
echo "Next:"
echo "  $PY structural_framing/analysis/sf_metrics.py $RESULTS_DIR     # per-run SF1 metrics -> final/sf_metrics.json"
echo "  $PY structural_framing/scripts/upload_sf.py $RESULTS_DIR          # Docent (idempotent; --dry-run to validate)"
echo "  $PY structural_framing/analysis/sf_summary.py                      # per-arm table + G-LAX vs C-LAX contrast"
