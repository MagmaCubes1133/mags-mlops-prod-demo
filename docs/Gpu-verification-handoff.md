# GPU verification handoff

Purpose: everything Phase 1 could NOT verify without a GPU. Each item has the exact command, what "pass" looks like, and where to record the result. Results go in `docs/verification-results.md` (one row per check ID, with GPU type, driver, image digest, timestamp, raw log excerpt).

Pins: see `docs/reference/phase1-verified-facts.md`.

## A. Host / platform  (→ Checkpoint 1)
| # | Check | Command | Pass criteria | Record |
|---|---|---|---|---|
| A1 | Jarvislabs VM availability for L4 in IN2 | `jl gpus --json` → filter `workload_type=="vm"` and `gpu_type=="L4"` | `num_free_devices >= 1` | free count + price/hr; repeat on 1 Dec and the morning of 3 Dec |
| A2 | VM create works | `jl create --gpu L4 --vm --storage 200 --name mags-mlops-prod-demo --yes --json` | JSON has `machine_id`; status Running | machine_id, boot time (s) |
| A3 | Docker + toolkit present | `docker --version; nvidia-ctk --version; docker info \| grep -i runtimes` | docker present; `nvidia` runtime listed (else install toolkit + `nvidia-ctk runtime configure --runtime=docker`) | versions |
| A4 | Host driver vs CUDA 13 image | `nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv` | driver ≥ 580 → normal. 535/570 → set `VLLM_ENABLE_CUDA_COMPATIBILITY=1` and confirm boot | driver, memory.total MiB (expect ~23034), compute_cap 8.9 |
| A5 | Public reachability | from outside: `curl -sk https://<public-ip>/health` once Caddy is up | 200 (or document blocked ports; fallback = SSH tunnel `ssh -L 8443:localhost:443`) | open ports |
| A6 | Billing granularity | dashboard / `jl status --json` | per-minute vs per-second | value |
| A7 | GPU swap on resume (backup path) | `jl pause <id>` then `jl resume <id> --gpu H100 --yes --json` (both IN2) | resumes on new GPU, disk intact (`ls ~/.cache/huggingface/hub`) | new machine_id (may change), time taken |

## B. vLLM boot & memory (L4)
| # | Check | Command | Pass criteria | Record |
|---|---|---|---|---|
| B1 | Image pull time + digest | `time docker pull vllm/vllm-openai:v0.34.0`; `docker inspect --format '{{index .RepoDigests 0}}' vllm/vllm-openai:v0.34.0` | completes | digest, minutes |
| B2 | BF16 boot log numbers | `docker compose --profile baseline up -d`; `docker logs mags-mlops-prod-demo-vllm 2>&1 \| grep -Ei 'model loading took\|kv cache\|maximum concurrency\|cuda graph\|extensible\|attention backend'` | boots with `--max-model-len 8192` | verbatim: weights GiB, KV GiB, KV tokens, max concurrency, graph memory, backend |
| B3 | Default util vs explicit | boot once with no `--gpu-memory-utilization`, once with `0.90` | both boot | KV tokens each |
| B4 | Cold-start time | `docker compose up` → `/health` 200 | < 5 min (set healthcheck start_period) | seconds, cold vs warm (VLLM_CACHE_ROOT reused) |
| B5 | Decode floor sanity | single stream, `max_tokens=256`, `temperature=0` | BF16 ITL ≈ 50–60 ms (floor 50.8 ms) | measured ITL |

## C. Quantization (L4)
| # | Check | Command / flag | Pass criteria | Record |
|---|---|---|---|---|
| C1 | AWQ uses Marlin | `--model Qwen/Qwen2.5-7B-Instruct-AWQ` (and once with `--quantization awq_marlin`) | log names Marlin/AutoAWQMarlin; NO "Falling back to unoptimized AWQ kernels" | log line; ITL (floor 18.6 ms) |
| C2 | Online FP8 | `--quantization fp8_per_tensor` on BF16 model | boots, no OOM during load-then-cast | weights GiB, KV tokens |
| C3 | Legacy flag fails as documented | `--quantization fp8` on BF16 model | fails with "no longer supports online quantization" | error text (slide screenshot) |
| C4 | FP8 KV backend | `--kv-cache-dtype fp8` | boots; backend FlashInfer or Triton (not FlashAttention) | backend name, KV tokens (~2×) |
| C5 | Benchmark matrix | `scripts/benchmark_concurrency.py` at concurrency 1, 8, 20, 32 × BF16, AWQ, FP8 | no 5xx | p50/p95 TTFT & ITL, total tok/s, peak kv_cache_usage_perc, preemptions delta → `results/*.csv` |

## D. Multi-LoRA (L4)
| # | Check | Command | Pass criteria | Record |
|---|---|---|---|---|
| D1 | Boot with adapters | `--enable-lora --max-loras 4 --max-lora-rank 16 --max-cpu-loras 8 --lora-modules '{"name":"sql-prod","path":"/adapters/sql-v1","base_model_name":"qwen2.5-7b"}' '{"name":"stoploss","path":"/adapters/stoploss"}'` + `VLLM_ALLOW_RUNTIME_LORA_UPDATING=1` | `/v1/models` lists base + both | KV tokens lost vs no-LoRA |
| D2 | Regressed v2 visibly worse | `scripts/make_regressed_adapter.py --alpha 256`; 3 fixed SQL prompts, v1 vs v2, temperature 0 | visibly degraded, not pure garbage; try α 128/256/512 | chosen α + sample outputs |
| D3 | In-place swap + rollback under load | traffic on `model=sql-prod`; `POST /v1/load_lora_adapter {"lora_name":"sql-prod","lora_path":"/adapters/sql-v2","load_inplace":true}` then back to v1 | zero non-2xx during both swaps | error count, swap latency |
| D4 | LoRA metric | `curl -s localhost:8000/metrics \| grep lora_requests_info` (inside the network) | shows running adapters | sample line |
| D5 | Mixed batch | concurrent base + sql-prod + stoploss | all succeed | — |

## E. Edge + guardrails
| # | Check | Pass criteria |
|---|---|---|
| E1 | SSE through Caddy streams token-by-token (`curl -N`; TTFT via Caddy ≈ direct) | no buffering |
| E2 | No/invalid bearer → 401; `/metrics`, `/load`, `/v1/load_lora_adapter`, `/v1/unload_lora_adapter` via public site → 403 | as stated |
| E3 | Oversized body → 413 (Caddy); prompt+max_tokens > max_model_len → 400 (vLLM) | both |
| E4 | `guided_json` silently ignored (200, schema violated) vs `structured_outputs` / `response_format json_schema` enforced | capture both |
| E6 | Prefix cache on multi-turn chat: `scripts/demo_prefix_cache.py` sends the same 3-turn chat (≈2k-token system prompt) twice | 2nd pass: TTFT per turn drops; `vllm:prefix_cache_hits_total / vllm:prefix_cache_queries_total` rises; record TTFT cold vs warm and hit ratio |
| E5 | Graceful drain: `--shutdown-timeout 30`, `stop_grace_period: 45s`; `docker compose stop` mid-stream | in-flight request completes |

## F. Fallback GPU dry run (once, before demo day)
Run `.github/workflows/demo-gpu.yml` with `gpu=H100` (or first free non-L4 VM in IN2), `emulate_l4=true`: provision → deploy → verify → destroy. Record time-to-healthy.