"""CompanyExtract schema — corporate-registry extracts.

Three formats v1 supports: NZ Companies Office Extract (companiesoffice.govt.nz),
UK Companies House extract, and CN 工商档案 (industrial-and-commerce extract).

The ``directors`` and ``shareholders`` fields are ``list[str] | None``,
defaulting to ``None`` rather than ``[]``. The distinction matters:

* ``None`` — the agent did not extract this field (e.g. the source was
  illegible or the field type wasn't on this kind of extract).
* ``[]`` — the document explicitly lists *zero* directors / shareholders
  (rare but real — a shell company about to be liquidated, for example).

Downstream consumers who care about the difference can branch on
``is None``; consumers who don't can treat both as falsy.

Why ``None`` and not ``Field(default_factory=list)`` for the default —
the empty-string-not-null convention from ``Frontmatter`` is for *string*
fields where ``""`` is the unambiguous "absent" sentinel. For lists,
PyYAML serialises ``None`` as ``null`` (not ``""``), and we WANT that
distinction so the round-trip surfaces "not extracted" vs "explicitly
empty" cleanly.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class CompanyExtract(Frontmatter):
    company_name: str | None = ""
    registration_number: str | None = ""
    incorporation_date: str | None = ""
    registered_address: str | None = ""
    directors: list[str] | None = None
    shareholders: list[str] | None = None
