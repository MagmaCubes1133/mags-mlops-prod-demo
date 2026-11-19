# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx>=0.27"]
# ///
"""Structured outputs on vLLM v0.34: the legacy `guided_json` field is silently ignored (HTTP 200,
unconstrained text), while `structured_outputs` and `response_format: json_schema` are enforced.

Usage: uv run scripts/demo_structured_output.py   (on the VM; BASE_URL defaults to http://localhost)
"""

import json
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = {
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "country": {"type": "string"},
        "population_millions": {"type": "number"},
    },
    "required": ["city", "country", "population_millions"],
    "additionalProperties": False,
}
MESSAGES = [{"role": "user", "content": "Tell me about Mumbai in one short paragraph."}]


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.split(" #")[0].strip())


def conforms(text: str) -> bool:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return False
    props = SCHEMA["properties"]
    return (
        isinstance(obj, dict)
        and set(obj) == set(props)
        and isinstance(obj["city"], str)
        and isinstance(obj["country"], str)
        and isinstance(obj["population_millions"], (int, float))
    )


def main() -> int:
    load_env()
    base = os.environ.get("BASE_URL", "http://localhost")
    headers = {"Authorization": f"Bearer {os.environ['GATEWAY_KEY']}"}
    variants = {
        "guided_json (legacy, removed)": {"guided_json": SCHEMA},
        "structured_outputs": {"structured_outputs": {"json": SCHEMA}},
        "response_format json_schema": {
            "response_format": {"type": "json_schema", "json_schema": {"name": "city", "schema": SCHEMA}}
        },
    }
    results = {}
    with httpx.Client(base_url=base, headers=headers, timeout=120) as c:
        for name, extra in variants.items():
            body = {"model": "qwen2.5-7b", "messages": MESSAGES, "max_tokens": 128, "temperature": 0, **extra}
            r = c.post("/v1/chat/completions", json=body)
            text = r.json()["choices"][0]["message"]["content"] if r.status_code == 200 else r.text
            results[name] = (r.status_code, conforms(text))
            print(f"\n=== {name}: HTTP {r.status_code}, schema-valid={conforms(text)}\n{text[:300]}")

    expected = {
        "guided_json (legacy, removed)": (200, False),
        "structured_outputs": (200, True),
        "response_format json_schema": (200, True),
    }
    ok = results == expected
    print("\nRESULT:", "as documented" if ok else f"UNEXPECTED {results}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
