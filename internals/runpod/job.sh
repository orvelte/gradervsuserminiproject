#!/usr/bin/env bash
# The only route to a RunPod job pod (created with `pod.py create-job`), for internals/persona.
#
#   bash internals/runpod/job.sh setup                 # check the pod image's torch/transformers/vllm; install fla kernels
#   bash internals/runpod/job.sh push                  # rsync the pod scripts and inputs to /workspace/job
#   bash internals/runpod/job.sh run NAME CMD...       # start CMD detached in /workspace/job; log in logs/NAME.log
#   bash internals/runpod/job.sh status NAME           # tail of the log and whether it has finished
#   bash internals/runpod/job.sh pull                  # rsync /workspace/job/out back to results/persona_min/pod_out
#   bash internals/runpod/job.sh gpu                   # nvidia-smi summary
# Uses the job key internals/runpod/ssh_key and the endpoint in internals/runpod/.ssh (both gitignored).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(cd "$HERE/../.." && pwd)"
read -r IP PORT < "$HERE/.ssh"
SSH=(ssh -i "$HERE/ssh_key" -p "$PORT" -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$HERE/known_hosts" -o ConnectTimeout=20 -o ServerAliveInterval=30 "root@$IP")
RSH="ssh -i $HERE/ssh_key -p $PORT -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$HERE/known_hosts"
J=/workspace/job

case "${1:-}" in
  setup)
    "${SSH[@]}" "mkdir -p $J/logs $J/out && python3 -c 'import torch, transformers, vllm; print(\"torch\", torch.__version__, \"transformers\", transformers.__version__, \"vllm\", vllm.__version__, \"cuda\", torch.cuda.is_available())' && (pip install -q flash-linear-attention 2>&1 | tail -1; python3 -c 'import fla; print(\"fla ok\")' || echo 'fla not available: transformers falls back to the torch implementation')"
    ;;
  push)
    "${SSH[@]}" "mkdir -p $J/logs $J/out"
    rsync -rltz --no-owner --no-group -e "$RSH" "$REPO"/internals/persona/pod_*.py "root@$IP:$J/"
    rsync -rltz --no-owner --no-group -e "$RSH" "$REPO/${DATA:-results/persona_min}/prompts.jsonl" "root@$IP:$J/"; [ -e "$REPO/results/persona_min/v1/seqs.jsonl" ] && rsync -rltz --no-owner --no-group -e "$RSH" "$REPO/results/persona_min/v1/seqs.jsonl" "root@$IP:$J/"
    for f in "$REPO"/results/persona_min/smoke/*.jsonl; do [ -e "$f" ] && rsync -rltz --no-owner --no-group -e "$RSH" "$f" "root@$IP:$J/"; done
    echo "pushed"
    ;;
  run)
    name="$2"; shift 2
    "${SSH[@]}" -n "cd $J && rm -f logs/$name.done && (setsid nohup bash -c 'export HF_HOME=/workspace/hf; $* ; echo EXIT=\$? > logs/$name.done' > logs/$name.log 2>&1 < /dev/null &) ; echo started $name"
    ;;
  status)
    "${SSH[@]}" "tail -n 15 $J/logs/$2.log 2>/dev/null; cat $J/logs/$2.done 2>/dev/null || echo RUNNING"
    ;;
  pull)
    mkdir -p "$REPO/results/persona_min/pod_out"
    rsync -rltz --no-owner --no-group -e "$RSH" "root@$IP:$J/out/" "$REPO/results/persona_min/pod_out/"
    du -sh "$REPO/results/persona_min/pod_out"
    ;;
  gpu)
    "${SSH[@]}" "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader"
    ;;
  *)
    sed -n '2,10p' "$0"; exit 1
    ;;
esac
