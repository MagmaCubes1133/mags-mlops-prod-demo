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

## Measured on L4 (Phase B, 2026-11-19/20, vLLM v0.34.0)

| Number | Value | Source |
|---|---|---|
| Weights GiB BF16 / FP8 / AWQ / BF16+LoRA | 14.29 / 8.17 / 5.29 / 14.59 | B2 / C2 / C1 / D1 boot log |
| KV tokens @0.90 BF16 / FP8w / AWQ / fp8-KV / LoRA | 70,656 (cold) – 78,848 (warm) / 182,272 / 237,568 / 114,688 / 53,248 | B2, C2, C1, C4, D1 |
| KV tokens BF16 @ default util 1.0 | 96,256 (7.03 GiB) | B3 |
| Max concurrency @8k BF16 / FP8 / AWQ | 8.62× / 22.25× / 29.0× | B2, C2, C1 |
| fp8 KV attention backend | FLASHINFER (BF16 default: FLASH_ATTN) | C4 |
| Cold start to /health (first compile) / warm restart | 123 s / 40–61 s | B4 |
| Profile switch via lab.yml (dispatch→done) | 99–128 s | lab-actions.md |
| ITL p50 single stream BF16 / FP8 / AWQ | 56.5 / 34.0 / 18.8 ms (BF16 floor 50.8) | B5, C5 |
| ITL p50 @32 concurrent BF16 / FP8 / AWQ | 64.2 / 37.1 / 22.7 ms | C5, `results/bench-*.csv` |
| Throughput @32 BF16 / FP8 / AWQ | 484 / 832 / 1,295 tok/s | C5 |
| Peak KV usage @32 × 256 tok (BF16) / preemptions | 13% / 0 | C5 metrics-watch |
| Caddy overhead on TTFT | 0 ms (123.4 vs 123.4) | E1 |
| Prefix cache: turn-1 TTFT cold → warm / hit rate | 709 → 127 ms / 81.8% | E6 |
| Drain: vLLM stop with a stream in flight | 26 s, stream completed (900 tok) | E5 |
| LoRA swap under load: requests / non-2xx | 1,199 / 0 | D3 |
| sql-v2 α | 64 (α ≥ 96 → `nan` / gibberish) | D2 |
| `--quantization fp8` on BF16 | deprecation warning, runs as fp8_per_tensor | C3 / C-9 |

## Phase B addenda (L4, 2026-11-20)

| Number | Value | Source |
|---|---|---|
| KV tokens AWQ + `--kv-cache-dtype=fp8` | **448,512** (13.27 GiB pool), max concurrency **54.75×** at 8k → ~54 full 8k chats, not ~60 (S4-04) | B-add-1, boot log |
| AWQ + fp8 KV attention backend | FLASHINFER; kernels still `MarlinLinearKernel for AutoAWQMarlinLinearMethod` | B-add-1 |
| Pressure preset, 32 × (3,011-tok prompt + 1,024 out), unique first block | **BF16:** KV peak 100%, requests waiting peak 29 for **110.6 s**, **6 preemptions**, TTFT p50/p95 14.2 / 110.9 s, ITL p50 79.6 ms, 182 tok/s, wall **179.5 s** | B-add-2, `results/bench-bf16-pressure.csv` |
| same, AWQ | **AWQ:** KV peak 52.5%, waiting peak 29 for **29.2 s**, **0 preemptions**, TTFT p50/p95 16.7 / 30.2 s, ITL p50 49.2 ms, 400 tok/s, wall **81.8 s** | B-add-2, `results/bench-awq-pressure.csv` |
| Why AWQ also shows "waiting 29" | prefill queue, not memory: chunked prefill admits ≤ 2,048 tokens/step, so 32 × 3k prompts queue briefly on any variant. Quote **time waiting** (110.6 s vs 29.2 s) and preemptions (6 vs 0), not the peak | B-add-2 |
| Prefix cache, ~8k history (recompute row) | 7,854-token prompt: turn-1 TTFT **2,247 ms cold → 133 ms warm** (≈17×); hit rate 83.0% (39,424 / 47,474) | B-add-3, `demo_prefix_cache.py --repeat 130` |
| Plain `--quantization fp8` warning (exact) | `WARNING [weight_utils.py:383] --quantization fp8 is deprecated for online quantization; use --quantization fp8_per_tensor instead.` | B-add-4 |
| …what it actually runs | `Selected CutlassFP8ScaledMMLinearKernel for Fp8PerTensorOnlineLinearMethod`; `Quantizing 112 layers` (qkv_proj, o_proj, gate_up_proj, down_proj × 28, `fp8_per_tensor_static`); weights 8.17 GiB; 182,272 KV tokens: identical to `fp8_per_tensor` | B-add-4 |

Live timing: pressure BF16 ≈ 3 min + AWQ ≈ 1.5 min (switch BF16→AWQ ≈ 1–2 min, do it backstage or during the BF16 discussion).
