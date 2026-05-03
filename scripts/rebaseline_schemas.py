#!/usr/bin/env python3
"""Re-baseline the schema byte-stability snapshots (Story 7.2).

The schema-as-contract workflow (architecture §Schema-as-Contract) gates
every PR on byte-equal YAML serialisations of canonical Pydantic instances.
This script is the seed of those snapshots: each canonical instance lives
here as a Python literal; running the script writes the deterministic
``yaml.safe_dump(allow_unicode=True, sort_keys=False)`` output to
``tests/unit/schema_snapshots/<name>.yaml``.

After deliberate schema edits + a major-version bump (per FR27), run::

    python scripts/rebaseline_schemas.py --dry-run    # preview diffs
    python scripts/rebaseline_schemas.py              # write snapshots

Adding a new schema?

1. Add the canonical instance to ``CANONICAL_INSTANCES`` below.
2. Run this script (no flags) to write the new ``<name>.yaml``.
3. Append the same ``(model_cls, snapshot_name)`` pair to
   ``tests/unit/test_schema_byte_stability.py``'s
   ``SCHEMAS_AND_FIXTURES`` list.
4. If the schema is a DOC_TYPES doc-type, also remove its name from
   ``KNOWN_PENDING_DOC_TYPES`` in the test file (the forward-compat
   sentinel will fail loudly if you forget either step).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "tests" / "unit" / "schema_snapshots"

# Make src/ importable when this script is run from the repo root via
# `python scripts/rebaseline_schemas.py` without `pip install -e .`.
sys.path.insert(0, str(REPO_ROOT / "src"))

from doc_extractor.schemas import (  # noqa: E402
    Classification,
    Frontmatter,
    IDDocBase,
    Passport,
    PaymentReceipt,
    VerifierAudit,
)
from doc_extractor.schemas.application_form import ApplicationForm  # noqa: E402
from doc_extractor.schemas.bank import BankDocBase  # noqa: E402
from doc_extractor.schemas.bank_account_confirmation import (  # noqa: E402
    BankAccountConfirmation,
)
from doc_extractor.schemas.bank_statement import BankStatement  # noqa: E402
from doc_extractor.schemas.company_extract import CompanyExtract  # noqa: E402
from doc_extractor.schemas.entity_ownership import (  # noqa: E402
    EntityOwnership,
    UltimateBeneficialOwner,
)
from doc_extractor.schemas.ids import DriverLicence, NationalID, Visa  # noqa: E402
from doc_extractor.schemas.other import Other  # noqa: E402
from doc_extractor.schemas.pep_declaration import PEP_Declaration  # noqa: E402
from doc_extractor.schemas.proof_of_address import ProofOfAddress  # noqa: E402
from doc_extractor.schemas.tax_residency import TaxResidency  # noqa: E402
from doc_extractor.schemas.verification_report import VerificationReport  # noqa: E402


def _dump(instance: BaseModel) -> str:
    """Serialise via the canonical YAML contract used everywhere in the project."""
    body: str = yaml.safe_dump(
        instance.model_dump(),
        allow_unicode=True,
        sort_keys=False,
    )
    return body


# ---------------------------------------------------------------------------
# Canonical instances — single source of truth for the snapshot files.
#
# Each entry pairs a Pydantic instance (with all schema fields populated to
# plausible values) with the snapshot filename stem. The instances mix
# CJK, masked account numbers, and edge-case values where applicable so
# the byte-stable proof is meaningful, not just a tautology.
# ---------------------------------------------------------------------------


def _canonical_passport() -> Passport:
    return Passport(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="passport@1.0.0",
        doc_type="Passport",
        doc_subtype="",
        jurisdiction="HKG",
        name_latin="CHAN TAI MAN",
        name_cjk="陳大文",
        doc_number="K12345678",
        dob="1990-01-15",
        issue_date="2020-06-01",
        expiry_date="2030-05-31",
        place_of_birth="HONG KONG",
        sex="M",
        passport_number="K12345678",
        nationality="CHN",
        mrz_line_1="P<HKGCHAN<<TAI<MAN<<<<<<<<<<<<<<<<<<<<<<<<<<",
        mrz_line_2="K123456786CHN9001152M3005317<<<<<<<<<<<<<<00",
    )


def _canonical_payment_receipt() -> PaymentReceipt:
    return PaymentReceipt(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T19:00:00Z",
        prompt_version="0.1.0",
        doc_type="PaymentReceipt",
        jurisdiction="CN",
        receipt_amount="15000.00",
        receipt_currency="CNY",
        receipt_time="2025-07-01T00:00:00Z",
        receipt_debit_account_name="张三",
        receipt_debit_account_number="6217 **** **** 0083",
        receipt_debit_bank_name="中国工商银行",
        receipt_credit_account_name="GM6040",
        receipt_credit_account_number="02-0248-0242329-02",
        receipt_credit_bank_name="ANZ",
        receipt_reference="INV-2025-001",
        receipt_payment_app="工商银行手机银行",
    )


def _canonical_driver_licence() -> DriverLicence:
    return DriverLicence(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="driver_licence@0.1.0",
        doc_type="DriverLicence",
        doc_subtype="",
        jurisdiction="NZL",
        name_latin="JOHN DOE",
        name_cjk="",
        doc_number="EH123456",
        dob="1990-06-15",
        issue_date="2020-06-01",
        expiry_date="2030-05-31",
        place_of_birth="",
        sex="M",
        licence_class="Class 1",
        licence_endorsements="",
        licence_restrictions="",
        address="123 Queen Street Auckland 1010",
    )


def _canonical_national_id() -> NationalID:
    return NationalID(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="national_id@0.1.0",
        doc_type="NationalID",
        doc_subtype="",
        jurisdiction="CN",
        name_latin="",
        name_cjk="张三",
        doc_number="110101199003150019",
        dob="1990-03-15",
        issue_date="2020-06-01",
        expiry_date="2040-05-31",
        place_of_birth="",
        sex="M",
        nationality="中国",
        id_card_number="110101199003150019",
        issuing_authority="北京市公安局朝阳分局",
        address="北京市朝阳区建国门外大街1号",
    )


def _canonical_visa() -> Visa:
    return Visa(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="visa@0.1.0",
        doc_type="Visa",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="CHAN TAI MAN",
        name_cjk="",
        doc_number="ABCD1234567",
        dob="1990-01-15",
        issue_date="2024-03-01",
        expiry_date="2027-02-28",
        place_of_birth="",
        sex="M",
        visa_class="Resident Visa",
        issuing_country="NZ",
        host_country="NZ",
        valid_from="2024-03-01",
        valid_to="2027-02-28",
        entries_allowed="Multiple",
    )


def _canonical_pep_declaration() -> PEP_Declaration:
    return PEP_Declaration(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="pep_declaration@0.1.0",
        doc_type="PEP_Declaration",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="JOHN DOE",
        name_cjk="",
        is_pep="yes",
        pep_role="Member of Parliament",
        pep_jurisdiction="NZ",
        pep_relationship="self",
        declaration_date="2026-04-15",
        declarant_name="John Doe",
    )


def _canonical_verification_report() -> VerificationReport:
    return VerificationReport(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="verification_report@0.1.0",
        doc_type="VerificationReport",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        verifier_name="DIA",
        verification_date="2026-04-15",
        verification_method="electronic",
        subject_name="Jane Smith",
        subject_id_type="Passport",
        subject_id_number="LA123456",
        verification_outcome="verified",
    )


def _canonical_application_form() -> ApplicationForm:
    return ApplicationForm(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="application_form@0.1.0",
        doc_type="ApplicationForm",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        application_date="2026-04-15",
        applicant_name="Alice Wong",
        applicant_dob="1990-06-15",
        application_type="remittance customer onboarding",
        applicant_address="123 Queen Street Auckland 1010",
        applicant_occupation="Software Engineer",
    )


def _canonical_bank_statement() -> BankStatement:
    return BankStatement(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="bank_statement@0.1.0",
        doc_type="BankStatement",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        bank_name="ANZ Bank New Zealand",
        account_holder_name="John Doe",
        account_number="02-0248-0242329-02",
        account_type="savings",
        currency="NZD",
        statement_period_start="2025-06-01",
        statement_period_end="2025-06-30",
        statement_date="2025-07-01",
        closing_balance="NZD 12,345.67",
    )


def _canonical_bank_account_confirmation() -> BankAccountConfirmation:
    return BankAccountConfirmation(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="bank_account_confirmation@0.1.0",
        doc_type="BankAccountConfirmation",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        bank_name="ANZ Bank New Zealand",
        account_holder_name="Jane Smith",
        account_number="02-0248-0242329-02",
        account_type="current",
        currency="NZD",
        confirmation_date="2026-04-15",
        confirmation_authority="Sarah Chen, Branch Manager",
    )


def _canonical_company_extract() -> CompanyExtract:
    return CompanyExtract(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="company_extract@0.1.0",
        doc_type="CompanyExtract",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        company_name="Acme Holdings Limited",
        registration_number="1234567",
        incorporation_date="2018-04-15",
        registered_address="123 Queen Street, Auckland 1010, New Zealand",
        directors=["Alice Wong", "Bob Chen", "Charlie Smith"],
        shareholders=["Acme Group Ltd", "Beta Capital"],
    )


def _canonical_entity_ownership() -> EntityOwnership:
    return EntityOwnership(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="entity_ownership@0.1.0",
        doc_type="EntityOwnership",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        entity_name="Acme Holdings Limited",
        ultimate_beneficial_owners=[
            UltimateBeneficialOwner(
                name="Alice Wong", dob="1985-07-12", ownership_percentage="60%"
            ),
            UltimateBeneficialOwner(
                name="陳大文", dob="1990-01-15", ownership_percentage="40%"
            ),
        ],
    )


def _canonical_proof_of_address() -> ProofOfAddress:
    return ProofOfAddress(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="proof_of_address@0.1.0",
        doc_type="ProofOfAddress",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        holder_name="John Doe",
        address="123 Queen Street, Auckland 1010, New Zealand",
        document_date="2026-04-15",
        issuer="Mercury Energy",
        document_type="utility bill",
    )


def _canonical_tax_residency() -> TaxResidency:
    return TaxResidency(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="tax_residency@0.1.0",
        doc_type="TaxResidency",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        holder_name="John Doe",
        tax_jurisdiction="NZ",
        tin="123-456-789",
        residency_status="resident",
        effective_from="2024-01-01",
    )


def _canonical_other() -> Other:
    return Other(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="other@0.1.0",
        doc_type="Other",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        description="A handwritten document of unclear provenance",
        extracted_text="Page 1 reads: 'Please forward to processing.'",
        notes="model uncertain — flagging for human review",
    )


# Auxiliary schemas — base classes + helpers that don't ship as their own
# DOC_TYPES, but still need to be byte-stable because the rest of the
# package depends on their field shapes.


def _canonical_frontmatter() -> Frontmatter:
    return Frontmatter(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="frontmatter@0.1.0",
        doc_type="",
        doc_subtype="",
        jurisdiction="OTHER",
        name_latin="John Doe",
        name_cjk="约翰·杜",
    )


def _canonical_id_doc_base() -> IDDocBase:
    return IDDocBase(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="id_doc_base@0.1.0",
        doc_type="",
        doc_subtype="",
        jurisdiction="HKG",
        name_latin="CHAN TAI MAN",
        name_cjk="陳大文",
        doc_number="K12345678",
        dob="1990-01-15",
        issue_date="2020-06-01",
        expiry_date="2030-05-31",
        place_of_birth="HONG KONG",
        sex="M",
    )


def _canonical_bank_doc_base() -> BankDocBase:
    return BankDocBase(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="bank_doc_base@0.1.0",
        doc_type="",
        doc_subtype="",
        jurisdiction="NZ",
        name_latin="",
        name_cjk="",
        bank_name="ANZ Bank New Zealand",
        account_holder_name="John Doe",
        account_number="02-0248-0242329-02",
        account_type="savings",
        currency="NZD",
    )


def _canonical_classification() -> Classification:
    return Classification(
        doc_type="PaymentReceipt",
        jurisdiction="CN",
        doc_subtype="P",
    )


def _canonical_verifier_audit() -> VerifierAudit:
    return VerifierAudit(
        field_audits={
            "receipt_debit_account_name": "agree",
            "receipt_credit_account_name": "disagree",
            "receipt_debit_account_number": "abstain",
        },
        notes="image shows credit name 王五 but specialist claimed 李四",
    )


def _canonical_ultimate_beneficial_owner() -> UltimateBeneficialOwner:
    return UltimateBeneficialOwner(
        name="陳大文",
        dob="1990-01-15",
        ownership_percentage="40%",
    )


# (snapshot_name, factory) — list ordered for stable iteration; rebaseline
# always re-emits in this order so the diff in PR review is local to each
# changed schema, not noisy across the whole battery.
CANONICAL_INSTANCES: list[tuple[str, BaseModel]] = [
    ("passport", _canonical_passport()),
    ("driver_licence", _canonical_driver_licence()),
    ("national_id", _canonical_national_id()),
    ("visa", _canonical_visa()),
    ("payment_receipt", _canonical_payment_receipt()),
    ("pep_declaration", _canonical_pep_declaration()),
    ("verification_report", _canonical_verification_report()),
    ("application_form", _canonical_application_form()),
    ("bank_statement", _canonical_bank_statement()),
    ("bank_account_confirmation", _canonical_bank_account_confirmation()),
    ("company_extract", _canonical_company_extract()),
    ("entity_ownership", _canonical_entity_ownership()),
    ("proof_of_address", _canonical_proof_of_address()),
    ("tax_residency", _canonical_tax_residency()),
    ("other", _canonical_other()),
    # Auxiliary schemas — base classes + helpers.
    ("frontmatter", _canonical_frontmatter()),
    ("id_doc_base", _canonical_id_doc_base()),
    ("bank_doc_base", _canonical_bank_doc_base()),
    ("classification", _canonical_classification()),
    ("verifier_audit", _canonical_verifier_audit()),
    ("ultimate_beneficial_owner", _canonical_ultimate_beneficial_owner()),
]


def write_snapshots(
    out_dir: Path = DEFAULT_SNAPSHOT_DIR,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Write each canonical instance's YAML to ``<out_dir>/<name>.yaml``.

    Returns ``(written, unchanged)`` counts for the caller's stdout summary.
    In ``--dry-run`` mode the diff is printed and nothing is written; the
    counts still reflect what *would* change.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    unchanged = 0
    for name, instance in CANONICAL_INSTANCES:
        target = out_dir / f"{name}.yaml"
        new_body = _dump(instance)
        old_body = target.read_text(encoding="utf-8") if target.is_file() else ""
        if new_body == old_body:
            unchanged += 1
            continue
        if dry_run:
            print(f"--- {target} (would-change) ---")
            print(_unified_diff(old_body, new_body))
        else:
            target.write_text(new_body, encoding="utf-8")
            print(f"wrote {target.relative_to(REPO_ROOT)}")
        written += 1
    return written, unchanged


def _unified_diff(old: str, new: str) -> str:
    """Tiny line-by-line diff for ``--dry-run`` output, no extra deps."""
    import difflib

    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="current",
            tofile="canonical",
            lineterm="",
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rebaseline_schemas",
        description=(
            "Re-emit schema byte-stability snapshots from canonical Pydantic "
            "instances. Run after deliberate schema edits + a major-version "
            "bump (FR27)."
        ),
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_SNAPSHOT_DIR,
        help="Directory to write snapshot YAMLs into.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print diffs without writing.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    written, unchanged = write_snapshots(out_dir=args.out_dir, dry_run=args.dry_run)
    verb = "would-change" if args.dry_run else "changed"
    print(
        f"\nrebaseline_schemas: {verb}={written}, unchanged={unchanged}, "
        f"total={written + unchanged}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
