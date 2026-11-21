# Labs: every step, the scripts behind it, and how to run it

Each lab is one workflow in the **Actions** tab. Pick a step in its dropdown, click **Run workflow**.

- Steps **without a prefix** run on the GPU VM: [`scripts/lab.sh`](../scripts/lab.sh) `<lab> <step> [arg]`, over SSH.
- Steps named **`client-…`** run on a fresh GitHub-hosted runner that calls the VM's public endpoint, like any outside client. Metrics come through an SSH tunnel to the VM's loopback-only port 9090.

Every run prints the same report twice:
- **Live log:** a header naming the scripts it calls, where it runs and the exact command, then the raw output.
- **Run page summary:** pass/fail, the scripts (linked at that commit), the command, highlighted lines, any tables the scripts print, and the full output in a code block.

The raw output is also attached as a `log-…` artifact. The step → scripts map lives in [`.github/lab-steps.tsv`](../.github/lab-steps.tsv), so the reports and this page share one source.

**Run it yourself**, three ways for every step:

| Where you are | Command |
|---|---|
| GitHub (no terminal) | Actions → *Lab N* → step → Run workflow |
| Laptop with `gh` | `scripts/remote.sh <lab> <step> [arg]` (clicks the same button, prints the output) |
| On the GPU host | VM steps: `bash scripts/lab.sh <lab> <step> [arg]` · client steps: the `uv run …` command shown below, with `BASE_URL` and `GATEWAY_KEY` set |

**Test everything:** Actions → **Rehearsal · all labs** runs all 42 steps below in run-sheet order through the same engine, with the real interplay (swaps during rollout traffic, a drain during a stream). It ends with a pass/fail table. Last run: 21 Nov 2026, **42/42 passed in 35.5 min** on the L4 ([run](https://github.com/MagmaCubes1133/mags-mlops-prod-demo/actions/runs/44892418265)).

---

## Lab 0 · Common (any time)

| Step | Runs | What you see |
|---|---|---|
| `status` | [`lab.sh`](../scripts/lab.sh) | GPU, containers, **active profile**, `/health` code, disk, commit |
| `logs vllm` / `logs caddy` | [`lab.sh`](../scripts/lab.sh) | last 50 lines of that container, IPs redacted |
| `restart` | [`lab.sh`](../scripts/lab.sh) | `docker restart` vLLM, waits for `/health` (≈ 60 s) |
| `capture` | [`lab.sh`](../scripts/lab.sh) | boot log + metrics + `nvidia-smi` → `capture-…` artifact |
| `down` | [`lab.sh`](../scripts/lab.sh), [`docker-compose.yml`](../docker-compose.yml) | stops and removes the stack |
| `client-smoke` | [`smoke_test.sh`](../scripts/smoke_test.sh) | 401/403/413/400, `/health`, a stream, every model, metric names: all PASS |

## Lab 1 · First boot (S3, 3.3)

| Step | Runs | What you see |
|---|---|---|
| `up` | [`lab.sh`](../scripts/lab.sh) → [`up.sh`](../scripts/up.sh) `baseline` → [`docker-compose.yml`](../docker-compose.yml) | `HEALTHY` in 40–60 s warm, then `VERIFIED: profile=baseline` and the boot numbers |
| `bootlog` | [`lab.sh`](../scripts/lab.sh) | weights **14.29 GiB**, KV **70,656–78,848 tokens**, max concurrency **8.6–9.6×** at 8k, attention backend |
| `nvidia-smi` | [`lab.sh`](../scripts/lab.sh) | NVIDIA L4, 23,034 MiB, driver 580.196.07 |

Laptop maths for the same numbers: `python3 scripts/vram_math.py` ([`vram_math.py`](../scripts/vram_math.py); also Lab 4 → `vram-math`).

## Lab 2 · Gateway (S3, 3.4)

| Step | Runs | What you see |
|---|---|---|
| `edge-up` | [`lab.sh`](../scripts/lab.sh), [`docker-compose.yml`](../docker-compose.yml), [`Caddyfile`](../Caddyfile) | `caddy: healthy; public /health -> 200` |
| `caddy-validate` | [`lab.sh`](../scripts/lab.sh), [`Caddyfile`](../Caddyfile) | `Valid configuration` (checked inside the pinned Caddy image) |
| `caddy-reload` | [`lab.sh`](../scripts/lab.sh), [`Caddyfile`](../Caddyfile) | zero-downtime reload; `/health` stays 200 |
| `show-config` | [`lab.sh`](../scripts/lab.sh), [`docker-compose.yml`](../docker-compose.yml), [`Caddyfile`](../Caddyfile) | the rendered config, secrets redacted |
| `client-smoke` | [`smoke_test.sh`](../scripts/smoke_test.sh) | every attack gets its code: 401/401/403×4/413/400; `SMOKE OK` |
| `client-stream` | `curl -sN` in [`lab.yml`](../.github/workflows/lab.yml) | the answer arrives word by word; `stream complete: [DONE], finish_reason=stop` |
| `client-structured-output` | [`demo_structured_output.py`](../scripts/demo_structured_output.py) | `guided_json` silently ignored; `structured_outputs` and `json_schema` valid; `RESULT: as documented` |

Client commands: `bash scripts/smoke_test.sh` · `uv run scripts/demo_structured_output.py`.

## Lab 3 · Observability (S3, 3.5)

| Step | Runs | What you see |
|---|---|---|
| `metrics` / `metrics kv_cache` | [`lab.sh`](../scripts/lab.sh) | key `vllm:*` lines (filtered) from the operator listener |
| `client-prefix-cache` | [`demo_prefix_cache.py`](../scripts/demo_prefix_cache.py) | the same 3-turn chat twice; turn-1 TTFT cold → warm; hit ≈ 82% |
| `client-prefix-cache-8k` | [`demo_prefix_cache.py`](../scripts/demo_prefix_cache.py) `--repeat 130` | ~7.9k-token history; bigger cold/warm gap; hit ≈ 83% |
| `prefix-cache` | [`lab.sh`](../scripts/lab.sh) | prefix-cache hit/query counters and rate on the server |

Client commands: `uv run scripts/demo_prefix_cache.py [--repeat 130]`. From a GitHub runner TTFT includes ≈ 200 ms of round trip to an India VM; see [`benchmarks.md`](benchmarks.md) for laptop numbers.

## Break · warm AWQ

| Step | Runs | What you see |
|---|---|---|
| `awq-warm` | [`lab.sh`](../scripts/lab.sh) → [`up.sh`](../scripts/up.sh) `awq` | `VERIFIED: profile=awq`, three warm-up requests 200 |

## Lab 4 · Quantization under load (S4, 4.2)

| Step | Runs | What you see |
|---|---|---|
| `client-bench-pressure` (label `awq`) | [`benchmark_concurrency.py`](../scripts/benchmark_concurrency.py) `--preset pressure` | AWQ: KV peak ≈ 52%, **0 preemptions**, ≈ 82 s; CSV attached |
| `switch baseline` / `awq` / `fp8` / `fp8-kv` | [`lab.sh`](../scripts/lab.sh) → [`up.sh`](../scripts/up.sh) | `VERIFIED: profile=…` plus that variant's boot numbers; exits red on a wrong profile |
| `metrics-watch start` / `stop` | [`lab.sh`](../scripts/lab.sh) | background sampler; `stop` prints peak KV usage and the preemption delta |
| `client-bench-pressure` (label `bf16`) | [`benchmark_concurrency.py`](../scripts/benchmark_concurrency.py) `--preset pressure` | BF16: KV peak **100%**, **6 preemptions**, ≈ 180 s |
| `vram-math` | [`lab.sh`](../scripts/lab.sh) → [`vram_math.py`](../scripts/vram_math.py) | 7,615,616,512 params; 57,344 B/token; the KV budget table |
| `client-bench-sweep` | [`benchmark_concurrency.py`](../scripts/benchmark_concurrency.py) | 1/8/20/32 concurrent; markdown table + CSV |

Client commands: `uv run scripts/benchmark_concurrency.py --label awq-pressure --preset pressure` · `--label awq` (sweep).

## Lab 5 · Multi-LoRA rollout (S4, 4.3)

| Step | Runs | What you see |
|---|---|---|
| `lora-up` | [`lab.sh`](../scripts/lab.sh) → [`up.sh`](../scripts/up.sh) `lora` | `VERIFIED: profile=lora`, adapters `sql-prod`, `stoploss` listed |
| `lora-status` | [`lab.sh`](../scripts/lab.sh) | `/v1/models` with each adapter's path; `lora_requests_info` |
| `make-v2` | [`lab.sh`](../scripts/lab.sh) → [`make_regressed_adapter.py`](../scripts/make_regressed_adapter.py) | the "bad release": sql-v1 with `lora_alpha` 64 |
| `client-lora-rollout` (duration 180) | [`demo_multilora_rollout.py`](../scripts/demo_multilora_rollout.py) `rollout --swap-mode none` | steady traffic on all three models; a `sql-prod` answer sampled every few seconds |
| `lora-swap v2` → `lora-swap v1` (during the rollout) | [`lab.sh`](../scripts/lab.sh) | in-place repoint of `sql-prod`; the samples flip to wrong SQL and back; rollout ends `TOTAL non-2xx during rollout: 0` |
| `client-lora-compare` | [`demo_multilora_rollout.py`](../scripts/demo_multilora_rollout.py) `compare` | sql-v1 vs sql-v2 answers side by side |

Client commands: `uv run scripts/demo_multilora_rollout.py rollout --swap-mode none --duration 180` · `… compare /adapters/sql-v1 /adapters/sql-v2` (needs the tunnel).

## Lab 6 · Graceful drain (S4, 4.4)

| Step | Runs | What you see |
|---|---|---|
| `client-stream` | `curl -sN` in [`lab.yml`](../.github/workflows/lab.yml) | a 900-token answer streaming |
| `drain` (≈ 30 s after the stream starts) | [`lab.sh`](../scripts/lab.sh), [`docker-compose.yml`](../docker-compose.yml) | `draining in-flight requests count=1`; vLLM stops ≈ 26 s; the stream still ends `[DONE]` |
| `restart` | [`lab.sh`](../scripts/lab.sh) (`common restart`) | `HEALTHY` again ≈ 60 s |

## Lifecycle: demo-gpu

[`demo-gpu.yml`](../.github/workflows/demo-gpu.yml): `provision`, `resume`, `deploy`, `verify` (runs `smoke_test.sh` on the VM), `swap-gpu`, `pause`, `destroy`. Resume → verified ≈ 6 min. Steps: [`setup_host.sh`](../scripts/setup_host.sh), [`prefetch_artifacts.sh`](../scripts/prefetch_artifacts.sh), [`up.sh`](../scripts/up.sh), [`smoke_test.sh`](../scripts/smoke_test.sh), with knobs from [`profiles/<GPU>.env`](../profiles/).
