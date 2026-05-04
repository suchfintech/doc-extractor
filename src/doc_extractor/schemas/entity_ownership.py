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

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from doc_extractor.schemas.base import Frontmatter, coerce_none_to_empty_for_string_fields


class UltimateBeneficialOwner(BaseModel):
    """Nested type for :class:`EntityOwnership`.

    The first nested-object schema in the project. ``markdown_io``'s YAML
    serialisation handles ``list[BaseModel]`` natively via ``model_dump`` →
    PyYAML; the round-trip via ``parse_md`` round-trips correctly because
    ``EntityOwnership`` is registered in ``markdown_io._SCHEMA_BY_DOC_TYPE``
    so Pydantic re-validates the nested dict back into a typed UBO instance.

    P16 (code review Round 1) — UBO does NOT inherit from ``Frontmatter``
    (would add 10 unrelated provenance fields), so it has to bring its own
    ``extra="forbid"`` and the type-aware ``None → ""`` validator.
    Without these the byte-stability invariant breaks: ``UBO(name=None)``
    used to render as ``name: null`` in YAML and silently accept any
    spurious extra key.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = ""
    dob: str | None = ""
    ownership_percentage: str | None = ""

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any, info: ValidationInfo) -> Any:
        return coerce_none_to_empty_for_string_fields(cls, v, info)


class EntityOwnership(Frontmatter):
    entity_name: str | None = ""
    ultimate_beneficial_owners: list[UltimateBeneficialOwner] | None = None
