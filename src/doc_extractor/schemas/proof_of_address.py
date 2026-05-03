"""ProofOfAddress schema — utility bills, council notices, bank statements,
CN 户口本, etc. used as residential-address evidence.

The schema captures what's printed; **freshness filtering is downstream**.
AML rules typically require the document be dated within the last 3 months,
but the agent's job is verbatim extraction of the printed date — a downstream
consumer compares against "now" to decide acceptance.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class ProofOfAddress(Frontmatter):
    holder_name: str | None = ""
    address: str | None = ""
    document_date: str | None = ""
    issuer: str | None = ""
    document_type: str | None = ""
