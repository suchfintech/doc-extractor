"""Snapshot test for the Pydantic → YAML output contract.

`Frontmatter`-derived schemas are the externally-consumed contract; an accidental
field rename, reorder, or type change must surface in CI as a diff. The expected
YAML below is committed verbatim — regenerate it intentionally (and bump
`extractor_version` per the schema-as-contract workflow) when a field genuinely
changes.
"""
from __future__ import annotations

import yaml

from doc_extractor.schemas import Passport

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
