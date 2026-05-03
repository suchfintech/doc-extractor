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

from doc_extractor.schemas.base import Frontmatter


class PaymentReceipt(Frontmatter):
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
