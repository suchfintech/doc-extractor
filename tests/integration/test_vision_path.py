"""Integration test for the v1 Passport-only vision pipeline."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agno.agent import Agent

from doc_extractor import s3_io
from doc_extractor.pipelines import vision_path
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.ids import Passport
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.verifier import VerifierAudit

SOURCE_KEY = "passports/sample-001.jpeg"
EXPECTED_ANALYSIS_KEY = f"{SOURCE_KEY}.md"


def _passport_fixture() -> Passport:
    return Passport(
        doc_type="Passport",
        passport_number="E12345678",
        nationality="NZL",
        doc_number="E12345678",
        dob="1990-04-15",
        issue_date="2020-04-15",
        expiry_date="2030-04-14",
        sex="M",
        mrz_line_1="P<NZLDOE<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
        mrz_line_2="E12345678<NZL9004151M3004142<<<<<<<<<<<<<<00",
        name_latin="DOE, JOHN",
        jurisdiction="NZL",
    )


def _make_async_agent(content: Any) -> tuple[Agent, AsyncMock]:
    """Return a MagicMock that quacks like an Agno Agent for ``arun``.

    The ``AsyncMock`` is returned alongside so callers can introspect
    ``await_count`` etc. without fighting the ``spec=Agent`` overload that
    hides ``AsyncMock`` attributes from mypy.
    """
    arun = AsyncMock(return_value=MagicMock(content=content))
    agent = MagicMock(spec=Agent)
    agent.arun = arun
    return agent, arun


@pytest.fixture
def patched_io(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Patch S3 and agent factories. ``head_analysis`` defaults to False.

    ``head_source`` defaults to ``image/jpeg`` so the legacy non-PDF tests
    keep flowing through the presigned-URL fast path.
    """
    head = MagicMock(return_value=False)
    head_src = MagicMock(return_value={"content_type": "image/jpeg", "size": 1024})
    presign = MagicMock(return_value="https://example.invalid/presigned-url")
    write = MagicMock(return_value=None)
    get_bytes = MagicMock(return_value=b"")
    monkeypatch.setattr(s3_io, "head_analysis", head)
    monkeypatch.setattr(s3_io, "head_source", head_src)
    monkeypatch.setattr(s3_io, "get_presigned_url", presign)
    monkeypatch.setattr(s3_io, "get_source_bytes", get_bytes)
    monkeypatch.setattr(s3_io, "write_analysis", write)
    return {
        "head": head,
        "head_src": head_src,
        "presign": presign,
        "get_bytes": get_bytes,
        "write": write,
    }


@pytest.mark.asyncio
async def test_happy_path_writes_passport_markdown(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier_agent, classifier_arun = _make_async_agent(
        Classification(doc_type="Passport", jurisdiction="NZ")
    )
    passport_agent, passport_arun = _make_async_agent(_passport_fixture())

    monkeypatch.setattr(
        vision_path, "create_classifier_agent", lambda: classifier_agent
    )
    monkeypatch.setattr(
        vision_path, "create_passport_agent", lambda: passport_agent
    )

    result = await vision_path.run(SOURCE_KEY)

    assert result == {
        "analysis_key": EXPECTED_ANALYSIS_KEY,
        "skipped": False,
        "doc_type": "Passport",
        "verifier_audit": None,
        "disagreement_key": None,
    }
    patched_io["head"].assert_called_once_with(EXPECTED_ANALYSIS_KEY)
    patched_io["presign"].assert_called_once()
    patched_io["write"].assert_called_once()

    write_args = patched_io["write"].call_args
    assert write_args.args[0] == EXPECTED_ANALYSIS_KEY
    body = write_args.args[1]
    assert body.startswith("---\n")
    assert "passport_number: E12345678" in body
    assert "doc_type: Passport" in body

    assert classifier_arun.await_count == 1
    assert passport_arun.await_count == 1


@pytest.mark.asyncio
async def test_head_skip_short_circuits_before_provider(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    patched_io["head"].return_value = True

    classifier_agent, classifier_arun = _make_async_agent(content=None)

    monkeypatch.setattr(
        vision_path, "create_classifier_agent", lambda: classifier_agent
    )
    monkeypatch.setattr(
        vision_path, "create_passport_agent", lambda: MagicMock(spec=Agent)
    )

    result = await vision_path.run(SOURCE_KEY)

    assert result == {
        "analysis_key": EXPECTED_ANALYSIS_KEY,
        "skipped": True,
        "doc_type": "",
        "verifier_audit": None,
        "disagreement_key": None,
    }
    patched_io["head"].assert_called_once_with(EXPECTED_ANALYSIS_KEY)
    patched_io["presign"].assert_not_called()
    patched_io["write"].assert_not_called()
    assert classifier_arun.await_count == 0


@pytest.mark.asyncio
async def test_non_passport_classification_raises_not_implemented(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="DriverLicence", jurisdiction="NZ")
    )
    passport_agent, passport_arun = _make_async_agent(content=None)

    monkeypatch.setattr(
        vision_path, "create_classifier_agent", lambda: classifier_agent
    )
    monkeypatch.setattr(
        vision_path, "create_passport_agent", lambda: passport_agent
    )

    with pytest.raises(NotImplementedError, match="DriverLicence"):
        await vision_path.run(SOURCE_KEY)

    assert passport_arun.await_count == 0
    patched_io["write"].assert_not_called()


PDF_SOURCE_KEY = "passports/sample-001.pdf"
EXPECTED_PDF_ANALYSIS_KEY = f"{PDF_SOURCE_KEY}.md"


@pytest.mark.asyncio
async def test_pdf_source_routes_through_pdf_to_images(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """PDFs go through pdf_to_images and reach the classifier as Image(content=...)."""
    patched_io["head_src"].return_value = {
        "content_type": "application/pdf",
        "size": 4096,
    }
    fake_png = b"\x89PNG\r\n\x1a\nFAKE-PAGE-1"
    patched_io["get_bytes"].return_value = b"%PDF-1.4 fake-bytes"
    pdf_to_images_mock = MagicMock(return_value=[fake_png])
    monkeypatch.setattr(vision_path, "pdf_to_images", pdf_to_images_mock)

    classifier_agent, classifier_arun = _make_async_agent(
        Classification(doc_type="Passport", jurisdiction="NZ")
    )
    passport_agent, _ = _make_async_agent(_passport_fixture())
    monkeypatch.setattr(
        vision_path, "create_classifier_agent", lambda: classifier_agent
    )
    monkeypatch.setattr(
        vision_path, "create_passport_agent", lambda: passport_agent
    )

    result = await vision_path.run(PDF_SOURCE_KEY)

    assert result["doc_type"] == "Passport"
    assert result["analysis_key"] == EXPECTED_PDF_ANALYSIS_KEY
    pdf_to_images_mock.assert_called_once()
    args, kwargs = pdf_to_images_mock.call_args
    assert args[0] == b"%PDF-1.4 fake-bytes"
    assert kwargs.get("mode") == "page1"
    patched_io["presign"].assert_not_called()

    classifier_arun.assert_awaited_once()
    sent_image = classifier_arun.call_args.kwargs["images"][0]
    assert sent_image.url is None
    assert sent_image.content == fake_png


def test_pdf_mode_for_returns_all_pages_only_for_bank_statement() -> None:
    assert vision_path._pdf_mode_for("BankStatement") == "all_pages"
    for doc_type in ("Passport", "DriverLicence", "PaymentReceipt", "Other", ""):
        assert vision_path._pdf_mode_for(doc_type) == "page1"


# ---------------------------------------------------------------------------
# Story 3.7 — verifier step on PaymentReceipt
# ---------------------------------------------------------------------------


PR_SOURCE_KEY = "documents/transactions/12345/abc.jpeg"
PR_ANALYSIS_KEY = f"{PR_SOURCE_KEY}.md"


def _payment_receipt_fixture() -> PaymentReceipt:
    return PaymentReceipt(
        doc_type="PaymentReceipt",
        jurisdiction="CN",
        receipt_amount="15000.00",
        receipt_currency="CNY",
        receipt_time="2025-07-01T00:00:00Z",
        receipt_debit_account_name="张三",
        receipt_debit_account_number="6217 **** **** 0083",
        receipt_debit_bank_name="中国工商银行",
        receipt_credit_account_name="李四",
        receipt_credit_account_number="6230 **** **** 2235",
        receipt_credit_bank_name="平安银行",
    )


def _verifier_audit_fixture(overall: str = "pass") -> VerifierAudit:
    # The validator pins `overall` to the field-audits derivation, so feed
    # field-audits that match the requested overall.
    if overall == "fail":
        field_audits = {"receipt_debit_account_name": "disagree"}
    elif overall == "uncertain":
        field_audits = {"receipt_debit_account_name": "abstain"}
    else:
        field_audits = {"receipt_debit_account_name": "agree"}
    return VerifierAudit(field_audits=field_audits, notes="test")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_verifier_runs_when_classification_is_payment_receipt(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: classifier→PaymentReceipt→specialist→verifier→write."""
    classifier_agent, classifier_arun = _make_async_agent(
        Classification(doc_type="PaymentReceipt", jurisdiction="CN")
    )
    pr_agent, pr_arun = _make_async_agent(_payment_receipt_fixture())
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(
        vision_path, "create_payment_receipt_agent", lambda: pr_agent
    )
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(PR_SOURCE_KEY)

    assert result["doc_type"] == "PaymentReceipt"
    assert result["analysis_key"] == PR_ANALYSIS_KEY
    assert result["skipped"] is False
    # Verifier output round-tripped to dict in the result payload.
    assert isinstance(result["verifier_audit"], dict)
    assert result["verifier_audit"]["overall"] == "pass"
    assert result["verifier_audit"]["field_audits"]["receipt_debit_account_name"] == "agree"

    assert classifier_arun.await_count == 1
    assert pr_arun.await_count == 1
    assert verifier_arun.await_count == 1
    # The verifier received the JSON dump of the specialist's claim plus the image.
    verifier_input = verifier_arun.call_args.args[0]
    assert isinstance(verifier_input, str)
    assert "receipt_debit_account_name" in verifier_input
    assert "张三" in verifier_input
    assert verifier_arun.call_args.kwargs["images"]


@pytest.mark.asyncio
async def test_verifier_fail_verdict_propagates_to_result_dict(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `fail` verifier verdict reaches the result dict so Story 3.9 can route to queue."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="PaymentReceipt", jurisdiction="CN")
    )
    pr_agent, _ = _make_async_agent(_payment_receipt_fixture())
    verifier_agent, _ = _make_async_agent(_verifier_audit_fixture("fail"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_payment_receipt_agent", lambda: pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(PR_SOURCE_KEY)

    assert result["verifier_audit"]["overall"] == "fail"


@pytest.mark.asyncio
async def test_verifier_skipped_when_classification_is_passport(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifier gating: for non-PaymentReceipt types, the verifier agent is
    never constructed and never called. Sentinel for Story 4.4 (which will
    expand verification to ID types and need to update this test)."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="Passport", jurisdiction="NZ")
    )
    passport_agent, _ = _make_async_agent(_passport_fixture())
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture())

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_passport_agent", lambda: passport_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert result["doc_type"] == "Passport"
    assert result["verifier_audit"] is None
    assert verifier_arun.await_count == 0


@pytest.mark.asyncio
async def test_verifier_not_called_when_classification_is_other(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Other` raises NotImplementedError before any specialist runs — the
    verifier must NOT be constructed or called along that path either."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="Other", jurisdiction="NZ")
    )
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture())

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    with pytest.raises(NotImplementedError, match="Other"):
        await vision_path.run(SOURCE_KEY)

    assert verifier_arun.await_count == 0
    patched_io["write"].assert_not_called()


# ---------------------------------------------------------------------------
# Story 3.9 — disagreement-queue write triggered by overall=="fail"
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_disagreement_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture record_disagreement kwargs without writing to S3."""
    calls: list[dict[str, Any]] = []

    def fake_record(**kwargs: Any) -> str:
        calls.append(kwargs)
        return f"disagreements/{kwargs['source_key']}.json"

    monkeypatch.setattr(vision_path, "record_disagreement", fake_record)
    return calls


@pytest.mark.asyncio
async def test_disagreement_written_when_verifier_overall_is_fail(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="PaymentReceipt", jurisdiction="CN")
    )
    pr_agent, _ = _make_async_agent(_payment_receipt_fixture())
    verifier_agent, _ = _make_async_agent(_verifier_audit_fixture("fail"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_payment_receipt_agent", lambda: pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(PR_SOURCE_KEY)

    assert len(captured_disagreement_calls) == 1
    call = captured_disagreement_calls[0]
    assert call["source_key"] == PR_SOURCE_KEY
    assert isinstance(call["primary"], PaymentReceipt)
    assert call["primary"].receipt_debit_account_name == "张三"
    assert isinstance(call["verifier"], VerifierAudit)
    assert call["verifier"].overall == "fail"
    assert call["status"] == "disagreement"

    # And the result dict surfaces the disagreement bucket key.
    assert result["disagreement_key"] == f"disagreements/{PR_SOURCE_KEY}.json"


@pytest.mark.asyncio
async def test_disagreement_NOT_written_when_verifier_overall_is_pass(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="PaymentReceipt", jurisdiction="CN")
    )
    pr_agent, _ = _make_async_agent(_payment_receipt_fixture())
    verifier_agent, _ = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_payment_receipt_agent", lambda: pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(PR_SOURCE_KEY)

    assert captured_disagreement_calls == []
    assert result["disagreement_key"] is None


@pytest.mark.asyncio
async def test_disagreement_NOT_written_when_verifier_overall_is_uncertain(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`uncertain` is NOT a fail — Story 3.9 leaves it as advisory only.
    Downstream review can still flag it; we don't auto-queue it."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="PaymentReceipt", jurisdiction="CN")
    )
    pr_agent, _ = _make_async_agent(_payment_receipt_fixture())
    verifier_agent, _ = _make_async_agent(_verifier_audit_fixture("uncertain"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_payment_receipt_agent", lambda: pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(PR_SOURCE_KEY)

    assert captured_disagreement_calls == []
    assert result["disagreement_key"] is None
    assert result["verifier_audit"]["overall"] == "uncertain"


@pytest.mark.asyncio
async def test_disagreement_NOT_written_for_passport_route(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No verifier runs on Passport, so no disagreement write is possible."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="Passport", jurisdiction="NZ")
    )
    passport_agent, _ = _make_async_agent(_passport_fixture())

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_passport_agent", lambda: passport_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert captured_disagreement_calls == []
    assert result["disagreement_key"] is None
