#!/usr/bin/env python3
"""Make a deliberately 'bad fine-tune' by copying a LoRA adapter and raising lora_alpha.

vLLM scales the LoRA delta by alpha/r, so alpha 32 -> 256 (r=16) multiplies the update 8x:
deterministic, reproducible degradation with no training.

Usage: python scripts/make_regressed_adapter.py --alpha 256 [--src adapters/sql-v1] [--dst adapters/sql-v2]
"""

import argparse
import json
import shutil
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--alpha", type=int, default=256)
ap.add_argument("--src", default="adapters/sql-v1")
ap.add_argument("--dst", default="adapters/sql-v2")
a = ap.parse_args()

src, dst = Path(a.src), Path(a.dst)
shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".cache"))
cfg_path = dst / "adapter_config.json"
cfg = json.loads(cfg_path.read_text())
old = cfg["lora_alpha"]
cfg["lora_alpha"] = a.alpha
cfg_path.write_text(json.dumps(cfg, indent=2))
print(f"{dst}: lora_alpha {old} -> {a.alpha} (r={cfg['r']}, scale {old / cfg['r']:g} -> {a.alpha / cfg['r']:g})")
