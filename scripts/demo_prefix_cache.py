# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Prefix caching on a multi-turn chat (check E6, lab3).

Sends the same 3-turn conversation (≈2k-token system prompt) twice and prints TTFT per turn.
Pass 2 reuses the cached KV blocks of the shared prefix, so its TTFT drops. If the operator listener
is reachable (on the VM, or scripts/tunnel.sh on a laptop) it also prints the prefix-cache hit ratio;
otherwise run `scripts/lab.sh lab3 prefix-cache` on the VM.

Usage: uv run scripts/demo_prefix_cache.py              (BASE_URL=http://<vm-ip> from a laptop)
       uv run scripts/demo_prefix_cache.py --repeat 130 (~8k-token history: the "recompute" row)
A per-run nonce opens the system prompt, so pass 1 is cold even if an earlier run cached the policy text.
"""

import argparse
import json
import os
import re
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
POLICY = (
    "You are the support assistant for a university research computing cluster. "
    "Rules: GPU jobs must request a partition, a wall time, and a memory limit. "
    "Interactive sessions are limited to 4 hours. Storage quotas: home 50 GB, scratch 2 TB purged after 30 days. "
)
TURNS = [
    "How long can an interactive session run?",
    "And what happens to files in scratch after a month?",
    "Summarise both answers in one sentence.",
]


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.split(" #")[0].strip())


def counters(ops: httpx.Client) -> tuple[float, float] | None:
    try:
        text = ops.get("/metrics").text
    except httpx.HTTPError:
        return None

    def total(name: str) -> float:
        return sum(float(v) for v in re.findall(rf"^{name}(?:{{[^}}]*}})? (\S+)$", text, re.MULTILINE))

    return total("vllm:prefix_cache_hits_total"), total("vllm:prefix_cache_queries_total")


def ttft(c: httpx.Client, messages: list[dict]) -> tuple[float, str, int]:
    body = {
        "model": "qwen2.5-7b",
        "messages": messages,
        "max_tokens": 48,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    t0, first, text, prompt_tokens = time.perf_counter(), None, [], 0
    with c.stream("POST", "/v1/chat/completions", json=body) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                chunk = json.loads(line[6:])
                if chunk.get("usage"):
                    prompt_tokens = chunk["usage"]["prompt_tokens"]
                if not chunk.get("choices"):
                    continue
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    first = first or time.perf_counter()
                    text.append(delta)
    return (first - t0) * 1000, "".join(text), prompt_tokens


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=40, help="policy repeats: 40 ~ 2.4k tokens, 130 ~ 7.9k (largest that fits 3 turns in 8192)")
    system = f"[session {uuid.uuid4().hex}] " + POLICY * ap.parse_args().repeat
    load_env()
    base = os.environ.get("BASE_URL", "http://localhost")
    headers = {"Authorization": f"Bearer {os.environ['GATEWAY_KEY']}"}
    with (
        httpx.Client(base_url=base, headers=headers, timeout=120) as c,
        httpx.Client(base_url=os.environ.get("METRICS_URL", "http://127.0.0.1:9090"), timeout=3) as ops,
    ):
        before = counters(ops)
        results = []
        for p in (1, 2):
            messages = [{"role": "system", "content": system}]
            for i, q in enumerate(TURNS, 1):
                messages.append({"role": "user", "content": q})
                ms, answer, n = ttft(c, messages)
                messages.append({"role": "assistant", "content": answer})
                results.append((p, i, ms))
                print(f"pass {p} turn {i}: {n} prompt tokens, TTFT {ms:7.1f} ms  {answer[:60]!r}")
        after = counters(ops)

    print("\n| turn | TTFT pass 1 (cold) ms | TTFT pass 2 (warm) ms |\n|---|---|---|")
    for i in range(1, len(TURNS) + 1):
        a, b = (ms for p, t, ms in results if t == i)
        print(f"| {i} | {a:.1f} | {b:.1f} |")
    if before and after and after[1] > before[1]:
        hits, queries = after[0] - before[0], after[1] - before[1]
        print(f"\nprefix cache during this run: {hits:.0f} / {queries:.0f} tokens hit = {100 * hits / queries:.1f}%")
    else:
        print("\nprefix-cache counters: metrics unreachable -> run `scripts/lab.sh lab3 prefix-cache` on the VM")


if __name__ == "__main__":
    main()
