#!/usr/bin/env bash
# Run agent episodes on a GCP VM instead of this laptop (the sandboxes are Docker containers; the model is remote).
#
#   bash internals/cloudvm.sh start | stop | status          # PAID while running (n2-standard-32, ~$1.55/hr); stopped = disk only
#   bash internals/cloudvm.sh push                           # sync the code (+ .git; never .env, results/ or .venv)
#   bash internals/cloudvm.sh run NAME CMD...                # run CMD detached in ~/repo on the VM; log in ~/logs/NAME.log
#   bash internals/cloudvm.sh log NAME                       # tail of that log and whether it has finished
#   bash internals/cloudvm.sh pull [results/holdout/BATCH]   # copy results back (default: all of results/holdout)
#   bash internals/cloudvm.sh ssh                            # interactive shell
# Provider keys are not copied by this script (CLAUDE.md); see `keys` below for how they reach the VM.
set -euo pipefail
export PATH="$HOME/google-cloud-sdk/bin:$PATH"
P=gradervsuser-runs-1023; Z=us-central1-a; VM=runner-1
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/.." && pwd)"
G=(gcloud compute --project "$P"); S=("${G[@]}" ssh "$VM" --zone "$Z" --quiet)
TMP="${TMPDIR:-/tmp}"

case "${1:-}" in
  start) "${G[@]}" instances start "$VM" --zone "$Z" --quiet; for i in $(seq 1 30); do "${S[@]}" --command "docker info >/dev/null 2>&1" 2>/dev/null && break; sleep 10; done; echo "VM up" ;;
  stop) "${G[@]}" instances stop "$VM" --zone "$Z" --quiet; echo "VM stopped (disk kept)" ;;
  status) "${G[@]}" instances describe "$VM" --zone "$Z" --format="value(status,machineType.basename())" ;;
  push)
    cd "$REPO"
    tar --exclude='.env' --exclude='.env.*' --exclude='results' --exclude='.venv' --exclude='internals/vendor' \
        --exclude='internals/runpod/ssh_key*' --exclude='internals/runpod/.ssh*' --exclude='internals/runpod/.pod_id*' \
        --exclude='__pycache__' -czf "$TMP/cloudvm_repo.tgz" .
    if tar -tzf "$TMP/cloudvm_repo.tgz" | grep -qE '(^|/)\.env(\.[^/]*)?$' ; then
      tar -tzf "$TMP/cloudvm_repo.tgz" | grep -E '(^|/)\.env(\.[^/]*)?$' | grep -vqE '\.env\.example$' && { echo "refusing: an env file is in the archive"; exit 1; }
    fi
    "${G[@]}" scp "$TMP/cloudvm_repo.tgz" "$VM:~/cloudvm_repo.tgz" --zone "$Z" --quiet
    "${S[@]}" --command "mkdir -p ~/repo ~/logs && cd ~/repo && tar -xzf ~/cloudvm_repo.tgz 2>/dev/null && export PATH=\$HOME/.local/bin:\$PATH && uv sync -q && git log --oneline -1"
    ;;
  run)
    name="$2"; shift 2
    "${S[@]}" --command "cd ~/repo && rm -f ~/logs/$name.done && (setsid nohup bash -c '$* ; echo EXIT=\$? > ~/logs/$name.done' > ~/logs/$name.log 2>&1 < /dev/null &) ; echo started $name" ;;
  log) "${S[@]}" --command "tail -n 20 ~/logs/$2.log 2>/dev/null; cat ~/logs/$2.done 2>/dev/null || echo RUNNING" ;;
  pull)
    sub="${2:-results/holdout}"
    "${S[@]}" --command "cd ~/repo && tar -czf ~/cloudvm_results.tgz $sub"
    "${G[@]}" scp "$VM:~/cloudvm_results.tgz" "$TMP/cloudvm_results.tgz" --zone "$Z" --quiet
    (cd "$REPO" && tar -xzf "$TMP/cloudvm_results.tgz" && echo "pulled $sub") ;;
  ssh) "${S[@]}" ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
