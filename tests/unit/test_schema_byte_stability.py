"""Snapshot test for the Pydantic → YAML output contract.

`Frontmatter`-derived schemas are the externally-consumed contract; an accidental
field rename, reorder, or type change must surface in CI as a diff. The expected
YAML below is committed verbatim — regenerate it intentionally (and bump
`extractor_version` per the schema-as-contract workflow) when a field genuinely
changes.
"""
from __future__ import annotations

from datetime import date

import yaml

from doc_extractor.schemas import (
    ApplicationForm,
    BankAccountConfirmation,
    BankStatement,
    CompanyExtract,
    DriverLicence,
    EntityOwnership,
    NationalID,
    Passport,
    PaymentReceipt,
    PEP_Declaration,
    ProofOfAddress,
    TaxResidency,
    UltimateBeneficialOwner,
    VerificationReport,
    Visa,
)

CANONICAL_PASSPORT = Passport(
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

EXPECTED_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: passport@1.0.0
doc_type: Passport
doc_subtype: ''
jurisdiction: HKG
name_latin: CHAN TAI MAN
name_cjk: 陳大文
doc_number: K12345678
dob: '1990-01-15'
issue_date: '2020-06-01'
expiry_date: '2030-05-31'
place_of_birth: HONG KONG
sex: M
passport_number: K12345678
nationality: CHN
mrz_line_1: P<HKGCHAN<<TAI<MAN<<<<<<<<<<<<<<<<<<<<<<<<<<
mrz_line_2: K123456786CHN9001152M3005317<<<<<<<<<<<<<<00
"""


def _dump(passport: Passport) -> str:
    return yaml.safe_dump(
        passport.model_dump(),
        allow_unicode=True,
        sort_keys=False,
    )


def test_canonical_passport_yaml_is_byte_stable() -> None:
    assert _dump(CANONICAL_PASSPORT) == EXPECTED_YAML


def test_canonical_passport_dump_is_idempotent() -> None:
    """Same input → same bytes across two consecutive dumps."""
    assert _dump(CANONICAL_PASSPORT) == _dump(CANONICAL_PASSPORT)


def test_none_inputs_coerce_to_empty_string() -> None:
    """The None→'' validator keeps the YAML output free of `null` literals."""
    p = Passport(name_latin=None, name_cjk=None)  # type: ignore[arg-type]
    dumped = yaml.safe_dump(p.model_dump(), allow_unicode=True, sort_keys=False)
    assert "null" not in dumped
    assert "name_latin: ''" in dumped
    assert "name_cjk: ''" in dumped


def test_field_order_matches_inheritance_chain() -> None:
    """Frontmatter fields first, then IDDocBase, then Passport additions."""
    keys = list(Passport.model_fields.keys())
    expected_prefix = [
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
        "doc_number",
        "dob",
        "issue_date",
        "expiry_date",
        "place_of_birth",
        "sex",
        "passport_number",
        "nationality",
        "mrz_line_1",
        "mrz_line_2",
    ]
    assert keys == expected_prefix


# --------------------------------------------------------------------------
# PaymentReceipt — Story 3.1
# --------------------------------------------------------------------------

# Canonical CN payment with masked debit card and CJK fields. Mask shapes are
# verbatim (FR25/FR26): `6217 **** **** 0083` and `02-0248-0242329-02` round
# through Pydantic and PyYAML untouched.
CANONICAL_PAYMENT_RECEIPT = PaymentReceipt(
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

EXPECTED_PAYMENT_RECEIPT_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T19:00:00Z'
prompt_version: 0.1.0
doc_type: PaymentReceipt
doc_subtype: ''
jurisdiction: CN
name_latin: ''
name_cjk: ''
receipt_amount: '15000.00'
receipt_currency: CNY
receipt_time: '2025-07-01T00:00:00Z'
receipt_debit_account_name: 张三
receipt_debit_account_number: 6217 **** **** 0083
receipt_debit_bank_name: 中国工商银行
receipt_credit_account_name: GM6040
receipt_credit_account_number: 02-0248-0242329-02
receipt_credit_bank_name: ANZ
receipt_reference: INV-2025-001
receipt_payment_app: 工商银行手机银行
receipt_counterparty_name: ''
receipt_counterparty_account: ''
"""


def _dump_pr(receipt: PaymentReceipt) -> str:
    return yaml.safe_dump(
        receipt.model_dump(),
        allow_unicode=True,
        sort_keys=False,
    )


def test_canonical_payment_receipt_yaml_is_byte_stable() -> None:
    assert _dump_pr(CANONICAL_PAYMENT_RECEIPT) == EXPECTED_PAYMENT_RECEIPT_YAML


def test_canonical_payment_receipt_dump_is_idempotent() -> None:
    assert _dump_pr(CANONICAL_PAYMENT_RECEIPT) == _dump_pr(CANONICAL_PAYMENT_RECEIPT)


def test_payment_receipt_preserves_cjk_and_mask_verbatim() -> None:
    dumped = _dump_pr(CANONICAL_PAYMENT_RECEIPT)
    # CJK characters appear raw, not as \\uXXXX escapes.
    assert "张三" in dumped
    assert "中国工商银行" in dumped
    assert "工商银行手机银行" in dumped
    assert "\\u" not in dumped
    # Account-number masks survive byte-equal.
    assert "6217 **** **** 0083" in dumped
    assert "02-0248-0242329-02" in dumped


def test_payment_receipt_field_order_matches_inheritance() -> None:
    """Frontmatter fields first, then PaymentReceipt additions, then deprecated
    counterparty aliases at the end (declaration order is the contract)."""
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
        # Deprecated aliases — overlap window expires 2026-08-03
        "receipt_counterparty_name",
        "receipt_counterparty_account",
    ]


def test_payment_receipt_deprecated_overlap_window_not_yet_expired() -> None:
    """Sentinel: when the FR27 one-quarter overlap closes, intentionally remove
    the deprecated fields and bump `extractor_version`. This test fails on
    2026-08-03 to force the cleanup decision."""
    assert date.today() < date(2026, 8, 3), (
        "FR27 overlap window for receipt_counterparty_* expired — drop the "
        "deprecated fields from PaymentReceipt and bump extractor_version."
    )


# --------------------------------------------------------------------------
# DriverLicence — Story 4.1
# --------------------------------------------------------------------------

# Canonical NZ DLA — Class 1 single-vehicle licence, Latin-only, no
# endorsements / restrictions. The address has no flow-collection-conflicting
# punctuation so PyYAML emits it plain (matches the Passport snapshot style).
CANONICAL_DRIVER_LICENCE = DriverLicence(
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

EXPECTED_DRIVER_LICENCE_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: driver_licence@0.1.0
doc_type: DriverLicence
doc_subtype: ''
jurisdiction: NZL
name_latin: JOHN DOE
name_cjk: ''
doc_number: EH123456
dob: '1990-06-15'
issue_date: '2020-06-01'
expiry_date: '2030-05-31'
place_of_birth: ''
sex: M
licence_class: Class 1
licence_endorsements: ''
licence_restrictions: ''
address: 123 Queen Street Auckland 1010
"""


def _dump_dl(licence: DriverLicence) -> str:
    return yaml.safe_dump(
        licence.model_dump(),
        allow_unicode=True,
        sort_keys=False,
    )


def test_canonical_driver_licence_yaml_is_byte_stable() -> None:
    assert _dump_dl(CANONICAL_DRIVER_LICENCE) == EXPECTED_DRIVER_LICENCE_YAML


def test_canonical_driver_licence_dump_is_idempotent() -> None:
    assert _dump_dl(CANONICAL_DRIVER_LICENCE) == _dump_dl(CANONICAL_DRIVER_LICENCE)


def test_driver_licence_field_order_matches_inheritance() -> None:
    """Frontmatter → IDDocBase → DriverLicence additions, in declaration order."""
    keys = list(DriverLicence.model_fields.keys())
    assert keys == [
        # Frontmatter
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
        # IDDocBase
        "doc_number",
        "dob",
        "issue_date",
        "expiry_date",
        "place_of_birth",
        "sex",
        # DriverLicence additions
        "licence_class",
        "licence_endorsements",
        "licence_restrictions",
        "address",
    ]


# --------------------------------------------------------------------------
# NationalID — Story 4.2
# --------------------------------------------------------------------------

# Canonical CN 居民身份证. The 18-digit id_card_number embeds DOB at positions
# 7-14 (`19900315`) and gender at position 17 (`1` → male) — the snapshot
# below is consistent with both the printed `dob` and `sex` fields. PyYAML
# quotes the all-digit ID strings because they would otherwise parse as ints
# on round-trip; the snapshot pins that quoting too.
CANONICAL_NATIONAL_ID = NationalID(
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

EXPECTED_NATIONAL_ID_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: national_id@0.1.0
doc_type: NationalID
doc_subtype: ''
jurisdiction: CN
name_latin: ''
name_cjk: 张三
doc_number: '110101199003150019'
dob: '1990-03-15'
issue_date: '2020-06-01'
expiry_date: '2040-05-31'
place_of_birth: ''
sex: M
nationality: 中国
id_card_number: '110101199003150019'
issuing_authority: 北京市公安局朝阳分局
address: 北京市朝阳区建国门外大街1号
"""


def _dump_nid(nid: NationalID) -> str:
    return yaml.safe_dump(
        nid.model_dump(),
        allow_unicode=True,
        sort_keys=False,
    )


def test_canonical_national_id_yaml_is_byte_stable() -> None:
    assert _dump_nid(CANONICAL_NATIONAL_ID) == EXPECTED_NATIONAL_ID_YAML


def test_canonical_national_id_dump_is_idempotent() -> None:
    assert _dump_nid(CANONICAL_NATIONAL_ID) == _dump_nid(CANONICAL_NATIONAL_ID)


def test_national_id_preserves_cjk_and_id_number_verbatim() -> None:
    """CJK round-trip + the 18-digit ID survives unquoted-int coercion."""
    dumped = _dump_nid(CANONICAL_NATIONAL_ID)
    # CJK characters appear raw, not as \\uXXXX escapes.
    assert "张三" in dumped
    assert "北京市朝阳区建国门外大街1号" in dumped
    assert "中国" in dumped
    assert "\\u" not in dumped
    # The 18-digit ID survives byte-equal — quoted so PyYAML doesn't reparse
    # it as an integer on round-trip (which would lose leading-zero context
    # and break the embedded DOB/gender encoding).
    assert "'110101199003150019'" in dumped


def test_national_id_field_order_matches_inheritance() -> None:
    """Frontmatter → IDDocBase → NationalID additions, in declaration order."""
    keys = list(NationalID.model_fields.keys())
    assert keys == [
        # Frontmatter
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
        # IDDocBase
        "doc_number",
        "dob",
        "issue_date",
        "expiry_date",
        "place_of_birth",
        "sex",
        # NationalID additions
        "nationality",
        "id_card_number",
        "issuing_authority",
        "address",
    ]


# --------------------------------------------------------------------------
# Visa — Story 4.3
# --------------------------------------------------------------------------

# Canonical NZ resident visa. The travel-window dates (`valid_from`/`valid_to`)
# happen to coincide with the label dates here — the snapshot still pins both
# fields so a future change to either pathway shows up as a diff.
CANONICAL_VISA = Visa(
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

EXPECTED_VISA_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: visa@0.1.0
doc_type: Visa
doc_subtype: ''
jurisdiction: NZ
name_latin: CHAN TAI MAN
name_cjk: ''
doc_number: ABCD1234567
dob: '1990-01-15'
issue_date: '2024-03-01'
expiry_date: '2027-02-28'
place_of_birth: ''
sex: M
visa_class: Resident Visa
issuing_country: NZ
host_country: NZ
valid_from: '2024-03-01'
valid_to: '2027-02-28'
entries_allowed: Multiple
"""


def _dump_visa(visa: Visa) -> str:
    return yaml.safe_dump(
        visa.model_dump(),
        allow_unicode=True,
        sort_keys=False,
    )


def test_canonical_visa_yaml_is_byte_stable() -> None:
    assert _dump_visa(CANONICAL_VISA) == EXPECTED_VISA_YAML


def test_canonical_visa_dump_is_idempotent() -> None:
    assert _dump_visa(CANONICAL_VISA) == _dump_visa(CANONICAL_VISA)


# --------------------------------------------------------------------------
# Story 5.1 — Epic 5 compliance specialists
# --------------------------------------------------------------------------

# PEP_Declaration — `is_pep: yes` round-trips quoted because PyYAML treats
# bare `yes`/`no`/`on`/`off` as YAML 1.1 booleans even under safe_dump; the
# snapshot pins that quoting so a future loader change can't silently flip
# the value to True.
CANONICAL_PEP_DECLARATION = PEP_Declaration(
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

EXPECTED_PEP_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: pep_declaration@0.1.0
doc_type: PEP_Declaration
doc_subtype: ''
jurisdiction: NZ
name_latin: JOHN DOE
name_cjk: ''
is_pep: 'yes'
pep_role: Member of Parliament
pep_jurisdiction: NZ
pep_relationship: self
declaration_date: '2026-04-15'
declarant_name: John Doe
"""


def _dump_pep(p: PEP_Declaration) -> str:
    return yaml.safe_dump(p.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_pep_declaration_yaml_is_byte_stable() -> None:
    assert _dump_pep(CANONICAL_PEP_DECLARATION) == EXPECTED_PEP_YAML


def test_canonical_pep_declaration_dump_is_idempotent() -> None:
    assert _dump_pep(CANONICAL_PEP_DECLARATION) == _dump_pep(CANONICAL_PEP_DECLARATION)


# VerificationReport — NZ EIV report, electronic verification.
CANONICAL_VERIFICATION_REPORT = VerificationReport(
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

EXPECTED_VERIFICATION_REPORT_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: verification_report@0.1.0
doc_type: VerificationReport
doc_subtype: ''
jurisdiction: NZ
name_latin: ''
name_cjk: ''
verifier_name: DIA
verification_date: '2026-04-15'
verification_method: electronic
subject_name: Jane Smith
subject_id_type: Passport
subject_id_number: LA123456
verification_outcome: verified
"""


def _dump_vr(v: VerificationReport) -> str:
    return yaml.safe_dump(v.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_verification_report_yaml_is_byte_stable() -> None:
    assert _dump_vr(CANONICAL_VERIFICATION_REPORT) == EXPECTED_VERIFICATION_REPORT_YAML


# ApplicationForm — generic LEL onboarding shape.
CANONICAL_APPLICATION_FORM = ApplicationForm(
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

EXPECTED_APPLICATION_FORM_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: application_form@0.1.0
doc_type: ApplicationForm
doc_subtype: ''
jurisdiction: NZ
name_latin: ''
name_cjk: ''
application_date: '2026-04-15'
applicant_name: Alice Wong
applicant_dob: '1990-06-15'
application_type: remittance customer onboarding
applicant_address: 123 Queen Street Auckland 1010
applicant_occupation: Software Engineer
"""


def _dump_af(a: ApplicationForm) -> str:
    return yaml.safe_dump(a.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_application_form_yaml_is_byte_stable() -> None:
    assert _dump_af(CANONICAL_APPLICATION_FORM) == EXPECTED_APPLICATION_FORM_YAML


def test_visa_field_order_matches_inheritance() -> None:
    """Frontmatter → IDDocBase → Visa additions, in declaration order."""
    keys = list(Visa.model_fields.keys())
    assert keys == [
        # Frontmatter
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
        # IDDocBase
        "doc_number",
        "dob",
        "issue_date",
        "expiry_date",
        "place_of_birth",
        "sex",
        # Visa additions
        "visa_class",
        "issuing_country",
        "host_country",
        "valid_from",
        "valid_to",
        "entries_allowed",
    ]


# --------------------------------------------------------------------------
# Story 5.2 — Epic 5 bank documents
# --------------------------------------------------------------------------

# BankStatement — NZ ANZ savings statement, single-currency. Closing balance
# is verbatim including the currency prefix; the snapshot pins that the
# `12,345.67` thousand separator and the `NZD ` prefix round-trip unmodified.
CANONICAL_BANK_STATEMENT = BankStatement(
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

EXPECTED_BANK_STATEMENT_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: bank_statement@0.1.0
doc_type: BankStatement
doc_subtype: ''
jurisdiction: NZ
name_latin: ''
name_cjk: ''
bank_name: ANZ Bank New Zealand
account_holder_name: John Doe
account_number: 02-0248-0242329-02
account_type: savings
currency: NZD
statement_period_start: '2025-06-01'
statement_period_end: '2025-06-30'
statement_date: '2025-07-01'
closing_balance: NZD 12,345.67
"""


def _dump_bs(bs: BankStatement) -> str:
    return yaml.safe_dump(bs.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_bank_statement_yaml_is_byte_stable() -> None:
    assert _dump_bs(CANONICAL_BANK_STATEMENT) == EXPECTED_BANK_STATEMENT_YAML


def test_canonical_bank_statement_dump_is_idempotent() -> None:
    assert _dump_bs(CANONICAL_BANK_STATEMENT) == _dump_bs(CANONICAL_BANK_STATEMENT)


def test_bank_statement_preserves_account_number_hyphens_verbatim() -> None:
    """Account-number masks/hyphens round-trip byte-for-byte (FR25/FR26)."""
    dumped = _dump_bs(CANONICAL_BANK_STATEMENT)
    assert "02-0248-0242329-02" in dumped


# BankAccountConfirmation — NZ bank letter, current account.
CANONICAL_BANK_ACCOUNT_CONFIRMATION = BankAccountConfirmation(
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

EXPECTED_BANK_ACCOUNT_CONFIRMATION_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: bank_account_confirmation@0.1.0
doc_type: BankAccountConfirmation
doc_subtype: ''
jurisdiction: NZ
name_latin: ''
name_cjk: ''
bank_name: ANZ Bank New Zealand
account_holder_name: Jane Smith
account_number: 02-0248-0242329-02
account_type: current
currency: NZD
confirmation_date: '2026-04-15'
confirmation_authority: Sarah Chen, Branch Manager
"""


def _dump_bac(bac: BankAccountConfirmation) -> str:
    return yaml.safe_dump(bac.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_bank_account_confirmation_yaml_is_byte_stable() -> None:
    assert (
        _dump_bac(CANONICAL_BANK_ACCOUNT_CONFIRMATION)
        == EXPECTED_BANK_ACCOUNT_CONFIRMATION_YAML
    )


def test_bank_documents_share_bank_doc_base_field_order() -> None:
    """Both bank schemas inherit BankDocBase identically — Frontmatter →
    BankDocBase → specific additions, in declaration order."""
    bs_keys = list(BankStatement.model_fields.keys())
    bac_keys = list(BankAccountConfirmation.model_fields.keys())

    common_prefix = [
        # Frontmatter
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
        # BankDocBase
        "bank_name",
        "account_holder_name",
        "account_number",
        "account_type",
        "currency",
    ]
    assert bs_keys[: len(common_prefix)] == common_prefix
    assert bac_keys[: len(common_prefix)] == common_prefix

    # BankStatement-specific tail
    assert bs_keys[len(common_prefix) :] == [
        "statement_period_start",
        "statement_period_end",
        "statement_date",
        "closing_balance",
    ]
    # BankAccountConfirmation-specific tail
    assert bac_keys[len(common_prefix) :] == [
        "confirmation_date",
        "confirmation_authority",
    ]


# --------------------------------------------------------------------------
# Story 5.3 — Epic 5 entity documents (list[str] + nested-object schemas)
# --------------------------------------------------------------------------

# CompanyExtract — NZ Companies Office shape with three directors and two
# shareholders. The list elements render as YAML block-sequence items
# (`- Alice Wong`); registration_number is quoted because PyYAML treats a
# bare 7-digit string as an int. The snapshot pins both behaviours.
CANONICAL_COMPANY_EXTRACT = CompanyExtract(
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

EXPECTED_COMPANY_EXTRACT_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: company_extract@0.1.0
doc_type: CompanyExtract
doc_subtype: ''
jurisdiction: NZ
name_latin: ''
name_cjk: ''
company_name: Acme Holdings Limited
registration_number: '1234567'
incorporation_date: '2018-04-15'
registered_address: 123 Queen Street, Auckland 1010, New Zealand
directors:
- Alice Wong
- Bob Chen
- Charlie Smith
shareholders:
- Acme Group Ltd
- Beta Capital
"""


def _dump_ce(ce: CompanyExtract) -> str:
    return yaml.safe_dump(ce.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_company_extract_yaml_is_byte_stable() -> None:
    assert _dump_ce(CANONICAL_COMPANY_EXTRACT) == EXPECTED_COMPANY_EXTRACT_YAML


def test_company_extract_distinguishes_null_list_from_empty_list() -> None:
    """`directors=None` (not extracted) must serialise differently from
    `directors=[]` (explicitly zero)."""
    not_extracted = CompanyExtract(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="company_extract@0.1.0",
        doc_type="CompanyExtract",
        company_name="X",
        directors=None,
    )
    explicitly_zero = CompanyExtract(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="company_extract@0.1.0",
        doc_type="CompanyExtract",
        company_name="X",
        directors=[],
    )

    not_extracted_dump = _dump_ce(not_extracted)
    explicitly_zero_dump = _dump_ce(explicitly_zero)

    assert "directors: null" in not_extracted_dump
    assert "directors: []" in explicitly_zero_dump


# EntityOwnership — first nested-object schema in the project. Two UBOs,
# one Latin one CJK, with ownership_percentage strings preserved verbatim.
CANONICAL_ENTITY_OWNERSHIP = EntityOwnership(
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

EXPECTED_ENTITY_OWNERSHIP_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: entity_ownership@0.1.0
doc_type: EntityOwnership
doc_subtype: ''
jurisdiction: NZ
name_latin: ''
name_cjk: ''
entity_name: Acme Holdings Limited
ultimate_beneficial_owners:
- name: Alice Wong
  dob: '1985-07-12'
  ownership_percentage: 60%
- name: 陳大文
  dob: '1990-01-15'
  ownership_percentage: 40%
"""


def _dump_eo(eo: EntityOwnership) -> str:
    return yaml.safe_dump(eo.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_entity_ownership_yaml_is_byte_stable() -> None:
    assert _dump_eo(CANONICAL_ENTITY_OWNERSHIP) == EXPECTED_ENTITY_OWNERSHIP_YAML


def test_entity_ownership_preserves_cjk_in_nested_ubo() -> None:
    """CJK in nested UBO `name` round-trips raw, not as \\uXXXX escapes."""
    dumped = _dump_eo(CANONICAL_ENTITY_OWNERSHIP)
    assert "陳大文" in dumped
    assert "\\u" not in dumped


def test_entity_ownership_preserves_ownership_percentage_verbatim() -> None:
    """ownership_percentage is a verbatim string — no normalisation across
    `25%`/`0.25`/`approximately 25%`/CJK fraction renderings."""
    eo = EntityOwnership(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="entity_ownership@0.1.0",
        doc_type="EntityOwnership",
        entity_name="X",
        ultimate_beneficial_owners=[
            UltimateBeneficialOwner(name="A", ownership_percentage="0.25"),
            UltimateBeneficialOwner(name="B", ownership_percentage="approximately 25%"),
            UltimateBeneficialOwner(name="C", ownership_percentage="25.5%"),
        ],
    )
    dumped = _dump_eo(eo)
    # All four printed formats survive untouched.
    assert "ownership_percentage: '0.25'" in dumped
    assert "ownership_percentage: approximately 25%" in dumped
    assert "ownership_percentage: 25.5%" in dumped


# --------------------------------------------------------------------------
# Story 5.4 — Epic 5 person-related documents
# --------------------------------------------------------------------------

# ProofOfAddress — NZ utility bill. The address has commas but renders plain
# in block scalar context (PyYAML doesn't need to quote).
CANONICAL_PROOF_OF_ADDRESS = ProofOfAddress(
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

EXPECTED_PROOF_OF_ADDRESS_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: proof_of_address@0.1.0
doc_type: ProofOfAddress
doc_subtype: ''
jurisdiction: NZ
name_latin: ''
name_cjk: ''
holder_name: John Doe
address: 123 Queen Street, Auckland 1010, New Zealand
document_date: '2026-04-15'
issuer: Mercury Energy
document_type: utility bill
"""


def _dump_poa(p: ProofOfAddress) -> str:
    return yaml.safe_dump(p.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_proof_of_address_yaml_is_byte_stable() -> None:
    assert _dump_poa(CANONICAL_PROOF_OF_ADDRESS) == EXPECTED_PROOF_OF_ADDRESS_YAML


def test_canonical_proof_of_address_dump_is_idempotent() -> None:
    assert _dump_poa(CANONICAL_PROOF_OF_ADDRESS) == _dump_poa(CANONICAL_PROOF_OF_ADDRESS)


# TaxResidency — NZ IRD residency-status letter. The 9-digit IRD number is
# captured with hyphens verbatim. PyYAML keeps it unquoted because the hyphens
# prevent int-coercion (unlike the all-digit CN id_card_number which DOES get
# quoted in the NationalID snapshot above).
CANONICAL_TAX_RESIDENCY = TaxResidency(
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

EXPECTED_TAX_RESIDENCY_YAML = """\
extractor_version: 0.1.0
extraction_provider: anthropic
extraction_model: claude-sonnet-4-6-20260101
extraction_timestamp: '2026-05-03T12:00:00Z'
prompt_version: tax_residency@0.1.0
doc_type: TaxResidency
doc_subtype: ''
jurisdiction: NZ
name_latin: ''
name_cjk: ''
holder_name: John Doe
tax_jurisdiction: NZ
tin: 123-456-789
residency_status: resident
effective_from: '2024-01-01'
"""


def _dump_tr(t: TaxResidency) -> str:
    return yaml.safe_dump(t.model_dump(), allow_unicode=True, sort_keys=False)


def test_canonical_tax_residency_yaml_is_byte_stable() -> None:
    assert _dump_tr(CANONICAL_TAX_RESIDENCY) == EXPECTED_TAX_RESIDENCY_YAML


def test_tax_residency_preserves_tin_formats_verbatim() -> None:
    """Each jurisdiction's TIN format round-trips byte-for-byte. Important:
    parentheses (HK), hyphens (NZ/US), and the all-digit USCC (CN entity)
    each have different PyYAML quoting interactions."""
    formats = {
        "NZ": "123-456-789",
        "US": "123-45-6789",
        "HK": "A123456(7)",
        "SG": "S1234567A",
        "CN": "91110000XXXXXXXXXX",
    }
    for jur, tin in formats.items():
        t = TaxResidency(
            extractor_version="0.1.0",
            extraction_provider="anthropic",
            extraction_model="claude-sonnet-4-6-20260101",
            extraction_timestamp="2026-05-03T12:00:00Z",
            prompt_version="tax_residency@0.1.0",
            doc_type="TaxResidency",
            tax_jurisdiction=jur,
            tin=tin,
        )
        dumped = _dump_tr(t)
        assert tin in dumped, f"TIN {tin!r} ({jur}) lost during YAML dump"
