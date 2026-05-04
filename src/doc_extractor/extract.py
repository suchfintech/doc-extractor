"""Library entry point: ``extract(key, ...)`` + ``extract_batch(keys, ...)``.

This module is the canonical surface for one-off and batched document
extraction. ``extract()`` always returns a typed :class:`ExtractedDoc`;
HEAD-skip idempotency (Story 8.4) is enforced before any pipeline import
so an already-extracted batch costs exactly one S3 HEAD per key.

P13 (code review Round 3) — the inline orchestration path is gone.
``extract()`` always delegates to :func:`pipelines.vision_path.run`;
verbose / dry-run / show-image / provider / model overrides thread
through directly. Telemetry is emitted exclusively by ``vision_path.run``
(P10) — there's no longer a duplicate emission site here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from doc_extractor import s3_io
from doc_extractor.pipelines import vision_path

DEFAULT_BATCH_CONCURRENCY = 10


class ExtractedDoc(BaseModel):
    """Typed return value for ``extract()`` and ``extract_batch()``.

    ``doc_type`` is ``None`` when ``skipped`` is True — the classifier did
    not run on a HEAD-skip and we deliberately don't reach into the
    existing analysis just to fill in this field.

    ``cost_usd`` (P12, code review Round 2) carries the rolled-up provider
    cost for this extraction (sum across specialist retry attempts +
    verifier when run). Pre-fix the eval harness's ``_resolve_cost`` was
    hardcoded to 0.0, which made the $15 cost ceiling (Story 8.7 / NFR7)
    unable to fire. ``vision_path.run`` populates this from
    ``run_response.metrics.cost`` — see ``_read_run_response``.
    """

    key: str
    skipped: bool
    analysis_key: str
    doc_type: str | None = Field(default=None)
    cost_usd: float = Field(default=0.0)


def _analysis_key_for(key: str) -> str:
    return f"{key}.md"


async def extract(
    key: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    verbose: bool = False,
    show_image: bool = False,
    dry_run: bool = False,
) -> ExtractedDoc:
    """Extract one document. HEAD-skip is checked before any pipeline import.

    The HEAD-skip short-circuit fires uniformly — even with ``--dry-run`` or
    ``--verbose`` — so an already-extracted source key costs exactly one S3
    HEAD and zero provider tokens. To force re-extraction, delete the
    analysis object first.

    All other behaviour (classification, dispatch, verification, render,
    write, telemetry) lives in ``vision_path.run`` post-P13.
    """
    analysis_key = _analysis_key_for(key)

    if s3_io.head_analysis(analysis_key):
        return ExtractedDoc(
            key=key,
            skipped=True,
            analysis_key=analysis_key,
            doc_type=None,
            cost_usd=0.0,
        )

    result = await vision_path.run(
        key,
        provider=provider,
        model=model,
        verbose=verbose,
        show_image=show_image,
        dry_run=dry_run,
    )
    return ExtractedDoc(
        key=key,
        skipped=bool(result.get("skipped", False)),
        analysis_key=str(result["analysis_key"]),
        doc_type=(str(result["doc_type"]) or None),
        cost_usd=float(result.get("cost_usd", 0.0)),
    )


# Story 8.5 — extract_batch lives in ``pipelines.batch`` so the CLI batch
# surface and the rate-limit retry shell have a dedicated home. Re-imported
# here at module bottom (after ``extract`` / ``ExtractedDoc`` are defined)
# so the public API stays at ``from doc_extractor.extract import
# extract_batch`` and ``from doc_extractor import extract_batch``.
from doc_extractor.pipelines.batch import extract_batch  # noqa: E402

__all__ = ["DEFAULT_BATCH_CONCURRENCY", "ExtractedDoc", "extract", "extract_batch"]
