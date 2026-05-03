#!/usr/bin/env python3
"""Cost-ceiling CI gate (FR22 / NFR5).

Reads the last 7 daily telemetry JSONL files from ``telemetry/`` (one file
per UTC day, named ``YYYY-MM-DD.jsonl`` by ``record_extraction``). For
every successful record (``success=True``), collects ``cost_usd`` and
checks the median against a ceiling (default ``$0.03`` per doc per
NFR5). Exits 0 on pass, 1 on breach.

Edge cases:

- No telemetry directory or no JSONL files → exits 0 with a "no
  telemetry data — skipping check" line. The CI workflow can decide
  whether that's a soft pass or a hard fail; the script itself stays
  permissive so empty caches don't redden a PR.
- Fewer than 7 daily files available → uses whatever exists. The 7-day
  window is the *upper* bound, not a minimum.
- Lines with ``success=False`` are ignored — they're failures, not cost
  signals. Lines without a ``cost_usd`` field are skipped silently
  (forward-compat for telemetry-shape additions).

The script is intentionally stdlib-only so CI doesn't need the project
venv to run it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

DEFAULT_TELEMETRY_DIR = Path("telemetry")
DEFAULT_CEILING_USD = 0.03
WINDOW_DAYS = 7


def _iter_recent_files(telemetry_dir: Path, window: int = WINDOW_DAYS) -> list[Path]:
    """Return the ``window`` most recent ``YYYY-MM-DD.jsonl`` files, newest first."""
    if not telemetry_dir.is_dir():
        return []
    candidates = sorted(
        (p for p in telemetry_dir.glob("*.jsonl") if p.is_file()),
        key=lambda p: p.name,
        reverse=True,
    )
    return candidates[:window]


def _collect_costs(files: list[Path]) -> list[float]:
    """Return ``cost_usd`` from every successful record in ``files``."""
    costs: list[float] = []
    for path in files:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    print(
                        f"warning: skipping malformed JSON in {path.name}",
                        file=sys.stderr,
                    )
                    continue
                if not record.get("success"):
                    continue
                cost = record.get("cost_usd")
                if isinstance(cost, int | float):
                    costs.append(float(cost))
    return costs


def check_cost_ceiling(
    telemetry_dir: Path = DEFAULT_TELEMETRY_DIR,
    ceiling_usd: float = DEFAULT_CEILING_USD,
) -> tuple[int, str]:
    """Return ``(exit_code, message)``. Exit 0 = pass; exit 1 = breach."""
    files = _iter_recent_files(telemetry_dir)
    if not files:
        return 0, "no telemetry data — skipping check"

    costs = _collect_costs(files)
    if not costs:
        return 0, "no successful extractions in window — skipping check"

    median = statistics.median(costs)
    if median <= ceiling_usd:
        return 0, (
            f"Cost ceiling OK: 7-day median per-doc cost = ${median:.4f} "
            f"(limit ${ceiling_usd:.2f}, {len(costs)} successful records "
            f"across {len(files)} day(s))"
        )

    return 1, (
        f"Cost ceiling breached: 7-day median per-doc cost = ${median:.4f} "
        f"(limit ${ceiling_usd:.2f}, {len(costs)} successful records "
        f"across {len(files)} day(s))"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "FR22 / NFR5 cost-ceiling gate — fails CI if the rolling 7-day "
            "median per-doc cost exceeds the ceiling."
        ),
    )
    parser.add_argument(
        "--telemetry-dir",
        type=Path,
        default=DEFAULT_TELEMETRY_DIR,
        help="Directory containing YYYY-MM-DD.jsonl telemetry files (default: ./telemetry).",
    )
    parser.add_argument(
        "--ceiling",
        type=float,
        default=DEFAULT_CEILING_USD,
        help="Maximum allowed median per-doc cost in USD (default: 0.03).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    exit_code, message = check_cost_ceiling(args.telemetry_dir, args.ceiling)
    print(message)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
