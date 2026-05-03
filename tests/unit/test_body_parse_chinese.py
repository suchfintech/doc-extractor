"""Per-variant + canonical-example tests for parse_chinese (Story 3.4).

Each label variant in the AC is exercised at least once; the canonical CN
payment fixture covers all 11 fields together; mask shapes round-trip
verbatim; bracket/markdown stripping is verified.
"""
from __future__ import annotations

import pytest

from doc_extractor.body_parse.chinese_labels import parse_chinese

# ---------------------------------------------------------------------------
# Debit-side label variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    ["付款人", "付款户名", "付款方", "汇款人", "汇款方"],
)
def test_debit_name_variants(label: str) -> None:
    body = f"{label}: 张三\n"
    result = parse_chinese(body)
    assert result.receipt_debit_account_name == "张三"


@pytest.mark.parametrize(
    "label",
    ["付款卡号", "付款账号", "付款账户", "付款账户号码"],
)
def test_debit_number_variants(label: str) -> None:
    body = f"{label}: 6217 **** **** 0083\n"
    result = parse_chinese(body)
    assert result.receipt_debit_account_number == "6217 **** **** 0083"


@pytest.mark.parametrize(
    "label",
    ["付款行", "付款银行", "付款方银行", "付款方开户行"],
)
def test_debit_bank_variants(label: str) -> None:
    body = f"{label}: 中国工商银行\n"
    result = parse_chinese(body)
    assert result.receipt_debit_bank_name == "中国工商银行"


# ---------------------------------------------------------------------------
# Credit-side label variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["收款人", "收款户名", "收款方"])
def test_credit_name_variants(label: str) -> None:
    body = f"{label}: 李四\n"
    result = parse_chinese(body)
    assert result.receipt_credit_account_name == "李四"


@pytest.mark.parametrize(
    "label",
    ["收款卡号", "收款账号", "收款账户", "收款账户号码"],
)
def test_credit_number_variants(label: str) -> None:
    body = f"{label}: 6230 **** **** 2235\n"
    result = parse_chinese(body)
    assert result.receipt_credit_account_number == "6230 **** **** 2235"


@pytest.mark.parametrize(
    "label",
    ["收款行", "收款银行", "收款方银行", "收款方开户行"],
)
def test_credit_bank_variants(label: str) -> None:
    body = f"{label}: 平安银行\n"
    result = parse_chinese(body)
    assert result.receipt_credit_bank_name == "平安银行"


# ---------------------------------------------------------------------------
# Other fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["金额", "付款金额"])
def test_amount_variants(label: str) -> None:
    body = f"{label}: 15000.00\n"
    assert parse_chinese(body).receipt_amount == "15000.00"


@pytest.mark.parametrize("label", ["币种", "货币", "币别"])
def test_currency_variants(label: str) -> None:
    body = f"{label}: CNY\n"
    assert parse_chinese(body).receipt_currency == "CNY"


@pytest.mark.parametrize("label", ["时间", "交易时间", "付款时间"])
def test_time_variants(label: str) -> None:
    body = f"{label}: 2025-07-01T00:00:00Z\n"
    assert parse_chinese(body).receipt_time == "2025-07-01T00:00:00Z"


@pytest.mark.parametrize("label", ["用途", "备注", "汇款附言"])
def test_reference_variants(label: str) -> None:
    body = f"{label}: INV-2025-001\n"
    assert parse_chinese(body).receipt_reference == "INV-2025-001"


@pytest.mark.parametrize("label", ["付款工具", "付款渠道"])
def test_payment_app_variants(label: str) -> None:
    body = f"{label}: 工商银行手机银行\n"
    assert parse_chinese(body).receipt_payment_app == "工商银行手机银行"


# ---------------------------------------------------------------------------
# Canonical full-CN-payment example (echoes the Story 3.1 fixture)
# ---------------------------------------------------------------------------


CANONICAL_BODY = (
    "付款人: 张三\n"
    "付款卡号: 6217 **** **** 0083\n"
    "付款行: 中国工商银行\n"
    "收款人: GM6040\n"
    "收款账户: 02-0248-0242329-02\n"
    "收款行: ANZ\n"
    "金额: 15000.00\n"
    "币种: CNY\n"
    "时间: 2025-07-01T00:00:00Z\n"
    "用途: INV-2025-001\n"
    "付款工具: 工商银行手机银行\n"
)


def test_canonical_full_cn_payment_populates_all_fields() -> None:
    result = parse_chinese(CANONICAL_BODY)
    assert result.doc_type == "PaymentReceipt"
    assert result.receipt_debit_account_name == "张三"
    assert result.receipt_debit_account_number == "6217 **** **** 0083"
    assert result.receipt_debit_bank_name == "中国工商银行"
    assert result.receipt_credit_account_name == "GM6040"
    assert result.receipt_credit_account_number == "02-0248-0242329-02"
    assert result.receipt_credit_bank_name == "ANZ"
    assert result.receipt_amount == "15000.00"
    assert result.receipt_currency == "CNY"
    assert result.receipt_time == "2025-07-01T00:00:00Z"
    assert result.receipt_reference == "INV-2025-001"
    assert result.receipt_payment_app == "工商银行手机银行"


# ---------------------------------------------------------------------------
# Mask + name-cleanup invariants
# ---------------------------------------------------------------------------


def test_account_number_mask_preserved_verbatim() -> None:
    """Internal whitespace and `*` characters in masked account numbers are
    preserved exactly. No collapse, no normalisation."""
    body = "付款卡号: 6217 **** **** 0083\n"
    assert parse_chinese(body).receipt_debit_account_number == "6217 **** **** 0083"


def test_account_number_with_full_mask_preserved() -> None:
    """Even fully-masked numbers (no leading visible digits) survive byte-equal."""
    body = "付款账号: **** **** **** 0083\n"
    assert parse_chinese(body).receipt_debit_account_number == "**** **** **** 0083"


def test_nz_style_hyphenated_account_number_preserved() -> None:
    """NZ-style account numbers (hyphenated) are preserved verbatim."""
    body = "收款账户: 02-0248-0242329-02\n"
    assert parse_chinese(body).receipt_credit_account_number == "02-0248-0242329-02"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("[张三]", "张三"),
        ("(张三)", "张三"),
        ("（张三）", "张三"),
        ("张三   ", "张三"),
        ("**张三**", "张三"),
    ],
)
def test_name_brackets_and_trailing_whitespace_stripped(raw: str, expected: str) -> None:
    body = f"付款人: {raw}\n"
    assert parse_chinese(body).receipt_debit_account_name == expected


def test_cjk_characters_inside_names_are_not_stripped() -> None:
    """Multi-character CJK names with internal spaces survive."""
    body = "付款人: 王 大 明\n"
    assert parse_chinese(body).receipt_debit_account_name == "王 大 明"


# ---------------------------------------------------------------------------
# Disambiguation: shorter labels must not eat longer-label prefixes
# ---------------------------------------------------------------------------


def test_dabit_name_label_does_not_swallow_bank_label() -> None:
    """`付款方` (debit name) and `付款方银行` (debit bank) on separate lines
    must not collide. The shorter label requires `[\\s\\*]*[:：]` after it,
    which `银行` blocks, so only the bank line populates the bank field."""
    body = "付款方银行: 中国工商银行\n付款方: 张三\n"
    result = parse_chinese(body)
    assert result.receipt_debit_account_name == "张三"
    assert result.receipt_debit_bank_name == "中国工商银行"


def test_only_bank_label_present_does_not_populate_name() -> None:
    body = "付款方银行: 中国工商银行\n"
    result = parse_chinese(body)
    assert result.receipt_debit_account_name == ""
    assert result.receipt_debit_bank_name == "中国工商银行"


# ---------------------------------------------------------------------------
# Unfound / partial-input behaviour
# ---------------------------------------------------------------------------


def test_empty_body_returns_empty_string_for_every_field() -> None:
    result = parse_chinese("")
    assert result.doc_type == "PaymentReceipt"
    for field in (
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
    ):
        assert getattr(result, field) == "", field


def test_partial_body_only_populates_present_labels() -> None:
    body = "付款人: 张三\n"
    result = parse_chinese(body)
    assert result.receipt_debit_account_name == "张三"
    assert result.receipt_credit_account_name == ""
    assert result.receipt_debit_account_number == ""
    assert result.receipt_amount == ""


# ---------------------------------------------------------------------------
# Markdown / fullwidth-colon variants
# ---------------------------------------------------------------------------


def test_fullwidth_colon_separator_works() -> None:
    body = "付款人：张三\n"
    assert parse_chinese(body).receipt_debit_account_name == "张三"


def test_markdown_bold_around_label() -> None:
    body = "**付款人**: 张三\n"
    assert parse_chinese(body).receipt_debit_account_name == "张三"


def test_label_after_list_marker() -> None:
    body = "- 付款人: 张三\n"
    assert parse_chinese(body).receipt_debit_account_name == "张三"
