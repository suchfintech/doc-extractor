"""Library entry point: ``extract(key, ...)`` + ``extract_batch(keys, ...)``.

This module is the canonical surface for one-off and batched document
extraction. Story 8.4 lifts HEAD-skip idempotency from the pipeline layer
up to this entry point so already-extracted batches don't pay the
pipeline-import cost. ``extract()`` always returns a typed
:class:`ExtractedDoc`; the previous dict shape is gone.

Verbose mode, ``--dry-run``, and per-invocation provider overrides need
intermediate state, so those paths inline the orchestration here. The
non-introspective fast path delegates to :func:`pipelines.vision_path.run`.
"""

from __future__ import annotations

import time

from agno.media import Image
from pydantic import BaseModel, Field

from doc_extractor import markdown_io, s3_io
from doc_extractor.agents.classifier import create_classifier_agent
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.pipelines import vision_path
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.ids import Passport

# Inlined string constants — a previous version reached into vision_path
# for these, which produced a static-import cycle once batch.py joined the
# graph (vision_path → agents.retry → doc_extractor → extract → vision_path).
# The bytes here must stay in sync with the same constants on vision_path.
CLASSIFIER_INPUT = "Classify this document image."
PASSPORT_INPUT = "Extract the passport fields from this image."

DEFAULT_BATCH_CONCURRENCY = 10


class ExtractedDoc(BaseModel):
    """Typed return value for ``extract()`` and ``extract_batch()``.

    ``doc_type`` is ``None`` when ``skipped`` is True — the classifier did
    not run on a HEAD-skip and we deliberately don't reach into the
    existing analysis just to fill in this field.
    """

    key: str
    skipped: bool
    analysis_key: str
    doc_type: str | None = Field(default=None)


def _section(title: str) -> None:
    print(f"=== {title} ===")


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
    """
    analysis_key = _analysis_key_for(key)

    if s3_io.head_analysis(analysis_key):
        return ExtractedDoc(
            key=key,
            skipped=True,
            analysis_key=analysis_key,
            doc_type=None,
        )

    needs_inline = bool(verbose or dry_run or show_image or provider or model)
    if not needs_inline:
        result = await vision_path.run(key)
        return ExtractedDoc(
            key=key,
            skipped=bool(result.get("skipped", False)),
            analysis_key=str(result["analysis_key"]),
            doc_type=(str(result["doc_type"]) or None),
        )

    presigned_url = s3_io.get_presigned_url(s3_io.SOURCE_BUCKET, key)
    if show_image:
        print(f"presigned_url: {presigned_url}")

    image = Image(url=presigned_url)
    start = time.monotonic()

    classifier = create_classifier_agent()
    classifier_result = await classifier.arun(CLASSIFIER_INPUT, images=[image])
    classification = classifier_result.content
    if not isinstance(classification, Classification):
        raise TypeError(
            f"Classifier returned {type(classification).__name__}, expected Classification"
        )

    if classification.doc_type != "Passport":
        raise NotImplementedError(
            f"specialist not yet implemented for doc_type={classification.doc_type!r}"
        )

    passport_prompt, _passport_version = load_prompt("passport")
    passport_agent = create_passport_agent(provider=provider, model=model)
    passport_result = await passport_agent.arun(PASSPORT_INPUT, images=[image])
    passport = passport_result.content
    if not isinstance(passport, Passport):
        raise TypeError(
            f"Passport agent returned {type(passport).__name__}, expected Passport"
        )

    md_text = markdown_io.render_to_md(passport)
    elapsed_ms = (time.monotonic() - start) * 1000.0

    if verbose:
        _section("1. Resolved prompt text")
        print(passport_prompt)
        _section("2. Raw model response")
        print(passport_result.content)
        _section("3. Pydantic validation result")
        print(passport.model_dump())
        _section("4. Rendered .md content")
        print(md_text)
        _section("5. Cost telemetry")
        model_id = model or "<resolved-by-config>"
        print(f"cost_usd=0.000 latency_ms={elapsed_ms:.0f} model={model_id}")

    if dry_run:
        if not verbose:
            print(md_text)
    else:
        s3_io.write_analysis(analysis_key, md_text)

    return ExtractedDoc(
        key=key,
        skipped=False,
        analysis_key=analysis_key,
        doc_type=classification.doc_type,
    )


# Story 8.5 — extract_batch lives in ``pipelines.batch`` so the CLI batch
# surface and the rate-limit retry shell have a dedicated home. Re-imported
# here at module bottom (after ``extract`` / ``ExtractedDoc`` are defined)
# so the public API stays at ``from doc_extractor.extract import
# extract_batch`` and ``from doc_extractor import extract_batch``.
from doc_extractor.pipelines.batch import extract_batch  # noqa: E402

__all__ = ["DEFAULT_BATCH_CONCURRENCY", "ExtractedDoc", "extract", "extract_batch"]
