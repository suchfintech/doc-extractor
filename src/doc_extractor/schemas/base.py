"""Frontmatter base — fields shared by every doc_type schema.

Convention: empty-string-not-null **for string fields**. Every string field is
`str | None` defaulting to `""`; a `field_validator` coerces incoming `None`
→ `""` so YAML dumps remain byte-stable (PyYAML renders `None` as `null`,
which would break the `tests/unit/test_schema_byte_stability.py` snapshot).

For non-string fields (e.g. `list[str]`, `list[BaseModel]` introduced in
Story 5.3's CompanyExtract / EntityOwnership), `None` is the "not extracted"
sentinel and `[]` is the "explicitly empty" sentinel — both meaningful and
distinct. The validator preserves `None` for those cases.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator


def _is_string_field(annotation: Any) -> bool:
    """Return True iff the annotation is `str` or `str | None` (or its alias)."""
    if annotation is str:
        return True
    # Handle `str | None`, `Optional[str]`, etc. — the args contain (str, NoneType).
    args = getattr(annotation, "__args__", ())
    return bool(args) and all(a is str or a is type(None) for a in args)


def coerce_none_to_empty_for_string_fields(
    cls: type[BaseModel], v: Any, info: ValidationInfo
) -> Any:
    """Type-aware ``None → ""`` validator body, shared with non-Frontmatter
    schemas (e.g. nested ``UltimateBeneficialOwner``).

    Non-string fields (list[...], nested BaseModel) keep ``None`` as the
    explicit "not extracted" sentinel; only str / str | None fields collapse
    to the empty-string sentinel that keeps YAML output free of ``null``
    literals (required for ``test_schema_byte_stability``).
    """
    if v is not None:
        return v
    field = cls.model_fields.get(info.field_name or "")
    if field is None or _is_string_field(field.annotation):
        return ""
    return v


class Frontmatter(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )

    extractor_version: str | None = ""
    extraction_provider: str | None = ""
    extraction_model: str | None = ""
    extraction_timestamp: str | None = ""
    prompt_version: str | None = ""
    doc_type: str | None = ""
    doc_subtype: str | None = ""
    jurisdiction: str | None = ""
    name_latin: str | None = ""
    name_cjk: str | None = ""

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any, info: ValidationInfo) -> Any:
        return coerce_none_to_empty_for_string_fields(cls, v, info)
