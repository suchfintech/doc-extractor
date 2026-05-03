"""PaymentReceipt schema (debit/credit sides + deprecated counterparty aliases).

Direction-correctness matters: debit is the payer side, credit is the payee
side. Per the merlin handoff, when both Chinese (`付款人/收款人`) and English
(`Payer/Payee`) labels are present and disagree, **Chinese is ground truth**.
That rule lives in the agent prompt; this schema only enforces shape.

Account-number masks (`6217 **** **** 0083`, `02-0248-0242329-02`) and the raw
amount string are preserved verbatim — no normalisation. All fields follow the
empty-string-not-null convention from `Frontmatter`.

Deprecated fields (`receipt_counterparty_name`, `receipt_counterparty_account`)
are kept for the FR27 one-quarter overlap window. They expire **2026-08-03**.
"""
from __future__ import annotations

from typing import ClassVar

from doc_extractor.schemas.base import Frontmatter


class PaymentReceipt(Frontmatter):
    """Payment-receipt extraction schema with FR27 deprecation registry.

    ``_deprecated_aliases`` (Story 7.1) maps deprecated alias field names to
    their canonical replacements. ``markdown_io.render_to_md`` reads this map
    and dual-emits both names during the overlap window;
    ``markdown_io.parse_md`` falls back ``old → new`` when only the legacy
    field is present. The aliases expire 2026-08-03 per FR27 — at that
    point drop the deprecated fields, drop this map, and bump
    ``extractor_version``.
    """

    _deprecated_aliases: ClassVar[dict[str, str]] = {
        "receipt_counterparty_name": "receipt_credit_account_name",
        "receipt_counterparty_account": "receipt_credit_account_number",
    }

    receipt_amount: str | None = ""
    receipt_currency: str | None = ""
    receipt_time: str | None = ""

    receipt_debit_account_name: str | None = ""
    receipt_debit_account_number: str | None = ""
    receipt_debit_bank_name: str | None = ""

    receipt_credit_account_name: str | None = ""
    receipt_credit_account_number: str | None = ""
    receipt_credit_bank_name: str | None = ""

    receipt_reference: str | None = ""
    receipt_payment_app: str | None = ""

    # ----- DEPRECATED aliases (FR27 overlap; window expires 2026-08-03) -----
    receipt_counterparty_name: str | None = ""
    """DEPRECATED — overlap window expires 2026-08-03. Use receipt_debit_account_name
    or receipt_credit_account_name instead. Populated alongside the new fields
    during the overlap window so downstream consumers can migrate gradually."""

    receipt_counterparty_account: str | None = ""
    """DEPRECATED — overlap window expires 2026-08-03. Use receipt_debit_account_number
    or receipt_credit_account_number instead."""
