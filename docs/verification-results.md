# Verification results

One row per check ID from `docs/reference/gpu-verification-handoff.md`. No IPs or machine ids here (public repo).
Image digests: vLLM `vllm/vllm-openai:v0.34.0@sha256:20fdb089454afbb324efa4110a2c025ff7b27cc1a086e07aa580b18df8ad1ce1`, Caddy `caddy:2.11.9@sha256:4851e54a46b206517c574821bb5cc67f170d2156041e9fbc4c9193b45e84a75b` (resolved from Docker Hub on 2026-11-19).

## Corrections to the verified facts / kickoff prompt

| # | Fact as written | What we observed | Impact |
|---|---|---|---|
| C-1 | Fallback chain `L4,H100,A100-80GB,A100,RTX-PRO6000` assumes VMs on all tiers | `jl gpus --json` 2026-11-19: **A100, A100-80GB and A30 are offered only as `container`, not `vm`**; H100 VM exists but 0 free; **H200 VM** (IN2) and RTX-PRO6000 VM (IN1) are the only non-L4 VMs with free devices | `gpu=auto` skips tiers with no free VM, so the chain still works; practical swap target in IN2 today is **H200**, not H100 |
| C-2 | Image is CUDA 13.0.3 | image env `CUDA_VERSION=13.0.2`, `NV_CUDA_CUDART_VERSION=13.0.96-1` | none (driver R580 satisfies both) |
| C-3 | Jarvislabs auth env var `JL_API_KEY` | correct for `jl`; the local `.env` names it `JARVISLABS_API_KEY` → export as `JL_API_KEY` | none |
| C-4 | Prices | Jarvislabs prices are **INR**, not USD (L4 VM ₹41.31/h ≈ $0.49/h) | budget maths |
| C-5 | (tooling) `jl exec` output | `jl exec` prints `Executing on <machine_id>: <command>` → the workflow masks the id before any `jl exec` | handled in `.github/jl.sh` |
| C-6 | (tooling) Compose `.env` | `KEY=   # comment` with an empty value is **not** stripped: the comment becomes the value | `.env.example` keeps comments on their own lines |
| C-8 | (checkpoint 1) "start needs ≥ 1 h incl. GST" | The API compares "available" vs "required", **both ≈ 1.17× the `jl status` figures** (paused L4: ₹469.56 avail vs ₹399.79 balance; running L4: ₹2,811.56 vs ₹2,397.23; 8×H200 required ₹4,084.24 ≈ 8 × ₹434.97 × 1.17). **A running VM is not reserved** (ratio identical running vs paused). Rule in `jl status` terms: balance ≥ 1 h of list price. | demo-gpu guard = `balance ≥ price + 5`; H200 needs ≈ ₹435 of `jl status` balance |
| C-7 | (tooling) Compose v5 profiles | enabling two profiles whose services share `container_name` is an error | `scripts/up.sh` removes the old vLLM container by service label |

## Results

| ID | Status | GPU | Driver | Timestamp (UTC) | Evidence |
|---|---|---|---|---|---|
| A1 | PASS | L4 (IN2, vm) | — | 2026-11-19 15:00 | `jl gpus --json`: L4 vm `num_free_devices=8`, `price_per_hour=41.31` (INR), spot 27.54. Other VMs: H100 0 free (₹330.48), H200 1 free (₹434.97), RTX-PRO6000 2 free (IN1, ₹207.36). Repeat on 1 Dec and 3 Dec morning. |
| A2 | PASS | L4 | — | 2026-11-19 15:06 | `jl create --gpu L4 --vm --storage 200 --name mags-mlops-prod-demo --yes --json` returned `status: Running` in **12 s**; SSH accepted ~40 s after create returned. JSON keys: `machine_id, gpu_type, status, public_ip, private_ip, ssh_command, billing_frequency, region, …`. User `ubuntu`, Ubuntu 22.04.5, 28 vCPU, 121 GiB RAM, 194 GB root disk. |
| A3 | PASS | L4 | 580.196.07 | 2026-11-19 15:08 | Docker 29.9.2, Compose v5.6.1, NVIDIA Container Toolkit 1.20.1 preinstalled; `Runtimes: io.containerd.runc.v2 nvidia runc` (default runc; compose `deploy.resources.reservations.devices` works). `ubuntu` not in `docker` group → `setup_host.sh` adds it. No `uv`/`jq` preinstalled. |
| A4 | PASS | L4 | 580.196.07 | 2026-11-19 15:08 | `NVIDIA L4, 580.196.07, 23034 MiB, 8.9`; `CUDA Version: 13.0` → no `VLLM_ENABLE_CUDA_COMPATIBILITY` needed. |
| A5 | PASS | L4 | — | 2026-11-19 15:10 | Test listeners on the VM; from outside: `:80` → 200, `:443` → 200 (no host firewall: ufw inactive, iptables INPUT ACCEPT). Public HTTP on :80 works; SSH-tunnel fallback documented in README anyway. |
| A6 | PASS (partial) | L4 | — | 2026-11-19 15:13 | `billing_frequency: "hour"` (rate is per hour) but cost accrues pro-rata: ₹0.16 at 14 s runtime, ₹5.27 at 7 m 15 s (≈ ₹43.6/h effective incl. 200 GB disk). Balance is debited in batches. **Start/resume requires balance ≥ 1 h of that instance's cost** (H200 resume refused: "minimum balance of ₹513.19 is required to run it for at least 1 hour"). Paused-disk cost: not yet measured. |
| A7 | BLOCKED (swap) / PASS (pause→resume) | L4 | 580.196.07 | 2026-11-19 15:18–15:21 | `jl pause` 33 s. `jl resume --gpu H200` refused: **insufficient balance** (needs ₹513.19 for 1 h). `--gpu H100`: "No free H100 GPUs in IN2 right now". `--gpu RTX-PRO6000`: "Paused instances can only resume in their original region" (region lock confirmed). `jl resume` (same L4): 16 s, **new machine id even without a GPU change**; disk intact: marker file, 20 G HF cache, 378 M adapters, both images (vLLM 36.3 GB unpacked), docker-group membership, `.env`. Cross-GPU swap still unverified → re-run after top-up. |
| B1 | PASS | L4 | 580.196.07 | 2026-11-19 15:15 | `docker pull` vLLM v0.34.0: **136 s** (≈10.0 GB compressed, 36.3 GB unpacked), Caddy 2 s; digests match the pins above. Prefetch (all profiles, unauthenticated HF): BF16 weights 71 s, AWQ 32 s, sql-v1 12 s, stoploss 6 s; whole `prefetch_artifacts.sh all` ≈ 4.5 min. sql-v2: `lora_alpha 32 -> 256 (scale 2 -> 16)`. |

## Phase B (L4, driver 580.196.07, vLLM digest sha256:20fdb089…, 2026-11-19) — partial, interrupted by usage limit

**Correction C-9:** `--quantization fp8` on a BF16 checkpoint does **not** error in v0.34.0. It logs `WARNING [weight_utils.py:383] --quantization fp8 is deprecated for online quantization; use --quantization fp8_per_tensor instead.` and runs as `Fp8PerTensorOnlineLinearMethod` (CutlassFP8ScaledMMLinearKernel, 112 layers quantized).

| ID | Status | Evidence |
|---|---|---|
| B2 | PASS | BF16 @0.90 cold: weights 14.29 GiB (39 s), FLASH_ATTN, available KV 4.31 GiB, **70,656 tokens**, max concurrency 8.62× @8k, CUDA graphs 0.47 GiB / 10 s, torch.compile 13 s, init engine 37.7 s. Warm restart: 4.83 GiB → **78,848 tokens**, 9.62×. |
| B3 | TODO | default util vs 0.90 not yet run |
| B4 | PASS | cold start to /health 123 s (first compile); warm restarts 42–61 s |
| B5 | PASS | single stream, 256 tok: ITL p50 56.5 ms / p95 57.4 ms (floor 50.8); TTFT p50 98 ms from laptop (`results/bench-b5-bf16-single.csv`) |
| C1 | PASS | AWQ: `Using MarlinLinearKernel for AutoAWQMarlinLinearMethod`, no fallback line; weights 5.29 GiB; KV 13.27 GiB, **237,568 tokens**, 29.0×; healthy 81 s; warm prewarm 0.20 s |
| C2 | PASS | fp8_per_tensor: weights 8.17 GiB (cast 0.14 s, no OOM); KV 10.27 GiB, **182,272 tokens**, 22.25× |
| C3 | CORRECTED | see C-9 (warning, not error) |
| C4 | PASS | `--kv-cache-dtype fp8`: **FLASHINFER** backend (candidates FLASHINFER, TRITON_ATTN); **114,688 tokens**, 14.0× |
| C5 | TODO | benchmark sweep 1/8/20/32 × BF16/AWQ/FP8 |
| D1–D5 | TODO | LoRA |
| E1 | PASS | TTFT via Caddy 123.4 ms = direct 123.4 ms; 18 incremental events/stream; ITL 56.5 ms both |
| E2/E3 | PASS | smoke_test via workflow: 401/401/403×4/413/400, SSE ≥5 events + [DONE] |
| E4 | PASS | guided_json → 200, prose (ignored); structured_outputs + response_format → valid JSON |
| E5 | PASS | `lab6 drain` mid-stream: vLLM stopped in 26 s, laptop stream finished all 900 tokens (`finish_reason: length`, `[DONE]`); `common restart` healthy in 42 s |
| E6 | PASS | 3-turn chat, ~2k-token system prompt: turn-1 TTFT 709 → 127 ms on 2nd pass; prefix-cache hit 81.8% (12,224 / 14,942) |
| A7/F | TODO | H200 round trip |
