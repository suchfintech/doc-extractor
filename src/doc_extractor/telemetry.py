"""Cost / latency telemetry — structured, PII-free by signature design.

Writes one compact JSON line per extraction to
``<cwd>/telemetry/YYYY-MM-DD.jsonl`` (UTC). The file is durable; the standard
``logging`` stream is for human-readable progress and stays separate (FR38).

PII contract
-----------
``record_extraction``'s keyword-only signature is the canonical PII-exclusion
filter. It accepts ONLY operational metrics — ``source_key``, ``doc_type``,
``agent``, ``provider``, ``model``, ``cost_usd``, ``latency_ms``,
``retry_count``, ``success``, ``prompt_version``, ``extractor_version``.

Adding any extracted-content field (name, account number, MRZ, ...) is a
schema migration: it requires a new function with a new signature, an updated
PRD entry, and a re-review of every call-site. ``mypy --strict`` will reject
unknown kwargs at compile-time, so PII cannot accidentally leak into the
JSONL stream by passing it to this function — the type system is the
enforcement mechanism (NFR10). Story 8.2 adds an additional regex-based PII
leak test on top of this contract.

S3 upload
---------
If ``DOC_EXTRACTOR_TELEMETRY_S3_BUCKET`` is set, accumulated daily files are
uploaded once at process exit (atexit). Callers in batch mode can also call
``flush_telemetry_to_s3()`` explicitly to avoid waiting for shutdown. Uploads
are upserts (overwrite-on-write); concurrent writers writing the *same* day
on different machines need a per-host filename suffix — out of scope for
v1, deferred to a future story.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("doc_extractor.telemetry")

_TELEMETRY_DIR = Path("telemetry")
_S3_BUCKET_ENV = "DOC_EXTRACTOR_TELEMETRY_S3_BUCKET"
_S3_PREFIX = "telemetry"

# Files written this process — flushed by ``flush_telemetry_to_s3`` (atexit
# or caller-driven). A new entry is added the first time we touch each day.
_files_written_this_process: set[Path] = set()
_atexit_registered = False


def _utcnow() -> datetime:
    """Indirection so tests can pin the clock with ``monkeypatch.setattr``."""
    return datetime.now(UTC)


def _today_path() -> Path:
    return _TELEMETRY_DIR / f"{_utcnow().strftime('%Y-%m-%d')}.jsonl"


def _ensure_atexit_registered() -> None:
    global _atexit_registered
    if not _atexit_registered:
        atexit.register(flush_telemetry_to_s3)
        _atexit_registered = True


def record_extraction(
    *,
    source_key: str,
    doc_type: str,
    agent: str,
    provider: str,
    model: str,
    cost_usd: float,
    latency_ms: float,
    retry_count: int,
    success: bool,
    prompt_version: str,
    extractor_version: str,
) -> None:
    """Append a single telemetry record to today's JSONL file.

    Keyword-only by design: see module docstring for the PII-exclusion
    rationale.
    """
    _TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)

    record: dict[str, object] = {
        "timestamp": _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_key": source_key,
        "doc_type": doc_type,
        "agent": agent,
        "provider": provider,
        "model": model,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "retry_count": retry_count,
        "success": success,
        "prompt_version": prompt_version,
        "extractor_version": extractor_version,
    }

    path = _today_path()
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)

    _files_written_this_process.add(path)

    # Only register the atexit hook when S3 upload is actually wanted; saves
    # the at-exit work in dev / unit-test environments where the bucket env
    # is unset.
    if os.environ.get(_S3_BUCKET_ENV):
        _ensure_atexit_registered()


def flush_telemetry_to_s3() -> None:
    """Upload all telemetry files written this process to S3.

    Idempotent — safe to call from both the atexit hook AND an explicit
    batch end-of-run point. No-op when ``DOC_EXTRACTOR_TELEMETRY_S3_BUCKET``
    is unset. Errors are logged but never re-raised: telemetry must not
    crash the host process.
    """
    bucket = os.environ.get(_S3_BUCKET_ENV)
    if not bucket:
        return

    # Deferred import — keeps boto3 out of the import graph for callers that
    # never touch S3 (the common dev / test case).
    from doc_extractor import s3_io

    for path in sorted(_files_written_this_process):
        if not path.exists():
            continue
        try:
            body = path.read_bytes()
            s3_io._get_client().put_object(
                Bucket=bucket,
                Key=f"{_S3_PREFIX}/{path.name}",
                Body=body,
                ContentType="application/x-ndjson; charset=utf-8",
            )
        except Exception:  # noqa: BLE001 — telemetry must not crash the host process
            logger.exception("telemetry flush to s3://%s/%s failed", bucket, path.name)
