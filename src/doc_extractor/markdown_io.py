"""Render Pydantic frontmatter to YAML-frontmatter Markdown and parse it back.

The output shape is `---\\n<yaml>\\n---\\n\\n` (leading fence, YAML body,
closing fence, one blank line). `yaml.safe_dump(allow_unicode=True,
sort_keys=False)` matches the byte-stable contract that
`tests/unit/test_schema_byte_stability.py` snapshots, so anything written
through `render_to_md` and re-rendered after `parse_md` is byte-identical.

Mask preservation is verbatim: pre-masked strings such as
``"6217 **** **** 0083"`` and CJK characters round-trip without escaping or
normalisation (FR25, FR26).
"""
from __future__ import annotations

from typing import Any

import yaml  # type: ignore[import-untyped]  # dev-dep `types-PyYAML` not yet wired

from doc_extractor.schemas import Frontmatter, Passport

_FENCE = "---"

# `Frontmatter` itself has `extra="forbid"`, so Passport-specific keys would
# fail to validate against the base class. Dispatch on `doc_type` to the
# matching subclass; unknown / empty doc_types fall back to `Frontmatter`.
_SCHEMA_BY_DOC_TYPE: dict[str, type[Frontmatter]] = {
    "Passport": Passport,
}


def render_to_md(frontmatter: Frontmatter) -> str:
    body = yaml.safe_dump(
        frontmatter.model_dump(),
        allow_unicode=True,
        sort_keys=False,
    )
    return f"{_FENCE}\n{body}{_FENCE}\n\n"


def parse_md(text: str) -> Frontmatter:
    # Split exactly twice so any `---` inside multi-line YAML strings stays
    # in the body rather than being treated as a fence.
    parts = text.split(_FENCE, 2)
    if len(parts) < 3:
        raise ValueError("missing YAML frontmatter fences (expected `---` ... `---`)")

    leading, yaml_body, _trailing = parts
    if leading.strip():
        raise ValueError("unexpected content before opening `---` fence")

    data: Any = yaml.safe_load(yaml_body)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"frontmatter must be a mapping, got {type(data).__name__}")

    schema_class = _SCHEMA_BY_DOC_TYPE.get(str(data.get("doc_type", "")), Frontmatter)
    return schema_class.model_validate(data)
