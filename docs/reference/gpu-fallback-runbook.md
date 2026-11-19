# GPU fallback runbook: one GitHub Actions workflow, switchable GPU tier

Goal: if an L4 VM is unavailable on Jarvislabs (JL) on demo day, bring the identical stack up on a higher tier by changing ONE workflow input. Same compose file, Caddyfile, scripts, and pins; only a per-GPU env profile changes.

## Jarvislabs facts (CLI `jarvislabs` 0.2.17, docs.jarvislabs.ai/cli)
- Install: `uv tool install jarvislabs==0.2.17`. Auth in CI: `JL_API_KEY` env var.
- `jl gpus --json`: entries carry `gpu_type`, `num_free_devices`, `price_per_hour`, `workload_type` ("container" | "vm").
- `jl create --gpu <TYPE> --vm --storage <GB> --name mags-mlops-prod-demo [--region IN1|IN2] --yes --json` blocks until Running. VM needs ≥1 SSH key registered first (`jl ssh-key add <pub> --name mags-mlops-prod-demo`); VM storage min 100 GB; no `--template` with `--vm`.
- `jl get <id> --json` (SSH command; Public IP row for running VMs), `jl ssh <id> --print-command --json`, `jl exec <id> -- <cmd>` (exit code propagates; wrap pipes in `sh -lc '...'`), `jl pause|resume|destroy <id> --yes --json`, `jl list --json`.
- `jl resume <id> --gpu <TYPE>` can change GPU, is **region-locked**, may return a **new machine ID**.
- GPU strings & regions: VM GPUs: IN2 = `L4`, `H100`, `H200`; IN1 = `RTX-PRO6000` (A100/A100-80GB/A30 are container-only); EU1 deprecated. Without `--region`, CLI auto-routes by GPU.
- Template (container) instances cannot run Docker → always `--vm`.

## Fallback ladder
| Order | GPU (JL string) | Region | Arch / cap | VRAM | What changes in the labs |
|---|---|---|---|---|---|
| 0 (primary) | `L4` | IN2 | Ada, sm_89 | 24 GB | Nothing — reference numbers |
| 1 | `H100` | IN2 | Hopper, sm_90 | 80 GB | Everything native; FP8 KV uses FlashAttention 3. Reachable by `jl resume --gpu H100` from the prepared L4 VM (same region, disk kept). Often 0 free. |
| 2 | `H200` | IN2 | Hopper, sm_90 | 141 GB | Same as H100, pricier (₹434.97/h). Same-region swap from the L4 VM. |
| 3 | `RTX-PRO6000` | IN1 | Blackwell, sm_120 | 96 GB | FP8 native; different region → fresh create only; re-prefetch (~5 min measured on IN2). |

**Dropped (2026-11-19, checkpoint 1):** `A100`, `A100-80GB`, `A30` are offered by Jarvislabs only as *container* instances, which cannot run Docker → no VM path. `select-gpu` filters on `workload_type=="vm"`.
**Balance rule:** a start/resume needs a `jl status` balance ≥ 1 h of the target's list price (H200 ₹434.97; the API error quotes it as ₹513 because it shows "available" and "required" ×≈1.17); running instances are not reserved — keep ≥ ₹1,000 on demo day.

## L4-emulation mode
`EMULATE_L4=true` adds `--kv-cache-memory-bytes=<L4 KV size from check B2>` (with `=`: a space breaks `source .env`) so KV capacity, preemptions and `kv_cache_usage_perc` match the L4 slides on bigger GPUs (latency still faster — say so). This disables the extensible KV cache — expected.

## Workflow design (`.github/workflows/demo-gpu.yml`)
Inputs: `action` (provision|deploy|verify|swap-gpu|pause|resume|destroy), `gpu` (auto|L4|H100|H200|RTX-PRO6000; default L4), `fallback_chain` (default `L4,H100,H200,RTX-PRO6000`, used when gpu=auto), `profile` (baseline|awq|fp8|lora|all), `emulate_l4` (bool; default true when gpu≠L4), `machine_id` (optional; else find by name `mags-mlops-prod-demo` via `jl list --json`).
Secrets: `JL_API_KEY`, `JL_SSH_PRIVATE_KEY`, `GATEWAY_KEY`, optional `HF_TOKEN`.
Jobs: select-gpu → provision (idempotent; resume if exists) → deploy (toolkit if absent, checkout this commit on VM, `.env` from `profiles/<gpu>.env`, prefetch, `docker compose --profile ... up -d`, wait `/health` ≤ 15 min) → verify (smoke_test.sh, upload `mags-mlops-prod-demo-results-<gpu>-<run>`). `swap-gpu` = pause → resume `--gpu` → redeploy with new id. `destroy` requires typing the machine name. `concurrency: mags-mlops-prod-demo`, `timeout-minutes: 45`.
Profiles (`profiles/<gpu>.env`): `MAX_MODEL_LEN`, `GPU_MEMORY_UTILIZATION`, `KV_CACHE_DTYPE_FP8_SUPPORTED`, `FP8_MODE` (w8a8|w8a16), `KV_CACHE_MEMORY_BYTES`, `VLLM_ENABLE_CUDA_COMPATIBILITY`.

## Demo-day decision tree
- T-24h: `select-gpu` dry run; if L4 VM free → provision + deploy + verify on L4, then pause (disk retained).
- T-60 min: resume on L4. Resume fails for capacity → `swap-gpu gpu=H100`. IN2 empty → `provision gpu=auto` (fresh; ~20–30 min).
- Mid-session failure: play pre-recorded lab captures; never debug live > 2 min.

## Unverified until a GPU run (handoff A1–A7)
VM L4 availability, `jl resume --gpu` on VMs, VM driver version, open inbound ports on the VM public IP, `--http-ports` on VMs.

## Measured round trip (2026-11-20, A7/F)

- `swap-gpu` runs provision → deploy → verify in one dispatch. **L4 → H200 with `profile=all emulate_l4=true`: 594 s to four green smoke tests** (provision 115 s, deploy 167 s, verify 280 s). First profile healthy 76 s after deploy starts.
- **H200 → L4 with `profile=baseline`: 337 s**; `pause` 53 s. The disk (images, HF cache, adapters, `.env`) survives both swaps; every profile boots offline.
- No H100 VM was free in IN2 on either day; H200 (₹434.97/h, needs ≈ ₹440 `jl status` balance) is the practical fallback.
- Demo-day: if the L4 fails, dispatch `swap-gpu gpu=auto profile=baseline emulate_l4=true` and keep teaching; it is verified ≈ 10 min later.
