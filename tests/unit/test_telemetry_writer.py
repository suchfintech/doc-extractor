"""Unit tests for the cost-telemetry JSONL writer (Story 8.1).

Covers: directory creation, append-one-line per call, valid-JSON shape,
auto-generated UTC timestamp with `Z` suffix, UTC-date filename, and the
S3 upload hook (skipped when env var unset, called when set).

The tests use ``monkeypatch.chdir(tmp_path)`` so each test has an isolated
``./telemetry/`` directory, and reset the module-level state between runs.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from doc_extractor import telemetry


@pytest.fixture(autouse=True)
def _reset_module_state() -> None:
    """Each test starts with no accumulated state and no atexit registration."""
    telemetry._files_written_this_process.clear()
    telemetry._atexit_registered = False


def _record_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_key": "documents/transactions/12345/abc.jpeg",
        "doc_type": "Passport",
        "agent": "passport",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6-20260101",
        "cost_usd": 0.0123,
        "latency_ms": 1234.5,
        "retry_count": 0,
        "success": True,
        "prompt_version": "0.1.0",
        "extractor_version": "0.1.0",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Directory + file behaviour
# ---------------------------------------------------------------------------


def test_record_extraction_creates_telemetry_directory_if_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(telemetry._S3_BUCKET_ENV, raising=False)

    telemetry_dir = tmp_path / "telemetry"
    assert not telemetry_dir.exists()

    telemetry.record_extraction(**_record_kwargs())

    assert telemetry_dir.is_dir()


def test_record_extraction_appends_exactly_one_line_per_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(telemetry._S3_BUCKET_ENV, raising=False)

    telemetry.record_extraction(**_record_kwargs())
    telemetry.record_extraction(**_record_kwargs(success=False, retry_count=2))
    telemetry.record_extraction(**_record_kwargs(doc_type="PaymentReceipt"))

    files = list((tmp_path / "telemetry").glob("*.jsonl"))
    assert len(files) == 1, "all three writes should land in today's single file"
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    # Each line is its own JSON object, not a multiline blob.
    for line in lines:
        json.loads(line)


# ---------------------------------------------------------------------------
# JSON shape + mandatory fields
# ---------------------------------------------------------------------------


def test_line_is_valid_json_with_all_mandatory_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(telemetry._S3_BUCKET_ENV, raising=False)

    telemetry.record_extraction(**_record_kwargs())

    file = next((tmp_path / "telemetry").glob("*.jsonl"))
    record = json.loads(file.read_text(encoding="utf-8").splitlines()[0])

    assert set(record.keys()) == {
        "timestamp",
        "source_key",
        "doc_type",
        "agent",
        "provider",
        "model",
        "cost_usd",
        "latency_ms",
        "retry_count",
        "success",
        "prompt_version",
        "extractor_version",
    }
    assert record["source_key"] == "documents/transactions/12345/abc.jpeg"
    assert record["cost_usd"] == 0.0123
    assert record["latency_ms"] == 1234.5
    assert record["retry_count"] == 0
    assert record["success"] is True


def test_timestamp_is_iso8601_utc_with_z_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(telemetry._S3_BUCKET_ENV, raising=False)

    telemetry.record_extraction(**_record_kwargs())

    file = next((tmp_path / "telemetry").glob("*.jsonl"))
    record = json.loads(file.read_text(encoding="utf-8"))

    assert record["timestamp"].endswith("Z")
    # Round-trip through strptime to verify the exact YYYY-MM-DDTHH:MM:SSZ shape.
    parsed = datetime.strptime(record["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
    assert parsed.year >= 2025


# ---------------------------------------------------------------------------
# UTC-date filename
# ---------------------------------------------------------------------------


def test_filename_uses_utc_date_from_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(telemetry._S3_BUCKET_ENV, raising=False)

    fixed = datetime(2026, 5, 3, 12, 30, 45, tzinfo=UTC)
    monkeypatch.setattr(telemetry, "_utcnow", lambda: fixed)

    telemetry.record_extraction(**_record_kwargs())

    expected = tmp_path / "telemetry" / "2026-05-03.jsonl"
    assert expected.exists()
    record = json.loads(expected.read_text(encoding="utf-8"))
    assert record["timestamp"] == "2026-05-03T12:30:45Z"


# ---------------------------------------------------------------------------
# S3 upload hook
# ---------------------------------------------------------------------------


class _CapturingS3Client:
    """Minimal stand-in for boto3.client('s3') — captures put_object calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ETag": "fake"}


def test_s3_upload_not_called_when_env_var_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(telemetry._S3_BUCKET_ENV, raising=False)

    captured = _CapturingS3Client()
    from doc_extractor import s3_io

    monkeypatch.setattr(s3_io, "_get_client", lambda: captured)

    telemetry.record_extraction(**_record_kwargs())
    telemetry.flush_telemetry_to_s3()

    assert captured.calls == []
    # And the atexit hook was never registered (no env var means no S3 work).
    assert telemetry._atexit_registered is False


def test_s3_upload_called_with_correct_args_when_env_var_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(telemetry._S3_BUCKET_ENV, "my-tel-bucket")

    fixed = datetime(2026, 5, 3, 12, 30, 45, tzinfo=UTC)
    monkeypatch.setattr(telemetry, "_utcnow", lambda: fixed)

    captured = _CapturingS3Client()
    from doc_extractor import s3_io

    monkeypatch.setattr(s3_io, "_get_client", lambda: captured)

    telemetry.record_extraction(**_record_kwargs())
    telemetry.flush_telemetry_to_s3()

    assert len(captured.calls) == 1
    call = captured.calls[0]
    assert call["Bucket"] == "my-tel-bucket"
    assert call["Key"] == "telemetry/2026-05-03.jsonl"
    assert call["ContentType"] == "application/x-ndjson; charset=utf-8"
    # Body matches the local file (the JSONL line we just wrote).
    local_file = tmp_path / "telemetry" / "2026-05-03.jsonl"
    assert call["Body"] == local_file.read_bytes()


def test_flush_telemetry_to_s3_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling flush twice (e.g. CLI explicit + atexit) re-uploads — no crash,
    no duplicate accumulation."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(telemetry._S3_BUCKET_ENV, "my-tel-bucket")

    captured = _CapturingS3Client()
    from doc_extractor import s3_io

    monkeypatch.setattr(s3_io, "_get_client", lambda: captured)

    telemetry.record_extraction(**_record_kwargs())
    telemetry.flush_telemetry_to_s3()
    telemetry.flush_telemetry_to_s3()

    # Two flushes → two uploads of the same body, both addressing the same key.
    assert len(captured.calls) == 2
    assert captured.calls[0]["Key"] == captured.calls[1]["Key"]


def test_flush_swallows_s3_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Telemetry must never crash the host process — S3 errors are logged."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(telemetry._S3_BUCKET_ENV, "my-tel-bucket")

    class _BoomClient:
        def put_object(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("simulated S3 outage")

    from doc_extractor import s3_io

    monkeypatch.setattr(s3_io, "_get_client", lambda: _BoomClient())

    telemetry.record_extraction(**_record_kwargs())
    # Must not raise.
    telemetry.flush_telemetry_to_s3()
