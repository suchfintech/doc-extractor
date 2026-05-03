"""PEP_Declaration schema — politically-exposed-person disclosures.

Three formats v1 supports: client-signed self-declaration, third-party
(lawyer / accountant) attestation, and AML-officer verification template.
The schema captures the disclosed status itself (`is_pep`), the role and
jurisdiction it applies to, and the relationship between the declarant
and the PEP (self / immediate family / close associate).

`is_pep` is intentionally a string (``"yes"`` / ``"no"`` / ``"unknown"``)
rather than a bool so it follows the empty-string-not-null convention from
``Frontmatter`` — `""` for genuinely-absent data is unambiguous.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class PEP_Declaration(Frontmatter):
    is_pep: str | None = ""
    pep_role: str | None = ""
    pep_jurisdiction: str | None = ""
    pep_relationship: str | None = ""
    declaration_date: str | None = ""
    declarant_name: str | None = ""
