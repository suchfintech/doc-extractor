#!/usr/bin/env python3
"""Canonical-4 verification gate (Story 2.7 / AR3 / FR16).

Reads canonical ``(image, expected.md)`` fixture pairs from
``tests/canonical/fixtures/`` and asserts the Vision pipeline reproduces
the four pinned receipt_debit_* / receipt_credit_* fields for each pair.

Pinned fields under exact-equality (per the merlin canonical-4 contract
ported in this story):

- ``receipt_debit_account_name``
- ``receipt_debit_account_number``
- ``receipt_credit_account_name``
- ``receipt_credit_account_number``

Modes
-----
``--mocked``
  CI structural smoke. The extractor is tautological — returns the
  expected fields unchanged — so the script's discovery / comparison /
  exit-code wiring is validated on every commit WITHOUT spending API
  budget. CI invokes this mode unconditionally; it fails only when the
  script itself is broken or a fixture is malformed.

real (default)
  Real-provider verification (Yang's nightly). Requires
  ``ANTHROPIC_API_KEY``. Until Story 2.1 ships the canonical fixtures
  AND wires the real-pipeline harness (mock-S3 serving the fixture
  image, capturing the rendered ``.md`` and re-parsing the four
  fields), the real-mode extractor raises ``NotImplementedError`` —
  the script catches this and returns a skip-pass so a partially
  configured runtime can't silently pretend it verified.

Skip paths (always exit 0)
- Fixtures directory missing or empty → "no canonical fixtures yet —
  pending Story 2.1".
- ``ANTHROPIC_API_KEY`` unset in real mode → "API key unset — skip".
- Real-mode extractor raising ``NotImplementedError`` → "skip with the
  underlying message".

Failure path (exit 1)
- One or more fixture pairs disagree on any of the four fields. Output
  lists every offending ``<example_id>.<field>: expected=…, actual=…``
  line so the diff is obvious in CI logs.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import yaml  # type: ignore[import-untyped]  # types-PyYAML not yet wired in dev deps

DEFAULT_FIXTURES_DIR = Path("tests/canonical/fixtures")
IMAGE_EXTENSIONS: tuple[str, ...] = (".jpeg", ".jpg", ".png", ".pdf")
PAIRED_FIELDS: tuple[str, ...] = (
    "receipt_debit_account_name",
    "receipt_debit_account_number",
    "receipt_credit_account_name",
    "receipt_credit_account_number",
)

# An ``Extractor`` consumes the fixture image path + the expected paired-field
# dict and returns its own paired-field dict for comparison.
Extractor = Callable[[Path, dict[str, str]], Awaitable[dict[str, str]]]


def _discover_pairs(fixtures_dir: Path) -> list[tuple[str, Path, Path]]:
    """Return ``(example_id, image_path, expected_md_path)`` triples, sorted.

    A pair exists iff ``<id>.<ext>`` and ``<id>.expected.md`` are both regular
    files. Image files without a matching ``.expected.md`` are silently
    skipped — the canonical-4 gate is opt-in per fixture.
    """
    if not fixtures_dir.is_dir():
        return []
    pairs: list[tuple[str, Path, Path]] = []
    for image in fixtures_dir.iterdir():
        if not image.is_file() or image.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        example_id = image.stem
        expected = fixtures_dir / f"{example_id}.expected.md"
        if expected.is_file():
            pairs.append((example_id, image, expected))
    return sorted(pairs, key=lambda p: p[0])


def _parse_expected(expected_md_path: Path) -> dict[str, str]:
    """Parse ``<example>.expected.md``'s YAML frontmatter; return the four
    paired fields as a string dict (missing or null values become ``""``).

    Other frontmatter fields are ignored — this gate intentionally enforces
    the four debit/credit fields only. Anything broader should land its
    own assertion test, not lean on this script.
    """
    text = expected_md_path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(
            f"{expected_md_path}: missing YAML frontmatter fences"
        )
    data = yaml.safe_load(parts[1]) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"{expected_md_path}: frontmatter is not a mapping "
            f"({type(data).__name__})"
        )
    return {field: str(data.get(field) or "") for field in PAIRED_FIELDS}


async def _tautological_extractor(
    _image_path: Path, expected: dict[str, str]
) -> dict[str, str]:
    """``--mocked`` extractor: returns the expected dict unchanged.

    The structural smoke test relies on this tautology: discovery +
    comparison + exit-code logic execute over real fixtures without an
    API call ever happening.
    """
    return dict(expected)


async def _real_extractor(
    _image_path: Path, _expected: dict[str, str]
) -> dict[str, str]:
    """Real-provider extractor placeholder.

    Story 2.1 wires this to: spin up a mock S3 client serving the fixture
    image, call ``vision_path.run(<source_key>)`` with a real Anthropic
    backend, capture the rendered analysis .md from ``write_analysis``,
    re-parse via ``markdown_io.parse_md``, and emit the four paired
    fields. Until then, the script catches this NotImplementedError at
    the call-site and returns a skip-pass (exit 0) so a misconfigured
    runtime can't silently pretend it verified anything.
    """
    raise NotImplementedError(
        "real-pipeline canonical verification not yet wired; depends on "
        "Story 2.1 fixtures + S3-mock harness. Use --mocked for the CI "
        "structural gate today."
    )


async def verify_canonical(
    *,
    fixtures_dir: Path = DEFAULT_FIXTURES_DIR,
    mocked: bool = False,
    extractor: Extractor | None = None,
) -> tuple[int, str]:
    """Return ``(exit_code, message)``. 0 = pass / skip, 1 = breach."""
    pairs = _discover_pairs(fixtures_dir)
    if not pairs:
        return 0, "no canonical fixtures yet — pending Story 2.1"

    if not mocked and not os.environ.get("ANTHROPIC_API_KEY"):
        return 0, (
            "ANTHROPIC_API_KEY unset — skipping real-mode canonical-4 "
            "verification (use --mocked for the CI structural smoke)"
        )

    if extractor is None:
        extractor = _tautological_extractor if mocked else _real_extractor

    failures: list[str] = []
    for example_id, image_path, expected_path in pairs:
        try:
            expected = _parse_expected(expected_path)
        except (ValueError, yaml.YAMLError) as exc:
            failures.append(f"{example_id}: bad expected.md — {exc}")
            continue

        try:
            actual = await extractor(image_path, expected)
        except NotImplementedError as exc:
            return 0, f"skipping canonical-4 verification: {exc}"
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{example_id}: extractor raised "
                f"{type(exc).__name__}: {exc}"
            )
            continue

        for field in PAIRED_FIELDS:
            exp_val = expected.get(field, "")
            act_val = str(actual.get(field, ""))
            if exp_val != act_val:
                failures.append(
                    f"{example_id}.{field}: expected={exp_val!r}, "
                    f"actual={act_val!r}"
                )

    if failures:
        return 1, (
            f"Canonical-4 failures ({len(failures)}):\n  "
            + "\n  ".join(failures)
        )

    return 0, (
        f"Canonical-4 OK: {len(pairs)} pair(s) verified "
        f"({'mocked' if mocked else 'real'} mode)"
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="verify_canonical",
        description=(
            "Canonical-4 verification gate (Story 2.7). Asserts the four "
            "pinned receipt_debit_/receipt_credit_ fields on every "
            "tests/canonical/fixtures/ pair."
        ),
    )
    p.add_argument(
        "--fixtures-dir",
        type=Path,
        default=DEFAULT_FIXTURES_DIR,
        help="Directory holding canonical fixture pairs. "
        "Default: tests/canonical/fixtures.",
    )
    p.add_argument(
        "--mocked",
        action="store_true",
        help=(
            "Structural smoke mode: tautological extractor returns "
            "expected. Use in CI to validate the script's wiring without "
            "API calls."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    exit_code, message = asyncio.run(
        verify_canonical(fixtures_dir=args.fixtures_dir, mocked=args.mocked)
    )
    out = sys.stdout if exit_code == 0 else sys.stderr
    print(message, file=out)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
