"""Frontmatter base — fields shared by every doc_type schema.

Convention: empty-string-not-null. Every field is `str | None` defaulting to
`""`; a `field_validator` coerces incoming `None` → `""` so YAML dumps remain
byte-stable (PyYAML renders `None` as `null`, which would break the
`tests/unit/test_schema_byte_stability.py` snapshot).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


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
    def _none_to_empty(cls, v: Any) -> Any:
        return "" if v is None else v
