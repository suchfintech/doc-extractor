"""Coverage for :func:`doc_extractor.body_parse.nz_narrative.parse_nz`.

Includes the FR-NFR4 timing assertion: 1000 calls against the canonical
example must complete in ≤200ms so a single eval pass against the golden
corpus stays well under the harness budget.
"""
from __future__ import annotations

import time

import pytest

from doc_extractor.body_parse.nz_narrative import parse_nz

CANONICAL = (
    'Bank transfer of NZD 15,000.00 sent to account GM6040 '
    '(account number 02-0248-0242329-02) from account "Free Up-00" '
    '(account number 38-9024-0437881-00) on Tuesday, 1 July 2025'
)


def test_canonical_happy_path() -> None:
    receipt = parse_nz(CANONICAL)

    assert receipt.receipt_amount == "15000.00"
    assert receipt.receipt_currency == "NZD"
    assert receipt.receipt_debit_account_name == "Free Up-00"
    assert receipt.receipt_debit_account_number == "38-9024-0437881-00"
    assert receipt.receipt_credit_account_name == "GM6040"
    assert receipt.receipt_credit_account_number == "02-0248-0242329-02"
    assert receipt.receipt_time == "2025-07-01T00:00:00Z"


def test_reversed_from_to_ordering() -> None:
    body = (
        'Bank transfer of NZD 15,000.00 sent from account "Free Up-00" '
        '(account number 38-9024-0437881-00) to account GM6040 '
        '(account number 02-0248-0242329-02) on Tuesday, 1 July 2025'
    )
    receipt = parse_nz(body)

    # Even with reversed surface order, debit (from) and credit (to) bind correctly.
    assert receipt.receipt_debit_account_name == "Free Up-00"
    assert receipt.receipt_debit_account_number == "38-9024-0437881-00"
    assert receipt.receipt_credit_account_name == "GM6040"
    assert receipt.receipt_credit_account_number == "02-0248-0242329-02"


def test_usd_variant() -> None:
    body = (
        "Bank transfer of USD 250.00 sent to account Acme "
        "(account number 12-3456-7890123-00) from account Payer "
        "(account number 98-7654-3210987-99) on Friday, 5 December 2025"
    )
    receipt = parse_nz(body)

    assert receipt.receipt_amount == "250.00"
    assert receipt.receipt_currency == "USD"
    assert receipt.receipt_time == "2025-12-05T00:00:00Z"


def test_aud_variant_with_amount_no_thousand_separator() -> None:
    body = (
        "Bank transfer of AUD 99.50 sent to account Vendor "
        "(account number 11-2222-3333333-44) from account Customer "
        "(account number 55-6666-7777777-88) on Monday, 1 January 2026"
    )
    receipt = parse_nz(body)

    assert receipt.receipt_amount == "99.50"
    assert receipt.receipt_currency == "AUD"
    assert receipt.receipt_time == "2026-01-01T00:00:00Z"


def test_unicode_smart_quotes_are_stripped_from_names() -> None:
    # U+201C / U+201D smart double quotes around the debit account name.
    body = (
        "Bank transfer of NZD 10.00 sent to account GM6040 "
        "(account number 02-0248-0242329-02) from account “Free Up-00” "
        "(account number 38-9024-0437881-00) on Tuesday, 1 July 2025"
    )
    receipt = parse_nz(body)

    assert receipt.receipt_debit_account_name == "Free Up-00"
    # Hyphens preserved verbatim.
    assert receipt.receipt_debit_account_number == "38-9024-0437881-00"


def test_missing_amount_raises_value_error() -> None:
    body = (
        "Bank transfer sent to account GM6040 "
        "(account number 02-0248-0242329-02) from account Payer "
        "(account number 38-9024-0437881-00) on Tuesday, 1 July 2025"
    )
    with pytest.raises(ValueError, match="currency"):
        parse_nz(body)


def test_missing_date_raises_value_error() -> None:
    body = (
        "Bank transfer of NZD 15,000.00 sent to account GM6040 "
        "(account number 02-0248-0242329-02) from account Payer "
        "(account number 38-9024-0437881-00)"
    )
    with pytest.raises(ValueError, match="date"):
        parse_nz(body)


def test_thousand_separator_collapsed_in_amount() -> None:
    receipt = parse_nz(CANONICAL)
    assert "," not in (receipt.receipt_amount or "")


def test_parse_nz_meets_200ms_per_1000_calls_budget() -> None:
    """NFR4 perf gate: 1000 parses ≤ 200ms total (mean ≤ 200µs/call)."""
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        parse_nz(CANONICAL)
    elapsed = time.perf_counter() - start

    assert elapsed <= 0.200, (
        f"parse_nz too slow: {iterations} calls took {elapsed * 1000:.1f}ms "
        f"({elapsed / iterations * 1_000_000:.1f}µs/call), budget 200µs/call"
    )
