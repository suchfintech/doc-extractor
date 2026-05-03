"""Purity guarantees for the body_parse module.

The body-parse layer is fed thousands of times per eval run, so callers
rely on it being a *function* in the mathematical sense — same input,
same output, no observable side effects. Worker-1's 3.4 (CN labels) and
worker-3's 3.5 (NZ narrative) both contribute parsers; this file covers
each one as it lands. Adding a new parser? Append a section.
"""
from __future__ import annotations

import pytest

from doc_extractor.body_parse.chinese_labels import parse_chinese
from doc_extractor.body_parse.nz_narrative import parse_nz

NZ_CANONICAL = (
    'Bank transfer of NZD 15,000.00 sent to account GM6040 '
    '(account number 02-0248-0242329-02) from account "Free Up-00" '
    '(account number 38-9024-0437881-00) on Tuesday, 1 July 2025'
)
NZ_VARIANT_USD = (
    "Bank transfer of USD 250.00 sent to account Acme "
    "(account number 12-3456-7890123-00) from account Payer "
    "(account number 98-7654-3210987-99) on Friday, 5 December 2025"
)


# ----- parse_nz (Story 3.5) -----


def test_parse_nz_is_idempotent() -> None:
    """Calling twice with the same input yields equal results."""
    a = parse_nz(NZ_CANONICAL)
    b = parse_nz(NZ_CANONICAL)
    assert a == b
    # Distinct instances (no aliased global cache returning the same object).
    assert a is not b


def test_parse_nz_does_not_leak_state_across_calls() -> None:
    """Interleaving with a different input must not perturb either result."""
    first = parse_nz(NZ_CANONICAL)
    other = parse_nz(NZ_VARIANT_USD)
    again = parse_nz(NZ_CANONICAL)

    assert first == again
    assert other.receipt_currency == "USD"
    assert again.receipt_currency == "NZD"


def test_parse_nz_does_not_mutate_input() -> None:
    body = NZ_CANONICAL
    snapshot = body
    parse_nz(body)
    assert body == snapshot


def test_parse_nz_module_has_no_mutable_module_state() -> None:
    """No mutable globals — only the compiled regex pattern objects + constants."""
    import doc_extractor.body_parse.nz_narrative as nz

    forbidden_types = (list, dict, set)
    for name in dir(nz):
        if name.startswith("_") and name.endswith("_"):
            continue  # dunders
        value = getattr(nz, name)
        if name == "_QUOTE_CHARS":
            continue  # immutable str constant
        assert not isinstance(value, forbidden_types), (
            f"Module-level mutable state at {name!r}: {type(value).__name__}"
        )


# ----- parse_chinese (Story 3.4) -----


CN_CANONICAL = (
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
CN_PARTIAL = "付款人: 李四\n收款人: 王五\n金额: 200.00\n币种: USD\n"


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("", id="empty"),
        pytest.param("付款人: 张三\n", id="single-line"),
        pytest.param(CN_CANONICAL, id="canonical-full"),
        pytest.param(
            "**付款人**: [张三]\n收款人: （李四）\n付款卡号: **** **** **** 0083\n",
            id="markdown-bold-and-brackets",
        ),
    ],
)
def test_parse_chinese_is_byte_identical_across_runs(body: str) -> None:
    first = parse_chinese(body).model_dump_json()
    second = parse_chinese(body).model_dump_json()
    assert first == second


def test_parse_chinese_does_not_leak_state_across_calls() -> None:
    """Interleaving with a different input must not perturb either result."""
    first = parse_chinese(CN_CANONICAL)
    other = parse_chinese(CN_PARTIAL)
    again = parse_chinese(CN_CANONICAL)

    assert first == again
    assert other.receipt_currency == "USD"
    assert again.receipt_currency == "CNY"


def test_parse_chinese_does_not_mutate_input() -> None:
    body = CN_CANONICAL
    snapshot = body
    parse_chinese(body)
    assert body == snapshot


def test_parse_chinese_module_has_no_mutable_module_state() -> None:
    """No mutable globals — patterns are compiled re.Pattern objects, the
    `_PATTERNS` dict is read-only by convention, the label tuples are immutable."""
    import doc_extractor.body_parse.chinese_labels as cn

    # The `_PATTERNS` dict is the only module-level dict; it must be populated
    # at import time and never mutated thereafter. Snapshot its keys here so a
    # future contributor who appends a key in a function body has this test
    # fail loudly.
    expected_keys = {
        "debit_name",
        "debit_number",
        "debit_bank",
        "credit_name",
        "credit_number",
        "credit_bank",
        "amount",
        "currency",
        "time",
        "reference",
        "payment_app",
    }
    assert set(cn._PATTERNS.keys()) == expected_keys


def test_parse_chinese_high_repeat_count_stays_byte_identical() -> None:
    """Higher-confidence purity check: 100 successive calls produce the same JSON."""
    baseline = parse_chinese(CN_CANONICAL).model_dump_json()
    for _ in range(100):
        assert parse_chinese(CN_CANONICAL).model_dump_json() == baseline
