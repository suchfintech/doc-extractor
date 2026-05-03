"""Disagreement-queue writer (Decision 1, FR4 — initial form).

When the verifier flags a specialist's claim as ``fail`` (any per-field
``disagree``), or when other documented failure modes occur, the pipeline
writes a forensic JSON entry to
``s3://golden-mountain-analysis/disagreements/<source_key>.json``. Story 6.1
will extend this entry to carry the raw model responses; for 3.9 we record
the typed Pydantic dump plus the audit verdict.

**Stable identity**: ``source_key`` is the filename. Re-running extraction
against the same ``source_key`` overwrites the same entry — Story 6.4 will
validate durability under retry.

**Status enum** (per Story 6.1 spec; 3.9 ships the subset):

- ``"disagreement"`` — verifier returned ``overall == "fail"``.
- ``"validation_failure"`` — Pydantic rejected the specialist's structured output.
- ``"rate_limited"`` — provider returned 429 after retry budget exhausted.
- ``"provider_unavailable"`` — provider 5xx / network error / model retired.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from doc_extractor import s3_io
from doc_extractor.schemas.verifier import VerifierAudit

DisagreementStatus = Literal[
    "disagreement",
    "validation_failure",
    "rate_limited",
    "provider_unavailable",
]


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
) -> str:
    """Write a disagreement-queue entry and return the bucket key written.

    The entry is a single JSON object with six top-level fields:

    - ``source_key`` — the original document key.
    - ``primary`` — ``primary.model_dump()`` or ``null`` (Story 3.8 — the
      validation-failure path has no valid Pydantic instance to dump).
    - ``verifier`` — ``verifier.model_dump()`` or ``null`` (validation-failure
      / provider-unavailable paths can't produce a verifier audit).
    - ``agreement_status`` — one of the documented status strings.
    - ``timestamp`` — ISO 8601 UTC with ``Z`` suffix, generated at write time.
    - ``extractor_version`` — caller-supplied; the pipeline passes the
      package ``__version__`` to keep replay deterministic.
    """
    entry: dict[str, object] = {
        "source_key": source_key,
        "primary": primary.model_dump() if primary is not None else None,
        "verifier": verifier.model_dump() if verifier is not None else None,
        "agreement_status": status,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extractor_version": extractor_version,
    }
    body = json.dumps(entry, ensure_ascii=False, indent=2)

    key = _disagreement_key_for(source_key)
    s3_io.write_disagreement(key, body)
    return key
