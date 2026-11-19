#!/usr/bin/env python3
"""VRAM budget for Qwen2.5-7B-Instruct: parameter count, KV bytes/token, KV capacity per config.

Usage: python scripts/vram_math.py [--config path/to/config.json] [--gpu-gib 22.49] [--util 0.90]
Without --config it uses the pinned Qwen2.5-7B-Instruct values (rev a09a354).
"""

import argparse
import json
from pathlib import Path

QWEN25_7B = {
    "hidden_size": 3584,
    "intermediate_size": 18944,
    "num_hidden_layers": 28,
    "num_attention_heads": 28,
    "num_key_value_heads": 4,
    "vocab_size": 152064,
    "tie_word_embeddings": False,
}
GIB = 1024**3


def param_count(c: dict) -> int:
    h, i, n_layers, v = c["hidden_size"], c["intermediate_size"], c["num_hidden_layers"], c["vocab_size"]
    head_dim = h // c["num_attention_heads"]
    kv = c["num_key_value_heads"] * head_dim
    attn = (h * h + h) + 2 * (h * kv + kv) + h * h  # q (+bias), k/v (+bias), o (no bias)
    mlp = 3 * h * i  # gate, up, down
    per_layer = attn + mlp + 2 * h  # + 2 RMSNorm weights
    embed = v * h * (1 if c.get("tie_word_embeddings") else 2)  # embed_tokens + lm_head
    return n_layers * per_layer + h + embed  # + final norm


def kv_bytes_per_token(c: dict, dtype_bytes: int = 2) -> int:
    head_dim = c["hidden_size"] // c["num_attention_heads"]
    return 2 * c["num_hidden_layers"] * c["num_key_value_heads"] * head_dim * dtype_bytes  # K and V


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="HF config.json (default: pinned Qwen2.5-7B values)")
    ap.add_argument("--gpu-gib", type=float, default=22.49, help="GiB visible to CUDA (L4 ≈ 22.49)")
    ap.add_argument("--util", type=float, default=0.90, help="--gpu-memory-utilization")
    ap.add_argument("--overhead-gib", type=float, default=2.0, help="activations + CUDA graphs + context")
    a = ap.parse_args()
    c = json.loads(Path(a.config).read_text()) if a.config else QWEN25_7B

    params = param_count(c)
    kv16, kv8 = kv_bytes_per_token(c, 2), kv_bytes_per_token(c, 1)
    if not a.config:  # self-check against the verified facts
        assert params == 7_615_616_512, params
        assert kv16 == 57_344, kv16

    print(f"params            {params:,}")
    print(f"KV bytes/token    {kv16:,} B BF16 ({kv16 / 1024:.0f} KiB), {kv8:,} B FP8")
    print(f"8k-token sequence {8192 * kv16 / 2**20:,.0f} MiB BF16")
    budget = a.gpu_gib * a.util - a.overhead_gib
    print(f"\nbudget = {a.gpu_gib} GiB x {a.util} - {a.overhead_gib} GiB overhead = {budget:.2f} GiB")
    print(f"{'config':<14}{'weights GiB':>12}{'KV GiB':>9}{'KV tokens':>11}{'8k seqs':>9}")
    awq_gib = 5_570_747_392 / GIB  # pinned AWQ checkpoint size (embed + lm_head stay fp16)
    embed_params = c["vocab_size"] * c["hidden_size"] * (1 if c.get("tie_word_embeddings") else 2)
    fp8_gib = (params + embed_params) / GIB  # 1 B/param, but embed + lm_head stay BF16
    rows = [
        ("BF16", params * 2 / GIB, kv16),
        ("BF16+FP8KV", params * 2 / GIB, kv8),
        ("FP8 weights", fp8_gib, kv16),
        ("AWQ", awq_gib, kv16),
        ("AWQ+FP8KV", awq_gib, kv8),
    ]
    for name, w, per_tok in rows:
        kv_gib = budget - w
        toks = int(kv_gib * GIB / per_tok)
        print(f"{name:<14}{w:>12.2f}{kv_gib:>9.2f}{toks:>11,}{toks // 8192:>9}")


if __name__ == "__main__":
    main()
