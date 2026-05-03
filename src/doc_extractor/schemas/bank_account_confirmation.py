"""BankAccountConfirmation schema — bank-issued account-existence letter.

Single-page bank letterhead confirming that a named account exists at
the bank as of a given date, signed by an authorised bank officer
(branch manager, branch operations officer, etc.). Distinct from a
BankStatement in that there's no period and no balance — just the
identity + signing authority.
"""
from __future__ import annotations

from doc_extractor.schemas.bank import BankDocBase


class BankAccountConfirmation(BankDocBase):
    confirmation_date: str | None = ""
    confirmation_authority: str | None = ""
