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

from doc_extractor.schemas import DriverLicence, NationalID, Passport, PaymentReceipt, Visa

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
