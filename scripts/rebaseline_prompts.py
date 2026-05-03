#!/usr/bin/env python3
"""Re-baseline ``tests/unit/prompt_hashes.json`` after a deliberate prompt edit.

Usage:

    # Inspect the diff vs the on-disk baseline
    python scripts/rebaseline_prompts.py --dry-run

    # Write the updated baseline (run after editing a prompt + bumping its version)
    python scripts/rebaseline_prompts.py

The tested invariant is:

- Body changed + version unchanged → CI fails (test_prompt_versioning.py).
- Body changed + version bumped + baseline updated in the same PR → CI passes.

So the workflow for an intentional prompt edit is:

1. Edit the prompt body (e.g. ``src/doc_extractor/prompts/passport.md``).
2. Bump the ``version`` in the prompt's frontmatter.
3. Run ``python scripts/rebaseline_prompts.py`` to refresh
   ``tests/unit/prompt_hashes.json``.
4. Commit prompt + baseline together; CI is green again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "src" / "doc_extractor" / "prompts"
BASELINE_PATH = REPO_ROOT / "tests" / "unit" / "prompt_hashes.json"

# Project package — added to sys.path so the bundled prompt loader is reusable.
sys.path.insert(0, str(REPO_ROOT / "src"))
from doc_extractor.prompts import loader  # noqa: E402


def _hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _build_current_baseline() -> dict[str, dict[str, str]]:
    """Walk the prompts dir and compute ``{name: {version, body_sha256}}``."""
    baseline: dict[str, dict[str, str]] = {}
    loader.load_prompt.cache_clear()
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        body, version = loader.load_prompt(path.stem)
        baseline[path.name] = {
            "version": version,
            "body_sha256": _hash_body(body),
        }
    return baseline


def _load_existing_baseline() -> dict[str, dict[str, str]]:
    if not BASELINE_PATH.exists():
        return {}
    with BASELINE_PATH.open("r", encoding="utf-8") as fh:
        return cast(dict[str, dict[str, str]], json.load(fh))


def _format_diff(
    existing: dict[str, dict[str, str]],
    current: dict[str, dict[str, str]],
) -> list[str]:
    """Return human-readable diff lines for the dry-run summary."""
    lines: list[str] = []
    all_names = sorted(set(existing) | set(current))
    for name in all_names:
        in_old = name in existing
        in_new = name in current
        if not in_old:
            new = current[name]
            lines.append(
                f"+ {name}: NEW version={new['version']} sha256={new['body_sha256'][:16]}…"
            )
            continue
        if not in_new:
            old = existing[name]
            lines.append(f"- {name}: REMOVED (was version={old['version']})")
            continue
        old = existing[name]
        new = current[name]
        if old == new:
            continue
        if old["version"] != new["version"]:
            lines.append(
                f"~ {name}: version {old['version']!r} → {new['version']!r}"
            )
        if old["body_sha256"] != new["body_sha256"]:
            lines.append(
                f"~ {name}: body_sha256 "
                f"{old['body_sha256'][:16]}… → {new['body_sha256'][:16]}…"
            )
    return lines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Re-baseline tests/unit/prompt_hashes.json after a prompt edit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the diff vs the existing baseline without writing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    current = _build_current_baseline()
    existing = _load_existing_baseline()

    diff = _format_diff(existing, current)
    if not diff:
        print("No changes — baseline already up to date.")
        return 0

    print(f"Diff vs {BASELINE_PATH.relative_to(REPO_ROOT)}:")
    for line in diff:
        print(f"  {line}")

    if args.dry_run:
        print("(--dry-run: baseline NOT written)")
        return 0

    BASELINE_PATH.write_text(
        json.dumps(current, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {BASELINE_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
