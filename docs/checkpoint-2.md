# Checkpoint 2 — Phase B + fallback round trip (2026-11-19/20)

**Status: all checks run. Every check passes or has a recorded correction.** Details: `docs/verification-results.md`. Numbers for the slides: `docs/slide-numbers.md`. Lab step latencies: `docs/lab-actions.md`.

## Done-when checklist
- [x] Phase A files exist and lint clean (`docker compose config` every profile, `caddy validate`, `actionlint`, `shellcheck`, `ruff check`; `vram_math.py` reproduces 7,615,616,512 / 57,344).
- [x] `demo-gpu` green on L4 (resume / deploy / verify / pause) and on the H200 round trip (`swap-gpu` H200 with `profile=all emulate_l4=true` → `swap-gpu` L4 → `pause`).
- [x] `verification-results.md`: a row for every check A1–F; corrections C-1 … C-11 at the top.
- [x] `slide-numbers.md` complete.
- [x] `lab.yml` green for every step on L4; `lab-actions.md` filled in.
- [x] Runbook corrected (VM-only ladder, balance rule, `--flag=value`, measured round trip).
- [x] End state: one paused L4 VM `mags-mlops-prod-demo`, with images, weights, adapters and `.env` on disk.

## Changes against the verified facts
- C-8: a running VM is not reserved. Start rule = `jl status` balance ≥ 1 h list price.
- C-9: `--quantization fp8` on BF16 only warns (deprecated) and runs as fp8_per_tensor. It does not error.
- C-10: sql-v2 α 256 → **64**. α ≥ 96 gives `nan` / gibberish.
- C-11: `VLLM_EXTRA_ARGS` values must use `--flag=value`.
- B3: the default `--gpu-memory-utilization` is 1.0 (confirmed). We keep 0.90.

## Spend
Round start ₹2,398.61 → end ₹2,200.19 (`jl status`, paused): **₹198.42** of the ₹1,200 cap.

## Addendum (2026-11-20): four extra measurements
B-add-1 … B-add-4 in `verification-results.md`, numbers in `slide-numbers.md`. Spend: ₹2,200.19 → ₹2,149.55 = **₹50.64** (≈ 1 h of L4). Running total for Checkpoint 2: **₹249.06**. Committed docs and git history were audited: they contain no machine ids.
