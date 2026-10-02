#!/usr/bin/env bash
# Launch COUNT rollouts of one experimental arm locally in Docker.
#
#   scripts/launch_arm.sh ARM COUNT [--max-concurrent N] [--dry-run] [extra scripts/run.py args]
#
#   ARM   one of N0 G0 G1 U0 U1 (or a config stem: N0_replication, G_noO, G_O, U_noO, U_O)
#   COUNT number of rollouts
#
# Results go to results/<model-slug>/<condition_id>/precommit_hook/<model>/<timestamp>/run-N/ and the
# matching Docent upload command is printed at the end. --dry-run resolves the config and
# prints the plan without building or launching anything (no cost).
#
# --max-concurrent defaults to 15. Measured 2026-10-01 against the pinned endpoint (OpenRouter ->
# AkashML bf16, GPT-OSS-120B): bursts of 12 and 24 simultaneous requests all succeeded (24/24, sub-second,
# all served by AkashML, no 429). OpenRouter documents no per-key request rate for paid models; limits come
# from the upstream provider. 15 stays well inside the tested burst while leaving headroom for late-run
# prompts of ~100k tokens, and OpenRouterProvider retries a 429 eight times with up to 60 s backoff, so a
# transient limit costs time, not money. Concurrency never changes the token bill; it only sets wall-clock
# time and 429 risk. (The earlier default of 8 was sized for Fireworks' per-model limits.)
#
# THIS SCRIPT LAUNCHES PAID ROLLOUTS. Olivia / her partner run it; the build agent never does.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

usage() { sed -n '2,20p' "$0"; exit 2; }
[ $# -ge 2 ] || usage
ARM="$1"; COUNT="$2"; shift 2

case "$ARM" in
  N0|N0_replication) CFG=configs/precommit_hook/N0_replication.yaml; CID=N0 ;;
  G0|G_noO)          CFG=configs/precommit_hook/G_noO.yaml;          CID=G0 ;;
  G1|G_O)            CFG=configs/precommit_hook/G_O.yaml;            CID=G1 ;;
  U0|U_noO)          CFG=configs/precommit_hook/U_noO.yaml;          CID=U0 ;;
  U1|U_O)            CFG=configs/precommit_hook/U_O.yaml;            CID=U1 ;;
  *) echo "unknown arm '$ARM' (N0 G0 G1 U0 U1)"; exit 2 ;;
esac

MAX_CONCURRENT=15
DRY_RUN=""
EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --max-concurrent) MAX_CONCURRENT="$2"; shift 2 ;;
    --max-concurrent=*) MAX_CONCURRENT="${1#*=}"; shift ;;
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then PY="$REPO_ROOT/.venv/bin/python"; else PY="python3"; fi
fi

# One results tree per model (results/<model-slug>/<ARM>/...), so runs of different models never
# share an arm directory and summarize.py/cost.py can be pointed at one model at a time.
MODEL="$(sed -n 's/^  model: //p' "$CFG" | head -1)"
MODEL_SLUG="$(printf '%s' "$MODEL" | tr '/:' '--')"
RESULTS_ROOT="$REPO_ROOT/results/$MODEL_SLUG"
RESULTS_DIR="$RESULTS_ROOT/$CID"
PROVIDER="$(sed -n 's/^  provider: //p' "$CFG" | head -1)"
case "$PROVIDER" in
  openrouter) KEY_VAR=OPENROUTER_API_KEY ;;
  fireworks|fireworks_completions) KEY_VAR=FIREWORKS_API_KEY ;;
  *) KEY_VAR="" ;;
esac
if [ -z "$DRY_RUN" ] && [ -n "$KEY_VAR" ] && { [ ! -f .env ] || ! grep -q "^$KEY_VAR=.\+" .env; }; then
  echo "WARNING: .env has no $KEY_VAR (agent.provider: $PROVIDER); the rollouts will fail at provider construction." >&2
fi

echo "arm=$CID config=$CFG count=$COUNT max_concurrent=$MAX_CONCURRENT results=$RESULTS_DIR ${DRY_RUN:+(dry run)}"
"$PY" scripts/run.py "$CFG" --count "$COUNT" --max-concurrent "$MAX_CONCURRENT" --results-dir "$RESULTS_DIR" \
  --no-judge $DRY_RUN ${EXTRA[@]+"${EXTRA[@]}"}

echo
echo "Next:"
echo "  $PY scripts/upload_to_docent.py $RESULTS_DIR            # upload to DOCENT_COLLECTION_ID (idempotent)"
echo "  $PY analysis/summarize.py $RESULTS_ROOT          # per-arm table + 2x2 contrasts (this model only)"
echo "  $PY analysis/cost.py $RESULTS_ROOT               # per-run and per-arm cost"
