# Lab actions: every VM-side step, two ways, measured

One entrypoint: `scripts/lab.sh <lab> <step> [arg]` on the VM.
- **SSH:** `ssh -i ~/.ssh/mags_jl ubuntu@<vm> 'bash mags-mlops-prod-demo/scripts/lab.sh <lab> <step> [arg]'`
- **gh:** `scripts/remote.sh <lab> <step> [arg]` (= `gh workflow run lab.yml -f lab=… -f step=… -f arg=…` + `gh run watch`)

Latency = dispatch → run done via `scripts/remote.sh` on L4, 2026-11-19 (sync=true unless noted). **Live** ≲ 60 s; **backstage** = start before the segment.

| Lab · step | What it does | gh latency | Use |
|---|---|---|---|
| common status | GPU, containers, active variant, /health, disk | 47 s (38 s with SYNC=false) | live |
| common logs vllm 40 | tail of a container log (IP-redacted) | 42 s | live |
| common capture | boot log + metrics + nvidia-smi → artifact | 56 s | live |
| common restart | restart vLLM, wait /health | 84 s | backstage |
| common down | stop + remove the stack | 44 s | backstage |
| lab1 up | BF16 up + wait /health (51 s warm) | 94 s | backstage |
| lab1 bootlog | weights / KV / concurrency / graphs / backend | 46 s | live |
| lab1 nvidia-smi | nvidia-smi + query | 39 s | live |
| lab2 show-config | Caddyfile + compose config, secrets redacted | 41 s | live |
| lab2 caddy-validate | validate Caddyfile in caddy image | 42 s | live |
| lab2 caddy-reload | zero-downtime reload via admin API (container loopback) | 42 s | live |
| lab2 edge-up | start Caddy, wait healthy | 40 s | live |
| lab3 metrics [filter] | key vllm:* lines from :9090 | 43 s / 41 s | live |
| lab3 prefix-cache | hit/query counters + rate | 53 s | live |
| break awq-warm | AWQ up + 3 warm requests | 128 s | backstage (start at break) |
| lab4 switch fp8 / fp8-kv / baseline | switch variant + boot numbers | 121 / 103 / 99 s | backstage |
| lab4 vram-math | KV/params budget table | 41 s | live |
| lab4 metrics-watch start / stop | background sampler; stop prints peak kv usage + preemption delta | 35 / 47 s (SYNC=false) | live |
| lab5 lora-up | LoRA profile + adapters listing | 133 s | backstage |
| lab5 make-v2 [α] | regressed sql-v2 (default α 64) | 31–39 s | live |
| lab5 lora-swap v1/v2 | in-place repoint of `sql-prod` | 35–36 s (SYNC=false) | live |
| lab5 lora-status | /v1/models + lora_requests_info | 44 s | live |
| lab6 drain | graceful stop of vLLM (stopped in 26 s) | 64 s | live |

## Client scripts via the `client` workflow

A GitHub-hosted runner calls the public endpoint; metrics via an SSH tunnel. Dispatch → done, L4 with the `lora` profile, 2026-11-21. About 30 s of each run is runner setup.

| `script` | gh latency | Result |
|---|---|---|
| smoke | 32 s | all PASS incl. metrics |
| stream | 64 s | `[DONE], finish_reason=stop`, 850 chunks |
| structured-output | 39 s | `RESULT: as documented` |
| prefix-cache-8k | 44 s | hit 82.7% |
| lora-compare | 51 s | v1 vs v2 answers |
| lora-rollout (duration 150) | 180 s | 800 requests, 0 non-2xx, with lab5 lora-swap v2 → v1 clicked meanwhile |
| bench-sweep | 4 min 17 s | ITL p50 56.6 ms, 482 tok/s at 32 |
| stream + lab6 drain | 70 s / 38 s | drain waited for 1 in-flight request; stream completed |
