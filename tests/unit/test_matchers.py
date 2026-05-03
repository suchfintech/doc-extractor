"""Coverage for the eval matchers — pass + fail case per matcher."""
from __future__ import annotations

from doc_extractor.eval.matchers import (
    match_exact,
    match_normalised,
    match_with_jurisdiction,
)


def test_match_exact_passes_on_byte_identical_strings() -> None:
    assert match_exact("passport_number", "E12345678", "E12345678") is True


def test_match_exact_fails_on_case_difference() -> None:
    assert match_exact("passport_number", "E12345678", "e12345678") is False


def test_match_normalised_passes_with_diacritics_and_trailing_ws_and_case() -> None:
    # NFKD of "ñ" decomposes to "n" + combining tilde; the Mn filter drops the tilde.
    # rstrip removes trailing whitespace; lower() folds case.
    assert match_normalised("name_latin", "MUÑOZ ", "muñoz") is True
    assert match_normalised("name_latin", "Café", "cafe") is True


def test_match_normalised_fails_when_substantive_chars_differ() -> None:
    assert match_normalised("name_latin", "Smith", "Smyth") is False


def test_match_normalised_preserves_cjk_characters() -> None:
    """CJK glyphs are category Lo, not Mn — they survive NFKD + Mn filter."""
    assert match_normalised("name_cjk", "张三", "张三") is True
    # And different CJK glyphs must still mismatch (i.e. we did not over-strip).
    assert match_normalised("name_cjk", "张三", "李四") is False


def test_match_with_jurisdiction_cn_collapses_star_mask_runs() -> None:
    assert (
        match_with_jurisdiction(
            "account_number",
            "6217 **** **** 1234",
            "6217 ******** 1234",
            jurisdiction="CN",
        )
        is True
    )


def test_match_with_jurisdiction_cn_still_rejects_genuine_mismatches() -> None:
    assert (
        match_with_jurisdiction(
            "account_number",
            "6217 **** **** 1234",
            "6217 **** **** 9999",
            jurisdiction="CN",
        )
        is False
    )


def test_match_with_jurisdiction_non_cn_falls_back_to_exact() -> None:
    # Outside CN, the mask collapse must NOT apply — different mask widths fail.
    assert (
        match_with_jurisdiction(
            "account_number",
            "6217 **** **** 1234",
            "6217 ******** 1234",
            jurisdiction="AU",
        )
        is False
    )
    # Identical strings still pass under exact-match semantics.
    assert (
        match_with_jurisdiction(
            "account_number",
            "6217 **** **** 1234",
            "6217 **** **** 1234",
            jurisdiction="AU",
        )
        is True
    )
