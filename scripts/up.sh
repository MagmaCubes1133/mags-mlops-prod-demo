#!/usr/bin/env bash
# Switch the stack to ONE vLLM profile and wait until /health is 200 through Caddy.
# Usage: scripts/up.sh baseline|awq|fp8|lora [timeout_seconds]   (default timeout 900)
# All profiles share the container name mags-mlops-prod-demo-vllm, so others are removed first.
set -euo pipefail
cd "$(dirname "$0")/.."
P=${1:?usage: scripts/up.sh baseline|awq|fp8|lora [timeout_s]}
T=${2:-900}
set -a
# shellcheck source=/dev/null
. ./.env
set +a
# UP_EXTRA_ARGS (e.g. --kv-cache-dtype fp8) is appended for this start only; exported env beats .env in compose.
export VLLM_EXTRA_ARGS="${VLLM_EXTRA_ARGS:-} ${UP_EXTRA_ARGS:-}"
c=mags-mlops-prod-demo-vllm

# Compose refuses to enable two profiles that share a container_name, so drop the old one directly.
running=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$c" 2>/dev/null || true)
if [ -n "$running" ] && [ "$running" != "vllm-$P" ]; then
  echo "switching $running -> vllm-$P"
  docker stop -t 45 "$c" >/dev/null && docker rm "$c" >/dev/null
fi
t=$(date +%s)
docker compose --profile "$P" up -d
until curl -sf -o /dev/null "http://localhost:${PUBLIC_PORT:-80}/health"; do
  # vLLM crashed (restart policy would loop it) or timed out → show the log tail and fail fast
  state=$(docker inspect -f '{{.State.Status}}/{{.RestartCount}}' mags-mlops-prod-demo-vllm 2>/dev/null || echo missing)
  if [ $(( $(date +%s) - t )) -ge "$T" ] || [ "$state" != running/0 ]; then
    docker logs --tail 40 mags-mlops-prod-demo-vllm 2>&1
    echo "NOT HEALTHY: profile=$P after $(( $(date +%s) - t ))s"
    exit 1
  fi
  sleep 5
done
echo "HEALTHY: profile=$P in $(( $(date +%s) - t ))s"

# Healthy is not enough: prove the running container IS the requested profile (+ UP_EXTRA_ARGS).
svc=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$c")
args=" $(docker inspect -f '{{join .Args " "}}' "$c") "
wrong() { echo "WRONG PROFILE: wanted $P${UP_EXTRA_ARGS:+ + $UP_EXTRA_ARGS}, running $svc: $*"; exit 1; }
[ "$svc" = "vllm-$P" ] || wrong "compose service label"
case $P in
  awq) [[ $args == *Instruct-AWQ* ]] || wrong "model is not the AWQ checkpoint" ;;
  fp8) [[ $args == *" --quantization fp8_per_tensor "* ]] || wrong "no --quantization fp8_per_tensor" ;;
  lora) [[ $args == *" --enable-lora "* ]] || wrong "no --enable-lora" ;;
  baseline) [[ $args != *Instruct-AWQ* && $args != *" --enable-lora "* && $args != *" --quantization fp8_per_tensor "* ]] \
    || wrong "baseline container carries another profile's flags" ;;
esac
for a in ${UP_EXTRA_ARGS:-}; do [[ $args == *" $a "* ]] || wrong "missing extra arg $a"; done
echo "VERIFIED: profile=$P$(grep -oE -- ' --(quantization|kv-cache-dtype|kv-cache-memory-bytes|enable-lora)([ =][^- ][^ ]*)?' <<<"$args" | tr -d '\n')"
