# Phase 1 — verified facts (vLLM v0.34.0, checked 2026-11-19)

Verified against vLLM source at tag v0.34.0, Caddy v2.11.9 source, and Hugging Face repo files. Re-check if the image pin changes.
Full human-readable report: https://claude.ai/artifact/4tn8mbQvCSMkoqbNnQ5kBa

## Pins
- `vllm/vllm-openai:v0.34.0` (CUDA 13.0.3 → host driver R580+, or `VLLM_ENABLE_CUDA_COMPATIBILITY=1` on R535/R570). Pin by digest after rehearsal; don't chase v0.35.
- `caddy:2.11.9`
- Qwen/Qwen2.5-7B-Instruct @ a09a35458c702b33eeacc393d103063234e8bc28 (15,231,233,024 B, 4 shards)
- Qwen/Qwen2.5-7B-Instruct-AWQ @ b25037543e9394b818fdfca67ab2a00ecc7dd641 (5,570,747,392 B; 4-bit, group 128, zero-point; embed + lm_head unquantized fp16)
- LoRA sql-v1: vindows/qwen2.5-7b-text-to-sql @ 909715efd1439651aee1f34de37ec3628dbb1945 (r16, α32, q/k/v/o/gate/up/down; 161.5 MB fp32; Apache-2.0)
- LoRA sql-v2: local copy of v1 with lora_alpha 32→256 (vLLM scales by α/r → deterministic simulated regression)
- LoRA stoploss: TIGER-Lab/StopLoss-Qwen2.5-7B-Instruct @ acceabf1d1ab6fc95b4d3058eeb6e9ac8d03b446 (r16, α32, q/k/v/o; 40.4 MB; MIT)

## Architecture math (Qwen2.5-7B-Instruct)
- 28 layers, hidden 3584, 28 Q heads, 4 KV heads, head_dim 128, intermediate 18944, vocab 152064 (untied), max_position 32768, QKV bias
- Params 7,615,616,512 (matches HF index exactly). BF16 14.19 GiB; AWQ 5.19 GiB (2.03 GiB of it = fp16 embed + lm_head)
- KV/token: 2·28·4·128·2 = 57,344 B (56 KiB); FP8 KV 28 KiB; 8k seq = 448 MiB; 32k seq = 1.75 GiB; one 64-token block = 3.5 MiB
- L4: 300 GB/s, ~121 dense BF16 TFLOPS → ridge ~400 FLOP/B; decode floor BF16 50.8 ms/token, AWQ 18.6 ms/token
- Estimated KV capacity at util 0.90 (assumes 22.49 GiB visible, ~2 GiB overhead): BF16 ≈ 76k tok, BF16+FP8KV ≈ 152k, FP8w ≈ 190k, AWQ ≈ 244k, AWQ+FP8KV ≈ 489k

## vLLM v0.34.0 behaviour (differs from older docs/blogs)
- Metrics: `vllm:kv_cache_usage_perc` (not `gpu_cache_usage_perc`); ITL `vllm:inter_token_latency_seconds`; TPOT `vllm:request_time_per_output_token_seconds`; TTFT `vllm:time_to_first_token_seconds`; `vllm:num_requests_running|waiting`; `vllm:num_preemptions_total`; `vllm:prompt_tokens_total`, `vllm:generation_tokens_total`; `vllm:request_success_total{finished_reason}`; `vllm:lora_requests_info{running_lora_adapters,waiting_lora_adapters,max_lora}`; `vllm:cache_config_info`. Counters get `_total`; histograms `_bucket/_sum/_count`; labels `model_name`, `engine`.
- Quantization: AWQ → serve the AWQ repo (`awq`, `awq_marlin`, `auto_awq`, `marlin` all map to AutoAWQConfig; Marlin auto-selected on CUDA, needs cap ≥7.5, group ∈ {-1,32,64,128}). `VLLM_BATCH_INVARIANT=1` / `VLLM_USE_TRITON_AWQ=1` force slow path.
- Online FP8: `--quantization fp8_per_tensor` (per-token activation scales on Ada/Hopper) / `fp8_per_channel` / `fp8_per_block`. `--quantization fp8` on a BF16 checkpoint raises "no longer supports online quantization".
- FP8 KV: `--kv-cache-dtype fp8` (= fp8_e4m3). FlashAttention FP8-KV needs FA3 on sm_90 or FA4 on sm_100 → on L4 vLLM uses FlashInfer or Triton. Triton raises on < sm_89 ("native FP8 requires SM89+") → skip FP8 KV on Ampere. Scales default 1.0 without calibration.
- Ampere (A100/A30): FP8 weights run as Marlin W8A16 (weight-only).
- Memory: extensible KV cache default on CUDA → `--gpu-memory-utilization` defaults to 1.0 (else 0.92). Default block size 64. `--kv-cache-memory-bytes 4G` (human-readable) pins KV pool and disables extensible KV. Default `max_num_seqs` 256 / `max_num_batched_tokens` 2048 on <70 GB GPUs (OpenAI server).
- LoRA flags: `--enable-lora`, `--max-loras` (default 1), `--max-lora-rank` (default 16; allowed 1,8,16,32,64,128,256,320,512), `--max-cpu-loras` (≥ max_loras), `--lora-modules` (JSON `{"name","path","base_model_name"}` or `name=path`), `--lora-target-modules`. Adapter tokenizers ignored.
- Runtime LoRA: `VLLM_ALLOW_RUNTIME_LORA_UPDATING=1` registers `POST /v1/load_lora_adapter {lora_name, lora_path, load_inplace=false}` and `POST /v1/unload_lora_adapter {lora_name}`. Reusing a name without `load_inplace: true` → 400; name equal to base model → 400. `lora_path` may be abs path, `~/…`, or HF repo id. Incompatible with `--api-server-count > 1`. Logs "ONLY for local development" → block at the edge.
- Kernels: Triton shrink/expand LoRA ops behind `PunicaWrapperGPU` (Punica SGMV lineage); fixed GPU slots + LRU CPU cache (not S-LoRA unified paging). 4 rank-16 all-module slots ≈ 0.32 GiB BF16.
- Structured outputs: `extra_body={"structured_outputs": {"json"|"regex"|"choice"|"grammar"|"structural_tag": ...}}` or `response_format={"type":"json_schema",...}`. `guided_*` removed in v0.12 and silently ignored (HTTP 200, unconstrained). Backends auto|xgrammar|guidance; lm-format-enforcer opt-in in v0.34, removed in v0.35.
- Auth: vLLM `--api-key`/`VLLM_API_KEY` guards only `/v1`, `/v2`, `/inference`, `/cohere`; `/metrics`, `/health`, `/load`, `/ping`, `/version` open.
- Drain: `--shutdown-timeout N` (default 0 = abort) + compose `stop_grace_period` > N.
- Sampling: vLLM applies model `generation_config.json` by default → send `temperature: 0`; load tests `ignore_eos: true` + fixed `max_tokens`.
- Benchmark CLI also exists: `vllm bench serve` (`--max-concurrency`, `--percentile-metrics`).

## Caddy 2.11.9
- `reverse_proxy` flushes immediately for `text/event-stream`, unknown Content-Length, and bidirectional h2 (streaming.go `flushInterval()`); `flush_interval -1` is explicit/defensive.
- Don't `encode` on `/v1/*` (compression vs SSE flushing, caddy#6293).
- `request_body { max_size 256KB }` → 413 (v2.10+, experimental). Token guard is vLLM `--max-model-len` (400).

## Jarvislabs
- Template instances are containers → no Docker. Use `--vm` (needs ≥1 SSH key registered; storage ≥100 GB).
- CLI `jarvislabs` 0.2.17, auth `JL_API_KEY`. GPU strings: IN2 = L4, A100, A100-80GB, A30, H100, H200; IN1 = RTX-PRO6000.
- `jl resume <id> --gpu <T>` changes GPU, region-locked, may return new machine id.
