"""Bank-document base — shared shape for BankStatement + BankAccountConfirmation.

Both documents identify a bank account at a moment in time; the statement
adds a period + closing balance, the confirmation adds the signing
authority. Keeping the shared fields on a base class means downstream
consumers (operator-fingerprint matching, balance-snapshot indexing) can
treat both alike via duck-typed attribute access without juggling two
schema imports.

Account-number masking discipline matches PaymentReceipt: the printed
mask round-trips byte-for-byte (`6217 **** **** 0083`,
`02-0248-0242329-02`). Currency is ISO 4217 three-letter (`NZD`, `CNY`,
`USD`).
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class BankDocBase(Frontmatter):
    bank_name: str | None = ""
    account_holder_name: str | None = ""
    account_number: str | None = ""
    account_type: str | None = ""
    currency: str | None = ""
