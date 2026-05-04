"""Story 2.1 bootstrap — seed golden-corpus draft `.expected.md` files
from legacy free-text analyses synced from ``s3://golden-mountain-analysis``.

The drafts are written to ``.local/golden-drafts/<doc_type>/`` (gitignored)
so Yang can review and redact PII before promoting committed test
fixtures into ``tests/golden/<doc_type>/``.

Usage:

    python scripts/seed_golden_corpus.py --doc-type passport \\
        --legacy-root /tmp/gt-scan/raw \\
        --picks 2706/3953c3487fd6dd042cd6b3c41bf491d1.jpeg.md \\
                2741/0a5fe56c5155995a5c8bb5758a406ce0.jpeg.md \\
        --out .local/golden-drafts/passport

    # Auto-pick: scan the legacy root, take first N matches per doc type:
    python scripts/seed_golden_corpus.py --doc-type all \\
        --legacy-root /tmp/gt-scan/raw \\
        --auto 5 \\
        --out .local/golden-drafts

The script:

1. Reads each legacy ``.md`` analysis.
2. Extracts the ``FIELDS:`` block via regex.
3. Maps to the v2 schema for the doc type (registry below).
4. Renders the v2 ``.expected.md`` via :func:`markdown_io.render_to_md`
   so it is byte-stable and round-trips through :func:`parse_md`.
5. Validates the round-trip — the script aborts on any draft that fails
   parse, so reviewers never see an invalid candidate.

Drafts include real PII from the legacy analyses; do not commit. Yang
hand-redacts each before promoting to ``tests/golden/``.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

# Ensure the local src/ is importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from doc_extractor.markdown_io import parse_md, render_to_md
from doc_extractor.schemas.application_form import ApplicationForm
from doc_extractor.schemas.bank_account_confirmation import BankAccountConfirmation
from doc_extractor.schemas.bank_statement import BankStatement
from doc_extractor.schemas.base import Frontmatter
from doc_extractor.schemas.company_extract import CompanyExtract
from doc_extractor.schemas.entity_ownership import EntityOwnership, UltimateBeneficialOwner
from doc_extractor.schemas.ids import DriverLicence, NationalID, Passport, Visa
from doc_extractor.schemas.other import Other
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.pep_declaration import PEP_Declaration
from doc_extractor.schemas.proof_of_address import ProofOfAddress
from doc_extractor.schemas.tax_residency import TaxResidency
from doc_extractor.schemas.verification_report import VerificationReport

# ---------------------------------------------------------------------------
# Field-block parsers (legacy free-text format)
# ---------------------------------------------------------------------------

_MONTH = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def _parse_date(s: str) -> str:
    """Best-effort date parser. Recognises ``30 JUN 1999``, ``30/Jun/1999``,
    ``2017-02-13``, and ``17 DEC 2012`` shapes; returns empty string on
    failure so the round-trip never crashes on a partial extract.
    """
    if not s:
        return ""
    s = s.strip()

    # ISO already
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # 30 JUN 1999 / 30 Jun 1999
    m = re.match(r"^(\d{1,2})[/\s]+([A-Za-z]{3})[a-z]*[/\s,]+(\d{4})", s)
    if m:
        day, mon, year = m.group(1).zfill(2), m.group(2).upper(), m.group(3)
        if mon in _MONTH:
            return f"{year}-{_MONTH[mon]}-{day}"

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        day, mon, year = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        return f"{year}-{mon}-{day}"

    return ""


def _extract_fields(text: str) -> dict[str, str]:
    """Parse the ``FIELDS:`` block of a legacy analysis into ``{label: value}``.

    Tolerates both ``FIELDS:`` and ``**FIELDS:**`` headers and stops at any
    section delimiter (``RAW_TEXT``, ``QUALITY``, code-fence, hr).
    """
    out: dict[str, str] = {}
    in_fields = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\*?\*?FIELDS:?\*?\*?\s*$", stripped, re.IGNORECASE):
            in_fields = True
            continue
        if in_fields:
            if not stripped:
                continue
            if re.match(
                r"^(\*?\*?(RAW_TEXT|QUALITY|NOTES|RAW TEXT)\*?\*?:|```|---)",
                stripped,
                re.IGNORECASE,
            ):
                break
            m = re.match(r"^[-*]\s*\*?\*?([^:*]+?)\*?\*?:\s*(.+?)\s*$", stripped)
            if m:
                key = m.group(1).strip()
                # Only store the first occurrence so duplicate keys (the
                # CN PRC passports often repeat ``Nationality``) don't lose
                # the label that landed first.
                if key not in out:
                    out[key] = m.group(2).strip()
    return out


def _grab(fields: dict[str, str], *labels: str) -> str:
    """Return the first non-empty value among the labels, or empty."""
    for lbl in labels:
        for k, v in fields.items():
            if k.lower() == lbl.lower() and v.strip():
                return v.strip()
    return ""


_CJK_RE = re.compile(r"[一-鿿]+")


def _split_latin_cjk(name: str) -> tuple[str, str]:
    """``SUN, JIAWEI (孙嘉蔚)`` → (``SUN JIAWEI``, ``孙嘉蔚``)."""
    name = name.strip()
    cjk = "".join(_CJK_RE.findall(name))
    latin = re.sub(r"\([^)]*\)", "", name)
    latin = re.sub(r"[,/]", " ", latin)
    latin = re.sub(r"\s+", " ", latin).strip()
    return latin, cjk


def _normalise_sex(value: str) -> str:
    if not value:
        return ""
    upper = value.upper()
    if "FEMALE" in upper or " F" in f" {upper}" or upper.startswith("F") or "女" in value:
        return "F"
    if "MALE" in upper or " M" in f" {upper}" or upper.startswith("M") or "男" in value:
        return "M"
    return ""


def _normalise_country(value: str) -> str:
    v = value.upper().strip()
    if not v:
        return ""
    if "CHN" in v or "CHINA" in v or "CHINESE" in v:
        return "CHN"
    if "NZL" in v or "NEW ZEALAND" in v or "KIWI" in v or "NZ" == v:
        return "NZL"
    if "HKG" in v or "HONG KONG" in v:
        return "HKG"
    if "USA" in v or "UNITED STATES" in v:
        return "USA"
    if "GBR" in v or "UNITED KINGDOM" in v or "BRITISH" in v:
        return "GBR"
    if "AUS" in v or "AUSTRALIA" in v:
        return "AUS"
    return v[:3] if len(v) <= 3 else v


def _strip_paren(value: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", value).strip()


def _provenance_kwargs(source_path: Path) -> dict[str, str]:
    """Extract ``Analyzed:`` and ``Model:`` from the analysis header so the
    extraction-timestamp / -model frontmatter fields stay faithful to the
    real run that produced the seed.
    """
    text = source_path.read_text(encoding="utf-8", errors="replace")
    model_match = re.search(r"\*\*Model:\*\*\s*`?([^`\n]+)`?", text)
    when_match = re.search(r"\*\*Analyzed:\*\*\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s+([0-9:]+)", text)
    when = (
        f"{when_match.group(1)}T{when_match.group(2)}:00Z"
        if when_match
        else "2026-03-21T19:00:00Z"
    )
    return {
        "extractor_version": "0.1.0",
        "extraction_provider": "anthropic",
        "extraction_model": (model_match.group(1).strip() if model_match else "claude-haiku-4-5-20251001"),
        "extraction_timestamp": when,
    }


# ---------------------------------------------------------------------------
# Per-schema mappers
# ---------------------------------------------------------------------------


def map_passport(text: str) -> Passport:
    fields = _extract_fields(text)
    full_name = _grab(fields, "Full Name", "Name")
    name_latin, name_cjk = _split_latin_cjk(full_name)
    return Passport(
        prompt_version="passport@1.0.0",
        doc_type="Passport",
        jurisdiction=_normalise_country(_grab(fields, "Country Code", "Country of Issue", "Nationality")),
        name_latin=name_latin,
        name_cjk=name_cjk,
        doc_number=_grab(fields, "Document Number", "Passport Number"),
        dob=_parse_date(_grab(fields, "Date of Birth")),
        issue_date=_parse_date(_grab(fields, "Issue Date")),
        expiry_date=_parse_date(_grab(fields, "Expiry Date")),
        place_of_birth=_strip_paren(_grab(fields, "Place of Birth")).upper(),
        sex=_normalise_sex(_grab(fields, "Gender", "Sex", "Sex/Gender")),
        passport_number=_grab(fields, "Passport Number", "Document Number"),
        nationality=_normalise_country(_grab(fields, "Nationality", "Country Code")),
    )


def map_driver_licence(text: str) -> DriverLicence:
    fields = _extract_fields(text)
    full_name = _grab(fields, "Full Name", "Name", "Holder Name")
    name_latin, name_cjk = _split_latin_cjk(full_name)
    return DriverLicence(
        prompt_version="driver_licence@1.0.0",
        doc_type="DriverLicence",
        jurisdiction=_normalise_country(_grab(fields, "Issuing Country", "Country", "Jurisdiction")) or "NZL",
        name_latin=name_latin,
        name_cjk=name_cjk,
        doc_number=_grab(fields, "Licence Number", "License Number", "Document Number"),
        dob=_parse_date(_grab(fields, "Date of Birth")),
        issue_date=_parse_date(_grab(fields, "Issue Date", "Date of Issue")),
        expiry_date=_parse_date(_grab(fields, "Expiry Date", "Date of Expiry")),
        place_of_birth=_strip_paren(_grab(fields, "Place of Birth")).upper(),
        sex=_normalise_sex(_grab(fields, "Gender", "Sex")),
        licence_class=_grab(fields, "Licence Class", "License Class", "Class"),
        licence_endorsements=_grab(fields, "Endorsements"),
        licence_restrictions=_grab(fields, "Restrictions", "Conditions"),
        address=_grab(fields, "Address", "Residential Address"),
    )


def map_national_id(text: str) -> NationalID:
    fields = _extract_fields(text)
    full_name = _grab(fields, "Full Name", "Name")
    name_latin, name_cjk = _split_latin_cjk(full_name)
    return NationalID(
        prompt_version="national_id@1.0.0",
        doc_type="NationalID",
        jurisdiction=_normalise_country(_grab(fields, "Country", "Issuing Country")) or "CHN",
        name_latin=name_latin,
        name_cjk=name_cjk,
        doc_number=_grab(fields, "ID Number", "Document Number"),
        dob=_parse_date(_grab(fields, "Date of Birth")),
        issue_date=_parse_date(_grab(fields, "Issue Date")),
        expiry_date=_parse_date(_grab(fields, "Expiry Date", "Valid Until")),
        place_of_birth=_strip_paren(_grab(fields, "Place of Birth")).upper(),
        sex=_normalise_sex(_grab(fields, "Gender", "Sex")),
        nationality=_normalise_country(_grab(fields, "Nationality")),
        id_card_number=_grab(fields, "ID Number", "ID Card Number", "Document Number"),
        issuing_authority=_grab(fields, "Issuing Authority", "Authority"),
        address=_grab(fields, "Address", "Residential Address"),
    )


def map_visa(text: str) -> Visa:
    fields = _extract_fields(text)
    full_name = _grab(fields, "Full Name", "Name")
    name_latin, name_cjk = _split_latin_cjk(full_name)
    return Visa(
        prompt_version="visa@1.0.0",
        doc_type="Visa",
        jurisdiction=_normalise_country(_grab(fields, "Issuing Country", "Country Code", "Host Country")),
        name_latin=name_latin,
        name_cjk=name_cjk,
        doc_number=_grab(fields, "Visa Number", "Document Number (Visa)", "Document Number"),
        dob=_parse_date(_grab(fields, "Date of Birth")),
        issue_date=_parse_date(_grab(fields, "Issue Date", "Visa Start Date")),
        expiry_date=_parse_date(_grab(fields, "Expiry Date", "Visa Expiry Date")),
        place_of_birth=_strip_paren(_grab(fields, "Place of Birth")).upper(),
        sex=_normalise_sex(_grab(fields, "Gender", "Sex")),
        visa_class=_grab(fields, "Visa Type", "Visa Class", "Class"),
        issuing_country=_normalise_country(_grab(fields, "Issuing Country", "Country Code")),
        host_country=_normalise_country(_grab(fields, "Host Country")),
        valid_from=_parse_date(_grab(fields, "Visa Start Date", "Valid From")),
        valid_to=_parse_date(_grab(fields, "Visa Expiry Date", "Valid To")),
        entries_allowed=_grab(fields, "Number of Entries", "Entries Allowed"),
    )


def map_payment_receipt(text: str) -> PaymentReceipt:
    fields = _extract_fields(text)
    return PaymentReceipt(
        prompt_version="payment_receipt@0.1.0",
        doc_type="PaymentReceipt",
        jurisdiction=_normalise_country(_grab(fields, "Country", "Currency Country")),
        receipt_amount=_grab(fields, "Amount", "Receipt Amount", "Transaction Amount"),
        receipt_currency=_grab(fields, "Currency", "Currency Code"),
        receipt_time=_parse_date(_grab(fields, "Date", "Transaction Date", "Receipt Date", "Time")),
        receipt_debit_account_name=_grab(fields, "Payer Name", "Debit Account Name", "From Name", "Payer", "付款人"),
        receipt_debit_account_number=_grab(fields, "Payer Account", "Debit Account Number", "From Account"),
        receipt_debit_bank_name=_grab(fields, "Payer Bank", "Debit Bank Name", "From Bank"),
        receipt_credit_account_name=_grab(fields, "Payee Name", "Credit Account Name", "To Name", "Payee", "收款人"),
        receipt_credit_account_number=_grab(fields, "Payee Account", "Credit Account Number", "To Account"),
        receipt_credit_bank_name=_grab(fields, "Payee Bank", "Credit Bank Name", "To Bank"),
        receipt_reference=_grab(fields, "Reference", "Transaction Reference", "Memo"),
        receipt_payment_app=_grab(fields, "Payment App", "App", "Source"),
    )


def map_pep_declaration(text: str) -> PEP_Declaration:
    fields = _extract_fields(text)
    is_pep_raw = _grab(fields, "Is PEP", "PEP Status", "Politically Exposed").lower()
    is_pep = "yes" if "yes" in is_pep_raw or "true" in is_pep_raw else (
        "no" if "no" in is_pep_raw or "not" in is_pep_raw else ""
    )
    return PEP_Declaration(
        prompt_version="pep_declaration@1.0.0",
        doc_type="PEP_Declaration",
        is_pep=is_pep,
        pep_role=_grab(fields, "Role", "PEP Role", "Position"),
        pep_jurisdiction=_normalise_country(_grab(fields, "Jurisdiction", "Country")),
        pep_relationship=_grab(fields, "Relationship", "PEP Relationship"),
        declaration_date=_parse_date(_grab(fields, "Declaration Date", "Date Signed", "Date")),
        declarant_name=_grab(fields, "Declarant Name", "Name", "Signed By"),
    )


def map_verification_report(text: str) -> VerificationReport:
    fields = _extract_fields(text)
    full_name = _grab(fields, "Subject Name", "Full Name", "Name")
    name_latin, name_cjk = _split_latin_cjk(full_name)
    return VerificationReport(
        prompt_version="verification_report@1.0.0",
        doc_type="VerificationReport",
        jurisdiction=_normalise_country(_grab(fields, "Country", "Jurisdiction")),
        name_latin=name_latin,
        name_cjk=name_cjk,
        verifier_name=_grab(fields, "Verifier", "Verified By", "Verification Service", "Provider"),
        verification_date=_parse_date(_grab(fields, "Verification Date", "Date Verified", "Report Date", "Date")),
        verification_method=_grab(fields, "Method", "Verification Method"),
        subject_name=full_name,
        subject_id_type=_grab(fields, "ID Type", "Document Type"),
        subject_id_number=_grab(fields, "ID Number", "Document Number"),
        verification_outcome=_grab(fields, "Outcome", "Result", "Verification Result"),
    )


def map_application_form(text: str) -> ApplicationForm:
    fields = _extract_fields(text)
    full_name = _grab(fields, "Applicant Name", "Full Name", "Name")
    name_latin, name_cjk = _split_latin_cjk(full_name)
    return ApplicationForm(
        prompt_version="application_form@1.0.0",
        doc_type="ApplicationForm",
        jurisdiction=_normalise_country(_grab(fields, "Country")),
        name_latin=name_latin,
        name_cjk=name_cjk,
        application_date=_parse_date(_grab(fields, "Application Date", "Date", "Date Signed")),
        applicant_name=full_name,
        applicant_dob=_parse_date(_grab(fields, "Date of Birth", "DOB")),
        application_type=_grab(fields, "Application Type", "Form Type", "Type"),
        applicant_address=_grab(fields, "Address", "Residential Address"),
        applicant_occupation=_grab(fields, "Occupation", "Employment"),
    )


def map_bank_statement(text: str) -> BankStatement:
    fields = _extract_fields(text)
    holder = _grab(fields, "Account Holder Name", "Account Holder", "Name", "Holder Name")
    name_latin, name_cjk = _split_latin_cjk(holder)
    return BankStatement(
        prompt_version="bank_statement@1.0.0",
        doc_type="BankStatement",
        jurisdiction=_normalise_country(_grab(fields, "Country")),
        name_latin=name_latin,
        name_cjk=name_cjk,
        bank_name=_grab(fields, "Bank Name", "Bank", "Issuer"),
        account_holder_name=holder,
        account_number=_grab(fields, "Account Number"),
        account_type=_grab(fields, "Account Type"),
        currency=_grab(fields, "Currency"),
        statement_period_start=_parse_date(_grab(fields, "Statement Period Start", "Period Start", "From Date")),
        statement_period_end=_parse_date(_grab(fields, "Statement Period End", "Period End", "To Date")),
        statement_date=_parse_date(_grab(fields, "Statement Date", "Date")),
        closing_balance=_grab(fields, "Closing Balance", "Balance"),
    )


def map_bank_account_confirmation(text: str) -> BankAccountConfirmation:
    fields = _extract_fields(text)
    holder = _grab(fields, "Account Holder Name", "Account Holder", "Name")
    name_latin, name_cjk = _split_latin_cjk(holder)
    return BankAccountConfirmation(
        prompt_version="bank_account_confirmation@1.0.0",
        doc_type="BankAccountConfirmation",
        jurisdiction=_normalise_country(_grab(fields, "Country")),
        name_latin=name_latin,
        name_cjk=name_cjk,
        bank_name=_grab(fields, "Bank Name", "Bank", "Issuer"),
        account_holder_name=holder,
        account_number=_grab(fields, "Account Number"),
        account_type=_grab(fields, "Account Type"),
        currency=_grab(fields, "Currency"),
        confirmation_date=_parse_date(_grab(fields, "Confirmation Date", "Date Issued", "Date")),
        confirmation_authority=_grab(fields, "Signed By", "Signing Authority", "Authority", "Authorised By"),
    )


def map_company_extract(text: str) -> CompanyExtract:
    fields = _extract_fields(text)
    directors_raw = _grab(fields, "Directors", "Director")
    shareholders_raw = _grab(fields, "Shareholders", "Shareholder")
    directors = [s.strip() for s in re.split(r"[;,]|\band\b", directors_raw) if s.strip()] if directors_raw else None
    shareholders = [s.strip() for s in re.split(r"[;,]|\band\b", shareholders_raw) if s.strip()] if shareholders_raw else None
    return CompanyExtract(
        prompt_version="company_extract@1.0.0",
        doc_type="CompanyExtract",
        jurisdiction=_normalise_country(_grab(fields, "Country", "Jurisdiction")),
        company_name=_grab(fields, "Company Name", "Name"),
        registration_number=_grab(fields, "Registration Number", "Company Number"),
        incorporation_date=_parse_date(_grab(fields, "Incorporation Date", "Registered On", "Date of Incorporation")),
        registered_address=_grab(fields, "Registered Address", "Address"),
        directors=directors,
        shareholders=shareholders,
    )


def map_entity_ownership(text: str) -> EntityOwnership:
    fields = _extract_fields(text)
    ubo_name = _grab(fields, "UBO Name", "Beneficial Owner", "Name")
    ubo_dob = _parse_date(_grab(fields, "UBO Date of Birth", "Date of Birth"))
    ubo_pct = _grab(fields, "Ownership Percentage", "Percentage", "Ownership %")
    ubos = (
        [UltimateBeneficialOwner(name=ubo_name, dob=ubo_dob, ownership_percentage=ubo_pct)]
        if ubo_name
        else None
    )
    return EntityOwnership(
        prompt_version="entity_ownership@1.0.0",
        doc_type="EntityOwnership",
        jurisdiction=_normalise_country(_grab(fields, "Country", "Jurisdiction")),
        entity_name=_grab(fields, "Entity Name", "Company Name"),
        ultimate_beneficial_owners=ubos,
    )


def map_proof_of_address(text: str) -> ProofOfAddress:
    fields = _extract_fields(text)
    return ProofOfAddress(
        prompt_version="proof_of_address@1.0.0",
        doc_type="ProofOfAddress",
        jurisdiction=_normalise_country(_grab(fields, "Country")),
        holder_name=_grab(fields, "Holder Name", "Name", "Account Holder"),
        address=_grab(fields, "Address", "Residential Address"),
        document_date=_parse_date(_grab(fields, "Document Date", "Date Issued", "Bill Date", "Date")),
        issuer=_grab(fields, "Issuer", "Issued By", "Provider"),
        document_type=_grab(fields, "Document Type", "Bill Type"),
    )


def map_tax_residency(text: str) -> TaxResidency:
    fields = _extract_fields(text)
    return TaxResidency(
        prompt_version="tax_residency@1.0.0",
        doc_type="TaxResidency",
        jurisdiction=_normalise_country(_grab(fields, "Country", "Jurisdiction", "Tax Jurisdiction")),
        holder_name=_grab(fields, "Holder Name", "Name", "Taxpayer Name"),
        tax_jurisdiction=_grab(fields, "Tax Jurisdiction", "Country of Residence", "Country"),
        tin=_grab(fields, "TIN", "Tax Identification Number", "IRD Number", "SSN"),
        residency_status=_grab(fields, "Residency Status", "Status"),
        effective_from=_parse_date(_grab(fields, "Effective From", "Date")),
    )


def map_other(text: str) -> Other:
    fields = _extract_fields(text)
    return Other(
        prompt_version="other@1.0.0",
        doc_type="Other",
        description=_grab(fields, "Description", "Document Type") or "",
        extracted_text=_grab(fields, "Raw Text", "Extracted Text", "Content")[:500],
        notes=_grab(fields, "Notes", "Quality") or "",
    )


# ---------------------------------------------------------------------------
# Auto-pick: doc-type detection from the legacy ``DOCUMENT_TYPE:`` line
# ---------------------------------------------------------------------------

_TYPE_PATTERNS: list[tuple[str, str]] = [
    ("verification_report", r"verification report|verification summary|data zoo|idu verification|identity verification|kyc verification"),
    ("payment_receipt", r"payment receipt|transaction receipt|remittance|wire transfer|deposit slip|tt receipt|bank receipt|payment confirmation|payment slip"),
    ("application_form", r"application form|due diligence|account opening|customer due diligence|kyc form|baseline update form"),
    ("entity_ownership", r"ownership|beneficial owner|ubo|trust deed"),
    ("company_extract", r"company extract|certificate of incorporation|companies office|company.*registration"),
    ("tax_residency", r"tax residency|fatca|crs|ird|w-?8|w-?9|tax certificate|self.?certification.*tax"),
    ("bank_account_confirmation", r"bank account confirmation|bank confirmation|account confirmation|account verification.*letter|confirmation of bank|bank.*letter"),
    ("bank_statement", r"bank statement|account statement"),
    ("pep_declaration", r"\bpep\b|politically exposed|member.?check|sanction|self.?certif"),
    ("proof_of_address", r"proof of address|utility bill|address verification|residence proof"),
    ("driver_licence", r"driver.?licen[cs]e|driving licen[cs]e|nzta drivers|机动车驾驶证"),
    ("national_id", r"national id|身份证|china id|chinese id|prc national id"),
    ("visa", r"\bvisa\b"),
    ("passport", r"^passport|护照"),
]


def _detect_doc_type(text: str) -> str | None:
    """Return the matching doc-type slug or ``None`` for catch-all."""
    m = re.search(r"\*?\*?DOCUMENT_TYPE:?\*?\*?\s*(.+)", text)
    if not m:
        return None
    label = m.group(1).strip().lower()
    for slug, pat in _TYPE_PATTERNS:
        if re.search(pat, label, re.IGNORECASE):
            return slug
    return "other"


# ---------------------------------------------------------------------------
# Mapper registry
# ---------------------------------------------------------------------------

MAPPERS: dict[str, Callable[[str], Frontmatter]] = {
    "passport": map_passport,
    "driver_licence": map_driver_licence,
    "national_id": map_national_id,
    "visa": map_visa,
    "payment_receipt": map_payment_receipt,
    "pep_declaration": map_pep_declaration,
    "verification_report": map_verification_report,
    "application_form": map_application_form,
    "bank_statement": map_bank_statement,
    "bank_account_confirmation": map_bank_account_confirmation,
    "company_extract": map_company_extract,
    "entity_ownership": map_entity_ownership,
    "proof_of_address": map_proof_of_address,
    "tax_residency": map_tax_residency,
    "other": map_other,
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _seed_one(legacy_path: Path, mapper: Callable[[str], Frontmatter], out_path: Path) -> None:
    text = legacy_path.read_text(encoding="utf-8", errors="replace")
    instance = mapper(text)
    # Patch in real provenance from the legacy header.
    for k, v in _provenance_kwargs(legacy_path).items():
        setattr(instance, k, v)
    rendered = render_to_md(instance)
    round_tripped = parse_md(rendered)
    assert round_tripped.model_dump() == instance.model_dump(), (
        f"Round-trip mismatch for {legacy_path}"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")


def _auto_pick(legacy_root: Path, n_per_type: int) -> dict[str, list[Path]]:
    picks: dict[str, list[Path]] = {k: [] for k in MAPPERS}
    for md in legacy_root.rglob("*.md"):
        try:
            head = md.read_text(encoding="utf-8", errors="replace")[:1500]
        except OSError:
            continue
        slug = _detect_doc_type(head)
        if slug and len(picks[slug]) < n_per_type:
            picks[slug].append(md)
    return picks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-type", required=True, help="One of: " + ", ".join(sorted(MAPPERS)) + ", or 'all'")
    ap.add_argument("--legacy-root", required=True, type=Path)
    ap.add_argument("--picks", nargs="+", help="paths relative to legacy-root (single doc-type only)")
    ap.add_argument("--auto", type=int, help="auto-pick N per doc type (use with --doc-type all)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    if args.doc_type == "all":
        if not args.auto:
            ap.error("--doc-type all requires --auto N")
        picks_by_type = _auto_pick(args.legacy_root, args.auto)
        total = 0
        for slug, paths in sorted(picks_by_type.items()):
            for i, p in enumerate(paths, start=1):
                out_path = args.out / slug / f"example_{i:02d}.expected.md"
                _seed_one(p, MAPPERS[slug], out_path)
                total += 1
            print(f"  {slug:30s} {len(paths):3d} drafts → {args.out / slug}")
        print(f"\n{total} drafts produced in {args.out}")
    else:
        if args.doc_type not in MAPPERS:
            ap.error(f"--doc-type must be one of {sorted(MAPPERS)} or 'all'")
        if args.auto:
            picks = _auto_pick(args.legacy_root, args.auto).get(args.doc_type, [])
        elif args.picks:
            picks = [args.legacy_root / rel for rel in args.picks]
        else:
            ap.error("provide either --picks or --auto N")
        for i, p in enumerate(picks, start=1):
            out_path = args.out / f"example_{i:02d}.expected.md"
            _seed_one(p, MAPPERS[args.doc_type], out_path)
            print(f"wrote {out_path} ← {p.name}")
        print(f"\n{len(picks)} drafts produced in {args.out}")

    print("\nNext: review each .expected.md, redact PII per repo policy, "
          "then promote selected examples (and their source images) into "
          "tests/golden/<doc_type>/.")


if __name__ == "__main__":
    main()
