#!/usr/bin/env bash
# Edge + serving smoke test. Run on the VM from anywhere in the repo. Exits 1 on any failure.
# Checks: 401 / 403 / 413 / 400, /health, one SSE stream, one call per served model/adapter, metrics names.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
set -a
# shellcheck source=/dev/null
. ./.env
set +a
BASE=${BASE_URL:-http://localhost:${PUBLIC_PORT:-80}}
OPS=${OPS_URL:-http://127.0.0.1:9090}       # operator listener (VM loopback only)
AUTH="Authorization: Bearer $GATEWAY_KEY"
JSON="Content-Type: application/json"
fail=0

check() { # <name> <want> <got>
  if [ "$2" = "$3" ]; then echo "PASS  $1 ($3)"; else echo "FAIL  $1 (want $2, got $3)"; fail=1; fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

check "GET /health (public)" 200 "$(code "$BASE/health")"
check "no bearer -> 401" 401 "$(code "$BASE/v1/models")"
check "wrong bearer -> 401" 401 "$(code -H 'Authorization: Bearer wrong' "$BASE/v1/models")"
for p in /metrics /load /v1/load_lora_adapter /v1/unload_lora_adapter; do
  check "public $p -> 403" 403 "$(code -X POST -H "$AUTH" "$BASE$p")"
done
check "300 KB body -> 413" 413 "$(head -c 300000 /dev/zero | tr '\0' a | code -H "$AUTH" -H "$JSON" --data-binary @- "$BASE/v1/completions")"
check "max_tokens > max_model_len -> 400" 400 \
  "$(code -H "$AUTH" -H "$JSON" -d '{"model":"qwen2.5-7b","prompt":"hi","max_tokens":100000}' "$BASE/v1/completions")"

# SSE through Caddy: several data: events, terminated by [DONE]
sse=$(curl -sN -H "$AUTH" -H "$JSON" "$BASE/v1/chat/completions" \
  -d '{"model":"qwen2.5-7b","stream":true,"temperature":0,"max_tokens":16,"messages":[{"role":"user","content":"Count to five."}]}')
check "SSE events >= 5" yes "$([ "$(grep -c '^data: ' <<<"$sse")" -ge 5 ] && echo yes || echo no)"
check "SSE ends with [DONE]" yes "$(grep -q '^data: \[DONE\]' <<<"$sse" && echo yes || echo no)"

# One call per served model (base + any LoRA adapters)
models=$(curl -s -H "$AUTH" "$BASE/v1/models" | python3 -c 'import sys,json; print(" ".join(m["id"] for m in json.load(sys.stdin)["data"]))')
echo "models: $models"
for m in $models; do
  check "chat model=$m" 200 "$(code -H "$AUTH" -H "$JSON" "$BASE/v1/chat/completions" \
    -d "{\"model\":\"$m\",\"temperature\":0,\"max_tokens\":8,\"messages\":[{\"role\":\"user\",\"content\":\"Say OK.\"}]}")"
done

# Metric names (v0.34): kv_cache_usage_perc present, legacy gpu_cache_usage_perc absent
metrics=$(curl -s "$OPS/metrics")
check "metric vllm:kv_cache_usage_perc" yes "$(grep -q '^vllm:kv_cache_usage_perc' <<<"$metrics" && echo yes || echo no)"
check "legacy gpu_cache_usage_perc absent" yes "$(grep -q 'gpu_cache_usage_perc' <<<"$metrics" && echo no || echo yes)"
grep -E '^vllm:(num_requests_running|num_preemptions_total|generation_tokens_total)' <<<"$metrics" | head -5

[ $fail = 0 ] && echo "SMOKE OK" || echo "SMOKE FAILED"
exit $fail
