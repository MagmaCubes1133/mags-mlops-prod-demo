#!/usr/bin/env bash
# Laptop: SSH tunnel to the VM's operator listener (Caddy 127.0.0.1:9090 → /metrics + LoRA admin), so local
# scripts can scrape metrics. Without the tunnel they skip metrics cleanly.
# Usage: scripts/tunnel.sh        forward localhost:9090 → VM 127.0.0.1:9090 (foreground; Ctrl-C closes)
#        scripts/tunnel.sh ip     print the VM's public IP (e.g. export BASE_URL=http://$(scripts/tunnel.sh ip))
# Needs: jl (JL_API_KEY, or JARVISLABS_API_KEY in .env) and ~/.ssh/mags_jl registered as mags-mlops-prod-demo.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -z "${JL_API_KEY:-}" ] && [ -f .env ]; then
  JL_API_KEY=$(sed -n 's/^JARVISLABS_API_KEY=//p; s/^JL_API_KEY=//p' .env | tail -1)
  export JL_API_KEY
fi
PY=$(command -v python3 || command -v python)
ip=$(PYTHONIOENCODING=utf-8 jl list --json | "$PY" -c 'import sys, json
vms = [i for i in json.load(sys.stdin) if i["name"] == "mags-mlops-prod-demo" and i["status"] == "Running"]
print(vms[0]["public_ip"] if vms else "")')
[ -n "$ip" ] || { echo "no running VM named mags-mlops-prod-demo" >&2; exit 1; }
if [ "${1:-}" = ip ]; then echo "$ip"; exit 0; fi
echo "tunnel: localhost:${LOCAL_PORT:-9090} → VM 127.0.0.1:9090 (Ctrl-C to close)"
exec ssh -i "${SSH_KEY:-$HOME/.ssh/mags_jl}" -o StrictHostKeyChecking=accept-new -o ExitOnForwardFailure=yes \
  -N -L "${LOCAL_PORT:-9090}:127.0.0.1:9090" "ubuntu@$ip"
