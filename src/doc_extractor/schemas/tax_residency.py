"""TaxResidency schema — IRD letters, IR3 declarations, FATCA W-8/W-9, CRS.

The TIN (taxpayer identification number) format varies wildly per
jurisdiction — IRD numbers in NZ, SSN/EIN in the US, the 18-digit USCC for
CN entities, the 8-character HKID-derived TIN in HK, etc. The schema
captures the printed string verbatim including any check-digit hyphens
(`123-45-6789` SSN, `12-345-678` IRD); downstream consumers parse against
the jurisdiction.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class TaxResidency(Frontmatter):
    holder_name: str | None = ""
    tax_jurisdiction: str | None = ""
    tin: str | None = ""
    residency_status: str | None = ""
    effective_from: str | None = ""
