# Slide numbers (with provenance)

Every measured number a slide quotes. Source = check ID in `docs/verification-results.md` + file. "calc" = `scripts/vram_math.py` (not measured).

## Platform (L4 VM, Jarvislabs IN2)

| Number | Value | Source |
|---|---|---|
| L4 `memory.total` | 23034 MiB | A4, `nvidia-smi` |
| Driver / CUDA (host) | 580.196.07 / 13.0 | A4 |
| Compute capability | 8.9 | A4 |
| L4 VM price | ₹41.31/h (≈ $0.49/h); spot ₹27.54/h | A1, `jl gpus --json` 2026-11-19 |
| VM create → Running | 12 s (+ ~40 s until SSH) | A2 |
| Effective running cost incl. 200 GB disk | ≈ ₹43.6/h | A6 |
| Pause / resume (same GPU) | 33 s / 16 s (new machine id each resume) | A7 |
| vLLM image pull | 136 s, 10.0 GB compressed → 36.3 GB on disk | B1 |
| Full prefetch (image + BF16 + AWQ + 2 adapters) | ≈ 4.5 min | B1, `results/prefetch.log` on VM |

## Model maths (calc)

| Number | Value | Source |
|---|---|---|
| Parameters | 7,615,616,512 | calc (matches HF index) |
| KV bytes/token BF16 / FP8 | 57,344 B (56 KiB) / 28,672 B | calc |
| 8k-token sequence KV | 448 MiB | calc |
| Weights BF16 / FP8 / AWQ | 14.19 / 8.11 / 5.19 GiB | calc |
| Est. KV tokens @0.90 (BF16 / FP8w / AWQ) | ~76k / ~190k / ~244k | calc — replace with B2/C2/C1 measured |

## Measured on L4 (Phase B — pending)

| Number | Value | Source |
|---|---|---|
| Weights GiB BF16 / AWQ / FP8 | TBD | B2 / C1 / C2 boot log |
| KV GiB + tokens per config | TBD | B2, B3, C1, C2, C4 |
| Max concurrency (8k) | TBD | B2 |
| Cold-start to /health | TBD | B4 |
| Single-stream ITL BF16 / AWQ / FP8 | TBD | B5, C1, C2 |
| Benchmark p50/p95 table | TBD | C5, `results/bench-*.csv` |
| LoRA swap non-2xx count | TBD | D3 |
| sql-v2 α + sample outputs | TBD | D2 |
