"""Disagreement-queue writer (Decision 1, FR4 — full forensic payload).

When the verifier flags a specialist's claim as ``fail`` (any per-field
``disagree``), or when other documented failure modes occur, the pipeline
writes a forensic JSON entry to
``s3://golden-mountain-analysis/disagreements/<source_key>.json``.

**Stable identity**: ``source_key`` is the filename. Re-running extraction
against the same ``source_key`` overwrites the same entry — Story 6.4 will
validate durability under retry.

**Status enum**:

- ``"disagreement"`` — verifier returned ``overall == "fail"``.
- ``"validation_failure"`` — Pydantic rejected the specialist's structured output.
- ``"rate_limited"`` — provider returned 429 after retry budget exhausted.
- ``"provider_unavailable"`` — provider 5xx / network error / model retired.

Story 3.9 shipped the typed-instance forensic record; **Story 6.1 inlines the
raw model responses** (primary + verifier) plus per-call metadata so
downstream review surfaces have everything needed to debug an extraction
without replaying the model. The raw fields default to ``None`` so callers
that pre-date 6.1 (or paths where capture isn't possible — e.g. an
exception thrown before arun completed) round-trip cleanly.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from doc_extractor import s3_io
from doc_extractor.schemas.verifier import VerifierAudit

DisagreementStatus = Literal[
    "disagreement",
    "validation_failure",
    "rate_limited",
    "provider_unavailable",
]

# Story 6.1 — raw payload shape. The dict carries provider/model/latency_ms/
# cost_usd; widening to ``Any`` for the dict values keeps the helper out of
# the typing thicket of partial Agno surfaces while still type-checking.
RawResponse = tuple[str, dict[str, Any]]


def _disagreement_key_for(source_key: str) -> str:
    """Stable analysis-bucket key for a disagreement entry."""
    return f"disagreements/{source_key}.json"


def record_disagreement(
    *,
    source_key: str,
    primary: BaseModel | None,
    verifier: VerifierAudit | None,
    status: DisagreementStatus,
    extractor_version: str | None = None,
    primary_raw: RawResponse | None = None,
    verifier_raw: RawResponse | None = None,
) -> str:
    """Write a disagreement-queue entry and return the bucket key written.

    The entry is a single JSON object with the following top-level fields:

    - ``source_key`` — the original document key.
    - ``primary`` — ``primary.model_dump()`` or ``null`` (Story 3.8 — the
      validation-failure path has no valid Pydantic instance to dump).
    - ``verifier`` — ``verifier.model_dump()`` or ``null`` (validation-failure
      / provider-unavailable paths can't produce a verifier audit).
    - ``agreement_status`` — one of the documented status strings.
    - ``timestamp`` — ISO 8601 UTC with ``Z`` suffix, generated at write time.
    - ``extractor_version`` — caller-supplied; the pipeline passes the
      package ``__version__`` to keep replay deterministic.
    - ``primary_raw_response_text`` — Story 6.1, the raw model output verbatim
      (CJK preserved, no normalisation), or ``null`` when capture isn't
      available.
    - ``primary_raw_response_metadata`` — ``{provider, model, latency_ms,
      cost_usd}``, or ``null`` paired with ``primary_raw_response_text``.
    - ``verifier_raw_response_text`` / ``verifier_raw_response_metadata`` —
      same shape for the verifier call. ``null`` when no verifier ran (e.g.
      validation_failure path).
    """
    primary_raw_text, primary_raw_metadata = (
        primary_raw if primary_raw is not None else (None, None)
    )
    verifier_raw_text, verifier_raw_metadata = (
        verifier_raw if verifier_raw is not None else (None, None)
    )

    entry: dict[str, object] = {
        "source_key": source_key,
        "primary": primary.model_dump() if primary is not None else None,
        "verifier": verifier.model_dump() if verifier is not None else None,
        "agreement_status": status,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extractor_version": extractor_version,
        "primary_raw_response_text": primary_raw_text,
        "primary_raw_response_metadata": primary_raw_metadata,
        "verifier_raw_response_text": verifier_raw_text,
        "verifier_raw_response_metadata": verifier_raw_metadata,
    }
    body = json.dumps(entry, ensure_ascii=False, indent=2)

    key = _disagreement_key_for(source_key)
    s3_io.write_disagreement(key, body)
    return key
