"""Body-parse repair pipeline for PaymentReceipt analyses.

Reads an existing ``.md`` analysis from S3, extracts whatever ``parse_chinese``
or ``parse_nz`` can recover from the body, and writes back a *frontmatter-only*
update. The body markdown after the closing ``---`` fence is preserved
**byte-identical** so anything the LLM emitted (prose, tables, images) survives
intact.

Dispatch order:
1. ``parse_chinese`` — if any PaymentReceipt-specific field comes back
   non-empty, use it.
2. Otherwise ``parse_nz`` — raises ``ValueError`` on miss, which we translate
   to ``BodyParseUnmatchedError``.
3. Otherwise both missed: raise ``BodyParseUnmatchedError``.

Merge semantics: parsed non-empty fields overwrite the existing frontmatter;
parsed empty-string fields preserve whatever was there before.
"""
from __future__ import annotations

from typing import Any

import yaml  # type: ignore[import-untyped]  # types-PyYAML not yet wired

from doc_extractor import s3_io
from doc_extractor.body_parse.chinese_labels import parse_chinese
from doc_extractor.body_parse.nz_narrative import parse_nz
from doc_extractor.exceptions import BodyParseUnmatchedError
from doc_extractor.schemas import PaymentReceipt

_OPENING_FENCE = "---\n"
_CLOSING_FENCE = "\n---\n"

# The 11 PaymentReceipt-specific fields (everything beyond the Frontmatter
# base). If all of these are empty after a parse, the parser missed.
_PR_FIELDS: tuple[str, ...] = (
    "receipt_amount",
    "receipt_currency",
    "receipt_time",
    "receipt_debit_account_name",
    "receipt_debit_account_number",
    "receipt_debit_bank_name",
    "receipt_credit_account_name",
    "receipt_credit_account_number",
    "receipt_credit_bank_name",
    "receipt_reference",
    "receipt_payment_app",
)


def _has_any_pr_field(receipt: PaymentReceipt) -> bool:
    return any(getattr(receipt, name) for name in _PR_FIELDS)


def body_parse(md_text: str) -> PaymentReceipt:
    """Try CN parser first, fall back to NZ; raise if neither matches."""
    cn = parse_chinese(md_text)
    if _has_any_pr_field(cn):
        return cn

    try:
        return parse_nz(md_text)
    except ValueError as exc:
        raise BodyParseUnmatchedError(
            "Body matched neither CN-label format nor NZ-narrative format"
        ) from exc


def _split_frontmatter_and_body(md_text: str) -> tuple[str, str]:
    """Return ``(yaml_block, body_after_closing_fence)``.

    ``yaml_block`` is the content between the two ``---\\n`` fences, trailing
    newline included so the round-trip with ``yaml.safe_dump`` works without
    fiddling. ``body_after_closing_fence`` is everything after the closing
    fence — typically begins with ``\\n`` so a re-render preserves the blank
    line that ``markdown_io.render_to_md`` produces.
    """
    if not md_text.startswith(_OPENING_FENCE):
        raise ValueError("analysis markdown must start with `---\\n` opening fence")
    rest = md_text[len(_OPENING_FENCE):]
    closing_idx = rest.find(_CLOSING_FENCE)
    if closing_idx == -1:
        raise ValueError("analysis markdown missing closing `\\n---\\n` fence")
    yaml_block = rest[: closing_idx + 1]  # include the trailing newline
    body_after = rest[closing_idx + len(_CLOSING_FENCE):]
    return yaml_block, body_after


def _merge_non_empty(existing: dict[str, Any], parsed: PaymentReceipt) -> dict[str, Any]:
    merged = dict(existing)
    for field, value in parsed.model_dump().items():
        if value:
            merged[field] = value
    return merged


def _reassemble(merged: dict[str, Any], body_after_fence: str) -> str:
    yaml_block = yaml.safe_dump(merged, allow_unicode=True, sort_keys=False)
    return f"{_OPENING_FENCE}{yaml_block}---\n{body_after_fence}"


async def run(source_key: str) -> dict[str, Any]:
    """Body-parse repair: read S3 → parse → frontmatter-only update → write S3.

    Returns a small status dict for telemetry — caller-friendly, no PII.
    """
    raw_bytes = s3_io.read_analysis(source_key)
    raw_md = raw_bytes.decode("utf-8")

    yaml_block, body_after = _split_frontmatter_and_body(raw_md)
    existing = yaml.safe_load(yaml_block) or {}
    if not isinstance(existing, dict):
        raise ValueError(
            f"frontmatter must be a YAML mapping; got {type(existing).__name__}"
        )

    parsed = body_parse(raw_md)

    fields_updated = sorted(
        name for name in _PR_FIELDS if getattr(parsed, name) and existing.get(name, "") != getattr(parsed, name)
    )

    merged = _merge_non_empty(existing, parsed)
    new_md = _reassemble(merged, body_after)
    s3_io.write_analysis(source_key, new_md)

    return {
        "key": source_key,
        "fields_updated": fields_updated,
        "body_bytes_preserved": True,
    }
