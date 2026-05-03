"""Integration tests for the corrections-overlay reader (Story 6.2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from doc_extractor import markdown_io, s3_io
from doc_extractor.corrections import read_corrected_or_canonical
from doc_extractor.schemas.ids import Passport

SOURCE_KEY = "passports/case-001.jpeg"
EXPECTED_CORRECTIONS_KEY = f"corrections/{SOURCE_KEY}.md"
EXPECTED_CANONICAL_KEY = f"{SOURCE_KEY}.md"


def _passport(name_latin: str) -> Passport:
    return Passport(
        doc_type="Passport",
        passport_number="X9988776",
        nationality="NZL",
        doc_number="X9988776",
        dob="1985-09-12",
        issue_date="2022-09-12",
        expiry_date="2032-09-11",
        sex="F",
        mrz_line_1="P<NZLDOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
        mrz_line_2="X9988776<NZL8509121F3209118<<<<<<<<<<<<<<00",
        name_latin=name_latin,
        jurisdiction="NZL",
    )


@pytest.fixture
def mocked_s3(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    head = MagicMock(return_value=False)
    read = MagicMock(return_value=b"")
    monkeypatch.setattr(s3_io, "head_analysis", head)
    monkeypatch.setattr(s3_io, "read_analysis", read)
    return {"head": head, "read": read}


@pytest.mark.asyncio
async def test_correction_present_wins_over_canonical(
    mocked_s3: dict[str, MagicMock],
) -> None:
    canonical_md = markdown_io.render_to_md(_passport("WRONG"))
    corrected_md = markdown_io.render_to_md(_passport("CORRECTED"))

    def head_side_effect(key: str) -> bool:
        if key == EXPECTED_CORRECTIONS_KEY:
            return True
        if key == EXPECTED_CANONICAL_KEY:
            return True
        return False

    def read_side_effect(key: str) -> bytes:
        if key == EXPECTED_CORRECTIONS_KEY:
            return corrected_md.encode("utf-8")
        if key == EXPECTED_CANONICAL_KEY:
            return canonical_md.encode("utf-8")
        raise AssertionError(f"unexpected read for {key!r}")

    mocked_s3["head"].side_effect = head_side_effect
    mocked_s3["read"].side_effect = read_side_effect

    result = await read_corrected_or_canonical(SOURCE_KEY)

    assert isinstance(result, Passport)
    assert result.name_latin == "CORRECTED"
    mocked_s3["read"].assert_called_once_with(EXPECTED_CORRECTIONS_KEY)


@pytest.mark.asyncio
async def test_falls_back_to_canonical_when_correction_absent(
    mocked_s3: dict[str, MagicMock],
) -> None:
    canonical_md = markdown_io.render_to_md(_passport("CANONICAL"))

    def head_side_effect(key: str) -> bool:
        return key == EXPECTED_CANONICAL_KEY

    def read_side_effect(key: str) -> bytes:
        if key == EXPECTED_CANONICAL_KEY:
            return canonical_md.encode("utf-8")
        raise AssertionError(f"unexpected read for {key!r}")

    mocked_s3["head"].side_effect = head_side_effect
    mocked_s3["read"].side_effect = read_side_effect

    result = await read_corrected_or_canonical(SOURCE_KEY)

    assert isinstance(result, Passport)
    assert result.name_latin == "CANONICAL"
    mocked_s3["read"].assert_called_once_with(EXPECTED_CANONICAL_KEY)


@pytest.mark.asyncio
async def test_both_missing_raises_file_not_found(
    mocked_s3: dict[str, MagicMock],
) -> None:
    mocked_s3["head"].return_value = False

    with pytest.raises(FileNotFoundError, match=SOURCE_KEY):
        await read_corrected_or_canonical(SOURCE_KEY)

    mocked_s3["read"].assert_not_called()


@pytest.mark.asyncio
async def test_corrections_head_runs_before_canonical_head(
    mocked_s3: dict[str, MagicMock],
) -> None:
    """The corrections-take-priority invariant must not be reorderable."""
    mocked_s3["head"].return_value = False

    with pytest.raises(FileNotFoundError):
        await read_corrected_or_canonical(SOURCE_KEY)

    head_call_keys = [call.args[0] for call in mocked_s3["head"].call_args_list]
    assert head_call_keys == [EXPECTED_CORRECTIONS_KEY, EXPECTED_CANONICAL_KEY]


@pytest.mark.asyncio
async def test_re_export_from_top_level_package() -> None:
    """The helper is part of the package's public surface (additive __init__)."""
    import doc_extractor

    assert hasattr(doc_extractor, "read_corrected_or_canonical")
    assert (
        doc_extractor.read_corrected_or_canonical is read_corrected_or_canonical
    )
