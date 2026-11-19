# Checkpoint 1 — Phase A + platform checks A1–A7 (2026-11-19)

## Status
- **Phase A: done.** All scaffold files are committed. Lint is clean: `docker compose config` for all 4 profiles and `caddy validate` (both run on the L4 VM), actionlint, shellcheck, ruff. `vram_math.py` reproduces 7,615,616,512 params and 57,344 B/token.
- **The workflow has not run yet.** It needs repo secrets (`JL_API_KEY`, `JL_SSH_PRIVATE_KEY`, `GATEWAY_KEY`), which are not set yet and need your approval.

## Platform checks
| Check | Result |
|---|---|
| A1 L4 VM availability | PASS: 8 free in IN2, **₹41.31/h** (≈ $0.49), spot ₹27.54 |
| A2 VM create | PASS: Running in 12 s, SSH about 40 s later |
| A3 Docker + toolkit | PASS: Docker 29.9.2, Compose v5.6.1, toolkit 1.20.1 and the `nvidia` runtime come preinstalled |
| A4 Driver | PASS: **580.196.07**, CUDA 13.0, 23034 MiB, compute capability 8.9. No compatibility flag needed |
| A5 Inbound ports | PASS: **80 and 443 are reachable** from the internet, with no host firewall |
| A6 Billing | Cost accrues pro-rata at ≈ ₹43.6/h, including the disk. **Starting a VM requires a balance of at least 1 hour of its cost** |
| A7 GPU swap | **BLOCKED.** H200 swap refused for insufficient balance; H100 has 0 free. Region lock confirmed. Pause/resume on the same L4 works (33 s / 16 s), the disk stays intact, and **the machine id changes on every resume** |

## Corrected facts (details in `verification-results.md`)
1. **A100, A100-80GB and A30 are offered only as containers, not VMs.** H100 VMs had 0 free. In IN2, the only usable non-L4 VMs today are **H200** (₹434.97/h). RTX-PRO6000 VMs are in IN1, so they need a fresh create.
2. Prices are in **INR**.
3. A resume always returns a new machine id. The workflow already re-derives the id by name.
4. The image reports CUDA 13.0.2, not 13.0.3. This has no impact.

## Budget risk (needs your decision)
- The Jarvislabs balance is **₹398.83 (≈ $4.70)**. Spend in this session so far is ₹10.56 (≈ $0.13).
- Phase B on L4 needs about 3–5 GPU-hours, roughly ₹130–220.
- The H100/H200 dry run (F) and the cross-GPU swap test (A7) each need **at least ₹513** in the account, because of the 1-hour minimum balance.
- **Demo day:** keep the balance above ₹520 (≈ $6.20), or the H200 fallback cannot start.

## Next (after your OK)
1. Set the repo secrets.
2. Run Phase B on L4 (B–E).
3. Top up the account, then re-run A7 with an H200 swap and run F.

The VM is **paused** on L4 with the images, weights, adapters and `.env` on disk.
