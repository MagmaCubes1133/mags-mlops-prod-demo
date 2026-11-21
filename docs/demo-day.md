# Demo-day run sheet — Thu 3 Dec 2026, 2:00–5:15 PM IST

One page for presenters. Numbers come from [`benchmarks.md`](benchmarks.md) (L4, vLLM v0.34.0); step timings from [`lab-actions.md`](lab-actions.md).
Every VM step has two forms: **SSH** `L <lab> <step> [arg]` (fastest) or **gh** `scripts/remote.sh <lab> <step> [arg]` (no SSH needed, 35–130 s).

## Button-only mode (recommended)

No terminal on stage. In the repo's **Actions** tab each lab is one workflow; pick a step in its dropdown and click **Run workflow**. Steps named `client-…` run on a fresh GitHub runner that calls the public endpoint; the rest run `scripts/lab.sh` on the VM. Nothing needs updating after a resume: each run looks up the VM itself. Wait for a VM step to go green before the next VM click; `client-…` steps can overlap with anything.

| Segment | Workflow → step, in order | Expect (client run times measured 21 Nov, L4) |
|---|---|---|
| Lab 1 | **Lab 1** → `up` → `bootlog` → `nvidia-smi` · **Lab 4** → `vram-math` | numbers in the table below |
| Lab 2 | **Lab 2** → `edge-up` → `caddy-validate` → `caddy-reload` → `show-config` → `client-smoke` → `client-stream` → `client-structured-output` | smoke all PASS incl. metrics (≈ 30 s); stream ends `[DONE], finish_reason=stop`; structured: `RESULT: as documented` (≈ 40 s) |
| Lab 3 | **Lab 3** → `client-prefix-cache` → `client-prefix-cache-8k` → `prefix-cache` | hit ≈ 83% (≈ 45 s); warm TTFT is lower but includes ≈ 200 ms runner round trip (see note) |
| BREAK | **Lab 3→4 · Break** → `awq-warm` | `VERIFIED: profile=awq` |
| Lab 4 | **Lab 4** → `client-bench-pressure` (label `awq`) → `switch baseline` → `client-bench-pressure` (label `bf16`); then **Lab 5** → `lora-up` | as in *Lab 4 order*; CSVs attached to each client run |
| Lab 5 | **Lab 5** → `client-lora-rollout` (duration 180) → after ≈ 40 s `lora-swap v2` (`sync` off) → `lora-swap v1` → `client-lora-compare` | answers flip to wrong SQL and back; `TOTAL non-2xx during rollout: 0` (21 Nov: 800 requests, 0) |
| Lab 6 | **Lab 6** → `client-stream` → after ≈ 30 s `drain` → `restart` | drain log `draining in-flight requests count=1`; the stream still ends `[DONE]` |
| Any time | **Lab 0 · Common** → `status` / `logs vllm` / `capture` / `restart` | `active profile: …`, `/health 200` |
| End | **demo-gpu** → `action=pause` | `Paused` |

**TTFT from a runner** includes the round trip from GitHub's datacentre to the VM (≈ 200 ms to an India VM; 21 Nov: single-stream TTFT p50 329 ms vs 98 ms from a laptop in India). Inter-token latency (56.6 ms), throughput (482 tok/s at 32) and KV/preemption numbers match the slides. Quote the slide numbers for TTFT, or say "plus one trip across the world".

## Laptop prerequisites (Windows Git Bash shown; macOS/Linux skip the first line)

```bash
export MSYS_NO_PATHCONV=1 PYTHONUTF8=1      # Git Bash: keep /adapters/... paths intact; UTF-8 output
# .env in the repo root: GATEWAY_KEY=... and JARVISLABS_API_KEY=... (never shown on screen)
gh auth status && uv --version && ls ~/.ssh/mags_jl
export BASE_URL=http://$(scripts/tunnel.sh ip)
L() { ssh -i ~/.ssh/mags_jl "ubuntu@${BASE_URL#http://}" "bash mags-mlops-prod-demo/scripts/lab.sh $*"; }
scripts/tunnel.sh                            # 2nd terminal, keep open: localhost:9090 = metrics + LoRA admin
```

## Before

| When | Check | Pass |
|---|---|---|
| T-24 h (2 Dec) | `jl gpus --json` (use `PYTHONIOENCODING=utf-8`): L4 VM free count in IN2; H100/H200 free | L4 ≥ 1 free; note fallback options |
| T-24 h | `jl status` balance | **≥ ₹1,000** (H200 start needs ≈ ₹440 of it). Paused disk is billed daily; top up if close |
| T-24 h | `gh workflow run demo-gpu.yml -f action=resume -f gpu=L4 -f profile=baseline` | green: resume + deploy + SMOKE OK (≈ 4 min) |
| T-24 h | Actions → **Rehearsal · all labs** | every row ✅ in the final table (≈ 36 min) |
| T-24 h | dashboard: the VM shows the reserved IP; `scripts/tunnel.sh ip` prints the same address as last time | same IP across pause/resume |
| T-24 h | `gh workflow run demo-gpu.yml -f action=pause -f gpu=L4` | VM `Paused` |
| T-60 min | same `resume` run | green, SMOKE OK |
| T-60 min | **Lab 0** → `status` | `active profile: baseline`, `/health 200` |
| T-60 min | **Lab 0** → `client-smoke` (or laptop `bash scripts/smoke_test.sh`, tunnel open) | all PASS, metrics checks PASS (not SKIP) |
| T-60 min | **Lab 3** → `client-prefix-cache` once | warms the cache path; ignore the numbers |

## Per segment

**Fallback swap** (if the L4 dies mid-segment): `gh workflow run demo-gpu.yml -f action=swap-gpu -f gpu=H200 -f profile=<P> -f emulate_l4=true` (`gpu=H100` if `jl gpus` shows one free). One dispatch runs swap, deploy and verify: **≈ 10 min to green** (measured 594 s). Keep teaching from the slides meanwhile. Afterwards, laptop users restart `tunnel.sh`; the reserved IP should survive a GPU swap (check `scripts/tunnel.sh ip` once at T-24 h). The buttons need nothing.

| Segment | VM step (SSH · gh) | Laptop | Expect | Fallback `P` |
|---|---|---|---|---|
| **S3-01a** About me (60–90 s) | — | — | — | — |
| **Lab 1** first boot (3.3) | `L lab1 up` · `remote.sh lab1 up` (94 s); then `lab1 bootlog`, `lab1 nvidia-smi` | `python3 scripts/vram_math.py` | HEALTHY 40–60 s warm; weights **14.29 GiB**; KV **70,656–78,848 tok**, **8.6–9.6×** at 8k; L4 23034 MiB, driver 580.196.07; calc 7,615,616,512 params, 57,344 B/token | `baseline` |
| **Lab 2** gateway (3.4) | `lab2 edge-up` → `lab2 caddy-validate` → `lab2 caddy-reload` → `lab2 show-config` (each ≈ 40 s via gh) | `bash scripts/smoke_test.sh`; `curl -N` a stream; `uv run scripts/demo_structured_output.py` | 401/401/403×4/413/400 all PASS; reload → `/health 200`; Caddy adds **0 ms** TTFT (123.4 vs 123.4); `guided_json` → 200 with prose (ignored) | `baseline` |
| **Lab 3** observability (3.5) | `lab3 metrics kv_cache` · `lab3 prefix-cache` | `uv run scripts/demo_prefix_cache.py`, then `--repeat 130` (S3-20b) | 2.4k history: turn 1 **709 → 127 ms**, hit ≈ 82%; ~8k history: **2,247 → 133 ms**, hit 83% | `baseline` |
| **BREAK** | at the *start* of the break: `L break awq-warm` · `remote.sh break awq-warm` (128 s) | — | `HEALTHY profile=awq`, `VERIFIED: profile=awq`, 3× prewarm 200 in ≈ 0.2 s | `awq` |
| **Lab 4** quantization + load (4.2) | see order below | see order below | see order below | `awq`, then `baseline` (read the caveat) |
| **Lab 5** multi-LoRA (4.3) | `lab5 lora-status`; `lab5 make-v2` (α 64, ≈ 35 s); during traffic: `lab5 lora-swap v2` … `lab5 lora-swap v1` (≈ 35 s each with `SYNC=false`) | `uv run scripts/demo_multilora_rollout.py rollout --swap-mode none --duration 180` | sql-prod answer flips v1 → wrong SQL on invented tables → v1; **TOTAL non-2xx: 0**; `lora_requests_info` shows `sql-prod,stoploss` together | `lora` |
| Lab 6 drain (4.4), if time | start a long `curl -N`, then `lab6 drain` → `common restart` | the stream | vLLM stops in ≈ 26 s; stream finishes (`[DONE]`); restart healthy ≈ 42 s | `baseline` |
| End | `gh workflow run demo-gpu.yml -f action=pause -f gpu=L4` | — | `Paused` | — |

### Lab 4 order (AWQ is warm from the break)

1. **AWQ pressure.** Laptop: `uv run scripts/benchmark_concurrency.py --label awq-pressure --preset pressure` (tunnel open). **≈ 82 s.** Expect KV peak **52.5%**, **0 preemptions**, waiting 29.2 s, TTFT p95 ≈ 30 s, ≈ 400 tok/s.
2. **Switch to BF16:** `L lab4 switch baseline` (≈ 50–60 s) · `remote.sh lab4 switch baseline` (≈ 100 s). The step must print `VERIFIED: profile=baseline`; it exits non-zero otherwise.
3. **BF16 pressure:** `--label bf16-pressure --preset pressure`. **≈ 180 s.** Expect KV peak **100%**, **6 preemptions**, waiting **110.6 s**, TTFT p95 ≈ 110 s, ≈ 182 tok/s. Point at *time waiting* and preemptions. The "waiting peak 29" appears on both variants (prefill queue).
4. **Switch to LoRA while you talk through S4-10/S4-11:** `L lab5 lora-up` · `remote.sh lab5 lora-up` (≈ 133 s). Expect KV 53,248 tok, 6.5×, and the adapters listed.

Static numbers for slides only (no live switch): FP8 weights 8.17 GiB / 182,272 tok; AWQ + fp8 KV 448,512 tok, **54.75×**; fp8 KV → FLASHINFER backend.

**Fallback caveat (Lab 4):** `emulate_l4=true` pins *every* profile to the BF16 L4 pool (≈ 70k tokens), AWQ included, so AWQ would preempt too. Without emulation, an H200 never preempts. Either way the BF16-vs-AWQ contrast is gone. On a fallback GPU, show the recorded L4 rows (`results/bench-{bf16,awq}-pressure.csv`) and say why.

## Likely questions

- **Does continuous batching still happen with chunked prefill?** Yes. vLLM V1 gives each step a 2,048-token budget on the L4 (`max_num_batched_tokens`). Requests already writing go first, 1 token each; new prompts fill the rest in chunks. Cost: a new person's first word is a bit later; nobody else freezes. (S3-09a)
- **How don't users' requests get mixed up?** Tokens are packed into one batch with a map (start/end, positions, block lists, request id). Linear layers are row-independent, attention follows each request's own block list, and each token is routed back by request id. Prefix blocks are shared only when the content is identical. Caveats: per-tenant `cache_salt` against prefix-cache timing probes; temperature 0 isn't bit-identical under load unless `VLLM_BATCH_INVARIANT=1` (slower; drops AWQ off Marlin). (S3-09b)
- **What's a sequence / what does `--max-num-seqs` limit?** One request's running token stream (prompt + words so far); n = 1 → one sequence. `--max-num-seqs` caps sequences per step (default 256); on the L4 the KV pool binds first: ~9 long chats on BF16, ~29 on AWQ. (S4-05)
