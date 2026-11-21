# Benchmarks

Every number the workshop slides quote, measured on one **NVIDIA L4** (24 GB, sm_89) with **vLLM v0.34.0**, Qwen2.5-7B-Instruct, `MAX_MODEL_LEN=8192`, `GPU_MEMORY_UTILIZATION=0.90`.
Measured 19–20 Nov 2026 on a Jarvislabs L4 VM (driver 580.196.07, CUDA 13.0). Raw data: [`results/`](../results/). "calc" means computed by [`scripts/vram_math.py`](../scripts/vram_math.py), not measured.

Reproduce: `uv run scripts/benchmark_concurrency.py --label <name>` (sweep) or `--preset pressure`; boot numbers come from `bash scripts/lab.sh lab1 bootlog`.

## Model maths (calc)

| Quantity | Value |
|---|---|
| Parameters | 7,615,616,512 (matches the HF index) |
| KV bytes per token, BF16 / FP8 | 57,344 B (56 KiB) / 28,672 B |
| KV for one 8k-token sequence | 448 MiB |
| Weights BF16 / FP8 / AWQ | 14.19 / 8.11 / 5.19 GiB |

## Memory and capacity (boot log)

| Quantity | BF16 | FP8 (online) | AWQ | BF16 + LoRA |
|---|---|---|---|---|
| Weights in VRAM | 14.29 GiB | 8.17 GiB | 5.29 GiB | 14.59 GiB |
| KV-cache tokens | 70,656 (cold) – 78,848 (warm) | 182,272 | 237,568 | 53,248 |
| Max concurrent 8k chats | 8.62× | 22.25× | 29.0× | 6.5× |

- BF16 at vLLM's default `--gpu-memory-utilization` (1.0): 96,256 KV tokens (7.03 GiB).
- BF16 + `--kv-cache-dtype=fp8`: 114,688 tokens. AWQ + fp8 KV: **448,512 tokens (13.27 GiB pool), 54.75× at 8k**.
- fp8 KV switches the attention backend from FLASH_ATTN to FLASHINFER; AWQ keeps its Marlin kernels.
- Plain `--quantization fp8` logs `WARNING [weight_utils.py:383] --quantization fp8 is deprecated for online quantization; use --quantization fp8_per_tensor instead.` and runs exactly as `fp8_per_tensor` (`CutlassFP8ScaledMMLinearKernel`, 112 layers quantized, same weights and KV numbers).

## Latency and throughput

Sweep: 256-token answers, 1/8/20/32 concurrent streams ([`results/bench-{bf16,fp8,awq}.csv`](../results/)).

| Quantity | BF16 | FP8 | AWQ |
|---|---|---|---|
| ITL p50, single stream | 56.5 ms (floor 50.8) | 34.0 ms | 18.8 ms |
| ITL p50, 32 concurrent | 64.2 ms | 37.1 ms | 22.7 ms |
| Throughput, 32 concurrent | 484 tok/s | 832 tok/s | 1,295 tok/s |

At 32 × 256 tokens, BF16 peaks at 13% KV usage with 0 preemptions: short answers never stress memory.

## Memory pressure

`--preset pressure`: 32 concurrent requests, each a 3,011-token prompt with a unique first block (no prefix sharing) and 1,024 output tokens ([`results/bench-{bf16,awq}-pressure.csv`](../results/)).

| Quantity | BF16 | AWQ |
|---|---|---|
| Peak KV usage | **100%** | 52.5% |
| Preemptions | **6** | 0 |
| Time with requests waiting | **110.6 s** | 29.2 s |
| TTFT p50 / p95 | 14.2 / 110.9 s | 16.7 / 30.2 s |
| ITL p50 | 79.6 ms | 49.2 ms |
| Throughput | 182 tok/s | 400 tok/s |
| Wall time | 179.5 s | 81.8 s |

Both variants peak at 29 waiting requests. That peak is the prefill queue, not memory: chunked prefill admits at most 2,048 tokens per step. Compare *time waiting* and preemptions instead.

## Prefix cache

`scripts/demo_prefix_cache.py` sends the same 3-turn chat twice (cold, then warm).

| History | Turn-1 TTFT cold → warm | Hit rate |
|---|---|---|
| ~2.4k tokens (default) | 709 → 127 ms | 81.8% |
| ~7.9k tokens (`--repeat 130`) | 2,247 → 133 ms (≈ 17×) | 83.0% |

## Gateway, rollout, drain

| Quantity | Value |
|---|---|
| Caddy overhead on TTFT | 0 ms (123.4 vs 123.4 ms) |
| LoRA in-place swap under load: requests / non-2xx | 1,199 / 0 |
| `sql-v2` regression | `lora_alpha` 64: confident, wrong SQL (α ≥ 96 gives `nan` / gibberish) |
| Graceful drain with a stream in flight | vLLM stops in 26 s; the 900-token stream completes |

## Platform and timings

| Quantity | Value |
|---|---|
| L4 `memory.total` / compute capability | 23,034 MiB / 8.9 |
| vLLM image pull | 136 s, 10.0 GB compressed → 36.3 GB on disk |
| Full prefetch (image + BF16 + AWQ + 2 adapters) | ≈ 4.5 min |
| Cold start to `/health` (first compile) / warm restart | 123 s / 40–61 s |
| Profile switch via GitHub Actions (dispatch → done) | 99–128 s |
| Jarvislabs L4 VM (Nov 2026) | ₹41.31/h (≈ $0.49/h); ≈ ₹43.6/h with a 200 GB disk; create → Running 12 s |
| Fallback round trip, L4 → H200 → L4 (same disk) | 594 s to verified on H200, 337 s back |
