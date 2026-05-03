"""Eval harness — assembles extract_batch + matchers + Scorecard.

Walks ``tests/golden/<doc_type>/<id>.{jpeg,png,pdf}`` paired with
``<id>.expected.md`` ground-truth files, runs ``extract_batch`` over the
discovered keys, and scores each extraction field-by-field against its
expected counterpart via ``match_with_jurisdiction``. Result rows feed
``Scorecard.from_results`` for per-agent / per-jurisdiction aggregation
(FR16, NFR3).

Story 2.1 (the corpus-data side) is shipped separately by Yang. Until
labelled pairs land, ``run_eval`` returns an empty
``Scorecard.from_results([])`` rather than failing — the harness is a
no-op when there's nothing to score, picks up new pairs additively.

Provenance fields (``extractor_version`` etc.) are deliberately
excluded from scoring because their values are run-specific metadata,
not extraction quality signals.

Concurrency: ``extract_batch(keys, max_concurrent=20)`` — eval batches
push harder than the user-facing batch (default 10) because every key
is already in golden corpus, the budget is bounded by the 300-example
NFR3 ceiling, and CI cares about wall-clock latency more than per-call
politeness.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path

from doc_extractor import markdown_io, s3_io
from doc_extractor.eval.matchers import match_with_jurisdiction
from doc_extractor.eval.scorecard import EvalResult, Scorecard
from doc_extractor.extract import ExtractedDoc
from doc_extractor.pipelines.batch import extract_batch
from doc_extractor.schemas.base import Frontmatter

logger = logging.getLogger(__name__)

DEFAULT_GOLDEN_DIR = Path("tests/golden")
DEFAULT_EVAL_CONCURRENCY = 20

# Story 8.7 / NFR7 — full eval-run cost ceiling. Above this, the harness
# sets ``Scorecard.cost_breach = True`` and emits a logging.warning;
# .github/workflows/eval.yml fails the workflow on the breach flag.
EVAL_COST_CEILING_USD = 15.00

IMAGE_SUFFIXES: tuple[str, ...] = (".jpeg", ".jpg", ".png", ".pdf")

# Provenance fields are run-specific metadata and don't reflect extraction
# quality — exclude from per-field scoring so they don't drag precision.
_PROVENANCE_FIELDS: frozenset[str] = frozenset(
    {
        "extractor_version",
        "extraction_provider",
        "extraction_model",
        "extraction_timestamp",
        "prompt_version",
    }
)


def _discover_pairs(
    golden_dir: Path, doc_type_filter: str | None
) -> list[tuple[str, Path, Path]]:
    """Return ``(doc_type, image_path, expected_md_path)`` tuples.

    Walks each ``<doc_type>/`` subdir of ``golden_dir``. If
    ``doc_type_filter`` is set, only that subdir is walked.
    Image-without-expected (or vice versa) is logged and skipped.
    """
    if not golden_dir.is_dir():
        return []

    if doc_type_filter is not None:
        type_dirs: Iterable[Path] = [golden_dir / doc_type_filter]
    else:
        type_dirs = (p for p in sorted(golden_dir.iterdir()) if p.is_dir())

    pairs: list[tuple[str, Path, Path]] = []
    for type_dir in type_dirs:
        if not type_dir.is_dir():
            continue
        doc_type = type_dir.name
        for image_path in sorted(type_dir.iterdir()):
            if image_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            expected_path = image_path.with_suffix(image_path.suffix + ".expected.md")
            # Also accept the conventional <basename>.expected.md sibling.
            if not expected_path.is_file():
                expected_path = type_dir / f"{image_path.stem}.expected.md"
            if not expected_path.is_file():
                logger.warning(
                    "eval: skipping %s — no .expected.md sibling", image_path
                )
                continue
            pairs.append((doc_type, image_path, expected_path))
    return pairs


def _load_expected(expected_path: Path) -> Frontmatter:
    return markdown_io.parse_md(expected_path.read_text(encoding="utf-8"))


def _load_extracted_content(analysis_key: str) -> Frontmatter:
    """Read ``analysis_key`` from S3 and parse it. Mockable for tests."""
    raw = s3_io.read_analysis(analysis_key)
    return markdown_io.parse_md(raw.decode("utf-8"))


def _resolve_cost(extracted: ExtractedDoc) -> float:
    """Per-extract cost attribution. Returns 0.0 by default — tests
    monkeypatch this when they want to assert ``total_cost_usd`` aggregation.
    Production cost lives in the telemetry JSONL, not on ExtractedDoc.
    """
    return 0.0


def _score_pair(
    *,
    doc_type: str,
    expected: Frontmatter,
    actual: Frontmatter,
    jurisdiction: str,
    cost_usd: float,
) -> list[EvalResult]:
    """Build one EvalResult per non-provenance field on the union of both schemas."""
    expected_dump = expected.model_dump()
    actual_dump = actual.model_dump()
    field_names = (set(expected_dump) | set(actual_dump)) - _PROVENANCE_FIELDS

    rows: list[EvalResult] = []
    for field in sorted(field_names):
        exp_val = str(expected_dump.get(field) or "")
        act_val = str(actual_dump.get(field) or "")
        # Skip fields where both sides are empty — Scorecard's precision /
        # recall denominators only count non-empty actual / expected, but
        # ``matched`` counts every True row, so empty/empty inflates the
        # ratio above 1.0. Empty/empty contributes no signal anyway.
        if not exp_val and not act_val:
            continue
        matched = match_with_jurisdiction(field, exp_val, act_val, jurisdiction)
        rows.append(
            EvalResult(
                agent_name=doc_type,
                field_name=field,
                expected=exp_val,
                actual=act_val,
                matched=matched,
                jurisdiction=jurisdiction,
                cost_usd=cost_usd,
            )
        )
    return rows


async def run_eval(
    doc_type: str | None = None,
    jurisdiction: str | None = None,
    *,
    max_concurrent: int = DEFAULT_EVAL_CONCURRENCY,
    golden_dir: Path | None = None,
    extract_batch_fn: Callable[..., Awaitable[list[ExtractedDoc]]] | None = None,
    cost_ceiling_usd: float = EVAL_COST_CEILING_USD,
) -> Scorecard:
    """Run the eval harness over the golden corpus and return a Scorecard.

    Args:
        doc_type: When set, only ``<golden_dir>/<doc_type>/`` is walked.
        jurisdiction: When set, only pairs whose expected
            ``frontmatter.jurisdiction`` equals this value are scored.
        max_concurrent: Forwarded to ``extract_batch``.
        golden_dir: Override the golden-corpus root (default ``tests/golden``).
        extract_batch_fn: Test seam — defaults to
            ``pipelines.batch.extract_batch``.

    Returns:
        ``Scorecard.from_results([...])``. When the corpus is empty
        (Story 2.1 not yet shipped, or filters reject everything), an
        empty Scorecard is returned without invoking ``extract_batch``.
    """
    root = golden_dir if golden_dir is not None else DEFAULT_GOLDEN_DIR
    pairs = _discover_pairs(root, doc_type)

    # Filter by jurisdiction (read frontmatter once per pair).
    filtered: list[tuple[str, Path, Path, Frontmatter]] = []
    for dt, image_path, expected_path in pairs:
        expected = _load_expected(expected_path)
        if jurisdiction is not None and (expected.jurisdiction or "") != jurisdiction:
            continue
        filtered.append((dt, image_path, expected_path, expected))

    if not filtered:
        return Scorecard.from_results([])

    keys = [str(item[1]) for item in filtered]
    runner = extract_batch_fn if extract_batch_fn is not None else extract_batch
    extracted_docs = await runner(keys, max_concurrent=max_concurrent)

    if len(extracted_docs) != len(filtered):
        raise RuntimeError(
            f"extract_batch returned {len(extracted_docs)} docs for "
            f"{len(filtered)} input keys — order/length contract broken"
        )

    rows: list[EvalResult] = []
    for (dt, _image_path, _expected_path, expected), extracted in zip(
        filtered, extracted_docs, strict=True
    ):
        if not isinstance(extracted, ExtractedDoc):
            raise TypeError(
                f"extract_batch returned {type(extracted).__name__}, expected ExtractedDoc"
            )
        if extracted.skipped:
            logger.info("eval: %s was HEAD-skipped — scoring against existing analysis", extracted.key)
        actual = _load_extracted_content(extracted.analysis_key)
        cost = _resolve_cost(extracted)
        rows.extend(
            _score_pair(
                doc_type=dt,
                expected=expected,
                actual=actual,
                jurisdiction=str(expected.jurisdiction or ""),
                cost_usd=cost,
            )
        )

    scorecard = Scorecard.from_results(rows)
    if scorecard.total_cost_usd > cost_ceiling_usd:
        logger.warning(
            "Eval-run cost ceiling breached: $%.2f (limit $%.2f)",
            scorecard.total_cost_usd,
            cost_ceiling_usd,
        )
        scorecard = scorecard.model_copy(update={"cost_breach": True})
    return scorecard
