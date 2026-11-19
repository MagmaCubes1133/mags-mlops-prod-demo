# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Concurrency sweep against the gateway: p50/p95 TTFT and ITL, total output tok/s,
peak vllm:kv_cache_usage_perc and vllm:num_preemptions_total delta per level.

Usage (on the VM):
  uv run scripts/benchmark_concurrency.py --label bf16 --concurrency 1 8 20 32
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


async def one_request(client: httpx.AsyncClient, model: str, max_tokens: int) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "ignore_eos": True,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    t0 = time.perf_counter()
    ttft, last, gaps, tokens, status = None, None, [], 0, 0
    async with client.stream("POST", "/v1/chat/completions", json=body) as r:
        status = r.status_code
        async for line in r.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            if chunk.get("usage"):
                tokens = chunk["usage"]["completion_tokens"]
            if chunk.get("choices") and chunk["choices"][0]["delta"].get("content"):
                now = time.perf_counter()
                if ttft is None:
                    ttft = now - t0
                else:
                    gaps.append(now - last)
                last = now
    return {"status": status, "ttft": ttft, "gaps": gaps, "tokens": tokens}


async def sample_kv(ops: httpx.AsyncClient, peak: list[float], stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            peak[0] = max(peak[0], metric((await ops.get("/metrics")).text, "vllm:kv_cache_usage_perc"))
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
        peak, stop = [0.0], asyncio.Event()
        sampler = asyncio.create_task(sample_kv(ops, peak, stop)) if ops else None
        sem = asyncio.Semaphore(conc)

        async def bounded():
            async with sem:
                return await one_request(client, args.model, args.max_tokens)

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
        "kv_usage_peak": round(peak[0], 3) if after is not None else "",
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
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 8, 20, 32])
    ap.add_argument("--rounds", type=int, default=3, help="requests per level = concurrency x rounds")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--model", default="qwen2.5-7b")
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost"))
    ap.add_argument(
        "--metrics-url",
        default=os.environ.get("METRICS_URL", "http://127.0.0.1:9090"),
        help="operator listener; from a laptop open scripts/tunnel.sh first ('' = skip metrics)",
    )
    args = ap.parse_args()
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
