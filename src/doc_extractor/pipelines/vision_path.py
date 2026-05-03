"""Vision pipeline.

Wires together: HEAD-skip → MIME-detect → (PDF→PNG | presign) → classify →
route → extract → (verify if PaymentReceipt) → render → write. Story 3.7
added the verifier step on the PaymentReceipt branch; Story 4.4 expands
verification to the ID-document family. Other doc-types still surface
``NotImplementedError`` until their specialists land.

Story 3.3 added the MIME pre-step: before classifier dispatch, ``head_source``
returns the object's content type. PDFs are downloaded and rendered to PNG
bytes via ``pdf.converter.pdf_to_images`` (page1 only at this stage —
``_pdf_mode_for`` is wired forward-compat for the BankStatement specialist
in Epic 5). Native images keep the presigned-URL fast path.
"""

from __future__ import annotations

import json
from typing import Any

from agno.media import Image

from doc_extractor import markdown_io, s3_io
from doc_extractor.agents.classifier import create_classifier_agent
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.agents.payment_receipt import create_payment_receipt_agent
from doc_extractor.agents.verifier import create_verifier_agent
from doc_extractor.pdf.converter import PdfMode, pdf_to_images
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.ids import Passport
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.verifier import VerifierAudit

CLASSIFIER_INPUT = "Classify this document image."
PASSPORT_INPUT = "Extract the passport fields from this image."
PAYMENT_RECEIPT_INPUT = "Extract the payment receipt fields from this image."

PDF_CONTENT_TYPE = "application/pdf"
PDF_KEY_SUFFIX = ".pdf"


def _analysis_key_for(source_key: str) -> str:
    """Derive the analysis-bucket key. AC §4: append ``.md`` to the source key."""
    return f"{source_key}.md"


def _pdf_mode_for(doc_type: str) -> PdfMode:
    """Per-doc-type rendering mode. Forward-compat for Epic 5's BankStatement.

    v1 only routes Passport (single page); BankStatement will be the first
    specialist that needs ``"all_pages"`` so a multi-page receipt fan-out
    can land downstream.
    """
    return "all_pages" if doc_type == "BankStatement" else "page1"


def _is_pdf_source(source_key: str, content_type: str) -> bool:
    """True if the source object is a PDF.

    Trust the MIME type when present; fall back to a key-suffix sniff so a
    PDF stored with a generic ``application/octet-stream`` still routes
    through preprocessing.
    """
    if content_type.lower().startswith(PDF_CONTENT_TYPE):
        return True
    return source_key.lower().endswith(PDF_KEY_SUFFIX)


def _build_image_for_source(source_key: str) -> Image:
    """Return the ``agno.media.Image`` primitive for ``source_key``.

    PDFs go through ``pdf_to_images(..., mode="page1")`` and are passed as
    raw PNG bytes via ``Image(content=...)``. Native images stay on the
    fast path with a presigned URL via ``Image(url=...)``.
    """
    metadata = s3_io.head_source(source_key)
    content_type = str(metadata.get("content_type") or "")
    if _is_pdf_source(source_key, content_type):
        pdf_bytes = s3_io.get_source_bytes(source_key)
        png_pages = pdf_to_images(pdf_bytes, mode="page1")
        return Image(content=png_pages[0])

    presigned_url = s3_io.get_presigned_url(s3_io.SOURCE_BUCKET, source_key)
    return Image(url=presigned_url)


async def run(source_key: str) -> dict[str, Any]:
    """Process a single source document end-to-end.

    Returns a result dict with ``analysis_key``, ``skipped`` (HEAD-skip
    flag), ``doc_type``, and ``verifier_audit`` (the dumped
    :class:`VerifierAudit` for PaymentReceipt-typed runs, ``None`` otherwise
    — including HEAD-skip and Passport runs). Story 3.9 will consume the
    audit when writing disagreement-queue entries.
    """
    analysis_key = _analysis_key_for(source_key)

    if s3_io.head_analysis(analysis_key):
        return {
            "analysis_key": analysis_key,
            "skipped": True,
            "doc_type": "",
            "verifier_audit": None,
        }

    image = _build_image_for_source(source_key)

    classifier = create_classifier_agent()
    classifier_result = await classifier.arun(CLASSIFIER_INPUT, images=[image])
    classification = classifier_result.content
    if not isinstance(classification, Classification):
        raise TypeError(
            f"Classifier returned {type(classification).__name__}, expected Classification"
        )

    extracted: Passport | PaymentReceipt
    verifier_audit: VerifierAudit | None = None

    if classification.doc_type == "Passport":
        passport_agent = create_passport_agent()
        extraction_result = await passport_agent.arun(PASSPORT_INPUT, images=[image])
        passport = extraction_result.content
        if not isinstance(passport, Passport):
            raise TypeError(
                f"Passport agent returned {type(passport).__name__}, expected Passport"
            )
        extracted = passport

    elif classification.doc_type == "PaymentReceipt":
        payment_receipt_agent = create_payment_receipt_agent()
        extraction_result = await payment_receipt_agent.arun(
            PAYMENT_RECEIPT_INPUT, images=[image]
        )
        receipt = extraction_result.content
        if not isinstance(receipt, PaymentReceipt):
            raise TypeError(
                f"PaymentReceipt agent returned {type(receipt).__name__},"
                f" expected PaymentReceipt"
            )
        extracted = receipt

        # Story 3.7 — verifier audit on PaymentReceipt. Story 4.4 expands
        # this to the ID-document family.
        verifier_input = json.dumps(receipt.model_dump(), ensure_ascii=False, indent=2)
        verifier_agent = create_verifier_agent()
        verifier_result = await verifier_agent.arun(verifier_input, images=[image])
        audit = verifier_result.content
        if not isinstance(audit, VerifierAudit):
            raise TypeError(
                f"Verifier agent returned {type(audit).__name__}, expected VerifierAudit"
            )
        verifier_audit = audit

    else:
        raise NotImplementedError(
            f"specialist not yet implemented for doc_type={classification.doc_type!r}"
        )

    md_text = markdown_io.render_to_md(extracted)
    s3_io.write_analysis(analysis_key, md_text)

    return {
        "analysis_key": analysis_key,
        "skipped": False,
        "doc_type": classification.doc_type,
        "verifier_audit": verifier_audit.model_dump() if verifier_audit else None,
    }
