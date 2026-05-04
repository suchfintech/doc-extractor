"""Schema byte-stability snapshot battery (Story 7.2).

The Pydantic schemas in ``src/doc_extractor/schemas/`` are the project's
public output contract — external consumers (merlin, cny-flow) re-read
``.md`` frontmatter against them, so an accidental field rename, type
change, or reordering is a breaking change masquerading as a typo.

Story 7.2 migrated the formerly-inline canonical-instance assertions to a
**snapshot-file** approach: each schema's canonical YAML lives at
``tests/unit/schema_snapshots/<name>.yaml`` so any drift surfaces as a
visible YAML diff in PR review (rather than a hidden ``EXPECTED_*_YAML``
triple-quoted string change buried in a 1000-line test file).

Workflow:

1. Edit a schema deliberately + bump ``extractor_version`` per FR27.
2. ``python scripts/rebaseline_schemas.py --dry-run`` to preview the
   snapshot delta.
3. ``python scripts/rebaseline_schemas.py`` to write the new snapshots.
4. Commit schema + snapshot updates together.

Adding a new schema?

1. Add a canonical-instance factory in ``scripts/rebaseline_schemas.py``
   and an entry in its ``CANONICAL_INSTANCES`` list.
2. Run the rebaseline script to write the new snapshot.
3. Append the same ``(model_cls, snapshot_name)`` pair to
   ``SCHEMAS_AND_FIXTURES`` below.
4. If it's a DOC_TYPES doc-type, also remove its name from
   ``KNOWN_PENDING_DOC_TYPES`` — the forward-compat sentinel below will
   fail loudly if you forget either step.

This file keeps a handful of *specialised* assertions alongside the
parametrized snapshot test — CJK preservation, mask preservation,
null-vs-empty-list distinctions, the FR27 deprecation expiry sentinel,
and field-order-matches-inheritance — because those have business
meaning beyond the byte-stable snapshot alone.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from doc_extractor.schemas import (
    Classification,
    DriverLicence,
    Frontmatter,
    IDDocBase,
    NationalID,
    Passport,
    PaymentReceipt,
    VerifierAudit,
    Visa,
)
from doc_extractor.schemas.application_form import ApplicationForm
from doc_extractor.schemas.bank import BankDocBase
from doc_extractor.schemas.bank_account_confirmation import BankAccountConfirmation
from doc_extractor.schemas.bank_statement import BankStatement
from doc_extractor.schemas.classification import DOC_TYPES
from doc_extractor.schemas.company_extract import CompanyExtract
from doc_extractor.schemas.entity_ownership import EntityOwnership, UltimateBeneficialOwner
from doc_extractor.schemas.other import Other
from doc_extractor.schemas.pep_declaration import PEP_Declaration
from doc_extractor.schemas.proof_of_address import ProofOfAddress
from doc_extractor.schemas.tax_residency import TaxResidency
from doc_extractor.schemas.verification_report import VerificationReport

SNAPSHOT_DIR = Path(__file__).parent / "schema_snapshots"


# ---------------------------------------------------------------------------
# Parametrised snapshot battery
# ---------------------------------------------------------------------------

# (model_cls, snapshot_name). Snapshot files live at
# ``tests/unit/schema_snapshots/<name>.yaml`` and are regenerated via
# ``scripts/rebaseline_schemas.py``.
SCHEMAS_AND_FIXTURES: list[tuple[type[BaseModel], str]] = [
    # All 15 DOC_TYPES schemas (Other landed in Story 5.5).
    (Passport, "passport"),
    (DriverLicence, "driver_licence"),
    (NationalID, "national_id"),
    (Visa, "visa"),
    (PaymentReceipt, "payment_receipt"),
    (PEP_Declaration, "pep_declaration"),
    (VerificationReport, "verification_report"),
    (ApplicationForm, "application_form"),
    (BankStatement, "bank_statement"),
    (BankAccountConfirmation, "bank_account_confirmation"),
    (CompanyExtract, "company_extract"),
    (EntityOwnership, "entity_ownership"),
    (ProofOfAddress, "proof_of_address"),
    (TaxResidency, "tax_residency"),
    (Other, "other"),
    # Auxiliary schemas (base classes + helpers).
    (Frontmatter, "frontmatter"),
    (IDDocBase, "id_doc_base"),
    (BankDocBase, "bank_doc_base"),
    (Classification, "classification"),
    (VerifierAudit, "verifier_audit"),
    (UltimateBeneficialOwner, "ultimate_beneficial_owner"),
]


def _load_snapshot(name: str) -> str:
    return (SNAPSHOT_DIR / f"{name}.yaml").read_text(encoding="utf-8")


def _load_canonical(model_cls: type[BaseModel], name: str) -> BaseModel:
    """Validate a snapshot YAML back into its canonical Pydantic instance."""
    data = yaml.safe_load(_load_snapshot(name))
    return model_cls.model_validate(data)


def _dump(instance: BaseModel) -> str:
    return yaml.safe_dump(
        instance.model_dump(),
        allow_unicode=True,
        sort_keys=False,
    )


@pytest.mark.parametrize(
    "model_cls,snapshot_name",
    SCHEMAS_AND_FIXTURES,
    ids=[name for _, name in SCHEMAS_AND_FIXTURES],
)
def test_yaml_snapshot_byte_stable(
    model_cls: type[BaseModel], snapshot_name: str
) -> None:
    """Validate snapshot YAML → instance → dump → byte-equal snapshot YAML.

    A failure here means a schema field renamed, retyped, reordered, or
    a default changed without re-baselining. Run
    ``python scripts/rebaseline_schemas.py --dry-run`` to see the diff;
    if intentional, re-baseline + bump ``extractor_version``.
    """
    expected = _load_snapshot(snapshot_name)
    instance = model_cls.model_validate(yaml.safe_load(expected))
    actual = _dump(instance)
    assert actual == expected, (
        f"{snapshot_name} byte-stability broke. Re-baseline if intentional:\n"
        f"  python scripts/rebaseline_schemas.py --dry-run\n"
        f"  python scripts/rebaseline_schemas.py"
    )


@pytest.mark.parametrize(
    "model_cls,snapshot_name",
    SCHEMAS_AND_FIXTURES,
    ids=[name for _, name in SCHEMAS_AND_FIXTURES],
)
def test_canonical_dump_is_idempotent(
    model_cls: type[BaseModel], snapshot_name: str
) -> None:
    """Two consecutive ``yaml.safe_dump`` calls on the same instance produce
    byte-equal output. Catches accidental introduction of nondeterministic
    serialisation (e.g. a Pydantic ``model_dump`` mode that emits dicts in
    insertion order vs. sorted order)."""
    instance = _load_canonical(model_cls, snapshot_name)
    assert _dump(instance) == _dump(instance)


# ---------------------------------------------------------------------------
# Forward-compat sentinel: DOC_TYPES coverage
# ---------------------------------------------------------------------------

# DOC_TYPES literals not yet implemented as a schema. Empty as of Story
# 5.5 (Other landed). The leak-detection assertion below fires when a
# name is added here that's actually been committed — keeps the gate
# tight as the schema set evolves.
KNOWN_PENDING_DOC_TYPES: frozenset[str] = frozenset()


def test_every_doc_type_has_a_snapshot_unless_explicitly_pending() -> None:
    """Every DOC_TYPES literal must either be covered by a snapshot fixture
    OR be in ``KNOWN_PENDING_DOC_TYPES``. Auto-fails when 5.5 (Other) lands
    so the contributor remembers to add the snapshot + parametrize entry."""
    all_doc_types = set(get_args(DOC_TYPES))
    fixture_class_names = {model_cls.__name__ for model_cls, _ in SCHEMAS_AND_FIXTURES}
    expected_covered = all_doc_types - KNOWN_PENDING_DOC_TYPES

    missing = expected_covered - fixture_class_names
    assert not missing, (
        "DOC_TYPES missing snapshot fixtures: "
        f"{sorted(missing)}. Add canonical-instance factories in "
        "scripts/rebaseline_schemas.py and append to SCHEMAS_AND_FIXTURES."
    )


def test_known_pending_doc_types_are_actually_pending() -> None:
    """If a name in ``KNOWN_PENDING_DOC_TYPES`` corresponds to a schema
    that's actually been committed, the pending-list is stale and silently
    weakens the gate. Detect by importing the package and checking for
    the class name."""
    import doc_extractor.schemas as schemas_pkg

    leaked: list[str] = []
    for pending in KNOWN_PENDING_DOC_TYPES:
        if hasattr(schemas_pkg, pending):
            leaked.append(pending)
    assert not leaked, (
        f"KNOWN_PENDING_DOC_TYPES contains schemas that have actually "
        f"landed: {sorted(leaked)}. Remove from the pending list, add a "
        f"canonical-instance factory in scripts/rebaseline_schemas.py, "
        f"append to SCHEMAS_AND_FIXTURES, and run "
        f"`python scripts/rebaseline_schemas.py`."
    )


def test_doc_types_count_is_15() -> None:
    """The fifteen-document scope was set in Story 1.7. Expanding it is a
    real architectural change; this sentinel forces the contributor to
    update the architecture doc + this test together rather than silently
    growing the schema set."""
    assert len(get_args(DOC_TYPES)) == 15


# ---------------------------------------------------------------------------
# Specialised assertions — kept because they have business meaning beyond
# the byte-stable snapshot. All load their canonical instance from the
# snapshot file rather than re-defining a Python literal.
# ---------------------------------------------------------------------------


def test_none_inputs_coerce_to_empty_string() -> None:
    """The None→'' validator on ``Frontmatter`` keeps YAML output free of
    ``null`` literals for string fields. Required for byte-stability —
    ``yaml.safe_dump(None)`` renders ``null``, not ``''``."""
    p = Passport(name_latin=None, name_cjk=None)  # type: ignore[arg-type]
    dumped = _dump(p)
    assert "null" not in dumped
    assert "name_latin: ''" in dumped
    assert "name_cjk: ''" in dumped


def test_passport_field_order_matches_inheritance_chain() -> None:
    """Frontmatter fields first, then IDDocBase, then Passport additions.
    Pydantic preserves declaration order, so an accidental reordering
    surfaces here before it shows up in a snapshot diff."""
    keys = list(Passport.model_fields.keys())
    assert keys == [
        # Frontmatter base
        "extractor_version",
        "extraction_provider",
        "extraction_model",
        "extraction_timestamp",
        "prompt_version",
        "doc_type",
        "doc_subtype",
        "jurisdiction",
        "name_latin",
        "name_cjk",
        # IDDocBase additions
        "doc_number",
        "dob",
        "issue_date",
        "expiry_date",
        "place_of_birth",
        "sex",
        # Passport additions
        "passport_number",
        "nationality",
        "mrz_line_1",
        "mrz_line_2",
    ]


def test_payment_receipt_field_order_matches_inheritance() -> None:
    keys = list(PaymentReceipt.model_fields.keys())
    assert keys == [
        # Frontmatter base
        "extractor_version",
        "extraction_provider",
        "extraction_model",
        "extraction_timestamp",
        "prompt_version",
        "doc_type",
        "doc_subtype",
        "jurisdiction",
        "name_latin",
        "name_cjk",
        # PaymentReceipt new fields (debit/credit split)
        "receipt_amount",
        "receipt_currency",
        "receipt_time",
        "receipt_debit_account_name",
        "receipt_debit_account_number",
        "receipt_debit_bank_name",
        "receipt_credit_account_name",
        "receipt_credit_account_number",
        "receipt_credit_bank_name",
        "receipt_reference",
        "receipt_payment_app",
        # Deprecated aliases — overlap window expires 2026-08-03 (FR27)
        "receipt_counterparty_name",
        "receipt_counterparty_account",
    ]


def test_payment_receipt_preserves_cjk_and_mask_verbatim() -> None:
    receipt = _load_canonical(PaymentReceipt, "payment_receipt")
    dumped = _dump(receipt)
    # CJK characters appear raw, not as \\uXXXX escapes.
    assert "张三" in dumped
    assert "中国工商银行" in dumped
    assert "工商银行手机银行" in dumped
    assert "\\u" not in dumped
    # Account-number masks survive byte-equal.
    assert "6217 **** **** 0083" in dumped
    assert "02-0248-0242329-02" in dumped


def test_payment_receipt_deprecated_overlap_window_not_yet_expired() -> None:
    """Sentinel: when the FR27 one-quarter overlap closes, intentionally
    remove the deprecated fields and bump ``extractor_version``. This test
    fails on 2026-08-03 to force the cleanup decision."""
    assert date.today() < date(2026, 8, 3), (
        "FR27 overlap window for receipt_counterparty_* expired — drop the "
        "deprecated fields from PaymentReceipt and bump extractor_version."
    )


def test_national_id_preserves_cjk_and_id_number_verbatim() -> None:
    nid = _load_canonical(NationalID, "national_id")
    dumped = _dump(nid)
    assert "张三" in dumped
    assert "中国" in dumped
    assert "北京市公安局朝阳分局" in dumped
    assert "北京市朝阳区建国门外大街1号" in dumped
    assert "\\u" not in dumped
    # The 18-digit Chinese national ID round-trips byte-equal — the embedded
    # DOB at positions 7–14 and gender at position 17 are content the
    # extractor must not rewrite.
    assert "110101199003150019" in dumped


def test_bank_statement_preserves_account_number_hyphens_verbatim() -> None:
    """NZ-style hyphenated account numbers and the comma-separated balance
    survive byte-equal — both are extractor outputs, not normalised values."""
    bs = _load_canonical(BankStatement, "bank_statement")
    dumped = _dump(bs)
    assert "02-0248-0242329-02" in dumped
    assert "NZD 12,345.67" in dumped


def test_bank_documents_share_bank_doc_base_field_order() -> None:
    """``BankStatement`` and ``BankAccountConfirmation`` both inherit from
    ``BankDocBase`` so the first 15 fields (10 Frontmatter + 5 BankDocBase)
    must be in the same order. Catches an accidental BankDocBase reorder
    that would silently desync the two doc types."""
    bs_keys = list(BankStatement.model_fields.keys())
    bac_keys = list(BankAccountConfirmation.model_fields.keys())
    common_prefix = bs_keys[:15]
    assert common_prefix == bac_keys[:15]
    # BankDocBase additions follow the Frontmatter base, in order.
    assert common_prefix[10:] == [
        "bank_name",
        "account_holder_name",
        "account_number",
        "account_type",
        "currency",
    ]


def test_company_extract_distinguishes_null_list_from_empty_list() -> None:
    """``list[str] | None = None`` is the explicit "not extracted" sentinel;
    ``[]`` is the explicit "extracted, but no items". Both are meaningful
    and YAML must render them distinctly. The Frontmatter validator has
    a type-aware None-coercion (Story 5.3) so list fields preserve None
    rather than collapsing to ``""``."""
    none_extract = CompanyExtract(directors=None, shareholders=None)
    none_dumped = _dump(none_extract)
    assert "directors: null" in none_dumped
    assert "shareholders: null" in none_dumped

    empty_extract = CompanyExtract(directors=[], shareholders=[])
    empty_dumped = _dump(empty_extract)
    assert "directors: []" in empty_dumped
    assert "shareholders: []" in empty_dumped


def test_entity_ownership_preserves_cjk_in_nested_ubo() -> None:
    """``list[BaseModel]`` round-trip: CJK content in a nested
    ``UltimateBeneficialOwner`` survives byte-equal."""
    eo = _load_canonical(EntityOwnership, "entity_ownership")
    dumped = _dump(eo)
    assert "陳大文" in dumped
    assert "\\u" not in dumped


def test_entity_ownership_preserves_ownership_percentage_verbatim() -> None:
    """``ownership_percentage`` is a free-form string ("60%", "0.4", "40")
    — extractor output is preserved as-is so downstream consumers see the
    document's printed format, not a normalised percentage."""
    eo = _load_canonical(EntityOwnership, "entity_ownership")
    dumped = _dump(eo)
    assert "ownership_percentage: 60%" in dumped
    assert "ownership_percentage: 40%" in dumped


def test_tax_residency_preserves_tin_formats_verbatim() -> None:
    """TINs are jurisdiction-specific formatted strings (NZ IRD numbers,
    US SSN-style, hyphenated, etc.). The extractor preserves the printed
    format byte-equal — no reformatting."""
    tr = _load_canonical(TaxResidency, "tax_residency")
    dumped = _dump(tr)
    assert "tin: 123-456-789" in dumped


def test_verifier_audit_overall_pinned_by_validator() -> None:
    """Sentinel: the ``VerifierAudit.overall`` validator pins the field to
    a deterministic rollup of ``field_audits`` (any disagree → fail). The
    canonical fixture has one disagree, so overall must be 'fail'."""
    audit = _load_canonical(VerifierAudit, "verifier_audit")
    assert audit.overall == "fail"


# ---------------------------------------------------------------------------
# Schema-level invariants — apply to every parametrized fixture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snapshot_name", [name for _, name in SCHEMAS_AND_FIXTURES]
)
def test_no_unicode_escapes_in_any_snapshot(snapshot_name: str) -> None:
    """``allow_unicode=True`` invariant — no ``\\uXXXX`` escapes in any
    committed snapshot. CJK / smart quotes / accents must round-trip raw."""
    body = _load_snapshot(snapshot_name)
    assert "\\u" not in body, f"{snapshot_name}.yaml contains \\u escapes"


def test_classifier_rejects_doc_type_outside_DOC_TYPES_literal() -> None:
    """``Classification.doc_type`` is the canonical 15-way enum;
    constructing a Classification with an unknown doc_type must fail
    Pydantic validation."""
    with pytest.raises(ValidationError):
        Classification(doc_type="MadeUpType")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# P16 — UltimateBeneficialOwner has its own validator + extra="forbid"
#
# UBO does NOT inherit from Frontmatter (would add 10 unrelated provenance
# fields), so the type-aware ``None → ""`` coercion and the ``extra="forbid"``
# guard had to be added explicitly. Pre-fix, ``UBO(name=None).name`` was
# ``None``, which renders as ``name: null`` in YAML — that breaks the
# byte-stability snapshot the moment a real document has a missing field.
# ---------------------------------------------------------------------------


def test_ubo_coerces_none_string_to_empty_string() -> None:
    """``None`` on a string field collapses to ``""`` so YAML output stays
    free of ``null`` literals (the byte-stability invariant)."""
    ubo = UltimateBeneficialOwner(name=None, dob=None, ownership_percentage=None)  # type: ignore[arg-type]
    assert ubo.name == ""
    assert ubo.dob == ""
    assert ubo.ownership_percentage == ""


def test_ubo_dump_renders_empty_string_not_null() -> None:
    """The validator-coerced empty strings render as ``''`` in YAML, not
    ``null``. Pre-fix the YAML body contained ``name: null`` which silently
    broke the byte-stable snapshot the first time a real document had a
    missing field."""
    ubo = UltimateBeneficialOwner(name=None)  # type: ignore[arg-type]
    dumped = yaml.safe_dump(ubo.model_dump(), allow_unicode=True, sort_keys=False)
    assert "name: ''" in dumped
    assert "null" not in dumped


def test_ubo_rejects_extra_fields() -> None:
    """``extra="forbid"`` blocks spurious keys — a typo or stale field
    name from an upstream change surfaces at validation time instead of
    silently dropping data."""
    with pytest.raises(ValidationError):
        UltimateBeneficialOwner(name="X", spurious_field="Y")  # type: ignore[call-arg]


def test_ubo_round_trip_preserves_cjk_via_entity_ownership() -> None:
    """Render → parse on an EntityOwnership with a CJK-named UBO survives
    byte-equal — the validator must NOT mangle non-empty strings on the
    way through."""
    from doc_extractor.markdown_io import parse_md, render_to_md

    eo = EntityOwnership(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-04T00:00:00Z",
        prompt_version="entity_ownership@0.1.0",
        doc_type="EntityOwnership",
        jurisdiction="HK",
        entity_name="Acme HK Ltd",
        ultimate_beneficial_owners=[
            UltimateBeneficialOwner(
                name="陳大文", dob="1990-01-15", ownership_percentage="60%"
            ),
        ],
    )
    md = render_to_md(eo)
    parsed = parse_md(md)
    assert parsed == eo
    assert isinstance(parsed, EntityOwnership)
    assert parsed.ultimate_beneficial_owners is not None
    assert parsed.ultimate_beneficial_owners[0].name == "陳大文"
