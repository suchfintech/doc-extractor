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
from doc_extractor.schemas.payment_receipt import PaymentReceipt

_FENCE = "---"

# `Frontmatter` itself has `extra="forbid"`, so subclass-specific keys would
# fail to validate against the base class. Dispatch on `doc_type` to the
# matching subclass; unknown / empty doc_types fall back to `Frontmatter`.
_SCHEMA_BY_DOC_TYPE: dict[str, type[Frontmatter]] = {
    "Passport": Passport,
    "PaymentReceipt": PaymentReceipt,
}


def _apply_deprecated_alias_dual_emit(
    cls: type[Frontmatter], data: dict[str, Any]
) -> None:
    """Story 7.1 / FR27 — populate both old and new alias fields on render.

    For each ``(old_name, new_name)`` pair declared on
    ``cls._deprecated_aliases``: if either side has a non-empty value but
    the other is empty, copy the value across. If both are present, leave
    them — render keeps both even when they disagree (the agent supplied
    them; reconciliation is the consumer's call).
    """
    aliases: dict[str, str] = getattr(cls, "_deprecated_aliases", {}) or {}
    for old_name, new_name in aliases.items():
        old_value = data.get(old_name)
        new_value = data.get(new_name)
        if new_value and not old_value:
            data[old_name] = new_value
        elif old_value and not new_value:
            data[new_name] = old_value


def render_to_md(frontmatter: Frontmatter) -> str:
    data = frontmatter.model_dump()
    _apply_deprecated_alias_dual_emit(type(frontmatter), data)
    body = yaml.safe_dump(
        data,
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

    # Story 7.1 / FR27 — read-side compat. Consumers still emitting only the
    # deprecated alias get their value copied into the new field name before
    # validation. When both are populated and disagree, the new field wins
    # (the canonical source); we only fill in when new is missing/empty.
    aliases: dict[str, str] = getattr(schema_class, "_deprecated_aliases", {}) or {}
    for old_name, new_name in aliases.items():
        old_value = data.get(old_name)
        if old_value and not data.get(new_name):
            data[new_name] = old_value

    return schema_class.model_validate(data)
