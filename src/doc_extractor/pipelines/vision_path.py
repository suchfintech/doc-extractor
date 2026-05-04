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
import time
from typing import Any

from agno.agent import Agent
from agno.media import Image

from doc_extractor import __version__, markdown_io, s3_io
from doc_extractor.agents.classifier import create_classifier_agent
from doc_extractor.agents.registry import FACTORIES
from doc_extractor.agents.retry import (
    AttemptRecord,
    _split_tier,
    tier_for_config,
    with_validation_retry,
)
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
from doc_extractor.telemetry import record_extraction

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
    """Story 6.1 + P4 (code review Round 2) — raw-text + metadata capture
    from an Agno Agent's ``run_response`` after ``arun`` returns.

    Verified against ``agno==2.6.4`` (pinned in ``pyproject.toml``). The
    actual shapes:

    * ``run_response.content`` — the typed Pydantic instance (NOT raw text).
    * ``run_response.messages`` — ordered ``Message`` list; the assistant-
      role message's ``content`` carries the model's raw text. Pre-fix
      this helper read ``messages[-1].content`` blindly which sometimes
      caught a tool / system message instead.
    * ``run_response.model_provider`` — provider name (``"anthropic"``).
      Pre-fix: read ``metrics.provider`` which doesn't exist.
    * ``run_response.model`` — model id (``"claude-sonnet-4-6-20260101"``).
      Pre-fix: read ``metrics.model`` which doesn't exist.
    * ``run_response.metrics.cost`` — float USD. Pre-fix: read
      ``metrics.cost_usd`` which doesn't exist.
    * ``run_response.metrics.duration`` — float SECONDS (multiplied by
      1000 here for the ms-shaped telemetry record). Pre-fix: read
      ``metrics.latency_ms`` which doesn't exist.

    All four pre-fix lookups silently returned ``None`` from
    ``getattr(..., None)`` and the defensive ``isinstance`` checks
    collapsed to defaults — the bug masqueraded as "Agno doesn't always
    populate metadata" rather than a typo. Tests using bare ``MagicMock``
    fixtures with explicitly-pinned ``provider``/``model`` attrs hid the
    bug because MagicMock returns truthy children for any attribute name.

    Defensive against ``MagicMock`` auto-attrs at the leaf level: only
    real ``str`` / numeric values populate the result; otherwise defaults
    pass through.
    """
    raw_text = ""
    metadata = dict(_EMPTY_METADATA)

    if agent is None:
        return raw_text, metadata

    run_response = getattr(agent, "run_response", None)
    if run_response is None:
        return raw_text, metadata

    # Raw text from the assistant's most recent message (walk backwards so
    # any post-extraction follow-up tool/system messages don't pre-empt it).
    messages = getattr(run_response, "messages", None)
    if isinstance(messages, list):
        for msg in reversed(messages):
            role = getattr(msg, "role", None)
            content = getattr(msg, "content", None)
            if role == "assistant" and isinstance(content, str) and content:
                raw_text = content
                break

    provider = getattr(run_response, "model_provider", None)
    if isinstance(provider, str) and provider:
        metadata["provider"] = provider
    model = getattr(run_response, "model", None)
    if isinstance(model, str) and model:
        metadata["model"] = model

    metrics = getattr(run_response, "metrics", None)
    if metrics is not None:
        cost = getattr(metrics, "cost", None)
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            metadata["cost_usd"] = float(cost)
        duration = getattr(metrics, "duration", None)
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            # Agno emits duration in SECONDS; telemetry stores ms.
            metadata["latency_ms"] = float(duration) * 1000.0

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


def _build_image_for_source(
    source_key: str, *, print_presigned_url: bool = False
) -> Image:
    """Return the ``agno.media.Image`` primitive for ``source_key``.

    PDFs go through ``pdf_to_images(..., mode="page1")`` and are passed as
    raw PNG bytes via ``Image(content=...)``. Native images stay on the
    fast path with a presigned URL via ``Image(url=...)``.

    When ``print_presigned_url=True`` (CLI ``--show-image`` flag), the
    presigned URL is printed to stdout — only meaningful on the
    non-PDF fast path. PDFs read raw bytes locally and don't presign.
    """
    metadata = s3_io.head_source(source_key)
    content_type = str(metadata.get("content_type") or "")
    if _is_pdf_source(source_key, content_type):
        pdf_bytes = s3_io.get_source_bytes(source_key)
        png_pages = pdf_to_images(pdf_bytes, mode="page1")
        return Image(content=png_pages[0])

    presigned_url = s3_io.get_presigned_url(s3_io.SOURCE_BUCKET, source_key)
    if print_presigned_url:
        print(f"presigned_url: {presigned_url}")
    return Image(url=presigned_url)


def _section(title: str) -> None:
    print(f"=== {title} ===")


async def run(
    source_key: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    verbose: bool = False,
    show_image: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Process a single source document end-to-end.

    Returns a result dict with ``analysis_key``, ``skipped`` (HEAD-skip
    flag), ``doc_type``, ``verifier_audit`` (dumped :class:`VerifierAudit`
    for any of the five verifier-gated doc types, ``None`` otherwise),
    ``disagreement_key`` (set when the verifier returned ``fail`` or the
    retry exhausted), ``retry_count`` (0 on first-attempt success, 1 on
    escalated retry success), and ``cost_usd`` (sum of per-call cost
    across every Agno agent invoked — specialist attempts + verifier).

    P10 (code review Round 2) — orchestration is the only ``record_extraction``
    caller now. The retry helper returns per-attempt :class:`AttemptRecord`
    instances; this function iterates and emits one telemetry row per
    attempt + one for the HEAD-skip case + one for the verifier when run.
    Cost telemetry rolls up into the result dict so the eval harness can
    read it back via ``ExtractedDoc.cost_usd`` (P12).

    P13 (code review Round 3) — accepts the CLI's introspection /
    override flags directly so ``extract.py`` no longer needs an inline
    orchestration path:

    * ``provider``/``model`` thread through the classifier, specialist,
      and verifier factory calls as CLI overrides (precedence chain
      still applies — explicit > env > YAML > per-class fallback).
    * ``show_image=True`` prints the source's presigned URL.
    * ``dry_run=True`` prints the rendered ``.md`` to stdout instead of
      writing to S3.
    * ``verbose=True`` prints the five forensic sections (FR51) —
      resolved prompt / raw model response / Pydantic validation /
      rendered .md / cost telemetry.
    """
    analysis_key = _analysis_key_for(source_key)

    if s3_io.head_analysis(analysis_key):
        # P10 — emit a skip-marker telemetry row so cost-tracker accounting
        # has a complete picture even when extraction is short-circuited.
        # ``success=True`` because the analysis IS available (HEAD-skip is
        # the desired outcome of an idempotent re-run); ``cost_usd=0`` and
        # empty provider/model reflect that no provider call was made.
        record_extraction(
            source_key=source_key,
            doc_type="",
            agent="",
            provider="",
            model="",
            cost_usd=0.0,
            latency_ms=0.0,
            retry_count=0,
            success=True,
            prompt_version="",
            extractor_version=__version__,
        )
        return {
            "analysis_key": analysis_key,
            "skipped": True,
            "doc_type": "",
            "verifier_audit": None,
            "disagreement_key": None,
            "retry_count": 0,
            "cost_usd": 0.0,
        }

    image = _build_image_for_source(source_key, print_presigned_url=show_image)

    classifier = create_classifier_agent(provider=provider, model=model)
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

    # P11 — load the specialist's prompt version once so both the telemetry
    # records below and the provenance auto-fill in
    # ``_populate_pipeline_provenance`` see the same string. Pre-fix the
    # retry helper hardcoded ``prompt_version=""`` on every record.
    _, prompt_version = load_prompt(meta.agent_name)

    # P8 — derive the retry helper's primary_provider tier from the
    # actual resolved AgentConfig instead of the hardcoded
    # ``"anthropic-sonnet"`` (which made escalation dead for every
    # specialist that already defaults to Sonnet, and silently bypassed
    # escalation for Haiku-default agents like ``Other``).
    specialist_config = resolve_agent_config(meta.agent_name)
    primary_tier = tier_for_config(specialist_config.provider, specialist_config.model)

    cost_usd_total = 0.0
    # P10 — pass a fresh attempts list to the retry helper so we can
    # iterate per-attempt telemetry rows on BOTH the success and the
    # exception path. Without this, the per-attempt cost / raw text /
    # provider info would be unrecoverable mid-exception.
    attempts: list[AttemptRecord] = []

    # The retry helper calls ``agent_factory(tier)`` with the tier string,
    # but FACTORIES entries are ``create_X_agent(provider=None, model=None)``
    # which only accept keyword args. Wrap to discard the tier and forward
    # the CLI provider/model overrides through to the specialist factory.
    # Tier is informational for the retry helper's own bookkeeping (and
    # the AttemptRecord) — the factory builds the same specialist
    # regardless of which retry tier prompted the call.
    def _retry_factory(_tier: str) -> Agent:
        return factory(provider=provider, model=model)

    def _emit_specialist_telemetry() -> None:
        nonlocal cost_usd_total
        for i, att in enumerate(attempts):
            provider_part, model_part = _split_tier(att.tier)
            _, attempt_meta = _read_run_response(att.agent)
            # Trust Agno's reported model/provider when populated; fall
            # back to the tier-derived names so failed attempts (where
            # metrics may be unset) still report something meaningful.
            provider = attempt_meta["provider"] or provider_part
            model = attempt_meta["model"] or model_part
            cost = float(attempt_meta["cost_usd"])
            cost_usd_total += cost
            record_extraction(
                source_key=source_key,
                doc_type=classification.doc_type,
                agent=meta.agent_name,
                provider=provider,
                model=model,
                cost_usd=cost,
                latency_ms=att.latency_ms,
                retry_count=i,
                success=att.success,
                prompt_version=prompt_version,
                extractor_version=__version__,
            )

    try:
        content, retry_count = await with_validation_retry(
            _retry_factory,
            meta.input_text,
            agent_name=meta.agent_name,
            source_key=source_key,
            primary_provider=primary_tier,
            arun_kwargs={"images": [image]},
            doc_type=classification.doc_type,
            prompt_version=prompt_version,
            attempts_out=attempts,
        )
    except PydanticValidationError:
        # Retry exhausted (top-tier primary or escalated tier still failed).
        # ``attempts`` was populated in-place by the helper before it
        # raised; emit per-attempt telemetry rows + the disagreement-queue
        # entry with the LAST attempt's raw response.
        _emit_specialist_telemetry()
        last_agent = attempts[-1].agent if attempts else None
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

    _emit_specialist_telemetry()

    # Story 3.7 (PaymentReceipt) → 4.4 (5 gated types): verifier audit
    # runs only on safety-critical specialists, using a single audit
    # prompt. The verifier receives the typed instance dump as JSON so
    # prompt-level diversity catches a different class of error than
    # re-running the extraction prompt would (architecture Decision 1).
    verifier_audit: VerifierAudit | None = None
    verifier_agent: Agent | None = None
    if classification.doc_type in _VERIFIER_GATED_TYPES:
        verifier_input = json.dumps(content.model_dump(), ensure_ascii=False, indent=2)
        verifier_agent = create_verifier_agent(provider=provider, model=model)
        verifier_start = time.monotonic()
        verifier_result = await verifier_agent.arun(verifier_input, images=[image])
        verifier_latency_ms = (time.monotonic() - verifier_start) * 1000.0
        audit = verifier_result.content
        if not isinstance(audit, VerifierAudit):
            raise TypeError(
                f"Verifier agent returned {type(audit).__name__}, expected VerifierAudit"
            )
        verifier_audit = audit

        # P10 — emit a verifier telemetry row alongside the specialist's.
        _, verifier_prompt_version = load_prompt("verifier")
        _, verifier_meta = _read_run_response(verifier_agent)
        verifier_cost = float(verifier_meta["cost_usd"])
        cost_usd_total += verifier_cost
        record_extraction(
            source_key=source_key,
            doc_type=classification.doc_type,
            agent="verifier",
            provider=verifier_meta["provider"],
            model=verifier_meta["model"],
            cost_usd=verifier_cost,
            latency_ms=verifier_meta["latency_ms"] or verifier_latency_ms,
            retry_count=0,
            success=True,
            prompt_version=verifier_prompt_version,
            extractor_version=__version__,
        )

    # P7 (code review Round 3) — write the disagreement entry BEFORE the
    # analysis. If write_analysis succeeds but record_disagreement fails
    # (network blip / IAM glitch), the next idempotent retry sees the
    # analysis on S3, head_analysis returns True, and the disagreement
    # entry is permanently lost. Reversing the order means a partial
    # write either leaves no analysis (next retry re-runs the whole
    # pipeline + re-writes the disagreement) or leaves both — the latter
    # is the desired terminal state. record_disagreement is idempotent
    # per Story 6.4 (last-writer-wins on stable source_key path), so
    # re-running is safe.
    #
    # Story 3.9 — write a disagreement-queue entry when the verifier
    # flagged ≥1 field as `disagree` (overall=="fail"). `uncertain` is
    # NOT written: downstream surfaces it as advisory only. Non-gated
    # types never reach this branch (verifier_audit stays None).
    # Story 6.1 — inline the raw responses from the successful specialist
    # call (last agent the retry layer used) and the verifier call so the
    # disagreement entry carries the full forensic payload.
    disagreement_key: str | None = None
    if verifier_audit is not None and verifier_audit.overall == "fail":
        last_agent = attempts[-1].agent if attempts else None
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

    md_text = markdown_io.render_to_md(extracted)
    if dry_run:
        # P13 — print the rendered .md instead of writing to S3 so the
        # CLI's --dry-run flag can preview output without touching the
        # analysis bucket. Verbose mode prints the .md inside section 4
        # below, so suppress the duplicate here.
        if not verbose:
            print(md_text)
    else:
        s3_io.write_analysis(analysis_key, md_text)

    if verbose:
        # P13/FR51 — five forensic sections in order. The raw model
        # response comes from the LAST specialist attempt (Sonnet on
        # retry-success, primary on first-try) via _read_run_response.
        last_agent = attempts[-1].agent if attempts else None
        last_text, last_meta = _read_run_response(last_agent)
        prompt_text, _ = load_prompt(meta.agent_name)
        _section("1. Resolved prompt text")
        print(prompt_text)
        _section("2. Raw model response")
        print(last_text or "(no raw model text on agent.run_response)")
        _section("3. Pydantic validation result")
        print(extracted.model_dump())
        _section("4. Rendered .md content")
        print(md_text)
        _section("5. Cost telemetry")
        model_id = last_meta["model"] or model or "<resolved-by-config>"
        print(
            f"cost_usd={cost_usd_total:.4f} latency_ms={last_meta['latency_ms']:.0f} "
            f"model={model_id}"
        )

    return {
        "analysis_key": analysis_key,
        "skipped": False,
        "doc_type": classification.doc_type,
        "verifier_audit": verifier_audit.model_dump() if verifier_audit is not None else None,
        "disagreement_key": disagreement_key,
        "retry_count": retry_count,
        "cost_usd": cost_usd_total,
    }
