# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Concurrency sweep against the gateway: p50/p95 TTFT and ITL, total output tok/s,
peak vllm:kv_cache_usage_perc and vllm:num_preemptions_total delta per level.

Usage (on the VM):
  uv run scripts/benchmark_concurrency.py --label bf16 --concurrency 1 8 20 32
  uv run scripts/benchmark_concurrency.py --label bf16-pressure --preset pressure
    pressure = ~3k-token prompts, max_tokens 1024, 32 concurrent, 1 round. Each request starts with its own
    nonce (system message), so no two requests share the first 64-token KV block and prefix caching cannot
    hide the pressure. BF16 on L4 (~70k KV tokens) cannot hold 32 x ~4k -> requests wait / get preempted.
Writes results/bench-<label>.csv (appends) and prints a markdown table.
Env: GATEWAY_KEY (or read from .env), BASE_URL (default http://localhost; laptop: http://<vm-ip>),
METRICS_URL (default http://127.0.0.1:9090 — on a laptop that needs scripts/tunnel.sh; else metrics are skipped).
"""

import argparse
import asyncio
import csv
import json
import os
import re
import statistics
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PROMPT = "Write a detailed technical explanation of how a CPU cache hierarchy works, with examples."


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.split(" #")[0].strip())


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


def metric(text: str, name: str) -> float:
    """Sum all series of a metric (labels differ per engine/model)."""
    vals = re.findall(rf"^{re.escape(name)}(?:{{[^}}]*}})? ([0-9.eE+-]+)$", text, re.MULTILINE)
    return sum(float(v) for v in vals)


def messages_for(args) -> list[dict]:
    if args.preset != "pressure":
        return [{"role": "user", "content": PROMPT}]
    # unique first block per request; ~3k tokens of body (PROMPT is ~18 tokens)
    return [
        {"role": "system", "content": f"Request {uuid.uuid4().hex}. You are a helpful assistant."},
        {"role": "user", "content": (PROMPT + " ") * 185},
    ]


async def one_request(client: httpx.AsyncClient, args) -> dict:
    body = {
        "model": args.model,
        "messages": messages_for(args),
        "max_tokens": args.max_tokens,
        "temperature": 0,
        "ignore_eos": True,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    t0 = time.perf_counter()
    ttft, last, gaps, tokens, prompt_tokens, status = None, None, [], 0, 0, 0
    async with client.stream("POST", "/v1/chat/completions", json=body) as r:
        status = r.status_code
        async for line in r.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            if chunk.get("usage"):
                tokens = chunk["usage"]["completion_tokens"]
                prompt_tokens = chunk["usage"]["prompt_tokens"]
            if chunk.get("choices") and chunk["choices"][0]["delta"].get("content"):
                now = time.perf_counter()
                if ttft is None:
                    ttft = now - t0
                else:
                    gaps.append(now - last)
                last = now
    return {"status": status, "ttft": ttft, "gaps": gaps, "tokens": tokens, "prompt_tokens": prompt_tokens}


async def sample_kv(ops: httpx.AsyncClient, peak: list[float], stop: asyncio.Event) -> None:
    # peak[0] max kv usage, peak[1] max requests waiting, peak[2] seconds with >= 1 request waiting
    last = time.perf_counter()
    while not stop.is_set():
        try:
            text = (await ops.get("/metrics")).text
            now = time.perf_counter()
            waiting = metric(text, "vllm:num_requests_waiting")
            peak[0] = max(peak[0], metric(text, "vllm:kv_cache_usage_perc"))
            peak[1] = max(peak[1], waiting)
            peak[2] += (now - last) if waiting > 0 else 0
            last = now
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)


async def scrape(ops: httpx.AsyncClient | None) -> str | None:
    if ops is None:
        return None
    try:
        return (await ops.get("/metrics")).text
    except httpx.HTTPError:
        return None


async def run_level(args, conc: int) -> dict:
    headers = {"Authorization": f"Bearer {os.environ['GATEWAY_KEY']}"}
    limits = httpx.Limits(max_connections=conc + 4)
    async with (
        httpx.AsyncClient(base_url=args.base_url, headers=headers, timeout=600, limits=limits) as client,
        httpx.AsyncClient(base_url=args.metrics_url, timeout=5) as ops_client,
    ):
        before = await scrape(ops_client if args.metrics_url else None)
        ops = ops_client if before is not None else None  # no tunnel → skip metrics cleanly
        peak, stop = [0.0, 0.0, 0.0], asyncio.Event()
        sampler = asyncio.create_task(sample_kv(ops, peak, stop)) if ops else None
        sem = asyncio.Semaphore(conc)

        async def bounded():
            async with sem:
                return await one_request(client, args)

        t0 = time.perf_counter()
        results = await asyncio.gather(*(bounded() for _ in range(conc * args.rounds)))
        wall = time.perf_counter() - t0
        stop.set()
        if sampler:
            await sampler
        after = await scrape(ops)

    ok = [r for r in results if r["status"] == 200]
    ttfts = [r["ttft"] * 1000 for r in ok if r["ttft"] is not None]
    itls = [g * 1000 for r in ok for g in r["gaps"]]
    return {
        "label": args.label,
        "concurrency": conc,
        "requests": len(results),
        "non_2xx": len(results) - len(ok),
        "ttft_p50_ms": round(pct(ttfts, 50), 1),
        "ttft_p95_ms": round(pct(ttfts, 95), 1),
        "itl_p50_ms": round(pct(itls, 50), 2),
        "itl_p95_ms": round(pct(itls, 95), 2),
        "itl_mean_ms": round(statistics.fmean(itls), 2) if itls else float("nan"),
        "total_tok_s": round(sum(r["tokens"] for r in ok) / wall, 1),
        "prompt_tok_mean": round(statistics.fmean(r["prompt_tokens"] for r in ok)) if ok else "",
        "kv_usage_peak": round(peak[0], 3) if after is not None else "",
        "waiting_peak": int(peak[1]) if after is not None else "",
        "waiting_s": round(peak[2], 1) if after is not None else "",
        "preemptions_delta": int(
            metric(after, "vllm:num_preemptions_total") - metric(before, "vllm:num_preemptions_total")
        )
        if after is not None and before is not None
        else "",
        "wall_s": round(wall, 1),
    }


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="e.g. bf16, awq, fp8")
    ap.add_argument("--preset", choices=["sweep", "pressure"], default="sweep")
    ap.add_argument("--concurrency", type=int, nargs="+")
    ap.add_argument("--rounds", type=int, help="requests per level = concurrency x rounds")
    ap.add_argument("--max-tokens", type=int)
    ap.add_argument("--model", default="qwen2.5-7b")
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost"))
    ap.add_argument(
        "--metrics-url",
        default=os.environ.get("METRICS_URL", "http://127.0.0.1:9090"),
        help="operator listener; from a laptop open scripts/tunnel.sh first ('' = skip metrics)",
    )
    args = ap.parse_args()
    pressure = args.preset == "pressure"
    args.concurrency = args.concurrency or ([32] if pressure else [1, 8, 20, 32])
    args.rounds = args.rounds or (1 if pressure else 3)
    args.max_tokens = args.max_tokens or (1024 if pressure else 256)
    print(f"prompt: {PROMPT!r}" + (" x185, unique prefix per request (~3k tokens)" if pressure else "") + f", max_tokens={args.max_tokens}")
    if not asyncio.run(scrape(httpx.AsyncClient(base_url=args.metrics_url, timeout=3) if args.metrics_url else None)):
        print(
            f"metrics: {args.metrics_url or '-'} unreachable -> skipping kv peak / preemptions (open scripts/tunnel.sh)"
        )

    rows = []
    for conc in args.concurrency:
        row = asyncio.run(run_level(args, conc))
        print(json.dumps(row), flush=True)
        rows.append(row)

    out = ROOT / "results" / f"bench-{args.label}.csv"
    out.parent.mkdir(exist_ok=True)
    new = not out.exists()
    with out.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        if new:
            w.writeheader()
        w.writerows(rows)

    cols = list(rows[0])
    print("\n| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    print(f"\nappended to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
