"""BankStatement schema — header + summary fields only for v1.

Line-level transaction extraction is **out of scope** for v1's BankStatement
specialist. The header (account identity + period) and the closing balance
are what downstream consumers need; per-row transaction parsing is a
separate v1.x feature, and the catch-all `Other` specialist (Story 5.5)
absorbs anything that doesn't fit a narrower schema in the meantime.

Multi-page PDFs are pre-rendered to per-page images via
`pdf/converter.py:pdf_to_images(mode="all_pages")` (Story 3.3) — the
agent prompt anticipates seeing all pages and extracts only from the
header section, regardless of which page it appears on.
"""
from __future__ import annotations

from doc_extractor.schemas.bank import BankDocBase


class BankStatement(BankDocBase):
    statement_period_start: str | None = ""
    statement_period_end: str | None = ""
    statement_date: str | None = ""
    closing_balance: str | None = ""
