"""Vision pipeline.

Wires together: HEAD-skip → MIME-detect → (PDF→PNG | presign) → classify →
route → extract → verify (per FR4 list) → render → write. Story 3.7 wired
the verifier on PaymentReceipt; Story 4.4 expanded the gating set to all
five safety-critical types (the four ID documents plus PaymentReceipt).
Doc-types outside the gated set still surface ``NotImplementedError``
until their specialists land in Epic 5.

Story 3.3 added the MIME pre-step: before classifier dispatch, ``head_source``
returns the object's content type. PDFs are downloaded and rendered to PNG
bytes via ``pdf.converter.pdf_to_images`` (page1 only at this stage —
``_pdf_mode_for`` is wired forward-compat for the BankStatement specialist
in Epic 5). Native images keep the presigned-URL fast path.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agno.agent import Agent
from agno.media import Image

from doc_extractor import __version__, markdown_io, s3_io
from doc_extractor.agents.classifier import create_classifier_agent
from doc_extractor.agents.driver_licence import create_driver_licence_agent
from doc_extractor.agents.national_id import create_national_id_agent
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.agents.payment_receipt import create_payment_receipt_agent
from doc_extractor.agents.retry import with_validation_retry
from doc_extractor.agents.verifier import create_verifier_agent
from doc_extractor.agents.visa import create_visa_agent
from doc_extractor.config.precedence import resolve_agent_config
from doc_extractor.disagreement import record_disagreement
from doc_extractor.exceptions import PydanticValidationError
from doc_extractor.pdf.converter import PdfMode, pdf_to_images
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.base import Frontmatter
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.ids import DriverLicence, NationalID, Passport, Visa
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.verifier import VerifierAudit

CLASSIFIER_INPUT = "Classify this document image."

PDF_CONTENT_TYPE = "application/pdf"
PDF_KEY_SUFFIX = ".pdf"


# Story 4.4 — five safety-critical doc types share the same wrapping:
# retry-with-escalation specialist call, post-extraction verifier audit,
# and disagreement-queue routing on fail / validation_failure. The CEL
# DSL the architecture sketches is informational only; production uses
# this Python-level dispatch table because it's easier to mypy / unit-test
# and adding a sixth type is one row, not a CEL grammar change.
class _SpecialistSpec:
    """Static config for one verifier-gated specialist."""

    __slots__ = ("agent_name", "factory", "input_text", "schema_cls")

    def __init__(
        self,
        *,
        agent_name: str,
        factory: Callable[[], Agent],
        input_text: str,
        schema_cls: type[Frontmatter],
    ) -> None:
        self.agent_name = agent_name
        self.factory = factory
        self.input_text = input_text
        self.schema_cls = schema_cls


# NOTE: each ``factory`` is wrapped in a lambda (rather than a direct
# reference to ``create_*_agent``) so the call-site goes through this
# module's globals at *call* time, honouring tests' ``monkeypatch.setattr(
# vision_path, "create_X_agent", ...)`` overrides. A direct function
# reference would be captured at import time and bypass the patch.
_SPECIALISTS: dict[str, _SpecialistSpec] = {
    "Passport": _SpecialistSpec(
        agent_name="passport",
        factory=lambda: create_passport_agent(),
        input_text="Extract the passport fields from this image.",
        schema_cls=Passport,
    ),
    "DriverLicence": _SpecialistSpec(
        agent_name="driver_licence",
        factory=lambda: create_driver_licence_agent(),
        input_text="Extract the driver licence fields from this image.",
        schema_cls=DriverLicence,
    ),
    "NationalID": _SpecialistSpec(
        agent_name="national_id",
        factory=lambda: create_national_id_agent(),
        input_text="Extract the national ID fields from this image.",
        schema_cls=NationalID,
    ),
    "Visa": _SpecialistSpec(
        agent_name="visa",
        factory=lambda: create_visa_agent(),
        input_text="Extract the visa fields from this image.",
        schema_cls=Visa,
    ),
    "PaymentReceipt": _SpecialistSpec(
        agent_name="payment_receipt",
        factory=lambda: create_payment_receipt_agent(),
        input_text="Extract the payment receipt fields from this image.",
        schema_cls=PaymentReceipt,
    ),
}

# Re-exported for backwards-compat with callers that imported these constants.
PASSPORT_INPUT = _SPECIALISTS["Passport"].input_text
PAYMENT_RECEIPT_INPUT = _SPECIALISTS["PaymentReceipt"].input_text


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


_EMPTY_METADATA: dict[str, Any] = {
    "provider": "",
    "model": "",
    "latency_ms": 0.0,
    "cost_usd": 0.0,
}


def _read_run_response(agent: Agent | None) -> tuple[str, dict[str, Any]]:
    """Story 6.1 — best-effort raw-text + metadata capture from an Agent.

    Agno exposes the last call's state on ``agent.run_response`` after
    ``arun`` returns: ``messages[-1].content`` is the model's raw text and
    ``metrics`` carries provider / model / latency_ms / cost_usd. The
    surface is best-effort — older Agno versions may not populate every
    attr — so this helper degrades to empty defaults rather than raising.

    Defensive against ``MagicMock`` auto-attrs (every getattr on a
    ``MagicMock`` returns a child mock, which is truthy). The
    ``isinstance`` checks below ensure we only trust real ``str`` /
    numeric values; bare-``MagicMock`` test fixtures fall back to defaults.
    """
    raw_text = ""
    metadata = dict(_EMPTY_METADATA)

    if agent is None:
        return raw_text, metadata

    run_response = getattr(agent, "run_response", None)
    if run_response is None:
        return raw_text, metadata

    messages = getattr(run_response, "messages", None)
    if isinstance(messages, list) and messages:
        last = messages[-1]
        last_content = getattr(last, "content", None)
        if isinstance(last_content, str):
            raw_text = last_content

    metrics = getattr(run_response, "metrics", None)
    if metrics is not None:
        for key in ("provider", "model"):
            value = getattr(metrics, key, None)
            if isinstance(value, str) and value:
                metadata[key] = value
        for key in ("latency_ms", "cost_usd"):
            value = getattr(metrics, key, None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metadata[key] = float(value)

    return raw_text, metadata


def _populate_pipeline_provenance(
    extracted: Frontmatter, *, agent_name: str
) -> None:
    """Story 7.5 — set the three pipeline-supplied provenance fields.

    ``markdown_io.render_to_md`` auto-fills ``extractor_version`` and
    ``extraction_timestamp``; the pipeline owns provider / model /
    prompt_version because only here are the resolved AgentConfig and
    the loaded prompt's version known together. Caller-set values on the
    schema instance win, so a custom orchestrator (or a future replay
    flow) can override.
    """
    config = resolve_agent_config(agent_name)
    _, prompt_version = load_prompt(agent_name)
    if not extracted.extraction_provider:
        extracted.extraction_provider = config.provider
    if not extracted.extraction_model:
        extracted.extraction_model = config.model
    if not extracted.prompt_version:
        extracted.prompt_version = prompt_version


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
    flag), ``doc_type``, ``verifier_audit`` (dumped :class:`VerifierAudit`
    for any of the five verifier-gated doc types, ``None`` otherwise),
    ``disagreement_key`` (set when the verifier returned ``fail`` or the
    retry exhausted), and ``retry_count`` (0 on first-attempt success,
    1 on escalated retry success).
    """
    analysis_key = _analysis_key_for(source_key)

    if s3_io.head_analysis(analysis_key):
        return {
            "analysis_key": analysis_key,
            "skipped": True,
            "doc_type": "",
            "verifier_audit": None,
            "disagreement_key": None,
            "retry_count": 0,
        }

    image = _build_image_for_source(source_key)

    classifier = create_classifier_agent()
    classifier_result = await classifier.arun(CLASSIFIER_INPUT, images=[image])
    classification = classifier_result.content
    if not isinstance(classification, Classification):
        raise TypeError(
            f"Classifier returned {type(classification).__name__}, expected Classification"
        )

    spec = _SPECIALISTS.get(classification.doc_type)
    if spec is None:
        raise NotImplementedError(
            f"specialist not yet implemented for doc_type={classification.doc_type!r}"
        )

    # Story 3.8 — wrap the specialist call in with_validation_retry. Story
    # 4.4 generalised this from PaymentReceipt to all five verifier-gated
    # types. Specialists default to Sonnet (top-tier) per agents.yaml, so
    # the escalation path is dormant in production today; the wrapping is
    # forward-compat and exercises the validation_failure → disagreement
    # queue branch uniformly across types.
    #
    # Story 6.1 — the factory closure captures every constructed agent so
    # we can read the LAST agent's ``run_response`` for the forensic
    # payload (raw text + metadata) regardless of whether the retry
    # succeeded or exhausted. Without this, the retry layer holds the
    # only reference and the caller can't see the raw model output.
    captured_agents: list[Agent] = []

    def _retry_factory(_tier: str) -> Agent:
        agent = spec.factory()
        captured_agents.append(agent)
        return agent

    try:
        content, retry_count = await with_validation_retry(
            _retry_factory,
            spec.input_text,
            agent_name=spec.agent_name,
            source_key=source_key,
            primary_provider="anthropic-sonnet",
            arun_kwargs={"images": [image]},
            doc_type=classification.doc_type,
        )
    except PydanticValidationError:
        # No more retries possible — route to disagreement queue and
        # propagate so the caller surfaces the failure. Story 6.1 inlines
        # the raw response from the LAST attempt so reviewers can see
        # exactly what the model emitted.
        last_agent = captured_agents[-1] if captured_agents else None
        primary_raw = _read_run_response(last_agent)
        record_disagreement(
            source_key=source_key,
            primary=None,
            verifier=None,
            status="validation_failure",
            extractor_version=__version__,
            primary_raw=primary_raw,
            verifier_raw=None,
        )
        raise

    if not isinstance(content, spec.schema_cls):
        raise TypeError(
            f"{spec.agent_name} retry returned {type(content).__name__},"
            f" expected {spec.schema_cls.__name__}"
        )
    _populate_pipeline_provenance(content, agent_name=spec.agent_name)
    extracted: Frontmatter = content

    # Story 3.7 (PaymentReceipt) → 4.4 (all five): verifier audit runs on
    # every gated specialist using a single audit prompt. The verifier
    # receives the typed instance dump as JSON so prompt-level diversity
    # catches a different class of error than re-running the extraction
    # prompt would (architecture Decision 1).
    verifier_input = json.dumps(content.model_dump(), ensure_ascii=False, indent=2)
    verifier_agent = create_verifier_agent()
    verifier_result = await verifier_agent.arun(verifier_input, images=[image])
    audit = verifier_result.content
    if not isinstance(audit, VerifierAudit):
        raise TypeError(
            f"Verifier agent returned {type(audit).__name__}, expected VerifierAudit"
        )
    verifier_audit: VerifierAudit = audit

    md_text = markdown_io.render_to_md(extracted)
    s3_io.write_analysis(analysis_key, md_text)

    # Story 3.9 — write a disagreement-queue entry when the verifier flagged
    # ≥1 field as `disagree` (overall=="fail"). `uncertain` is NOT written:
    # downstream surfaces it as advisory only.
    # Story 6.1 — inline the raw responses from the successful specialist
    # call (last agent the retry layer used) and the verifier call so the
    # disagreement entry carries the full forensic payload.
    disagreement_key: str | None = None
    if verifier_audit.overall == "fail":
        last_agent = captured_agents[-1] if captured_agents else None
        primary_raw = _read_run_response(last_agent)
        verifier_raw = _read_run_response(verifier_agent)
        disagreement_key = record_disagreement(
            source_key=source_key,
            primary=extracted,
            verifier=verifier_audit,
            status="disagreement",
            extractor_version=__version__,
            primary_raw=primary_raw,
            verifier_raw=verifier_raw,
        )

    return {
        "analysis_key": analysis_key,
        "skipped": False,
        "doc_type": classification.doc_type,
        "verifier_audit": verifier_audit.model_dump(),
        "disagreement_key": disagreement_key,
        "retry_count": retry_count,
    }
