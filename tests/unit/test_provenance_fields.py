"""Story 7.5 — Frontmatter provenance fields auto-fill + pipeline population.

The five provenance fields (``extractor_version``, ``extraction_provider``,
``extraction_model``, ``extraction_timestamp``, ``prompt_version``) must
land on every emitted ``.md``. ``markdown_io.render_to_md`` owns the two
deterministic ones (extractor_version, timestamp); the orchestrator owns
the other three. Caller-set values always win so deterministic snapshots
can pin any of them.
"""

from __future__ import annotations

import re

import yaml  # type: ignore[import-untyped]

import doc_extractor
from doc_extractor import markdown_io
from doc_extractor.markdown_io import parse_md, render_to_md
from doc_extractor.schemas.ids import Passport

ISO_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _yaml_body(rendered: str) -> dict[str, object]:
    parts = rendered.split("---", 2)
    return yaml.safe_load(parts[1]) or {}


def _passport(**overrides: object) -> Passport:
    base: dict[str, object] = {
        "doc_type": "Passport",
        "passport_number": "X9988776",
        "nationality": "NZL",
        "doc_number": "X9988776",
        "dob": "1985-09-12",
        "issue_date": "2022-09-12",
        "expiry_date": "2032-09-11",
        "sex": "F",
        "mrz_line_1": "P<NZLDOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
        "mrz_line_2": "X9988776<NZL8509121F3209118<<<<<<<<<<<<<<00",
        "name_latin": "DOE, JANE",
        "jurisdiction": "NZL",
    }
    base.update(overrides)
    return Passport(**base)  # type: ignore[arg-type]


def test_render_autofills_extractor_version_and_timestamp() -> None:
    receipt_like = _passport()
    body = _yaml_body(render_to_md(receipt_like))

    assert body["extractor_version"] == doc_extractor.__version__
    timestamp = body["extraction_timestamp"]
    assert isinstance(timestamp, str)
    assert ISO_REGEX.match(timestamp), (
        f"timestamp {timestamp!r} must match {ISO_REGEX.pattern}"
    )

    # Pipeline-owned provenance fields stay empty when no orchestrator
    # populated them — render does NOT invent values for these.
    assert body["extraction_provider"] == ""
    assert body["extraction_model"] == ""
    assert body["prompt_version"] == ""


def test_render_preserves_caller_supplied_provenance() -> None:
    pinned = _passport(
        extractor_version="9.9.9",
        extraction_timestamp="2025-01-01T00:00:00Z",
        extraction_provider="anthropic",
        extraction_model="claude-test-pinned",
        prompt_version="0.1.0",
    )
    body = _yaml_body(render_to_md(pinned))

    assert body["extractor_version"] == "9.9.9"
    assert body["extraction_timestamp"] == "2025-01-01T00:00:00Z"
    assert body["extraction_provider"] == "anthropic"
    assert body["extraction_model"] == "claude-test-pinned"
    assert body["prompt_version"] == "0.1.0"


def test_round_trip_preserves_all_five_provenance_fields() -> None:
    pinned = _passport(
        extractor_version="0.1.0",
        extraction_timestamp="2026-05-03T12:34:56Z",
        extraction_provider="anthropic",
        extraction_model="claude-sonnet-4-6-20260101",
        prompt_version="0.1.0",
    )
    rendered = render_to_md(pinned)
    parsed = parse_md(rendered)

    assert isinstance(parsed, Passport)
    assert parsed.extractor_version == "0.1.0"
    assert parsed.extraction_timestamp == "2026-05-03T12:34:56Z"
    assert parsed.extraction_provider == "anthropic"
    assert parsed.extraction_model == "claude-sonnet-4-6-20260101"
    assert parsed.prompt_version == "0.1.0"


def test_render_is_byte_stable_under_pinned_clock(monkeypatch: object) -> None:
    """No-clock-leak: pin the clock, render twice, assert byte-equal."""
    fixed = "2026-05-03T12:00:00Z"
    monkeypatch.setattr(markdown_io, "_now_iso8601", lambda: fixed)  # type: ignore[attr-defined]

    receipt_like = _passport()
    first = render_to_md(receipt_like)
    second = render_to_md(receipt_like)

    assert first == second
    assert fixed in first  # PyYAML may quote the timestamp; just check it landed.
