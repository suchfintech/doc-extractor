"""Byte-equal round-trip: Pydantic → render_to_md → parse_md → Pydantic.

The fixture deliberately mixes CJK characters and a pre-masked account-number
style string (verbatim mask preservation per FR25/FR26). If PyYAML or Pydantic
ever drift in a way that mangles either, this test fails.
"""
from __future__ import annotations

import pytest

from doc_extractor.markdown_io import parse_md, render_to_md
from doc_extractor.schemas import (
    EntityOwnership,
    Frontmatter,
    Passport,
    UltimateBeneficialOwner,
)


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
        name_cjk="陳大文 尾号 0083",
        doc_number="6217 **** **** 0083",
        dob="1990-01-15",
        issue_date="2020-06-01",
        expiry_date="2030-05-31",
        place_of_birth="香港",
        sex="M",
        passport_number="K12345678",
        nationality="CHN",
        mrz_line_1="P<HKGCHAN<<TAI<MAN<<<<<<<<<<<<<<<<<<<<<<<<<<",
        mrz_line_2="K123456786CHN9001152M3005317<<<<<<<<<<<<<<00",
    )


def test_render_wraps_body_with_fence_and_trailing_blank_line() -> None:
    md = render_to_md(_canonical_passport())
    assert md.startswith("---\n")
    assert md.endswith("---\n\n")
    # Exactly two fence lines.
    assert md.count("\n---\n") == 1  # closing fence
    assert md.split("\n", 1)[0] == "---"  # opening fence


def test_round_trip_is_byte_equal() -> None:
    original = _canonical_passport()
    md = render_to_md(original)
    parsed = parse_md(md)
    assert parsed == original
    # Re-rendering the parsed instance must produce identical bytes.
    assert render_to_md(parsed) == md


def test_mask_string_preserved_verbatim() -> None:
    original = _canonical_passport()
    md = render_to_md(original)
    assert "6217 **** **** 0083" in md
    parsed = parse_md(md)
    assert isinstance(parsed, Passport)
    assert parsed.doc_number == "6217 **** **** 0083"


def test_cjk_characters_are_not_escaped() -> None:
    original = _canonical_passport()
    md = render_to_md(original)
    assert "陳大文" in md
    assert "尾号" in md
    assert "香港" in md
    # No `\uXXXX` escape sequences in the YAML output.
    assert "\\u" not in md
    parsed = parse_md(md)
    assert parsed.place_of_birth == "香港"
    assert parsed.name_cjk == "陳大文 尾号 0083"


def test_parse_md_dispatches_to_passport_subclass_via_doc_type() -> None:
    md = render_to_md(_canonical_passport())
    parsed = parse_md(md)
    assert type(parsed) is Passport


def test_parse_md_falls_back_to_frontmatter_for_unknown_doc_type() -> None:
    # A bare Frontmatter (doc_type left empty) must round-trip without
    # tripping the dispatch table. Provenance fields are pinned so the
    # Story 7.5 auto-fill (extractor_version / extraction_timestamp) is a
    # no-op — preserves the byte-equal-after-roundtrip contract.
    fm = Frontmatter(
        extractor_version="0.1.0",
        extraction_timestamp="2026-05-03T00:00:00Z",
        doc_type="",
        jurisdiction="HKG",
        name_latin="ALEX",
    )
    md = render_to_md(fm)
    parsed = parse_md(md)
    assert type(parsed) is Frontmatter
    assert parsed == fm


def test_parse_md_rejects_input_without_fences() -> None:
    with pytest.raises(ValueError, match="missing YAML frontmatter fences"):
        parse_md("doc_type: Passport\n")


def test_parse_md_rejects_non_mapping_yaml_body() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        parse_md("---\n- just\n- a list\n---\n\n")


# --------------------------------------------------------------------------
# Story 5.3 — list[BaseModel] round-trip (first nested-object schema)
# --------------------------------------------------------------------------


def _canonical_entity_ownership() -> EntityOwnership:
    """Two UBOs, one Latin one CJK, plus a verbatim ownership_percentage with
    a non-numeric qualifier so PyYAML's number-coercion can't quietly normalise."""
    return EntityOwnership(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        extraction_timestamp="2026-05-03T12:00:00Z",
        prompt_version="entity_ownership@0.1.0",
        doc_type="EntityOwnership",
        jurisdiction="NZ",
        entity_name="Acme Holdings Limited",
        ultimate_beneficial_owners=[
            UltimateBeneficialOwner(
                name="Alice Wong", dob="1985-07-12", ownership_percentage="60%"
            ),
            UltimateBeneficialOwner(
                name="陳大文", dob="1990-01-15", ownership_percentage="approximately 40%"
            ),
        ],
    )


def test_entity_ownership_nested_list_round_trips_byte_equal() -> None:
    """list[UltimateBeneficialOwner] survives Pydantic → YAML → Pydantic.

    The dispatch entry in markdown_io._SCHEMA_BY_DOC_TYPE makes this work —
    without it, parse_md would fall back to Frontmatter (extra="forbid")
    and reject the EntityOwnership-specific keys.
    """
    eo = _canonical_entity_ownership()
    md = render_to_md(eo)
    parsed = parse_md(md)

    assert type(parsed) is EntityOwnership
    assert parsed == eo


def test_entity_ownership_round_trip_preserves_cjk_in_nested_ubo() -> None:
    """CJK characters in nested UBO `name` survive the YAML → text → YAML round."""
    eo = _canonical_entity_ownership()
    md = render_to_md(eo)
    # Raw CJK in the rendered body, not \uXXXX escapes.
    assert "陳大文" in md
    assert "\\u" not in md
    # Parse round-trip preserves the CJK glyph.
    parsed = parse_md(md)
    assert isinstance(parsed, EntityOwnership)
    assert parsed.ultimate_beneficial_owners is not None
    assert parsed.ultimate_beneficial_owners[1].name == "陳大文"


def test_entity_ownership_round_trip_preserves_verbatim_ownership_percentage() -> None:
    """`approximately 40%` survives unquoted-text round-trip without normalisation."""
    eo = _canonical_entity_ownership()
    md = render_to_md(eo)
    parsed = parse_md(md)
    assert isinstance(parsed, EntityOwnership)
    assert parsed.ultimate_beneficial_owners is not None
    assert parsed.ultimate_beneficial_owners[1].ownership_percentage == "approximately 40%"
