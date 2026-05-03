#!/usr/bin/env python3
"""Per-agent threshold-gate CI script (Story 2.6 / NFR18).

Reads the latest scorecard JSON committed under ``tests/scorecards/`` and
the threshold map at ``src/doc_extractor/eval/thresholds.yaml``. For every
``(agent, field)`` pair in ``scorecard.per_field``, compares the observed
``match_rate`` against either the explicitly-listed threshold or
``_default``. Exits 0 on pass, 1 on breach with a clear message naming the
agent + field + observed-vs-required values.

Mirrors the shape of ``scripts/check_cost_ceiling.py`` (Story 8.3) so a
contributor familiar with one finds the other:

- Stdlib + ``yaml`` only — the script needs to run in a slim CI image.
- Discovers the scorecard the same way (sorted by filename desc; latest
  wins). Override with ``--scorecard PATH``.
- Permissive on missing inputs: no scorecards directory → exit 0 with
  "no scorecard yet" message so empty caches don't redden a PR. The
  workflow can decide whether absent data should be a hard fail.

Edge cases:

- ``per_field`` is an empty dict → exit 0 with "empty scorecard" skip.
- Agent in scorecard but not listed in YAML → every field uses
  ``_default``.
- Field listed under agent but missing in scorecard → silently skipped
  (we only gate on what was actually measured; a YAML entry isn't a
  promise to measure).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]  # types-PyYAML not yet wired in dev deps

DEFAULT_SCORECARD_DIR = Path("tests/scorecards")
DEFAULT_THRESHOLDS_PATH = Path("src/doc_extractor/eval/thresholds.yaml")
DEFAULT_FALLBACK_KEY = "_default"


def _latest_scorecard(scorecard_dir: Path) -> Path | None:
    """Return the most-recent ``*.json`` scorecard, or ``None`` if directory
    is missing / empty. Sorted by filename desc — same convention as the
    cost-ceiling script."""
    if not scorecard_dir.is_dir():
        return None
    candidates = sorted(
        (p for p in scorecard_dir.glob("*.json") if p.is_file()),
        key=lambda p: p.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _load_thresholds(path: Path) -> dict[str, Any]:
    """Parse the thresholds YAML. Missing file is a hard fail — the gate
    exists for a reason and a typo'd path shouldn't silently pass."""
    if not path.is_file():
        raise FileNotFoundError(f"thresholds file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"thresholds YAML must be a mapping, got {type(data).__name__}"
        )
    return data


def _resolve_threshold(
    thresholds: dict[str, Any],
    agent: str,
    field: str,
) -> float:
    """Resolve the gate threshold for ``(agent, field)``.

    Lookup order: per-agent per-field → _default. Missing _default falls
    back to 0.0 (effectively no gate); the YAML in the repo always sets
    ``_default``, so this fallback is a defensive zero, not a real path.
    """
    agent_block = thresholds.get(agent)
    if isinstance(agent_block, dict):
        value = agent_block.get(field)
        if isinstance(value, int | float):
            return float(value)
    default = thresholds.get(DEFAULT_FALLBACK_KEY)
    if isinstance(default, int | float):
        return float(default)
    return 0.0


def _iter_breaches(
    scorecard: dict[str, Any], thresholds: dict[str, Any]
) -> Iterable[str]:
    """Yield human-readable breach lines for any field below its threshold."""
    per_field = scorecard.get("per_field") or {}
    if not isinstance(per_field, dict):
        return
    for agent, fields in per_field.items():
        if not isinstance(fields, dict):
            continue
        for field, metrics in fields.items():
            if not isinstance(metrics, dict):
                continue
            match_rate = metrics.get("match_rate")
            if not isinstance(match_rate, int | float):
                continue
            threshold = _resolve_threshold(thresholds, agent, field)
            observed = float(match_rate)
            if observed + 1e-9 < threshold:
                yield (
                    f"{agent}.{field}: match_rate={observed:.3f} "
                    f"< threshold={threshold:.3f}"
                )


def check_eval_thresholds(
    *,
    scorecard_path: Path | None = None,
    scorecard_dir: Path = DEFAULT_SCORECARD_DIR,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
) -> tuple[int, str]:
    """Return ``(exit_code, message)``. 0 = pass, 1 = breach."""
    if scorecard_path is None:
        scorecard_path = _latest_scorecard(scorecard_dir)
    if scorecard_path is None or not scorecard_path.is_file():
        return 0, "no scorecard yet — eval not run; skipping threshold check"

    with scorecard_path.open("r", encoding="utf-8") as fh:
        scorecard = json.load(fh)
    if not isinstance(scorecard, dict):
        return 1, (
            f"scorecard {scorecard_path} did not parse to a JSON object "
            f"(got {type(scorecard).__name__})"
        )

    per_field = scorecard.get("per_field") or {}
    if not per_field:
        return 0, (
            f"scorecard {scorecard_path.name} has no per-field metrics — "
            "skipping threshold check"
        )

    thresholds = _load_thresholds(thresholds_path)

    breaches = list(_iter_breaches(scorecard, thresholds))
    if not breaches:
        return 0, (
            f"Eval thresholds OK: {scorecard_path.name} passes all per-field "
            f"floors (defaults to {thresholds.get(DEFAULT_FALLBACK_KEY, 0.0):.2f})"
        )

    return 1, (
        f"Eval thresholds breached in {scorecard_path.name}:\n  "
        + "\n  ".join(breaches)
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_eval_thresholds",
        description=(
            "Fail CI if any agent.field match_rate in the latest scorecard "
            "falls below its declared threshold."
        ),
    )
    p.add_argument(
        "--scorecard",
        type=Path,
        default=None,
        help="Path to a specific scorecard JSON. Default: latest in tests/scorecards/.",
    )
    p.add_argument(
        "--scorecard-dir",
        type=Path,
        default=DEFAULT_SCORECARD_DIR,
        help="Directory to scan for the latest scorecard JSON.",
    )
    p.add_argument(
        "--thresholds",
        type=Path,
        default=DEFAULT_THRESHOLDS_PATH,
        help="Path to thresholds.yaml.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    exit_code, message = check_eval_thresholds(
        scorecard_path=args.scorecard,
        scorecard_dir=args.scorecard_dir,
        thresholds_path=args.thresholds,
    )
    out = sys.stdout if exit_code == 0 else sys.stderr
    print(message, file=out)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
