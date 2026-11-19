# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Multi-LoRA zero-downtime rollout demo (needs the `lora` compose profile).

rollout (default): concurrent traffic on base / sql-prod / stoploss while the operator repoints the
  alias sql-prod: v1 -> v2 (bad fine-tune) -> v1 (rollback) with load_inplace. Counts non-2xx per model,
  samples vllm:lora_requests_info mid-run, shows the SQL answer from each phase.
compare: load several adapter dirs under temporary names and print answers to 3 fixed prompts
  (used to choose the sql-v2 alpha).

Usage (on the VM):
  uv run scripts/demo_multilora_rollout.py rollout --duration 30
  uv run scripts/demo_multilora_rollout.py compare /adapters/sql-v1 /adapters/sql-v2-a128 /adapters/sql-v2
Traffic goes through Caddy (BASE_URL); adapter admin + metrics go through the operator listener (OPS_URL).
"""

import argparse
import asyncio
import collections
import os
import re
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SQL_PROMPT = "Convert the following natural language question to SQL:\n\nDatabase: {db}\nQuestion: {q}\n\nSQL:"
SQL_CASES = [
    ("employees(id, name, dept, salary)", "What is the average salary per department?"),
    ("orders(id, customer_id, total, created_at)", "How many orders were placed in 2024?"),
    ("students(id, name), grades(student_id, course, score)", "List names of students with any score above 90."),
]


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.split(" #")[0].strip())


async def complete(c: httpx.AsyncClient, model: str, prompt: str, max_tokens: int = 64) -> httpx.Response:
    return await c.post(
        "/v1/completions",
        json={"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0},
    )


async def load_adapter(ops: httpx.AsyncClient, name: str, path: str, inplace: bool) -> float:
    t = time.perf_counter()
    r = await ops.post("/v1/load_lora_adapter", json={"lora_name": name, "lora_path": path, "load_inplace": inplace})
    r.raise_for_status()
    return time.perf_counter() - t


async def rollout(args, client: httpx.AsyncClient, ops: httpx.AsyncClient) -> int:
    counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    stop = asyncio.Event()
    db, q = SQL_CASES[0]
    prompts = {
        "qwen2.5-7b": "Explain what a LoRA adapter is in one sentence.",
        "sql-prod": SQL_PROMPT.format(db=db, q=q),
        "stoploss": "Briefly: what is a stop-loss order?",
    }

    async def worker(model: str) -> None:
        while not stop.is_set():
            try:
                r = await complete(client, model, prompts[model], 32)
                counts[model][r.status_code] += 1
            except httpx.HTTPError as e:
                counts[model][type(e).__name__] += 1

    async def answer(tag: str) -> None:
        r = await complete(client, "sql-prod", prompts["sql-prod"])
        text = r.json()["choices"][0]["text"].strip() if r.status_code == 200 else f"HTTP {r.status_code}"
        print(f"[{tag}] sql-prod -> {text[:160]!r}")

    workers = [asyncio.create_task(worker(m)) for m in prompts for _ in range(args.workers)]
    phase = args.duration / 3
    await answer("v1")
    await asyncio.sleep(phase)
    m = (await ops.get("/metrics")).text
    print("metrics:", *re.findall(r"^vllm:lora_requests_info.*$", m, re.MULTILINE)[:2], sep="\n  ")
    print(f"swap sql-prod -> sql-v2: {await load_adapter(ops, 'sql-prod', args.v2, True):.2f}s")
    await answer("v2")
    await asyncio.sleep(phase)
    print(f"rollback sql-prod -> sql-v1: {await load_adapter(ops, 'sql-prod', args.v1, True):.2f}s")
    await answer("v1 again")
    await asyncio.sleep(phase)
    stop.set()
    await asyncio.gather(*workers)

    bad = 0
    for model, c in counts.items():
        non2xx = sum(n for k, n in c.items() if k != 200)
        bad += non2xx
        print(f"{model:<12} {dict(c)}  non-2xx={non2xx}")
    print(f"TOTAL non-2xx during rollout: {bad}")
    return 1 if bad else 0


async def compare(args, client: httpx.AsyncClient, ops: httpx.AsyncClient) -> int:
    for i, path in enumerate(args.paths):
        name = f"cmp-{i}"
        await load_adapter(ops, name, path, True)
        print(f"\n=== {path} (as {name})")
        for db, q in SQL_CASES:
            r = await complete(client, name, SQL_PROMPT.format(db=db, q=q), 96)
            print(f"- {q}\n  {r.json()['choices'][0]['text'].strip()!r}")
        await ops.post("/v1/unload_lora_adapter", json={"lora_name": name})
    return 0


async def main() -> int:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost"))
    ap.add_argument("--ops-url", default=os.environ.get("OPS_URL", "http://127.0.0.1:9090"))
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("rollout")
    r.add_argument("--duration", type=float, default=30)
    r.add_argument("--workers", type=int, default=4, help="concurrent workers per model")
    r.add_argument("--v1", default="/adapters/sql-v1")
    r.add_argument("--v2", default="/adapters/sql-v2")
    c = sub.add_parser("compare")
    c.add_argument("paths", nargs="+", help="adapter dirs as seen inside the vLLM container")
    args = ap.parse_args()
    if args.cmd is None:
        args = ap.parse_args(["rollout"])

    headers = {"Authorization": f"Bearer {os.environ['GATEWAY_KEY']}"}
    async with (
        httpx.AsyncClient(base_url=args.base_url, headers=headers, timeout=120) as client,
        httpx.AsyncClient(base_url=args.ops_url, headers=headers, timeout=120) as ops,
    ):
        return await (compare if args.cmd == "compare" else rollout)(args, client, ops)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
