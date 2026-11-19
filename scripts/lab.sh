#!/usr/bin/env bash
# On-VM lab entrypoint: the single source of truth for every VM-side workshop step.
#   GitHub Actions:  scripts/remote.sh <lab> <step> [arg]     (→ .github/workflows/lab.yml → SSH → this script)
#   Live over SSH:   ssh ubuntu@<vm> 'bash mags-mlops-prod-demo/scripts/lab.sh <lab> <step> [arg]'
# Usage: scripts/lab.sh help
# Never prints .env or GATEWAY_KEY. Every argument is checked against a per-step allowlist.
set -euo pipefail
cd "$(dirname "$0")/.."
LAB=${1:-help}
STEP=${2:-}
ARG=${3:-}
C=mags-mlops-prod-demo-vllm
OPS=http://127.0.0.1:9090          # Caddy operator listener (VM loopback only): metrics + LoRA admin
OUT=results/lab
KEYS='kv_cache_usage_perc|num_requests_(running|waiting)|num_preemptions_total|prompt_tokens_total|generation_tokens_total|request_success_total|(time_to_first_token|inter_token_latency|e2e_request_latency)_seconds_(sum|count)|lora_requests_info|cache_config_info|prefix_cache_(queries|hits)_total'

usage() {
  cat <<'EOF'
scripts/lab.sh <lab> <step> [arg]
  common  status | logs <vllm|caddy> [n] | restart | down | capture
  lab1    up | bootlog | nvidia-smi                         (3.3 first boot, BF16)
  lab2    edge-up | caddy-validate | caddy-reload | show-config   (3.4 gateway)
  lab3    metrics [filter] | prefix-cache                   (3.5 observability)
  break   awq-warm                                          (BREAK-01: AWQ up, healthy and warm)
  lab4    switch <baseline|awq|fp8|fp8-kv> | vram-math | metrics-watch <start|stop>   (4.2)
  lab5    lora-up | make-v2 [alpha] | lora-swap <v1|v2> | lora-status                (4.3)
  lab6    drain                                             (4.4 graceful stop mid-stream)
EOF
}
die() { echo "ERROR: $*" >&2; exit 2; }

[ "$LAB" = help ] && { usage; exit 0; }
case "$LAB $STEP" in
  "common status" | "common restart" | "common down" | "common capture") re='' ;;
  "common logs") re='^(vllm|caddy)( [0-9]{1,4})?$' ;;
  "lab1 up" | "lab1 bootlog" | "lab1 nvidia-smi") re='' ;;
  "lab2 edge-up" | "lab2 caddy-validate" | "lab2 caddy-reload" | "lab2 show-config") re='' ;;
  "lab3 metrics") re='^[a-z_:]{0,64}$' ;;
  "lab3 prefix-cache" | "break awq-warm") re='' ;;
  "lab4 switch") re='^(baseline|awq|fp8|fp8-kv)$' ;;
  "lab4 vram-math") re='' ;;
  "lab4 metrics-watch") re='^(start|stop)$' ;;
  "lab5 lora-up" | "lab5 lora-status") re='' ;;
  "lab5 make-v2") re='^([0-9]{1,4})?$' ;;
  "lab5 lora-swap") re='^(v1|v2)$' ;;
  "lab6 drain") re='' ;;
  *) usage; die "unknown step: $LAB $STEP" ;;
esac
if [ -z "$re" ]; then [ -z "$ARG" ] || die "$LAB $STEP takes no argument"
elif ! [[ $ARG =~ $re ]]; then die "invalid argument for $LAB $STEP"; fi

set -a
# shellcheck source=/dev/null
. ./.env
set +a
PUB=http://localhost:${PUBLIC_PORT:-80}
mkdir -p "$OUT"

# --- helpers ---------------------------------------------------------------------------------
redact() { sed -E 's/\b([0-9]{1,3}\.){3}[0-9]{1,3}\b/<ip>/g'; }
auth() { printf 'Authorization: Bearer %s' "$GATEWAY_KEY"; }       # fed to curl via -H @<(auth): not in argv
code() { curl -s -o /dev/null -w '%{http_code}' "$@" || true; }
metrics() { curl -s --max-time 5 "$OPS/metrics" || true; }
service() { docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$C" 2>/dev/null || true; }
profile() { local s; s=$(service); echo "${s#vllm-}"; }
variant() { # profile + the flags that distinguish fp8-kv / L4 emulation
  local p; p=$(profile); [ -n "$p" ] || { echo none; return; }
  echo "$p $(docker inspect -f '{{join .Args " "}}' "$C" | grep -oE -- '--(quantization|kv-cache-dtype|kv-cache-memory-bytes) [^ ]+' | tr '\n' ' ')"
}
wait_health() { # [timeout_s]
  local t; t=$(date +%s)
  until curl -sf -o /dev/null "$PUB/health"; do
    [ $(( $(date +%s) - t )) -lt "${1:-900}" ] || { docker logs --tail 30 "$C" 2>&1 | redact; die "not healthy after ${1:-900}s"; }
    sleep 3
  done
  echo "HEALTHY in $(( $(date +%s) - t ))s"
}
bootlog() {
  echo "== boot numbers ($(variant))"
  docker logs "$C" 2>&1 | sed 's/\x1b\[[0-9;]*m//g' \
    | grep -Ei 'model loading took|kv cache|maximum concurrency|graph captur|cuda graph|attention backend|using .*backend|marlin|falling back|quantiz|extensible|startup took|init engine' \
    | grep -v -i 'warning: you are sending' | tail -n 25 | redact || echo "(no boot lines yet)"
}
ts() { date -u +%Y%m%dT%H%M%SZ; }

# --- steps -----------------------------------------------------------------------------------
case "$LAB $STEP" in
"common status")
  echo "== GPU"; nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu --format=csv,noheader
  echo "== containers"; docker ps -a --filter name=mags-mlops-prod-demo --format '{{.Names}}  {{.Status}}'
  echo "== active vLLM: $(variant)"
  echo "== /health via Caddy: $(code "$PUB/health")"
  echo "== disk"; df -h / | tail -1; du -sh ~/.cache/huggingface/hub adapters 2>/dev/null || true
  echo "== commit: $(git log --oneline -1)"
  echo "== balance: printed by lab.yml (the VM has no Jarvislabs key)"
  ;;
"common logs")
  read -r svc n <<<"$ARG"
  docker logs --tail "${n:-50}" "mags-mlops-prod-demo-$svc" 2>&1 | redact
  ;;
"common restart")
  docker inspect "$C" >/dev/null 2>&1 || die "no vLLM container — run lab1 up (or lab4 switch …)"
  docker restart -t 45 "$C" >/dev/null; wait_health 900
  ;;
"common down")
  p=$(profile)
  if [ -n "$p" ]; then docker compose --profile "$p" down; else docker compose down; fi
  ;;
"common capture")
  d=$OUT/capture-$(ts); mkdir -p "$d"
  bootlog > "$d/boot.txt"
  docker logs "$C" 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | redact > "$d/vllm.log" || true
  metrics | grep '^vllm:' > "$d/metrics.txt" || true
  nvidia-smi > "$d/nvidia-smi.txt"
  bash "$0" common status > "$d/status.txt" 2>&1 || true
  wc -l "$d"/* | sed "s#$d/##"
  echo "ARTIFACT_DIR=$d"
  ;;
"lab1 up")
  bash scripts/up.sh baseline 900; bootlog
  ;;
"lab1 bootlog") bootlog ;;
"lab1 nvidia-smi")
  nvidia-smi
  nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv
  ;;
"lab2 edge-up")
  docker compose up -d caddy
  for _ in $(seq 1 30); do [ "$(docker inspect -f '{{.State.Health.Status}}' mags-mlops-prod-demo-caddy)" = healthy ] && break; sleep 2; done
  echo "caddy: $(docker inspect -f '{{.State.Health.Status}}' mags-mlops-prod-demo-caddy); public /health -> $(code "$PUB/health")"
  ;;
"lab2 caddy-validate")
  # Keep caddy's own exit code; info lines are noise (a filter that empties the output must not fail the step).
  rc=0
  out=$(docker run --rm -i -e GATEWAY_KEY -e SITE_ADDRESS "${CADDY_IMAGE:-caddy:2.11.9@sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b}" \
    caddy validate --adapter caddyfile --config /dev/stdin <Caddyfile 2>&1) || rc=$?
  grep -vE '"level":"info"' <<<"$out" | tail -n 5 || true
  exit "$rc"
  ;;
"lab2 caddy-reload")
  rc=0
  out=$(docker compose exec -T caddy caddy reload --adapter caddyfile --config /dev/stdin <Caddyfile 2>&1) || rc=$?
  grep -vE '"level":"info"' <<<"$out" | tail -n 5 || true
  [ "$rc" = 0 ] || die "caddy reload failed (exit $rc) — config unchanged, old config still serving"
  echo "reloaded (zero downtime); public /health -> $(code "$PUB/health")"
  ;;
"lab2 show-config")
  echo "== Caddyfile"; cat Caddyfile
  p=$(profile); echo "== docker compose config (profile ${p:-none}; secrets redacted)"
  docker compose ${p:+--profile "$p"} config \
    | sed -E 's/((GATEWAY_KEY|VLLM_API_KEY|HF_TOKEN): ).+/\1<redacted>/' \
    | { if [ -n "${GATEWAY_KEY:-}" ]; then sed "s/$GATEWAY_KEY/<redacted>/g"; else cat; fi; }
  ;;
"lab3 metrics")
  m=$(metrics); [ -n "$m" ] || die "metrics unreachable on $OPS (is the stack up?)"
  grep '^vllm:' <<<"$m" | grep -Ev '_bucket' | grep -E "${ARG:-$KEYS}" | head -n 60 || echo "(no matching vllm:* lines)"
  ;;
"lab3 prefix-cache")
  m=$(metrics)
  grep -E '^vllm:prefix_cache_(queries|hits)_total' <<<"$m" || { echo "(no prefix-cache counters)"; exit 0; }
  awk '/^vllm:prefix_cache_queries_total/{q+=$2} /^vllm:prefix_cache_hits_total/{h+=$2}
       END{printf "prefix-cache hit rate: %.1f%% (%d / %d tokens)\n", q ? 100*h/q : 0, h, q}' <<<"$m"
  ;;
"break awq-warm")
  bash scripts/up.sh awq 900
  body='{"model":"qwen2.5-7b","temperature":0,"max_tokens":32,"messages":[{"role":"user","content":"Warm-up: say hello."}]}'
  for i in 1 2 3; do
    s=$(curl -s -o /dev/null -w '%{http_code} %{time_total}s' -H @<(auth) -H 'Content-Type: application/json' -d "$body" "$OPS/v1/chat/completions")
    echo "prewarm $i: $s"
  done
  bootlog; echo "WARM: profile=$(variant)"
  ;;
"lab4 switch")
  case $ARG in
    fp8-kv)
      [ "${KV_CACHE_DTYPE_FP8_SUPPORTED:-true}" != false ] || die "FP8 KV cache unsupported on this GPU (Ampere)"
      UP_EXTRA_ARGS="--kv-cache-dtype fp8" bash scripts/up.sh baseline 900 ;;
    *) bash scripts/up.sh "$ARG" 900 ;;
  esac
  bootlog
  ;;
"lab4 vram-math") python3 scripts/vram_math.py ;;
"lab4 metrics-watch")
  W=$OUT/.watch; mkdir -p "$W"
  if [ "$ARG" = start ]; then
    if [ -f "$W/pid" ] && kill -0 "$(cat "$W/pid")" 2>/dev/null; then die "already watching"; fi
    m=$(metrics); [ -n "$m" ] || die "metrics unreachable"
    awk '/^vllm:num_preemptions_total/{s+=$2} END{print s+0}' <<<"$m" > "$W/pre"
    : > "$W/kv.txt"; date +%s > "$W/t0"
    # shellcheck disable=SC2016  # literal on purpose: expanded by the child shell
    setsid nohup bash -c 'while :; do curl -s --max-time 2 http://127.0.0.1:9090/metrics | awk "/^vllm:kv_cache_usage_perc/{print \$2}"; sleep 0.5; done' \
      >>"$W/kv.txt" 2>/dev/null </dev/null &
    echo $! > "$W/pid"
    echo "watching kv_cache_usage_perc + preemptions (variant: $(variant)) — run the load test now, then: metrics-watch stop"
  else
    [ -f "$W/pid" ] || die "not watching (run metrics-watch start first)"
    kill "$(cat "$W/pid")" 2>/dev/null || true; rm -f "$W/pid"
    post=$(metrics | awk '/^vllm:num_preemptions_total/{s+=$2} END{print s+0}')
    d=$OUT/metrics-watch-$(ts); mkdir -p "$d"
    {
      echo "variant: $(variant)"
      echo "duration_s: $(( $(date +%s) - $(cat "$W/t0") ))"
      echo "samples: $(wc -l <"$W/kv.txt")"
      echo "kv_cache_usage_perc_peak: $(sort -g "$W/kv.txt" | tail -1)"
      echo "num_preemptions_delta: $(awk -v a="$(cat "$W/pre")" -v b="$post" 'BEGIN{print b-a}')"
    } | tee "$d/summary.txt"
    cp "$W/kv.txt" "$d/kv_samples.txt"
    echo "ARTIFACT_DIR=$d"
  fi
  ;;
"lab5 lora-up")
  bash scripts/up.sh lora 900; bootlog; bash "$0" lab5 lora-status
  ;;
"lab5 make-v2")
  a=${ARG:-256}
  python3 scripts/make_regressed_adapter.py --alpha "$a" --dst "adapters/sql-v2-a$a"
  python3 scripts/make_regressed_adapter.py --alpha "$a" --dst adapters/sql-v2
  echo "sql-v2 is now alpha=$a (also kept as /adapters/sql-v2-a$a). If sql-prod already points at v2: lab5 lora-swap v2 to reload."
  ;;
"lab5 lora-swap")
  t=$(date +%s.%N)
  resp=$(curl -s -w '\n%{http_code}' -X POST -H @<(auth) -H 'Content-Type: application/json' \
    -d "{\"lora_name\":\"sql-prod\",\"lora_path\":\"/adapters/sql-$ARG\",\"load_inplace\":true}" "$OPS/v1/load_lora_adapter")
  http=${resp##*$'\n'}
  echo "sql-prod -> /adapters/sql-$ARG: HTTP $http in $(awk -v a="$t" -v b="$(date +%s.%N)" 'BEGIN{printf "%.2f", b-a}')s — ${resp%$'\n'*}"
  [ "$http" = 200 ] || exit 1
  ;;
"lab5 lora-status")
  echo "== /v1/models"
  curl -s -H @<(auth) "$OPS/v1/models" | python3 -c 'import sys,json
for m in json.load(sys.stdin)["data"]: print("  %-12s root=%s parent=%s" % (m["id"], m.get("root"), m.get("parent")))'
  echo "== vllm:lora_requests_info"; metrics | grep '^vllm:lora_requests_info' || echo "  (none yet: appears once LoRA traffic ran)"
  ;;
"lab6 drain")
  p=$(profile); [ -n "$p" ] || die "no vLLM container running"
  echo "draining vllm-$p (vLLM --shutdown-timeout 30, compose stop_grace_period 45s)..."
  t=$(date +%s)
  docker compose --profile "$p" stop "vllm-$p"
  echo "stopped in $(( $(date +%s) - t ))s"
  docker logs --tail 15 "$C" 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -Ei 'shutdown|drain|waiting|finished|abort|stopp' | redact || true
  echo "bring it back: lab.sh common restart"
  ;;
esac
