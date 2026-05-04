"""Render Pydantic frontmatter to YAML-frontmatter Markdown and parse it back.

The output shape is `---\\n<yaml>\\n---\\n\\n` (leading fence, YAML body,
closing fence, one blank line). `yaml.safe_dump(allow_unicode=True,
sort_keys=False)` matches the byte-stable contract that
`tests/unit/test_schema_byte_stability.py` snapshots, so anything written
through `render_to_md` and re-rendered after `parse_md` is byte-identical.

Mask preservation is verbatim: pre-masked strings such as
``"6217 **** **** 0083"`` and CJK characters round-trip without escaping or
normalisation (FR25, FR26).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml  # type: ignore[import-untyped]  # dev-dep `types-PyYAML` not yet wired

from doc_extractor.schemas import Frontmatter, Passport
from doc_extractor.schemas.application_form import ApplicationForm
from doc_extractor.schemas.bank_account_confirmation import BankAccountConfirmation
from doc_extractor.schemas.bank_statement import BankStatement
from doc_extractor.schemas.company_extract import CompanyExtract
from doc_extractor.schemas.entity_ownership import EntityOwnership
from doc_extractor.schemas.ids import DriverLicence, NationalID, Visa
from doc_extractor.schemas.other import Other
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.pep_declaration import PEP_Declaration
from doc_extractor.schemas.proof_of_address import ProofOfAddress
from doc_extractor.schemas.tax_residency import TaxResidency
from doc_extractor.schemas.verification_report import VerificationReport

_FENCE = "---"


def _now_iso8601() -> str:
    """Return the current UTC time as ISO 8601 with the ``Z`` suffix.

    Module-level hook so tests can monkeypatch a fixed clock without
    poking at ``datetime`` itself.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _autofill_provenance(data: dict[str, Any]) -> None:
    """Populate ``extractor_version`` and ``extraction_timestamp`` if empty.

    Caller-set values win — pre-populated provenance fields render verbatim
    so deterministic snapshots can pin a fixed timestamp / version. The
    other three provenance fields (``extraction_provider``,
    ``extraction_model``, ``prompt_version``) belong to the pipeline
    orchestrator (Story 7.5 §3) — this helper does NOT touch them.
    """
    if not data.get("extractor_version"):
        # Lazy import to dodge the ``doc_extractor.__init__`` circular path
        # — markdown_io is imported during package init via the schemas
        # subtree.
        from doc_extractor import __version__ as _ext_v

        data["extractor_version"] = _ext_v
    if not data.get("extraction_timestamp"):
        data["extraction_timestamp"] = _now_iso8601()

# `Frontmatter` itself has `extra="forbid"`, so subclass-specific keys would
# fail to validate against the base class. Dispatch on `doc_type` to the
# matching subclass; unknown / empty doc_types fall back to `Frontmatter`.
# Every DOC_TYPES literal must appear here — without an entry, parse_md
# falls back to Frontmatter and rejects the subclass-specific keys (the
# round-trip contract for `tests/unit/test_markdown_io_round_trip.py`
# parametrizes across all 15). Listed manually rather than imported from
# `agents.registry.FACTORIES` to avoid pulling agno + every specialist
# into the schema-only import graph.
_SCHEMA_BY_DOC_TYPE: dict[str, type[Frontmatter]] = {
    "Passport": Passport,
    "DriverLicence": DriverLicence,
    "NationalID": NationalID,
    "Visa": Visa,
    "PaymentReceipt": PaymentReceipt,
    "PEP_Declaration": PEP_Declaration,
    "VerificationReport": VerificationReport,
    "ApplicationForm": ApplicationForm,
    "BankStatement": BankStatement,
    "BankAccountConfirmation": BankAccountConfirmation,
    "CompanyExtract": CompanyExtract,
    "EntityOwnership": EntityOwnership,
    "ProofOfAddress": ProofOfAddress,
    "TaxResidency": TaxResidency,
    "Other": Other,
}


def render_to_md(frontmatter: Frontmatter) -> str:
    """Render a Frontmatter (or subclass) to YAML-frontmatter Markdown.

    Story 7.5 — auto-fills ``extractor_version`` (from
    ``doc_extractor.__version__``) and ``extraction_timestamp`` (current
    UTC, ISO 8601 with ``Z`` suffix) when those fields are empty. Caller-
    supplied values win, so deterministic snapshots can pin both. The
    pipeline-supplied provenance fields (``extraction_provider``,
    ``extraction_model``, ``prompt_version``) are populated by
    ``pipelines.vision_path`` before render.
    """
    data = frontmatter.model_dump()
    _autofill_provenance(data)
    body = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
    )
    return f"{_FENCE}\n{body}{_FENCE}\n\n"


def parse_md(text: str) -> Frontmatter:
    # Split exactly twice so any `---` inside multi-line YAML strings stays
    # in the body rather than being treated as a fence.
    parts = text.split(_FENCE, 2)
    if len(parts) < 3:
        raise ValueError("missing YAML frontmatter fences (expected `---` ... `---`)")

    leading, yaml_body, _trailing = parts
    if leading.strip():
        raise ValueError("unexpected content before opening `---` fence")

    data: Any = yaml.safe_load(yaml_body)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"frontmatter must be a mapping, got {type(data).__name__}")

    schema_class = _SCHEMA_BY_DOC_TYPE.get(str(data.get("doc_type", "")), Frontmatter)
    return schema_class.model_validate(data)
