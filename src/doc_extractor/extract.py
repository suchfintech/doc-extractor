"""Library entry point: ``extract(key, ...)`` coroutine + verbose orchestration.

The simple path delegates to ``pipelines.vision_path.run(key)``. Verbose
mode, ``--dry-run``, and per-invocation provider overrides all need to
inspect intermediate state, so those paths inline the orchestration here so
the five FR51 verbose sections can be emitted between steps.

This module is the CLI's only call into the pipeline layer — keeping the
verbose-printing concern out of ``vision_path.run`` so the latter remains a
pure async producer of analysis artifacts.
"""

from __future__ import annotations

import time
from typing import Any

from agno.media import Image

from doc_extractor import markdown_io, s3_io
from doc_extractor.agents.classifier import create_classifier_agent
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.pipelines import vision_path
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.ids import Passport

CLASSIFIER_INPUT = vision_path.CLASSIFIER_INPUT
PASSPORT_INPUT = vision_path.PASSPORT_INPUT


def _section(title: str) -> None:
    print(f"=== {title} ===")


async def extract(
    key: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    verbose: bool = False,
    show_image: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the vision pipeline for ``key`` and return the result dict.

    For the simple, non-introspective path this is a thin wrapper over
    :func:`pipelines.vision_path.run`. Any of ``verbose``, ``dry_run``,
    ``show_image``, ``provider``, or ``model`` enables the inlined
    orchestration below so the FR51 verbose sections can be emitted in the
    canonical order.
    """
    needs_inline = bool(verbose or dry_run or show_image or provider or model)
    if not needs_inline:
        return await vision_path.run(key)

    analysis_key = f"{key}.md"

    if not dry_run and s3_io.head_analysis(analysis_key):
        return {"analysis_key": analysis_key, "skipped": True, "doc_type": ""}

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
    passport_agent = create_passport_agent(provider=provider)
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
        print(
            f"cost_usd=0.000 latency_ms={elapsed_ms:.0f} model={model_id}"
        )

    if dry_run:
        if not verbose:
            print(md_text)
    else:
        s3_io.write_analysis(analysis_key, md_text)

    return {
        "analysis_key": analysis_key,
        "skipped": False,
        "doc_type": classification.doc_type,
        "dry_run": dry_run,
    }
