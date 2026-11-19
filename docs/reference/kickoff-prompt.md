Prompt for Claude Code — mags-mlops-prod-demo repo + GPU verification

Before you paste: (1) you're in your local clone of https://github.com/MagmaCubes1133/mags-mlops-prod-demo with the starter files (CLAUDE.md, docs/reference/*.md) added but uncommitted; (2) export JL_API_KEY=... in the shell you launch Claude Code from; (3) uv tool install jarvislabs==0.2.17, an SSH keypair for the VM (ssh-keygen -t ed25519 -f ~/.ssh/mags_jl -N ""), and its public half registered: jl ssh-key add ~/.ssh/mags_jl.pub --name mags-mlops-prod-demo; (4) gh auth status is green with push access to the repo. Then paste everything below the line.

You are building and verifying the demo repository for a 3-hour live-terminal workshop I'm teaching on 3 Dec 2026, 2:00–5:15 PM IST (ISTE STTP at K. J. Somaiya School of Engineering, Mumbai; audience = engineering professors and PG researchers). The repo is https://github.com/MagmaCubes1133/mags-mlops-prod-demo (public, default branch main, already has an initial commit with a placeholder README, a broad .gitignore, and .github/workflows/.gitkeep). It must let participants clone and reproduce every lab, and it must let ME bring the whole stack up on a Jarvislabs GPU VM from GitHub Actions, switching GPU tier by changing one workflow input if an L4 VM is unavailable.

Start by reading CLAUDE.md and everything in docs/reference/ (Phase 1 verified facts, the on-GPU verification checklist with check IDs A1–F, and the GPU fallback runbook). Those files and this prompt agree; if you find a conflict, this prompt wins and you note it.

Step 0 — reconcile and commit the starter files (do this first, before anything else)
git status / git remote -v — confirm origin is MagmaCubes1133/mags-mlops-prod-demo and you're on main, up to date with origin/main (git pull --ff-only).
If the starter zip created a nested mags-mlops-prod-demo/mags-mlops-prod-demo/ directory, move its contents to the repo root and remove the empty nest.
.gitignore merge: the repo's original .gitignore (from the initial commit) is the base — restore it with git checkout origin/main -- .gitignore if the starter overwrote it — then append the starter's extra rules (adapters/*, !adapters/.gitkeep, .cache/, id_*) plus these negations, because the repo's *.env / .env.* rules would otherwise silently ignore our non-secret per-GPU profiles: !profiles/*.env. Verify with git check-ignore -v profiles/L4.env (must print nothing once the file exists) and git check-ignore -v .env (must be ignored). Note the repo already ignores *.safetensors, models/, outputs/, logs/ — keep weights and adapters out of git; keep results/ (CSV/markdown) tracked.
Replace docs/reference/kickoff-prompt.md (an older draft) with this prompt verbatim. Commit only the starter files (CLAUDE.md, docs/reference/, .gitignore, adapters/.gitkeep) as chore: add workshop context and conventions and push. Then add a short "Repository" section to CLAUDE.md (URL, public visibility, log-hygiene rule below) in the same or next commit.
The existing README describes a generic training/registry project — replace it in Phase A with the workshop README described below.
Public-repo hygiene (the repo and its Actions logs are world-readable)
Never print secrets, the VM public IP, the machine id, SSH commands, or jl get/jl create JSON verbatim in workflow logs or job summaries. In the workflow, echo "::add-mask::$VALUE" every IP, machine id and SSH host as soon as it's read, and write only masked/redacted values to $GITHUB_STEP_SUMMARY.
Pass the machine id between jobs via job outputs only after masking, or re-derive it with jl list --json | jq by name inside each job.
Never commit .env, keys, jl config, or files under ~/.config. Committed docs may contain GPU type, driver version, image digests and timings — not IPs or ids.
Set secrets with gh secret set <NAME> --repo MagmaCubes1133/mags-mlops-prod-demo (ask me first, as below).
Naming convention (apply everywhere)

mags-mlops-prod-demo is the single name for: the GitHub repo, the docker compose project (name: key in compose and COMPOSE_PROJECT_NAME), the Jarvislabs VM (--name mags-mlops-prod-demo), the registered SSH key name, the workflow concurrency group, the results artifact prefix (mags-mlops-prod-demo-results-<gpu>-<run>), and container names (mags-mlops-prod-demo-vllm, mags-mlops-prod-demo-caddy). Served model name stays qwen2.5-7b; adapter aliases stay sql-prod, stoploss (with sql-v1/sql-v2 as directories).

Work in this order and keep a task list. Commit after each phase with clear messages. Ask me before (a) any action that spends more than ~$5 of GPU time in one go, (b) destroying any Jarvislabs instance you didn't create in this session, or (c) setting repo secrets.

Fixed facts (already verified against vLLM v0.34.0 source — do not "fix" these back to older conventions)

Pins

vLLM image: vllm/vllm-openai:v0.34.0 (CUDA 13.0.3 → host driver R580+; on R535/R570 set VLLM_ENABLE_CUDA_COMPATIBILITY=1). After first pull, pin by @sha256: digest everywhere.
Caddy: caddy:2.11.9
Base: Qwen/Qwen2.5-7B-Instruct revision a09a35458c702b33eeacc393d103063234e8bc28 (15,231,233,024 bytes)
AWQ: Qwen/Qwen2.5-7B-Instruct-AWQ revision b25037543e9394b818fdfca67ab2a00ecc7dd641
LoRA v1 (sql-v1): vindows/qwen2.5-7b-text-to-sql revision 909715efd1439651aee1f34de37ec3628dbb1945 (r=16, α=32, q/k/v/o/gate/up/down). Prompt format: Convert the following natural language question to SQL:\n\nDatabase: <db>\nQuestion: <q>\n\nSQL:
LoRA tenant 2 (stoploss): TIGER-Lab/StopLoss-Qwen2.5-7B-Instruct revision acceabf1d1ab6fc95b4d3058eeb6e9ac8d03b446 (r=16, q/k/v/o)
LoRA v2 (sql-v2) = generated locally: copy sql-v1 dir and set lora_alpha 32 → 256 in adapter_config.json (vLLM scales by α/r → deterministic simulated bad fine-tune). Script: scripts/make_regressed_adapter.py --alpha 256.
Jarvislabs CLI: uv tool install jarvislabs==0.2.17; auth via JL_API_KEY.

vLLM v0.34.0 behaviour that differs from most blog posts

Metrics: vllm:kv_cache_usage_perc (NOT gpu_cache_usage_perc), vllm:num_requests_running, vllm:num_requests_waiting, vllm:num_preemptions_total, vllm:time_to_first_token_seconds, vllm:inter_token_latency_seconds (ITL), vllm:request_time_per_output_token_seconds (TPOT), vllm:e2e_request_latency_seconds, vllm:prompt_tokens_total, vllm:generation_tokens_total, vllm:request_success_total{finished_reason}, vllm:lora_requests_info{running_lora_adapters,waiting_lora_adapters,max_lora}, vllm:cache_config_info. Counters have _total on the wire; histograms _bucket/_sum/_count; labels model_name, engine.
Quantization: AWQ → just serve the AWQ repo (--quantization awq_marlin is an accepted alias; Marlin auto-selected). Online FP8 → --quantization fp8_per_tensor (plain --quantization fp8 on a BF16 checkpoint ERRORS now). FP8 KV → --kv-cache-dtype fp8; on sm_89 this switches attention backend away from FlashAttention (FlashInfer/Triton); on Ampere (sm_80) FP8 KV is unsupported — skip it.
Memory: extensible KV cache is default on CUDA → --gpu-memory-utilization defaults to 1.0; we set 0.90 explicitly for teaching. Default KV block size is 64. --kv-cache-memory-bytes 4G (human-readable) pins the KV pool (disables extensible KV).
Structured outputs: extra_body={"structured_outputs": {"json": schema}} or response_format={"type":"json_schema","json_schema":{...}}. Legacy guided_json is silently ignored (HTTP 200, unconstrained) — the demo shows both. Backends: auto|xgrammar|guidance.
LoRA: --enable-lora --max-loras 4 --max-lora-rank 16 --max-cpu-loras 8 --lora-modules '{"name":"sql-prod","path":"/adapters/sql-v1","base_model_name":"qwen2.5-7b"}' '{"name":"stoploss","path":"/adapters/stoploss"}'; env VLLM_ALLOW_RUNTIME_LORA_UPDATING=1 enables POST /v1/load_lora_adapter {"lora_name","lora_path","load_inplace"} and POST /v1/unload_lora_adapter {"lora_name"}. Reusing a name requires load_inplace: true → this is our zero-downtime rollback primitive (clients always call alias sql-prod; operator repoints it v1→v2→v1). Incompatible with --api-server-count > 1.
vLLM --api-key only guards /v1, /v2, /inference, /cohere; /metrics, /health, /load stay open → Caddy must block them publicly.
Graceful drain: --shutdown-timeout 30 + compose stop_grace_period: 45s.
Determinism: send temperature: 0; load tests use ignore_eos: true + fixed max_tokens.
Always pass --revision <sha> and --served-model-name qwen2.5-7b; serve with --max-model-len 8192 on L4.

Caddy 2.11.9

reverse_proxy auto-flushes text/event-stream; still set flush_interval -1 explicitly. Never use encode on /v1/* (breaks SSE flushing).
Bearer auth via header matcher + respond 401; request_body { max_size 256KB } → 413; respond 403 for /metrics, /load, /v1/load_lora_adapter, /v1/unload_lora_adapter on the public site; expose /metrics only on an internal listener (e.g. :9090) on the Docker network. vLLM is on an internal bridge network with no published port.

Jarvislabs

Template instances are containers → cannot run Docker. Always jl create ... --vm. VMs need ≥1 SSH key registered (jl ssh-key add <pub> --name <n>), storage ≥100 GB.
jl gpus --json entries: gpu_type, num_free_devices, price_per_hour, workload_type ("vm"|"container").
jl create --gpu <T> --vm --storage 200 --name mags-mlops-prod-demo --yes --json (blocks until Running), jl get <id> --json, jl ssh <id> --print-command --json, jl exec <id> -- sh -lc '...', jl pause|resume|destroy <id> --yes --json, jl list --json. jl resume <id> --gpu <T> changes GPU, is region-locked, may return a NEW machine id.
GPU strings/regions: IN2 = L4, A100, A100-80GB, A30, H100, H200; IN1 = RTX-PRO6000.
Fallback chain default: L4,H100,A100-80GB,A100,RTX-PRO6000. On Ampere (A100/A30) FP8 becomes Marlin W8A16 and FP8-KV is skipped. On non-L4 GPUs default EMULATE_L4=true → add --kv-cache-memory-bytes <L4 KV size from rehearsal> so KV-capacity demos match the L4 slides.
If any CLI flag above turns out wrong, check jl <cmd> --help, adapt, and note the correction in docs/verification-results.md.
Phase A — scaffold the repo (no GPU needed)

Create:

mags-mlops-prod-demo/
├── CLAUDE.md                     # (already present) keep updated with conventions + current status
├── docs/reference/               # (already present) phase1-verified-facts.md, gpu-verification-handoff.md, gpu-fallback-runbook.md — read-only context
├── README.md                     # prerequisites, Jarvislabs VM + on-prem setup, lab runbook (Labs 1–5), troubleshooting
├── docker-compose.yml            # services: vllm (profiles: baseline, awq, fp8, lora), caddy; internal network; healthchecks; stop_grace_period
├── .env.example                  # GATEWAY_KEY, HF_TOKEN, MODEL_REVISION, MAX_MODEL_LEN, GPU_MEMORY_UTILIZATION, KV_CACHE_MEMORY_BYTES, FP8_MODE, ...
├── profiles/{L4,H100,A100,A100-80GB,RTX-PRO6000,H200,A30}.env
├── Caddyfile
├── adapters/.gitkeep             # filled by prefetch
├── scripts/
│   ├── prefetch_artifacts.sh     # docker pulls (record digests), hf download --revision for both models + both adapters, make sql-v2
│   ├── make_regressed_adapter.py
│   ├── benchmark_concurrency.py  # asyncio + httpx/openai; concurrency sweep; p50/p95 TTFT & ITL, total tok/s; scrape /metrics before/after (kv_cache_usage_perc peak, num_preemptions_total delta); CSV + markdown table to results/
│   ├── demo_multilora_rollout.py # concurrent base/sql-prod/stoploss traffic + scripted v1→v2→v1 load_inplace swap, counts non-2xx
│   ├── demo_structured_output.py # guided_json (silently ignored) vs structured_outputs vs response_format json_schema
│   ├── smoke_test.sh             # 401/403/413/400 checks, one streaming call, one call per model/adapter, metrics grep
│   └── vram_math.py              # KV bytes/token + budget table from config.json (must reproduce 7,615,616,512 params and 57,344 B/token)
├── .github/workflows/demo-gpu.yml
├── docs/verification-results.md  # table per check: status, GPU, driver, image digest, timestamp, raw log excerpt
├── docs/slide-numbers.md         # every measured number the slides need, with provenance
└── docs/checkpoint-1.md          # short report after Phase A + checks A1–A7 (see Checkpoints)

Workflow demo-gpu.yml: workflow_dispatch inputs action (provision|deploy|verify|swap-gpu|pause|resume|destroy), gpu (auto|L4|H100|A100-80GB|A100|RTX-PRO6000|H200|A30, default L4), fallback_chain, profile (baseline|awq|fp8|lora|all), emulate_l4 (bool), machine_id (optional; else find by name mags-mlops-prod-demo). Secrets: JL_API_KEY, JL_SSH_PRIVATE_KEY, GATEWAY_KEY, optional HF_TOKEN. Jobs: select-gpu (jq over jl gpus --json, first VM with free devices in chain, job summary table of availability) → provision (idempotent; resume if exists) → deploy (install NVIDIA Container Toolkit if absent, checkout this commit on the VM, write .env from profiles/<gpu>.env, prefetch, docker compose --profile ... up -d, wait for /health ≤15 min) → verify (smoke_test.sh, upload results/ artifact). swap-gpu = pause → resume --gpu → redeploy with new machine id. destroy requires an input that equals the machine name. concurrency: mags-mlops-prod-demo, timeout-minutes: 45. Follow the public-repo hygiene rules above (mask IPs/machine ids/SSH hosts; never echo secrets).

Lint everything you can locally: docker compose config for every profile, caddy validate (via the caddy image), actionlint, shellcheck, ruff, python scripts/vram_math.py (assert the two numbers above). Commit.

Phase B — GPU verification on Jarvislabs (L4 first)

Drive Jarvislabs directly from your terminal with jl (and/or trigger the workflow with gh workflow run demo-gpu.yml --repo MagmaCubes1133/mags-mlops-prod-demo once secrets exist). Execute and record every check below in docs/verification-results.md; put every number a slide will quote in docs/slide-numbers.md.

A. Platform: L4 VM free count + price (jl gpus --json); VM create time; docker/toolkit present; nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv; whether the VM public IP accepts inbound 443/80 (else document SSH-tunnel fallback); billing granularity; GPU swap test: pause L4 VM → jl resume --gpu H100 → disk intact? new machine id? B. Boot & memory on L4: image pull time + digest; BF16 boot log lines (weights GiB, KV GiB/tokens, max concurrency, CUDA-graph memory, attention backend) with default util AND with 0.90; cold-start time to /health; single-stream BF16 ITL (theory floor 50.8 ms/token). C. Quantization on L4: AWQ log shows Marlin with no "Falling back to unoptimized AWQ kernels" (ITL floor 18.6 ms); fp8_per_tensor boots without OOM; plain --quantization fp8 fails with "no longer supports online quantization" (save text for a slide); --kv-cache-dtype fp8 backend name + KV tokens; benchmark sweep (concurrency 1/8/20/32 × BF16/AWQ/FP8) → CSV. D. Multi-LoRA: boot with adapters, /v1/models lists all; tune sql-v2 α (128/256/512) so it's visibly worse but not garbage on 3 fixed prompts; in-place swap v1→v2→v1 under load with zero non-2xx; lora_requests_info under load; mixed-adapter batch succeeds. E. Edge: SSE streams through Caddy incrementally (TTFT via Caddy ≈ direct); 401/403/413/400 behave; guided_json vs structured_outputs; graceful drain mid-stream. F. Fallback dry run: run the workflow end-to-end with gpu=H100 (emulate_l4=true): provision → deploy → verify → destroy. Record time-to-healthy.

Cost hygiene: pause the VM whenever you're not actively testing; at the end, leave ONE paused L4 VM named mags-mlops-prod-demo with all images, weights, and adapters on disk (that's the demo-day machine), and destroy everything else. Report total spend.

Checkpoints (stop and report to me at each)
Checkpoint 1 — after Phase A is committed and platform checks A1–A7 are done: write docs/checkpoint-1.md (what passed/failed, L4 VM availability + price, driver, open ports, whether resume-with-different-GPU works, any corrected facts — no IPs or machine ids), push to main, and stop. I'll confirm before you spend on Phase B benchmarks.
Checkpoint 2 — after Phase B is complete: the "Done when" items below, pushed to GitHub.
Done when
All Phase A files exist and lint clean; workflow runs green for provision/deploy/verify/pause on L4 and the H100 dry run.
docs/verification-results.md has a row for every check with pass/fail and evidence; any fact above that turned out wrong is flagged at the top with the corrected value.
docs/slide-numbers.md lists: L4 memory.total, driver, weights GiB (BF16/AWQ/FP8), KV GiB + tokens per config, max concurrency, cold-start time, single-stream ITL per quant, benchmark p50/p95 table, LoRA swap error count, chosen sql-v2 α + sample outputs.
Everything pushed to main on MagmaCubes1133/mags-mlops-prod-demo.
Final message: a short summary of what passed, what failed, what changed vs these facts, total GPU spend, and the paused machine id.
