# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Multi-LoRA zero-downtime rollout demo (needs the `lora` compose profile).

rollout: concurrent traffic on base / sql-prod / stoploss; counts non-2xx per model and prints the
  sql-prod answer at each phase so the audience sees v1 -> v2 (bad fine-tune) -> v1.
  --swap-mode inline (rehearsal, all-in-one): this script also repoints sql-prod via load_inplace
      through the operator listener (on the VM, or from a laptop through scripts/tunnel.sh).
  --swap-mode none (workshop, laptop side): traffic only; the operator swaps on the VM with
      `scripts/lab.sh lab5 lora-swap v2` / `... v1` (or scripts/remote.sh lab5 lora-swap v2).
compare: load several adapter dirs under temporary names and print answers to 3 fixed prompts
  (used to choose the sql-v2 alpha). Needs the operator listener.

Usage:
  uv run scripts/demo_multilora_rollout.py rollout --swap-mode none --duration 90      # laptop, BASE_URL=http://<vm-ip>
  uv run scripts/demo_multilora_rollout.py rollout --duration 30                       # on the VM (inline swap)
  uv run scripts/demo_multilora_rollout.py compare /adapters/sql-v1 /adapters/sql-v2-a48 /adapters/sql-v2-a64 /adapters/sql-v2-a96
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
    if r.status_code != 200:
        raise SystemExit(f"load_lora_adapter {name} <- {path}: HTTP {r.status_code} {r.text[:300]}")
    return time.perf_counter() - t


async def lora_info(ops: httpx.AsyncClient | None) -> list[str]:
    if ops is None:
        return []
    try:
        # one series per label set; the value is the last time it was seen -> show the newest
        lines = re.findall(r"^vllm:lora_requests_info.*$", (await ops.get("/metrics")).text, re.MULTILINE)
        return sorted(lines, key=lambda line: float(line.rsplit(" ", 1)[1]))[-3:]
    except httpx.HTTPError:
        return []


async def rollout(args, client: httpx.AsyncClient, ops: httpx.AsyncClient | None) -> int:
    counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    stop = asyncio.Event()
    db, q = SQL_CASES[0]
    prompts = {
        "qwen2.5-7b": "Explain what a LoRA adapter is in one sentence.",
        "sql-prod": SQL_PROMPT.format(db=db, q=q),
        "stoploss": "Briefly: what is a stop-loss order?",
    }
    t0 = time.perf_counter()

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
        print(f"[{time.perf_counter() - t0:5.1f}s {tag}] sql-prod -> {text[:160]!r}", flush=True)

    workers = [asyncio.create_task(worker(m)) for m in prompts for _ in range(args.workers)]
    if args.swap_mode == "inline":
        phase = args.duration / 3
        await answer("v1")
        await asyncio.sleep(phase)
        print("metrics:", *await lora_info(ops), sep="\n  ")
        print(f"swap sql-prod -> sql-v2: {await load_adapter(ops, 'sql-prod', args.v2, True):.2f}s")
        await answer("v2")
        await asyncio.sleep(phase)
        print(f"rollback sql-prod -> sql-v1: {await load_adapter(ops, 'sql-prod', args.v1, True):.2f}s")
        await answer("v1 again")
        await asyncio.sleep(phase)
    else:  # traffic only: the swap comes from `lab.sh lab5 lora-swap` on the VM
        print(f"traffic for {args.duration:.0f}s — swap now: Actions → Lab 5 → lora-swap v2, then lora-swap v1 (or scripts/remote.sh lab5 lora-swap v2)")
        while time.perf_counter() - t0 < args.duration:
            await answer("sql-prod")
            await asyncio.sleep(args.sample_every)
        print("metrics:", *(await lora_info(ops) or ["(skipped: no tunnel)"]), sep="\n  ")
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
    ap.add_argument(
        "--metrics-url",
        "--ops-url",
        dest="ops_url",
        default=os.environ.get("METRICS_URL", "http://127.0.0.1:9090"),
        help="operator listener (metrics + LoRA admin); from a laptop: scripts/tunnel.sh",
    )
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("rollout")
    r.add_argument("--swap-mode", choices=["inline", "none"], default="inline")
    r.add_argument("--duration", type=float, default=30)
    r.add_argument("--sample-every", type=float, default=5, help="swap-mode none: seconds between sql-prod samples")
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
        try:
            await ops.get("/metrics", timeout=3)
            reachable = True
        except httpx.HTTPError:
            reachable = False
        if (args.cmd == "compare" or args.swap_mode == "inline") and not reachable:
            print(f"operator listener {args.ops_url} unreachable: open scripts/tunnel.sh (or use --swap-mode none)")
            return 2
        if args.cmd == "compare":
            return await compare(args, client, ops)
        return await rollout(args, client, ops if reachable else None)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
