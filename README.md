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

Every **VM-side** step has one entrypoint, `scripts/lab.sh <lab> <step> [arg]`, reachable two ways:

- **SSH (live, fastest):** `ssh ubuntu@<vm> 'bash mags-mlops-prod-demo/scripts/lab.sh lab1 up'`
- **GitHub Actions (no SSH on the presenting laptop):** `scripts/remote.sh lab1 up` → dispatches `.github/workflows/lab.yml`, streams the output, prints dispatch→done time. `SYNC=false scripts/remote.sh …` skips the VM git sync.

**Client-side** steps run on the laptop against Caddy: `export BASE_URL=http://$(scripts/tunnel.sh ip)` and `GATEWAY_KEY` from `.env`. For metrics before/after a load test, keep `scripts/tunnel.sh` open in another terminal (forwards `localhost:9090` → the VM's loopback-only operator listener); without it the scripts skip metrics cleanly.
Measured latencies per step: `docs/lab-actions.md`.

| Lab | VM-side (`lab.sh` / `remote.sh` args) | Laptop-side |
|---|---|---|
| any | `common status` · `common logs vllm 100` · `common restart` · `common down` · `common capture` (boot log + metrics → artifact) | — |
| 1 · first boot (3.3) | `lab1 up` (BF16, waits for /health) · `lab1 bootlog` (weights / KV GiB + tokens / max concurrency / CUDA graphs / backend) · `lab1 nvidia-smi` | `python3 scripts/vram_math.py` |
| 2 · gateway (3.4) | `lab2 edge-up` · `lab2 caddy-validate` · `lab2 caddy-reload` · `lab2 show-config` (secrets redacted) | `BASE_URL=… bash scripts/smoke_test.sh` (401/403/413/400 + SSE); `curl -N` a streamed chat; `uv run scripts/demo_structured_output.py` |
| 3 · observability (3.5) | `lab3 metrics` (key `vllm:*` lines; `lab3 metrics kv_cache` filters) · `lab3 prefix-cache` | send the same long prompt twice, then `lab3 prefix-cache` |
| break | `break awq-warm` (AWQ up, healthy **and** warm — BREAK-01) | — |
| 4 · quantization + load (4.2) | `lab4 switch baseline\|awq\|fp8\|fp8-kv` (prints boot numbers) · `lab4 vram-math` · `lab4 metrics-watch start` … `stop` (peak `kv_cache_usage_perc`, preemption delta) | `uv run scripts/benchmark_concurrency.py --label awq` between `metrics-watch start` and `stop` |
| 5 · multi-LoRA (4.3) | `lab5 lora-up` · `lab5 make-v2 256` · `lab5 lora-swap v2` / `lab5 lora-swap v1` (load_inplace; admin is blocked publicly) · `lab5 lora-status` | `uv run scripts/demo_multilora_rollout.py rollout --swap-mode none --duration 120` → must end with `TOTAL non-2xx: 0` |
| 6 · drain (4.4) | `lab6 drain` (graceful stop: `--shutdown-timeout 30`, `stop_grace_period: 45s`) then `common restart` | start a long `curl -N` stream first; it completes |

Rehearsal-only all-in-one (on the VM): `uv run scripts/demo_multilora_rollout.py rollout` swaps inline.

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
| `scripts/lab.sh` | **the** on-VM lab entrypoint (every VM-side step) |
| `scripts/remote.sh`, `scripts/tunnel.sh` | laptop: run a lab step via GitHub Actions; SSH tunnel for metrics |
| `scripts/` (rest) | setup, prefetch, `up.sh`, smoke test, benchmark, LoRA rollout, structured outputs, VRAM math |
| `.github/workflows/demo-gpu.yml` | Jarvislabs provision / deploy / verify / swap-gpu / pause / resume / destroy |
| `.github/workflows/lab.yml` | one `lab.sh` step on the VM over SSH (inputs `lab`, `step`, `arg`, `sync`) |

## Instructor: GitHub Actions fallback

`Actions → demo-gpu → Run workflow`. Secrets: `JL_API_KEY`, `JL_SSH_PRIVATE_KEY`, `GATEWAY_KEY`, optional `HF_TOKEN`.
L4 unavailable? Re-run with `gpu=auto` (walks `fallback_chain` = `L4,H100,H200,RTX-PRO6000`, VM offerings only) or `action=swap-gpu gpu=H200` (same disk, same region). A100/A30 are container-only on Jarvislabs (no Docker) and are not in the chain. **Balance rule:** Jarvislabs only starts an instance if the balance covers 1 h of it incl. GST (H200 ≈ ₹513) — keep ≥ ₹1,000 on demo day. `emulate_l4=true` pins the KV pool to the L4 size so KV-capacity demos match the slides (latency will still be faster — say so). Logs are public: ids and IPs are masked.

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
