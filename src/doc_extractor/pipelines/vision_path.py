"""Vision pipeline (Passport-only for v1).

Wires together: HEAD-skip → presign → classify → route → extract → render →
write. Verifier and retry are deliberately absent at this stage; Stories 3.7
and 3.8 land them. Non-Passport classifications surface ``NotImplementedError``
because Story 1.10's scope is the single Passport specialist; later epics
unlock the rest of the 15-way fan-out.
"""

from __future__ import annotations

from typing import Any

from agno.media import Image

from doc_extractor import markdown_io, s3_io
from doc_extractor.agents.classifier import create_classifier_agent
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.ids import Passport

CLASSIFIER_INPUT = "Classify this document image."
PASSPORT_INPUT = "Extract the passport fields from this image."


def _analysis_key_for(source_key: str) -> str:
    """Derive the analysis-bucket key. AC §4: append ``.md`` to the source key."""
    return f"{source_key}.md"


async def run(source_key: str) -> dict[str, Any]:
    """Process a single source document end-to-end.

    Returns a result dict with ``analysis_key``, ``skipped`` (HEAD-skip flag),
    and ``doc_type``. On HEAD-skip the dict carries ``doc_type=""`` because
    the classifier was never invoked.
    """
    analysis_key = _analysis_key_for(source_key)

    if s3_io.head_analysis(analysis_key):
        return {"analysis_key": analysis_key, "skipped": True, "doc_type": ""}

    presigned_url = s3_io.get_presigned_url(s3_io.SOURCE_BUCKET, source_key)
    image = Image(url=presigned_url)

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

    passport_agent = create_passport_agent()
    extraction_result = await passport_agent.arun(PASSPORT_INPUT, images=[image])
    passport = extraction_result.content
    if not isinstance(passport, Passport):
        raise TypeError(
            f"Passport agent returned {type(passport).__name__}, expected Passport"
        )

    md_text = markdown_io.render_to_md(passport)
    s3_io.write_analysis(analysis_key, md_text)

    return {
        "analysis_key": analysis_key,
        "skipped": False,
        "doc_type": classification.doc_type,
    }
