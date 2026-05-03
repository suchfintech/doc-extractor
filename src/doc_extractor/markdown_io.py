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

from datetime import UTC, datetime
from typing import Any

import yaml  # type: ignore[import-untyped]  # dev-dep `types-PyYAML` not yet wired

from doc_extractor.schemas import Frontmatter, Passport
from doc_extractor.schemas.company_extract import CompanyExtract
from doc_extractor.schemas.entity_ownership import EntityOwnership
from doc_extractor.schemas.payment_receipt import PaymentReceipt

_FENCE = "---"


def _now_iso8601() -> str:
    """Return the current UTC time as ISO 8601 with the ``Z`` suffix.

    Module-level hook so tests can monkeypatch a fixed clock without
    poking at ``datetime`` itself.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _autofill_provenance(data: dict[str, Any]) -> None:
    """Populate ``extractor_version`` and ``extraction_timestamp`` if empty.

    Caller-set values win — pre-populated provenance fields render verbatim
    so deterministic snapshots can pin a fixed timestamp / version. The
    other three provenance fields (``extraction_provider``,
    ``extraction_model``, ``prompt_version``) belong to the pipeline
    orchestrator (Story 7.5 §3) — this helper does NOT touch them.
    """
    if not data.get("extractor_version"):
        # Lazy import to dodge the ``doc_extractor.__init__`` circular path
        # — markdown_io is imported during package init via the schemas
        # subtree.
        from doc_extractor import __version__ as _ext_v

        data["extractor_version"] = _ext_v
    if not data.get("extraction_timestamp"):
        data["extraction_timestamp"] = _now_iso8601()

# `Frontmatter` itself has `extra="forbid"`, so subclass-specific keys would
# fail to validate against the base class. Dispatch on `doc_type` to the
# matching subclass; unknown / empty doc_types fall back to `Frontmatter`.
_SCHEMA_BY_DOC_TYPE: dict[str, type[Frontmatter]] = {
    "Passport": Passport,
    "PaymentReceipt": PaymentReceipt,
    # Story 5.3 — entity-document schemas need explicit dispatch so parse_md
    # round-trips list[str] (directors / shareholders) and list[BaseModel]
    # (ultimate_beneficial_owners) cleanly. Frontmatter base has
    # extra="forbid" which would reject these subclass-specific keys on
    # fallback, breaking the round-trip contract.
    "CompanyExtract": CompanyExtract,
    "EntityOwnership": EntityOwnership,
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
    """Render a Frontmatter (or subclass) to YAML-frontmatter Markdown.

    Story 7.5 — auto-fills ``extractor_version`` (from
    ``doc_extractor.__version__``) and ``extraction_timestamp`` (current
    UTC, ISO 8601 with ``Z`` suffix) when those fields are empty. Caller-
    supplied values win, so deterministic snapshots can pin both. The
    pipeline-supplied provenance fields (``extraction_provider``,
    ``extraction_model``, ``prompt_version``) are populated by
    ``pipelines.vision_path`` before render.
    """
    data = frontmatter.model_dump()
    _autofill_provenance(data)
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
