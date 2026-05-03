"""EntityOwnership schema — beneficial-ownership disclosure forms.

Formats v1 supports: NZ AML/CFT mandatory schedule, FATF UBO templates.

This is the **first nested-object schema** in the project. Per-UBO data
(name + DOB + ownership percentage) lives on a nested
:class:`UltimateBeneficialOwner` Pydantic model, and ``EntityOwnership``
holds a list of them.

The ``ownership_percentage`` field is intentionally a verbatim string —
documents render it inconsistently (``"25%"``, ``"0.25"``, ``"25.5%"``,
``"approximately 25%"``, ``"二十五分之一"``) and downstream consumers do
their own parsing rather than the agent guessing a numeric form.

The ≥25% AML/CFT threshold mentioned in the prompt is a **filter
applied downstream**, not at extraction time. The agent extracts every
UBO the document declares, even if the document mentions sub-25%
holders for completeness — that's information.
"""
from __future__ import annotations

from pydantic import BaseModel

from doc_extractor.schemas.base import Frontmatter


class UltimateBeneficialOwner(BaseModel):
    """Nested type for :class:`EntityOwnership`.

    The first nested-object schema in the project. ``markdown_io``'s YAML
    serialisation handles ``list[BaseModel]`` natively via ``model_dump`` →
    PyYAML; the round-trip via ``parse_md`` round-trips correctly because
    ``EntityOwnership`` is registered in ``markdown_io._SCHEMA_BY_DOC_TYPE``
    so Pydantic re-validates the nested dict back into a typed UBO instance.
    """

    name: str | None = ""
    dob: str | None = ""
    ownership_percentage: str | None = ""


class EntityOwnership(Frontmatter):
    entity_name: str | None = ""
    ultimate_beneficial_owners: list[UltimateBeneficialOwner] | None = None
