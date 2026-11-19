# CLAUDE.md — mags-mlops-prod-demo

Demo + lab repo for a 3-hour live-terminal workshop (ISTE STTP, K. J. Somaiya School of Engineering, Mumbai — Thu 3 Dec 2026, 2:00–5:15 PM IST; audience: engineering professors and PG researchers). Teaches production LLM serving with portable primitives: Docker + NVIDIA Container Toolkit + vLLM + Caddy, on a single NVIDIA L4 (24 GB, sm_89) Jarvislabs **VM**, with a GitHub Actions fallback to bigger GPUs.

## Repository
- https://github.com/MagmaCubes1133/mags-mlops-prod-demo — **public**, default branch `main`. Repo and Actions logs are world-readable.
- Log hygiene: never print secrets, VM public IPs, machine ids, SSH commands/hosts, or raw `jl get`/`jl create` JSON in logs, job summaries, or committed docs. Workflows `::add-mask::` every IP/id/host as soon as it is read. Committed docs may contain GPU type, driver, image digests, timings.
- Locally, the Jarvislabs key lives in `.env` as `JARVISLABS_API_KEY` (never read/print it); export it as `JL_API_KEY` for `jl`.

## Read first
- `docs/reference/phase1-verified-facts.md` — pins and vLLM v0.34.0 behaviour verified from source. Treat as ground truth unless a GPU run proves otherwise (then record the correction).
- `docs/reference/gpu-verification-handoff.md` — on-GPU checks A1–F with pass criteria.
- `docs/reference/gpu-fallback-runbook.md` — fallback ladder, `EMULATE_L4`, workflow design, demo-day plan.

## Naming convention
`mags-mlops-prod-demo` everywhere: GitHub repo, compose project (`name:` + `COMPOSE_PROJECT_NAME`), Jarvislabs VM name, registered SSH key name, workflow `concurrency` group, results artifact prefix (`mags-mlops-prod-demo-results-<gpu>-<run>`), container names (`mags-mlops-prod-demo-vllm`, `mags-mlops-prod-demo-caddy`).
Served model name: `qwen2.5-7b`. Adapter aliases: `sql-prod` (points at `/adapters/sql-v1` or `/adapters/sql-v2`), `stoploss`.

## Pins (never float)
- `vllm/vllm-openai:v0.34.0` → pin `@sha256:` digest after first pull; `caddy:2.11.9`; `jarvislabs==0.2.17`
- `Qwen/Qwen2.5-7B-Instruct@a09a35458c702b33eeacc393d103063234e8bc28`
- `Qwen/Qwen2.5-7B-Instruct-AWQ@b25037543e9394b818fdfca67ab2a00ecc7dd641`
- `vindows/qwen2.5-7b-text-to-sql@909715efd1439651aee1f34de37ec3628dbb1945` (sql-v1); sql-v2 = local copy with `lora_alpha` raised (default 256)
- `TIGER-Lab/StopLoss-Qwen2.5-7B-Instruct@acceabf1d1ab6fc95b4d3058eeb6e9ac8d03b446` (stoploss)

## Guardrails
- Ask before: spending >~$5 GPU in one go; destroying any Jarvislabs instance not created in this session; setting/changing repo secrets.
- Pause the VM whenever idle. Final state: exactly one paused L4 VM named `mags-mlops-prod-demo` with images, weights, adapters on disk.
- Never print secrets (`JL_API_KEY`, `GATEWAY_KEY`, `HF_TOKEN`, SSH private key). Never publish vLLM's port 8000; only Caddy faces the network.
- Don't "fix" verified facts back to older vLLM conventions (e.g. `gpu_cache_usage_perc`, `--quantization fp8` on BF16, `guided_json`).

## Where results go
- `docs/verification-results.md` — one row per check ID: status, GPU, driver, image digest, timestamp, evidence excerpt. Corrections to verified facts go at the top.
- `docs/slide-numbers.md` — every measured number the slides quote, with provenance (check ID + file).
- `docs/checkpoint-1.md` — report after Phase A + A1–A7; then stop for confirmation.
- `results/` — benchmark CSVs and markdown tables.

## Quality bar
Lint before commit: `docker compose config` (every profile), `caddy validate` via the caddy image, `actionlint`, `shellcheck`, `ruff`. `python scripts/vram_math.py` must reproduce 7,615,616,512 params and 57,344 B/token. Small, descriptive commits.

## Status
- [x] Phase A scaffold
- [x] Checkpoint 1 (A1–A6 done; A7 GPU swap blocked on balance — see docs/checkpoint-1.md)
- [ ] Phase B verification on L4
- [ ] Fallback dry run (H100)
- [ ] Checkpoint 2
