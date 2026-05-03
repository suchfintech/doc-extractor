"""Integration tests for the disagreement-queue writer (Story 3.9).

The disagreement queue is a JSON-per-document forensic record on the
analysis bucket. These tests pin the JSON shape (six top-level fields), the
S3 key prefix (``disagreements/<source_key>.json``), the stable-identity
contract (same source_key → same path → overwrite), and the no-verifier
fallback.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from doc_extractor import s3_io
from doc_extractor.disagreement import record_disagreement
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.verifier import VerifierAudit


def _payment_receipt() -> PaymentReceipt:
    return PaymentReceipt(
        doc_type="PaymentReceipt",
        jurisdiction="CN",
        receipt_amount="15000.00",
        receipt_currency="CNY",
        receipt_debit_account_name="张三",
        receipt_debit_account_number="6217 **** **** 0083",
        receipt_credit_account_name="李四",
    )


def _failing_audit() -> VerifierAudit:
    """A VerifierAudit whose `overall` derives to 'fail'."""
    return VerifierAudit(
        field_audits={
            "receipt_debit_account_name": "agree",
            "receipt_credit_account_name": "disagree",  # ← drives overall=fail
            "receipt_debit_account_number": "abstain",
        },
        notes="image shows credit name X but specialist claimed Y",
    )


@pytest.fixture
def s3_writes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture (key, body) tuples for write_disagreement calls.

    Stable identity is the contract: re-running with the same source_key
    must overwrite the same key. Tracking calls in order also lets us
    assert the count.
    """
    calls: list[tuple[str, str]] = []

    def fake_write(key: str, body: str | bytes) -> None:
        text = body.decode("utf-8") if isinstance(body, bytes) else body
        calls.append((key, text))

    monkeypatch.setattr(s3_io, "write_disagreement", fake_write)
    return calls


# ---------------------------------------------------------------------------
# JSON shape + key prefix
# ---------------------------------------------------------------------------


def test_record_disagreement_writes_to_disagreements_prefix(
    s3_writes: list[tuple[str, str]],
) -> None:
    source_key = "documents/transactions/12345/abc.jpeg"
    returned_key = record_disagreement(
        source_key=source_key,
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
        extractor_version="0.1.0",
    )

    assert len(s3_writes) == 1
    written_key, _ = s3_writes[0]
    assert written_key == f"disagreements/{source_key}.json"
    assert returned_key == written_key


def test_disagreement_json_carries_all_six_top_level_fields(
    s3_writes: list[tuple[str, str]],
) -> None:
    record_disagreement(
        source_key="doc-001.jpeg",
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
        extractor_version="0.1.0",
    )

    _, body = s3_writes[0]
    entry: dict[str, Any] = json.loads(body)

    assert set(entry.keys()) == {
        "source_key",
        "primary",
        "verifier",
        "agreement_status",
        "timestamp",
        "extractor_version",
    }
    assert entry["source_key"] == "doc-001.jpeg"
    assert entry["agreement_status"] == "disagreement"
    assert entry["extractor_version"] == "0.1.0"
    # primary dump is the full PaymentReceipt structure.
    assert entry["primary"]["receipt_debit_account_name"] == "张三"
    # verifier dump carries the VerifierAudit's pinned overall.
    assert entry["verifier"]["overall"] == "fail"
    assert entry["verifier"]["field_audits"]["receipt_credit_account_name"] == "disagree"
    # ISO 8601 UTC with Z suffix.
    assert entry["timestamp"].endswith("Z")
    assert "T" in entry["timestamp"]


def test_disagreement_json_preserves_cjk_verbatim(
    s3_writes: list[tuple[str, str]],
) -> None:
    """ensure_ascii=False so 张三 / 李四 stay raw, not \\u escaped."""
    record_disagreement(
        source_key="doc-cn.jpeg",
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
    )

    _, body = s3_writes[0]
    assert "张三" in body
    assert "李四" in body
    assert "\\u" not in body


# ---------------------------------------------------------------------------
# Stable identity — same source_key → same path → overwrite
# ---------------------------------------------------------------------------


def test_repeat_calls_with_same_source_key_write_to_same_path(
    s3_writes: list[tuple[str, str]],
) -> None:
    source_key = "documents/transactions/9999/xyz.jpeg"
    record_disagreement(
        source_key=source_key,
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
    )
    record_disagreement(
        source_key=source_key,
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
    )

    assert len(s3_writes) == 2
    assert s3_writes[0][0] == s3_writes[1][0]
    assert s3_writes[0][0] == f"disagreements/{source_key}.json"


def test_different_source_keys_write_to_different_paths(
    s3_writes: list[tuple[str, str]],
) -> None:
    record_disagreement(
        source_key="a.jpeg",
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
    )
    record_disagreement(
        source_key="b.jpeg",
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
    )

    keys = {entry[0] for entry in s3_writes}
    assert keys == {"disagreements/a.jpeg.json", "disagreements/b.jpeg.json"}


# ---------------------------------------------------------------------------
# No-verifier fallback (validation-failure / provider-unavailable paths)
# ---------------------------------------------------------------------------


def test_record_disagreement_with_no_verifier_writes_null(
    s3_writes: list[tuple[str, str]],
) -> None:
    """Validation-failure path: specialist returned malformed structured
    output, so no verifier ever ran — entry shape preserved with verifier=None."""
    record_disagreement(
        source_key="doc-bad.jpeg",
        primary=_payment_receipt(),
        verifier=None,
        status="validation_failure",
    )

    _, body = s3_writes[0]
    entry = json.loads(body)
    assert entry["verifier"] is None
    assert entry["agreement_status"] == "validation_failure"


def test_extractor_version_is_optional_and_serialises_as_null_when_absent(
    s3_writes: list[tuple[str, str]],
) -> None:
    record_disagreement(
        source_key="doc-no-ver.jpeg",
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
    )

    _, body = s3_writes[0]
    entry = json.loads(body)
    assert entry["extractor_version"] is None
