#!/usr/bin/env python3
"""Smoke-test the synthetic seed for the HTML prototype.

Runs in CI to verify the seed generator produced a coherent dataset:
- 50+ rows in the pipeline array
- 3+ deadlines populated
- 1+ blocked row

Exits 0 on PASS, 1 on FAIL. Prints a one-line summary.
"""
import json
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parents[2] / "synthetic-data" / "seed.json"


def main() -> int:
    if not SEED.exists():
        print(f"FAIL: {SEED} not found", file=sys.stderr)
        return 1
    try:
        data = json.loads(SEED.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: invalid JSON: {e}", file=sys.stderr)
        return 1

    pipeline = data.get("pipeline", [])
    if len(pipeline) < 50:
        print(f"FAIL: seed has only {len(pipeline)} rows (need 50+)", file=sys.stderr)
        return 1

    deadlines = sum(1 for r in pipeline if r.get("deadline"))
    if deadlines < 3:
        print(f"FAIL: only {deadlines} deadline-bearing roles (need 3+)", file=sys.stderr)
        return 1

    blocked = sum(1 for r in pipeline if r.get("status") == "blocked")
    if blocked < 1:
        print("FAIL: no blocked rows in seed", file=sys.stderr)
        return 1

    print(f"seed_ok {len(pipeline)} roles, {deadlines} deadlines, {blocked} blocked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
