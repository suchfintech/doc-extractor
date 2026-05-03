"""Full-pipeline forensic integration test for Story 6.1.

Drives ``vision_path.run`` end-to-end with mocks that pin BOTH the typed
content AND the raw model responses + metadata, then reads the resulting
disagreement-queue JSON entry from a captured S3 write to verify that the
forensic payload (raw text + metadata for both primary and verifier) is
inlined byte-equal — including CJK content.

Two scenarios:

1. Verifier disagrees (``overall == "fail"``) — both ``primary_raw_*`` and
   ``verifier_raw_*`` populate.
2. ``PydanticValidationError`` exhausts the retry budget
   (``status == "validation_failure"``) — only ``primary_raw_*`` populates;
   the verifier never ran, so its raw fields stay ``None``.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agno.agent import Agent
from pydantic import ValidationError

from doc_extractor import s3_io
from doc_extractor.pipelines import vision_path
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.verifier import VerifierAudit

SOURCE_KEY = "documents/transactions/12345/abc.jpeg"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


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
    return VerifierAudit(
        field_audits={
            "receipt_debit_account_name": "agree",
            "receipt_credit_account_name": "disagree",
        },
        notes="image shows credit name 王五 but specialist claimed 李四",
    )


def _make_agent_with_raw(
    *,
    content: Any,
    raw_text: str,
    metadata: dict[str, Any],
) -> tuple[Agent, AsyncMock, MagicMock]:
    """Build a MagicMock Agent whose ``arun`` returns a ``run_response``-shaped
    object AND whose ``agent.run_response`` attribute mirrors that state.
    Both shapes are populated so ``_read_run_response`` finds the data.
    """
    last_message = MagicMock(content=raw_text)
    metrics = MagicMock(
        provider=metadata["provider"],
        model=metadata["model"],
        latency_ms=metadata["latency_ms"],
        cost_usd=metadata["cost_usd"],
    )
    run_response = MagicMock(
        content=content,
        messages=[last_message],
        metrics=metrics,
    )
    arun = AsyncMock(return_value=run_response)
    agent = MagicMock(spec=Agent)
    agent.arun = arun
    agent.run_response = run_response
    return agent, arun, run_response


@pytest.fixture
def patched_io(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Mock S3 + classifier-side dependencies; analysis-write captured but a no-op."""
    head = MagicMock(return_value=False)
    head_src = MagicMock(return_value={"content_type": "image/jpeg", "size": 1024})
    presign = MagicMock(return_value="https://example.invalid/presigned")
    write_analysis = MagicMock(return_value=None)
    get_bytes = MagicMock(return_value=b"")
    monkeypatch.setattr(s3_io, "head_analysis", head)
    monkeypatch.setattr(s3_io, "head_source", head_src)
    monkeypatch.setattr(s3_io, "get_presigned_url", presign)
    monkeypatch.setattr(s3_io, "get_source_bytes", get_bytes)
    monkeypatch.setattr(s3_io, "write_analysis", write_analysis)
    return {
        "head": head,
        "head_src": head_src,
        "presign": presign,
        "get_bytes": get_bytes,
        "write_analysis": write_analysis,
    }


@pytest.fixture
def captured_disagreement_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, str]]:
    """Capture (key, body) pairs from s3_io.write_disagreement.

    Patched at the s3_io module level so disagreement.record_disagreement's
    actual writer call is intercepted (the function imports s3_io and
    references s3_io.write_disagreement at call time).
    """
    calls: list[tuple[str, str]] = []

    def fake_write(key: str, body: str | bytes) -> None:
        text = body.decode("utf-8") if isinstance(body, bytes) else body
        calls.append((key, text))

    monkeypatch.setattr(s3_io, "write_disagreement", fake_write)
    return calls


# ---------------------------------------------------------------------------
# Scenario 1 — Verifier disagrees: both raw payloads inlined
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verifier_disagreement_inlines_both_raw_responses(
    patched_io: dict[str, MagicMock],
    captured_disagreement_writes: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_raw_text = (
        '{"receipt_debit_account_name": "张三", '
        '"receipt_credit_account_name": "李四", '
        '"receipt_amount": "15000.00", "receipt_currency": "CNY"}'
    )
    primary_metadata = {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6-20260101",
        "latency_ms": 1234.5,
        "cost_usd": 0.0123,
    }
    verifier_raw_text = (
        '{"field_audits": {"receipt_credit_account_name": "disagree"}, '
        '"overall": "fail", '
        '"notes": "image shows credit name 王五 but specialist claimed 李四"}'
    )
    verifier_metadata = {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6-20260101",
        "latency_ms": 987.6,
        "cost_usd": 0.0234,
    }

    classifier_agent, _, _ = _make_agent_with_raw(
        content=Classification(doc_type="PaymentReceipt", jurisdiction="CN"),
        raw_text="(classifier raw — irrelevant for this test)",
        metadata={
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "latency_ms": 100.0,
            "cost_usd": 0.0001,
        },
    )
    pr_agent, _, _ = _make_agent_with_raw(
        content=_payment_receipt(),
        raw_text=primary_raw_text,
        metadata=primary_metadata,
    )
    verifier_agent, _, _ = _make_agent_with_raw(
        content=_failing_audit(),
        raw_text=verifier_raw_text,
        metadata=verifier_metadata,
    )

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_payment_receipt_agent", lambda: pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    # Disagreement-queue write happened.
    assert result["disagreement_key"] == f"disagreements/{SOURCE_KEY}.json"
    assert len(captured_disagreement_writes) == 1
    written_key, body = captured_disagreement_writes[0]
    assert written_key == f"disagreements/{SOURCE_KEY}.json"

    entry = json.loads(body)
    # 10-field shape (Story 6.1).
    assert set(entry.keys()) == {
        "source_key",
        "primary",
        "verifier",
        "agreement_status",
        "timestamp",
        "extractor_version",
        "primary_raw_response_text",
        "primary_raw_response_metadata",
        "verifier_raw_response_text",
        "verifier_raw_response_metadata",
    }
    assert entry["agreement_status"] == "disagreement"

    # Raw text fields are byte-identical to what the mocked agents emitted.
    assert entry["primary_raw_response_text"] == primary_raw_text
    assert entry["verifier_raw_response_text"] == verifier_raw_text
    assert entry["primary_raw_response_metadata"] == primary_metadata
    assert entry["verifier_raw_response_metadata"] == verifier_metadata


@pytest.mark.asyncio
async def test_raw_response_text_preserves_cjk_byte_equal(
    patched_io: dict[str, MagicMock],
    captured_disagreement_writes: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 6.1 invariant: CJK content in the raw response is preserved
    verbatim through the JSON dump (``ensure_ascii=False``)."""
    cjk_primary_raw = (
        "付款人姓名: 张三 (account 6217 **** **** 0083)\n"
        "收款人姓名: 李四 (note: image actually shows 王五)\n"
        "金额: 15000.00 元"
    )
    cjk_verifier_raw = "image shows 王五 but specialist claimed 李四 — disagree"

    classifier_agent, _, _ = _make_agent_with_raw(
        content=Classification(doc_type="PaymentReceipt", jurisdiction="CN"),
        raw_text="",
        metadata={"provider": "", "model": "", "latency_ms": 0.0, "cost_usd": 0.0},
    )
    pr_agent, _, _ = _make_agent_with_raw(
        content=_payment_receipt(),
        raw_text=cjk_primary_raw,
        metadata={"provider": "anthropic", "model": "sonnet", "latency_ms": 1.0, "cost_usd": 0.01},
    )
    verifier_agent, _, _ = _make_agent_with_raw(
        content=_failing_audit(),
        raw_text=cjk_verifier_raw,
        metadata={"provider": "anthropic", "model": "sonnet", "latency_ms": 1.0, "cost_usd": 0.01},
    )

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_payment_receipt_agent", lambda: pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    await vision_path.run(SOURCE_KEY)

    _, body = captured_disagreement_writes[0]
    # Raw CJK appears uneoscaped — no \\uXXXX sequences in the JSON body.
    assert "张三" in body
    assert "李四" in body
    assert "王五" in body
    assert "付款人姓名" in body
    assert "\\u" not in body

    entry = json.loads(body)
    assert entry["primary_raw_response_text"] == cjk_primary_raw
    assert entry["verifier_raw_response_text"] == cjk_verifier_raw


# ---------------------------------------------------------------------------
# Scenario 2 — Validation failure: only primary raw populates
# ---------------------------------------------------------------------------


def _pydantic_validation_error() -> ValidationError:
    from pydantic import BaseModel as _BM

    class _Strict(_BM):
        required: str

    try:
        _Strict.model_validate({})
    except ValidationError as exc:
        return exc
    raise RuntimeError("expected ValidationError")


@pytest.mark.asyncio
async def test_validation_failure_inlines_primary_raw_only(
    patched_io: dict[str, MagicMock],
    captured_disagreement_writes: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry exhausts on a Sonnet primary; the failed agent's raw text
    survives into the disagreement payload. The verifier never ran, so
    its raw fields are ``None``."""
    classifier_agent, _, _ = _make_agent_with_raw(
        content=Classification(doc_type="PaymentReceipt", jurisdiction="CN"),
        raw_text="",
        metadata={"provider": "", "model": "", "latency_ms": 0.0, "cost_usd": 0.0},
    )

    failing_raw = '{"this_is": "not a valid PaymentReceipt"}'
    failing_metadata = {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6-20260101",
        "latency_ms": 543.2,
        "cost_usd": 0.0567,
    }
    err = _pydantic_validation_error()

    # The PR agent's run_response carries a raw response, but its arun
    # raises before the retry layer can pull `.content`. ``_read_run_response``
    # still picks up the raw text from agent.run_response.messages[-1].
    last_message = MagicMock(content=failing_raw)
    metrics = MagicMock(
        provider=failing_metadata["provider"],
        model=failing_metadata["model"],
        latency_ms=failing_metadata["latency_ms"],
        cost_usd=failing_metadata["cost_usd"],
    )
    run_response = MagicMock(messages=[last_message], metrics=metrics)
    failing_pr_agent = MagicMock(spec=Agent)
    failing_pr_agent.arun = AsyncMock(side_effect=err)
    failing_pr_agent.run_response = run_response

    verifier_agent, verifier_arun, _ = _make_agent_with_raw(
        content=_failing_audit(),
        raw_text="(should not run)",
        metadata={"provider": "", "model": "", "latency_ms": 0.0, "cost_usd": 0.0},
    )

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(
        vision_path, "create_payment_receipt_agent", lambda: failing_pr_agent
    )
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    with pytest.raises(ValidationError):
        await vision_path.run(SOURCE_KEY)

    assert verifier_arun.await_count == 0  # verifier never ran
    assert len(captured_disagreement_writes) == 1
    _, body = captured_disagreement_writes[0]
    entry = json.loads(body)

    assert entry["agreement_status"] == "validation_failure"
    assert entry["primary"] is None
    assert entry["verifier"] is None
    # Primary raw populated from the failed agent's run_response.
    assert entry["primary_raw_response_text"] == failing_raw
    assert entry["primary_raw_response_metadata"] == failing_metadata
    # Verifier raw stays None — verifier never ran on this path.
    assert entry["verifier_raw_response_text"] is None
    assert entry["verifier_raw_response_metadata"] is None
