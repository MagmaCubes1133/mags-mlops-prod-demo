#!/usr/bin/env bash
# Pull pinned images, download pinned weights + adapters, build sql-v2. Idempotent; re-runs are cheap.
# Usage: scripts/prefetch_artifacts.sh [baseline|awq|fp8|lora|all]   (default: all)
# Downloads run inside the vLLM image (it ships huggingface_hub), so the host needs only Docker.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=/dev/null
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PROFILE=${1:-all}
VLLM_IMAGE=${VLLM_IMAGE:-vllm/vllm-openai:v0.34.0@sha256:20fdb089454afbb324efa4110a2c025ff7b27cc1a086e07aa580b18df8ad1ce1}
CADDY_IMAGE=${CADDY_IMAGE:-caddy:2.11.9@sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b}
HF=${HF_CACHE_DIR:-$HOME/.cache/huggingface}
mkdir -p results adapters "$HF" "${VLLM_CACHE_DIR:-$HOME/.cache/vllm}"
LOG=results/prefetch.log

for img in "$VLLM_IMAGE" "$CADDY_IMAGE"; do
  t=$(date +%s)
  docker pull -q "$img" >/dev/null
  echo "$(date -u +%FT%TZ) pull $img $(( $(date +%s) - t ))s digest=$(docker inspect --format '{{index .RepoDigests 0}}' "$img")" | tee -a "$LOG"
done

# dl <repo> <revision> [adapters/<dir>]  — base models go to the HF cache, adapters to ./adapters/<dir>
dl() {
  local t; t=$(date +%s)
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e HF_HOME=/hf -e HF_TOKEN="${HF_TOKEN:-}" \
    -v "$HF:/hf" -v "$PWD/adapters:/adapters" --entrypoint python3 "$VLLM_IMAGE" -c '
import sys
from huggingface_hub import snapshot_download
repo, rev = sys.argv[1], sys.argv[2]
local = "/adapters/" + sys.argv[3] if len(sys.argv) > 3 else None
snapshot_download(repo, revision=rev, local_dir=local,
                  allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja"])
' "$@"
  echo "$(date -u +%FT%TZ) download $1@${2:0:7} $(( $(date +%s) - t ))s" | tee -a "$LOG"
}

case $PROFILE in baseline|fp8|lora|all) dl Qwen/Qwen2.5-7B-Instruct "${MODEL_REVISION:-a09a35458c702b33eeacc393d103063234e8bc28}" ;; esac
case $PROFILE in awq|all) dl Qwen/Qwen2.5-7B-Instruct-AWQ "${AWQ_REVISION:-b25037543e9394b818fdfca67ab2a00ecc7dd641}" ;; esac
case $PROFILE in lora|all)
  dl vindows/qwen2.5-7b-text-to-sql 909715efd1439651aee1f34de37ec3628dbb1945 sql-v1
  dl TIGER-Lab/StopLoss-Qwen2.5-7B-Instruct acceabf1d1ab6fc95b4d3058eeb6e9ac8d03b446 stoploss
  python3 scripts/make_regressed_adapter.py --alpha "${SQL_V2_ALPHA:-64}"
  ;;
esac
du -sh "$HF/hub" adapters/* 2>/dev/null || true
