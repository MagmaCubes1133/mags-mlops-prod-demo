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
