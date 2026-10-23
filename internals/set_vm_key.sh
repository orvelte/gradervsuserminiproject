#!/usr/bin/env bash
# Store a provider key in the cloud VM's ~/repo/.env without it touching this laptop's disk, shell history or output.
#   bash internals/set_vm_key.sh                 # asks for an OpenRouter key (input hidden)
#   bash internals/set_vm_key.sh VLLM_API_KEY    # any other variable name
set -euo pipefail
NAME="${1:-OPENROUTER_API_KEY}"
GCLOUD="$HOME/google-cloud-sdk/bin/gcloud"
read -rs -p "Paste the value for $NAME (hidden), then press Enter: " VAL; echo
[ -n "$VAL" ] || { echo "nothing entered; nothing saved"; exit 1; }
printf '%s=%s\n' "$NAME" "$VAL" | "$GCLOUD" compute ssh runner-1 --project gradervsuser-runs-1023 --zone us-central1-a --quiet \
  --command "umask 077; touch ~/repo/.env; grep -v '^$NAME=' ~/repo/.env > ~/repo/.env.tmp || true; cat >> ~/repo/.env.tmp; mv ~/repo/.env.tmp ~/repo/.env; chmod 600 ~/repo/.env; echo saved $NAME on the VM"
unset VAL
