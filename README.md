# mags-mlops-prod-demo

Production LLM serving on **one GPU** with portable primitives: Docker + NVIDIA Container Toolkit + **vLLM v0.34.0** + **Caddy 2.11.9**.
Model: Qwen2.5-7B-Instruct (BF16 / AWQ / online FP8) with two LoRA tenants, behind an authenticated, streaming-safe gateway.

Built for a 3-hour live workshop (ISTE STTP, K. J. Somaiya School of Engineering, Mumbai, 3 Dec 2026). Reference GPU: **NVIDIA L4 (24 GB, sm_89)** on a Jarvislabs VM. Every lab runs the same way on any Ubuntu box with an NVIDIA GPU ≥ 24 GB.

```
client ──HTTP──► Caddy :80  (bearer auth · 401/403/413 · SSE flush)  ──internal network──► vLLM :8000 (never published)
operator ─SSH tunnel─► Caddy 127.0.0.1:9090  (/metrics, LoRA load/unload)  ──────────────►
```

## Prerequisites

- Ubuntu 22.04/24.04, NVIDIA driver **R580+** (the vLLM image is CUDA 13; on R535/R570 set `VLLM_ENABLE_CUDA_COMPATIBILITY=1` in `.env`).
- GPU with ≥ 24 GB, ~60 GB free disk (image ≈ 20 GB unpacked, weights ≈ 21 GB).
- `scripts/setup_host.sh` installs Docker, the NVIDIA Container Toolkit and `uv` if they are missing.

## Setup

### A. Jarvislabs VM (what the instructor uses)

```bash
uv tool install jarvislabs==0.2.17 && export JL_API_KEY=...        # https://jarvislabs.ai
ssh-keygen -t ed25519 -f ~/.ssh/mags_jl -N "" && jl ssh-key add ~/.ssh/mags_jl.pub --name mags-mlops-prod-demo
jl create --gpu L4 --vm --storage 200 --name mags-mlops-prod-demo --yes   # VM, not a template: templates can't run Docker
jl ssh <machine_id>
```
Pause when idle (`jl pause <id> --yes`); disk is kept. `jl resume <id> --gpu H100` moves the same disk to a bigger GPU in the same region.

### B. Your own machine / lab server

Skip the `jl` lines; everything else is identical.

### Then, on the GPU host

```bash
git clone https://github.com/MagmaCubes1133/mags-mlops-prod-demo && cd mags-mlops-prod-demo
bash scripts/setup_host.sh                      # then log out/in once if it added you to the docker group
cp .env.example .env && sed -i "s/^GATEWAY_KEY=.*/GATEWAY_KEY=$(openssl rand -hex 24)/" .env
bash scripts/prefetch_artifacts.sh all          # images + pinned weights + adapters + sql-v2  (~15 min)
bash scripts/up.sh baseline                     # waits for /health
bash scripts/smoke_test.sh
```
For the scripts below: `export GATEWAY_KEY=$(sed -n 's/^GATEWAY_KEY=//p' .env)`. Python scripts run with `uv run` (dependencies are declared inline).

## Lab runbook

| Lab | Topic | Commands |
|---|---|---|
| 1 | **Memory math → first boot** | `python3 scripts/vram_math.py` (7,615,616,512 params; 57,344 B/token KV) → `scripts/up.sh baseline` → `docker logs mags-mlops-prod-demo-vllm 2>&1 \| grep -Ei 'model loading took\|kv cache\|maximum concurrency'` |
| 2 | **Quantization + load testing** | `scripts/up.sh awq` / `scripts/up.sh fp8`; FP8 KV: `VLLM_EXTRA_ARGS=--kv-cache-dtype fp8` in `.env`; `uv run scripts/benchmark_concurrency.py --label awq` → `results/bench-awq.csv` |
| 3 | **The gateway** | `scripts/smoke_test.sh` (401/403/413/400, SSE); `curl -N` a streamed chat through Caddy; `uv run scripts/demo_structured_output.py` (legacy `guided_json` is silently ignored) |
| 4 | **Multi-LoRA + zero-downtime rollback** | `scripts/up.sh lora`; `uv run scripts/demo_multilora_rollout.py rollout` — clients call alias `sql-prod`, operator repoints v1 → v2 (bad) → v1 with `load_inplace`, non-2xx count must be 0 |
| 5 | **Operate it** | metrics via `ssh -L 9090:127.0.0.1:9090` → `curl localhost:9090/metrics \| grep -E 'kv_cache_usage_perc\|num_preemptions_total\|lora_requests_info'`; graceful drain: `docker compose stop` mid-stream (`--shutdown-timeout 30`, `stop_grace_period: 45s`); GPU fallback via the GitHub Actions workflow |

### Example requests

```bash
curl -s localhost/v1/chat/completions -H "Authorization: Bearer $GATEWAY_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-7b","temperature":0,"messages":[{"role":"user","content":"Hello"}]}'

# LoRA tenant (lora profile). Prompt format the sql adapter was trained on:
curl -s localhost/v1/completions -H "Authorization: Bearer $GATEWAY_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"sql-prod","temperature":0,"max_tokens":64,
       "prompt":"Convert the following natural language question to SQL:\n\nDatabase: employees(id, name, dept, salary)\nQuestion: Average salary per dept?\n\nSQL:"}'
```

## Things that differ from most blog posts (vLLM v0.34.0)

- KV metric is `vllm:kv_cache_usage_perc` (not `gpu_cache_usage_perc`).
- Online FP8 is `--quantization fp8_per_tensor`; plain `fp8` on a BF16 checkpoint errors. AWQ: just serve the AWQ repo (Marlin kernels auto-selected).
- `--gpu-memory-utilization` defaults to 1.0 (extensible KV cache); we set 0.90. `--kv-cache-memory-bytes 4G` pins the KV pool.
- `guided_json` is removed and **silently ignored**; use `structured_outputs` or `response_format: json_schema`.
- vLLM `--api-key` guards only `/v1…`; `/metrics`, `/health`, `/load` are open → the gateway blocks them.

Verified facts and on-GPU results: `docs/reference/phase1-verified-facts.md`, `docs/verification-results.md`, `docs/slide-numbers.md`.

## Files

| Path | What |
|---|---|
| `docker-compose.yml` | `vllm-{baseline,awq,fp8,lora}` (one profile at a time) + `caddy`; internal network; healthchecks; drain |
| `Caddyfile` | public site (auth, 403 for internal paths, 256 KB body cap, SSE flush) + operator listener `:9090` |
| `profiles/<GPU>.env` | per-GPU knobs merged into `.env` by the workflow |
| `scripts/` | setup, prefetch, `up.sh`, smoke test, benchmark, LoRA rollout, structured outputs, VRAM math |
| `.github/workflows/demo-gpu.yml` | Jarvislabs provision / deploy / verify / swap-gpu / pause / resume / destroy |

## Instructor: GitHub Actions fallback

`Actions → demo-gpu → Run workflow`. Secrets: `JL_API_KEY`, `JL_SSH_PRIVATE_KEY`, `GATEWAY_KEY`, optional `HF_TOKEN`.
L4 unavailable? Re-run with `gpu=auto` (walks `fallback_chain`) or `action=swap-gpu gpu=H200` (same disk, same region). `emulate_l4=true` pins the KV pool to the L4 size so KV-capacity demos match the slides (latency will still be faster — say so). Logs are public: ids and IPs are masked.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `could not select device driver "nvidia"` | `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker` |
| `permission denied … docker.sock` | `bash scripts/setup_host.sh`, then log out and back in |
| vLLM exits with CUDA driver error | driver < R580 → `VLLM_ENABLE_CUDA_COMPATIBILITY=1` in `.env` |
| CUDA OOM at boot | lower `MAX_MODEL_LEN` or `GPU_MEMORY_UTILIZATION`; one vLLM profile at a time (`scripts/up.sh` handles it) |
| `LocalEntryNotFoundError` / tries to download | run `scripts/prefetch_artifacts.sh <profile>`; vLLM runs offline on an internal network |
| Streaming arrives all at once | don't add `encode` to the public site; keep `flush_interval -1` |
| 401 with the right key | header must be exactly `Authorization: Bearer <key>` |
| Port 80 unreachable from outside | `ssh -L 8080:localhost:80 ubuntu@<vm>` and use `http://localhost:8080` |
