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
The fields stay readable in old `.md` files written before the rename, but
no auto-mapping happens on render or parse — direction (debit vs credit)
depends on the payment flow and a static counterparty→credit mapping is
wrong half the time.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class PaymentReceipt(Frontmatter):
    """Payment-receipt extraction schema.

    The deprecated ``receipt_counterparty_*`` fields below are read-only
    legacy slots for parsing pre-2026-05 ``.md`` files. They expire
    2026-08-03 per FR27 — at that point drop the fields and bump
    ``extractor_version``.
    """

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
    """DEPRECATED — read-only legacy slot for parsing pre-2026-05 .md files. Will be removed 2026-08-03 per FR27. Do not write new files with this field set."""

    receipt_counterparty_account: str | None = ""
    """DEPRECATED — read-only legacy slot for parsing pre-2026-05 .md files. Will be removed 2026-08-03 per FR27. Do not write new files with this field set."""
