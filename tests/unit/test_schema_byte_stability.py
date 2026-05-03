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

from doc_extractor.schemas import DriverLicence, Passport, PaymentReceipt

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
