"""Story 7.1 — schema-rename overlap mechanism (FR27 dual-emit).

Tests the ``_deprecated_aliases`` ClassVar registry on
:class:`PaymentReceipt` together with ``markdown_io``'s dual-emit on render
and ``old → new`` fallback on parse. The deprecation window for the
``receipt_counterparty_*`` fields expires 2026-08-03; the final test in
this module is a date sentinel that auto-fails on expiry to force the
cleanup decision (drop the deprecated fields, drop the registry, bump
``extractor_version``). Same pattern as
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


def test_render_dual_emits_when_only_new_field_set() -> None:
    receipt = PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_credit_account_name="Alice",
    )
    body = _yaml_body(render_to_md(receipt))

    assert body["receipt_credit_account_name"] == "Alice"
    assert body["receipt_counterparty_name"] == "Alice"
    # The other alias pair is empty on both sides — dual-emit should not
    # invent a value where neither side has one.
    assert body["receipt_credit_account_number"] == ""
    assert body["receipt_counterparty_account"] == ""


def test_render_dual_emits_when_only_legacy_field_set() -> None:
    """Consumer-migration scenario: caller supplies only the deprecated alias."""
    receipt = PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_counterparty_name="Bob",
        receipt_counterparty_account="6217 **** **** 0083",
    )
    body = _yaml_body(render_to_md(receipt))

    assert body["receipt_counterparty_name"] == "Bob"
    assert body["receipt_credit_account_name"] == "Bob"
    assert body["receipt_counterparty_account"] == "6217 **** **** 0083"
    assert body["receipt_credit_account_number"] == "6217 **** **** 0083"


def test_round_trip_preserves_new_shape_values() -> None:
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
    # Dual-emit propagated the value into the legacy field too.
    assert parsed.receipt_counterparty_name == "Charlie"
    assert parsed.receipt_counterparty_account == "1234-5678"
    assert parsed.receipt_amount == "100.00"


def test_parse_falls_back_old_to_new_when_new_field_absent() -> None:
    """A consumer still emitting only the legacy alias must round-trip."""
    legacy_md = (
        "---\n"
        "doc_type: PaymentReceipt\n"
        "receipt_counterparty_name: Dave\n"
        "receipt_counterparty_account: 02-0248-0242329-02\n"
        "---\n\n"
    )
    parsed = parse_md(legacy_md)

    assert isinstance(parsed, PaymentReceipt)
    assert parsed.receipt_credit_account_name == "Dave"
    assert parsed.receipt_credit_account_number == "02-0248-0242329-02"
    assert parsed.receipt_counterparty_name == "Dave"


def test_parse_disagreement_resolves_in_favour_of_new_field() -> None:
    """If both old and new are populated and disagree, the new field wins."""
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
    # The legacy slot keeps its disagreeing value — render-time will dual-emit
    # if asked, but parse does not silently overwrite the legacy field.
    assert parsed.receipt_counterparty_name == "X"


def test_fr27_overlap_window_not_yet_expired() -> None:
    """Sentinel: when the FR27 overlap closes, drop the deprecated fields,
    drop ``_deprecated_aliases``, and bump ``extractor_version``. This test
    fails on 2026-08-03 to force the cleanup decision."""
    assert date.today() < FR27_EXPIRY, (
        "FR27 overlap window expired — drop receipt_counterparty_* "
        "from PaymentReceipt and the _deprecated_aliases registry, then "
        "bump extractor_version."
    )
