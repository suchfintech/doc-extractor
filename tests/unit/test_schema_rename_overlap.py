"""Story 7.1 — schema-rename overlap (FR27): NO auto-mapping.

The earlier dual-emit / parse-fallback design was dropped in code review
Round 1 (2026-05): a static ``counterparty → credit`` map is direction-
wrong half the time because counterparty depends on whether the payment is
inbound or outbound. Each ``.md`` file now has ONE shape — the deprecated
``receipt_counterparty_*`` fields stay readable for old files but no
auto-mapping happens on render or parse.

The deprecation window for the ``receipt_counterparty_*`` fields expires
2026-08-03; the final test in this module is a date sentinel that
auto-fails on expiry to force the cleanup decision (drop the deprecated
fields entirely and bump ``extractor_version``). Same pattern as
``test_payment_receipt_deprecated_overlap_window_not_yet_expired`` in
``test_schema_byte_stability.py``.
"""

from __future__ import annotations

from datetime import date

import yaml  # type: ignore[import-untyped]

from doc_extractor.markdown_io import parse_md, render_to_md
from doc_extractor.schemas.payment_receipt import PaymentReceipt

FR27_EXPIRY = date(2026, 8, 3)


def _yaml_body(rendered: str) -> dict[str, object]:
    """Strip the `---` fences and parse the YAML body for assertions."""
    parts = rendered.split("---", 2)
    assert len(parts) >= 3, f"unexpected render shape:\n{rendered}"
    return yaml.safe_load(parts[1]) or {}


def test_render_does_not_dual_emit_when_only_new_field_set() -> None:
    """Setting only the new credit-side field must NOT auto-fill the
    deprecated counterparty alias on render."""
    receipt = PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_credit_account_name="Alice",
    )
    body = _yaml_body(render_to_md(receipt))

    assert body["receipt_credit_account_name"] == "Alice"
    assert body["receipt_counterparty_name"] == ""
    assert body["receipt_credit_account_number"] == ""
    assert body["receipt_counterparty_account"] == ""


def test_render_does_not_dual_emit_when_only_legacy_field_set() -> None:
    """Setting only the deprecated counterparty alias must NOT auto-fill the
    new credit-side field on render. Direction (debit vs credit) depends on
    the payment flow — a static counterparty→credit map is wrong half the
    time, so we leave each field in its own slot."""
    receipt = PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_counterparty_name="Bob",
        receipt_counterparty_account="6217 **** **** 0083",
    )
    body = _yaml_body(render_to_md(receipt))

    assert body["receipt_counterparty_name"] == "Bob"
    assert body["receipt_counterparty_account"] == "6217 **** **** 0083"
    assert body["receipt_credit_account_name"] == ""
    assert body["receipt_credit_account_number"] == ""


def test_render_preserves_both_when_both_populated() -> None:
    """If a caller explicitly sets BOTH the new and legacy field names
    (with disagreeing values), render keeps both verbatim — neither side
    overrides the other. The agent supplied them; reconciliation is the
    consumer's call."""
    receipt = PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_credit_account_name="NewName",
        receipt_counterparty_name="LegacyName",
    )
    body = _yaml_body(render_to_md(receipt))

    assert body["receipt_credit_account_name"] == "NewName"
    assert body["receipt_counterparty_name"] == "LegacyName"


def test_round_trip_keeps_new_shape_in_its_own_slot() -> None:
    """Render → parse: the new debit/credit fields stay in their own
    slots — counterparty is NOT populated as a side-effect."""
    receipt = PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_amount="100.00",
        receipt_currency="CNY",
        receipt_credit_account_name="Charlie",
        receipt_credit_account_number="1234-5678",
    )
    rendered = render_to_md(receipt)
    parsed = parse_md(rendered)

    assert isinstance(parsed, PaymentReceipt)
    assert parsed.receipt_credit_account_name == "Charlie"
    assert parsed.receipt_credit_account_number == "1234-5678"
    assert parsed.receipt_counterparty_name == ""
    assert parsed.receipt_counterparty_account == ""
    assert parsed.receipt_amount == "100.00"


def test_parse_does_not_copy_legacy_field_into_new_field() -> None:
    """An old ``.md`` written before the rename must round-trip with the
    counterparty values staying in the counterparty slot — parse_md does
    NOT auto-coerce ``receipt_counterparty_*`` → ``receipt_credit_*``.
    Each MD file has one shape; the consumer reads both slots."""
    legacy_md = (
        "---\n"
        "doc_type: PaymentReceipt\n"
        "receipt_counterparty_name: Dave\n"
        "receipt_counterparty_account: 02-0248-0242329-02\n"
        "---\n\n"
    )
    parsed = parse_md(legacy_md)

    assert isinstance(parsed, PaymentReceipt)
    assert parsed.receipt_counterparty_name == "Dave"
    assert parsed.receipt_counterparty_account == "02-0248-0242329-02"
    assert parsed.receipt_credit_account_name == ""
    assert parsed.receipt_credit_account_number == ""


def test_parse_keeps_disagreeing_values_in_their_own_slots() -> None:
    """If both old and new are populated and disagree, both stay verbatim —
    parse does not silently coerce one onto the other."""
    conflicted_md = (
        "---\n"
        "doc_type: PaymentReceipt\n"
        "receipt_credit_account_name: Y\n"
        "receipt_counterparty_name: X\n"
        "---\n\n"
    )
    parsed = parse_md(conflicted_md)

    assert isinstance(parsed, PaymentReceipt)
    assert parsed.receipt_credit_account_name == "Y"
    assert parsed.receipt_counterparty_name == "X"


def test_fr27_overlap_window_not_yet_expired() -> None:
    """Sentinel: when the FR27 overlap closes, drop the deprecated fields
    from PaymentReceipt and bump ``extractor_version``. This test fails on
    2026-08-03 to force the cleanup decision."""
    assert date.today() < FR27_EXPIRY, (
        "FR27 overlap window expired — drop receipt_counterparty_* "
        "from PaymentReceipt and bump extractor_version."
    )
