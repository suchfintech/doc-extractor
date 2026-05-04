"""Vision pipeline.

Wires together: HEAD-skip → MIME-detect → (PDF→PNG | presign) → classify →
route → extract → verify (gated) → render → write. Story 3.7 wired the
verifier on PaymentReceipt; Story 4.4 expanded the gating set to all five
safety-critical types (the four ID documents plus PaymentReceipt). Code
review Round 1 (P2) routes specialists via ``agents.registry.FACTORIES``
so all 15 doc-types reach production — the verifier branching stays
gated to the same five types.

Story 3.3 added the MIME pre-step: before classifier dispatch, ``head_source``
returns the object's content type. PDFs are downloaded and rendered to PNG
bytes via ``pdf.converter.pdf_to_images`` (page1 only at this stage —
``_pdf_mode_for`` is wired forward-compat for the BankStatement specialist
in Epic 5). Native images keep the presigned-URL fast path.
"""

from __future__ import annotations

import json
from typing import Any

from agno.agent import Agent
from agno.media import Image

from doc_extractor import __version__, markdown_io, s3_io
from doc_extractor.agents.classifier import create_classifier_agent
from doc_extractor.agents.registry import FACTORIES
from doc_extractor.agents.retry import with_validation_retry
from doc_extractor.agents.verifier import create_verifier_agent
from doc_extractor.config.precedence import resolve_agent_config
from doc_extractor.disagreement import record_disagreement
from doc_extractor.exceptions import PydanticValidationError
from doc_extractor.pdf.converter import PdfMode, pdf_to_images
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.application_form import ApplicationForm
from doc_extractor.schemas.bank_account_confirmation import BankAccountConfirmation
from doc_extractor.schemas.bank_statement import BankStatement
from doc_extractor.schemas.base import Frontmatter
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.company_extract import CompanyExtract
from doc_extractor.schemas.entity_ownership import EntityOwnership
from doc_extractor.schemas.ids import DriverLicence, NationalID, Passport, Visa
from doc_extractor.schemas.other import Other
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.pep_declaration import PEP_Declaration
from doc_extractor.schemas.proof_of_address import ProofOfAddress
from doc_extractor.schemas.tax_residency import TaxResidency
from doc_extractor.schemas.verification_report import VerificationReport
from doc_extractor.schemas.verifier import VerifierAudit

CLASSIFIER_INPUT = "Classify this document image."

PDF_CONTENT_TYPE = "application/pdf"
PDF_KEY_SUFFIX = ".pdf"


# Story 4.4 — five safety-critical doc types where the post-extraction
# verifier audit runs (and a `fail` verdict routes to the disagreement
# queue). Other doc-types skip the verifier; the specialist's typed
# output is the only contract.
_VERIFIER_GATED_TYPES: frozenset[str] = frozenset({
    "Passport",
    "DriverLicence",
    "NationalID",
    "Visa",
    "PaymentReceipt",
})


class _SpecialistMeta:
    """Per-doc-type pipeline metadata: agent name, prompt text, schema class.

    Factory dispatch goes through ``agents.registry.FACTORIES`` (P2 fix);
    this table carries the *other* per-type knobs the pipeline needs:
    the snake-case agent name (telemetry / config / provenance), the
    user-side prompt fed to the specialist, and the expected schema class
    so the post-retry typecheck has something concrete to assert.
    """

    __slots__ = ("agent_name", "input_text", "schema_cls")

    def __init__(
        self,
        *,
        agent_name: str,
        input_text: str,
        schema_cls: type[Frontmatter],
    ) -> None:
        self.agent_name = agent_name
        self.input_text = input_text
        self.schema_cls = schema_cls


# Every DOC_TYPES literal must appear here. The classifier is constrained
# to those 15 strings via Pydantic's structured-output schema, so a
# missing entry surfaces as a clean ``KeyError`` rather than silently
# routing to a fallback. The sentinel
# ``test_specialist_meta_covers_all_doc_types`` in the integration suite
# fails loudly if a new ``DOC_TYPES`` literal is added without a metadata
# row here.
_SPECIALIST_META: dict[str, _SpecialistMeta] = {
    "Passport": _SpecialistMeta(
        agent_name="passport",
        input_text="Extract the passport fields from this image.",
        schema_cls=Passport,
    ),
    "DriverLicence": _SpecialistMeta(
        agent_name="driver_licence",
        input_text="Extract the driver licence fields from this image.",
        schema_cls=DriverLicence,
    ),
    "NationalID": _SpecialistMeta(
        agent_name="national_id",
        input_text="Extract the national ID fields from this image.",
        schema_cls=NationalID,
    ),
    "Visa": _SpecialistMeta(
        agent_name="visa",
        input_text="Extract the visa fields from this image.",
        schema_cls=Visa,
    ),
    "PaymentReceipt": _SpecialistMeta(
        agent_name="payment_receipt",
        input_text="Extract the payment receipt fields from this image.",
        schema_cls=PaymentReceipt,
    ),
    "PEP_Declaration": _SpecialistMeta(
        agent_name="pep_declaration",
        input_text="Extract the PEP declaration fields from this image.",
        schema_cls=PEP_Declaration,
    ),
    "VerificationReport": _SpecialistMeta(
        agent_name="verification_report",
        input_text="Extract the verification report fields from this image.",
        schema_cls=VerificationReport,
    ),
    "ApplicationForm": _SpecialistMeta(
        agent_name="application_form",
        input_text="Extract the application form fields from this image.",
        schema_cls=ApplicationForm,
    ),
    "BankStatement": _SpecialistMeta(
        agent_name="bank_statement",
        input_text="Extract the bank statement header and closing balance from this image.",
        schema_cls=BankStatement,
    ),
    "BankAccountConfirmation": _SpecialistMeta(
        agent_name="bank_account_confirmation",
        input_text="Extract the bank account confirmation fields from this image.",
        schema_cls=BankAccountConfirmation,
    ),
    "CompanyExtract": _SpecialistMeta(
        agent_name="company_extract",
        input_text="Extract the company extract fields from this image.",
        schema_cls=CompanyExtract,
    ),
    "EntityOwnership": _SpecialistMeta(
        agent_name="entity_ownership",
        input_text="Extract the entity ownership fields from this image.",
        schema_cls=EntityOwnership,
    ),
    "ProofOfAddress": _SpecialistMeta(
        agent_name="proof_of_address",
        input_text="Extract the proof-of-address fields from this image.",
        schema_cls=ProofOfAddress,
    ),
    "TaxResidency": _SpecialistMeta(
        agent_name="tax_residency",
        input_text="Extract the tax residency fields from this image.",
        schema_cls=TaxResidency,
    ),
    "Other": _SpecialistMeta(
        agent_name="other",
        input_text="Extract any text and structure from this image.",
        schema_cls=Other,
    ),
}

# Re-exported for backwards-compat with callers that imported these constants.
PASSPORT_INPUT = _SPECIALIST_META["Passport"].input_text
PAYMENT_RECEIPT_INPUT = _SPECIALIST_META["PaymentReceipt"].input_text


def _analysis_key_for(source_key: str) -> str:
    """Derive the analysis-bucket key. AC §4: append ``.md`` to the source key."""
    return f"{source_key}.md"


def _pdf_mode_for(doc_type: str) -> PdfMode:
    """Per-doc-type rendering mode. BankStatement gets all pages; everything
    else stays on the single-page fast path."""
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

    # P2 fix: dispatch via FACTORIES instead of an inline Passport-only
    # import. The classifier's structured output is constrained to the 15
    # DOC_TYPES literals, so both lookups below are total — a KeyError
    # here would mean a developer added a new DOC_TYPES entry but forgot
    # to register a factory or specialist metadata.
    factory = FACTORIES[classification.doc_type]
    meta = _SPECIALIST_META[classification.doc_type]

    # Story 3.8 — wrap the specialist call in with_validation_retry. Story
    # 4.4 generalised this from PaymentReceipt to all five verifier-gated
    # types; P2 (this fix) extends it to every doc_type. Specialists
    # default to Sonnet (top-tier) per agents.yaml, so the escalation path
    # is dormant in production today; the wrapping is forward-compat and
    # exercises the validation_failure → disagreement queue branch
    # uniformly across types.
    #
    # Story 6.1 — the factory closure captures every constructed agent so
    # we can read the LAST agent's ``run_response`` for the forensic
    # payload (raw text + metadata) regardless of whether the retry
    # succeeded or exhausted. Without this, the retry layer holds the
    # only reference and the caller can't see the raw model output.
    captured_agents: list[Agent] = []

    def _retry_factory(_tier: str) -> Agent:
        agent = factory()
        captured_agents.append(agent)
        return agent

    try:
        content, retry_count = await with_validation_retry(
            _retry_factory,
            meta.input_text,
            agent_name=meta.agent_name,
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

    if not isinstance(content, meta.schema_cls):
        raise TypeError(
            f"{meta.agent_name} retry returned {type(content).__name__},"
            f" expected {meta.schema_cls.__name__}"
        )
    _populate_pipeline_provenance(content, agent_name=meta.agent_name)
    extracted: Frontmatter = content

    # Story 3.7 (PaymentReceipt) → 4.4 (5 gated types): verifier audit
    # runs only on safety-critical specialists, using a single audit
    # prompt. The verifier receives the typed instance dump as JSON so
    # prompt-level diversity catches a different class of error than
    # re-running the extraction prompt would (architecture Decision 1).
    verifier_audit: VerifierAudit | None = None
    verifier_agent: Agent | None = None
    if classification.doc_type in _VERIFIER_GATED_TYPES:
        verifier_input = json.dumps(content.model_dump(), ensure_ascii=False, indent=2)
        verifier_agent = create_verifier_agent()
        verifier_result = await verifier_agent.arun(verifier_input, images=[image])
        audit = verifier_result.content
        if not isinstance(audit, VerifierAudit):
            raise TypeError(
                f"Verifier agent returned {type(audit).__name__}, expected VerifierAudit"
            )
        verifier_audit = audit

    md_text = markdown_io.render_to_md(extracted)
    s3_io.write_analysis(analysis_key, md_text)

    # Story 3.9 — write a disagreement-queue entry when the verifier flagged
    # ≥1 field as `disagree` (overall=="fail"). `uncertain` is NOT written:
    # downstream surfaces it as advisory only. Non-gated types never reach
    # this branch (verifier_audit stays None).
    # Story 6.1 — inline the raw responses from the successful specialist
    # call (last agent the retry layer used) and the verifier call so the
    # disagreement entry carries the full forensic payload.
    disagreement_key: str | None = None
    if verifier_audit is not None and verifier_audit.overall == "fail":
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
        "verifier_audit": verifier_audit.model_dump() if verifier_audit is not None else None,
        "disagreement_key": disagreement_key,
        "retry_count": retry_count,
    }
