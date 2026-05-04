"""Integration test for the vision pipeline (FACTORIES dispatch + verifier gate)."""

from __future__ import annotations

from typing import Any, get_args
from unittest.mock import AsyncMock, MagicMock

import pytest
from agno.agent import Agent

from doc_extractor import s3_io
from doc_extractor.pipelines import vision_path
from doc_extractor.schemas.bank_statement import BankStatement
from doc_extractor.schemas.classification import DOC_TYPES, Classification
from doc_extractor.schemas.company_extract import CompanyExtract
from doc_extractor.schemas.ids import DriverLicence, NationalID, Passport, Visa
from doc_extractor.schemas.other import Other
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


def _patch_factory(
    monkeypatch: pytest.MonkeyPatch, doc_type: str, agent: Agent
) -> None:
    """P2 — replace the FACTORIES entry for ``doc_type`` with a thunk
    returning ``agent``. ``setitem`` reverts on test teardown.

    Replaces the previous pattern of patching ``vision_path.create_X_agent``
    by name; vision_path no longer imports those symbols directly — it
    dispatches via the ``FACTORIES`` registry."""
    monkeypatch.setitem(vision_path.FACTORIES, doc_type, lambda: agent)


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
    """Story 4.4 — Passport runs through the verifier-gated flow now, so
    ``verifier_audit`` populates and the verifier mock is required."""
    classifier_agent, classifier_arun = _make_async_agent(
        Classification(doc_type="Passport", jurisdiction="NZ")
    )
    passport_agent, passport_arun = _make_async_agent(_passport_fixture())
    verifier_agent, verifier_arun = _make_async_agent(
        VerifierAudit(field_audits={"passport_number": "agree"}, notes="ok")
    )

    monkeypatch.setattr(
        vision_path, "create_classifier_agent", lambda: classifier_agent
    )
    _patch_factory(monkeypatch, "Passport", passport_agent)
    monkeypatch.setattr(
        vision_path, "create_verifier_agent", lambda: verifier_agent
    )

    result = await vision_path.run(SOURCE_KEY)

    assert result["analysis_key"] == EXPECTED_ANALYSIS_KEY
    assert result["skipped"] is False
    assert result["doc_type"] == "Passport"
    assert result["disagreement_key"] is None
    assert result["retry_count"] == 0
    # 4.4: Passport goes through the verifier — verdict 'pass' (validator pin).
    assert isinstance(result["verifier_audit"], dict)
    assert result["verifier_audit"]["overall"] == "pass"

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
    assert verifier_arun.await_count == 1


@pytest.mark.asyncio
async def test_head_skip_short_circuits_before_provider(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    patched_io["head"].return_value = True

    classifier_agent, classifier_arun = _make_async_agent(content=None)

    monkeypatch.setattr(
        vision_path, "create_classifier_agent", lambda: classifier_agent
    )

    result = await vision_path.run(SOURCE_KEY)

    assert result == {
        "analysis_key": EXPECTED_ANALYSIS_KEY,
        "skipped": True,
        "doc_type": "",
        "verifier_audit": None,
        "disagreement_key": None,
        "retry_count": 0,
    }
    patched_io["head"].assert_called_once_with(EXPECTED_ANALYSIS_KEY)
    patched_io["presign"].assert_not_called()
    patched_io["write"].assert_not_called()
    assert classifier_arun.await_count == 0


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
    verifier_agent, _ = _make_async_agent(
        VerifierAudit(field_audits={"passport_number": "agree"})
    )
    monkeypatch.setattr(
        vision_path, "create_classifier_agent", lambda: classifier_agent
    )
    _patch_factory(monkeypatch, "Passport", passport_agent)
    monkeypatch.setattr(
        vision_path, "create_verifier_agent", lambda: verifier_agent
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
    _patch_factory(monkeypatch, "PaymentReceipt", pr_agent)
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
    _patch_factory(monkeypatch, "PaymentReceipt", pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(PR_SOURCE_KEY)

    assert result["verifier_audit"]["overall"] == "fail"


@pytest.mark.asyncio
async def test_verifier_runs_on_passport_classification(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Story 4.4: Passport joined the verifier-gated set. The verifier agent
    is constructed, called once with the dumped Passport JSON + image, and
    its audit lands in the result dict."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="Passport", jurisdiction="NZ")
    )
    passport_agent, _ = _make_async_agent(_passport_fixture())
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture())

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "Passport", passport_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert result["doc_type"] == "Passport"
    assert isinstance(result["verifier_audit"], dict)
    assert result["verifier_audit"]["overall"] == "pass"
    assert verifier_arun.await_count == 1
    # Verifier saw the Passport instance dumped to JSON plus the image.
    verifier_input = verifier_arun.call_args.args[0]
    assert isinstance(verifier_input, str)
    assert "passport_number" in verifier_input
    assert "E12345678" in verifier_input
    assert verifier_arun.call_args.kwargs["images"]


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
    _patch_factory(monkeypatch, "PaymentReceipt", pr_agent)
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
    _patch_factory(monkeypatch, "PaymentReceipt", pr_agent)
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
    _patch_factory(monkeypatch, "PaymentReceipt", pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(PR_SOURCE_KEY)

    assert captured_disagreement_calls == []
    assert result["disagreement_key"] is None
    assert result["verifier_audit"]["overall"] == "uncertain"


@pytest.mark.asyncio
async def test_disagreement_NOT_written_for_passport_when_verifier_passes(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 4.4: Passport now runs the verifier. With a passing verdict,
    no disagreement is written — the gate is on overall=='fail', not on
    the specialist type."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="Passport", jurisdiction="NZ")
    )
    passport_agent, _ = _make_async_agent(_passport_fixture())
    verifier_agent, _ = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "Passport", passport_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert captured_disagreement_calls == []
    assert result["disagreement_key"] is None


# ---------------------------------------------------------------------------
# Story 3.8 — validation_failure path on PaymentReceipt branch
# ---------------------------------------------------------------------------


def _pydantic_validation_error() -> Any:
    """A real PydanticValidationError instance, constructed via failing validate."""
    from pydantic import BaseModel, ValidationError

    class _Strict(BaseModel):
        required_field: str

    try:
        _Strict.model_validate({})
    except ValidationError as exc:
        return exc
    raise RuntimeError("expected ValidationError")


@pytest.mark.asyncio
async def test_validation_failure_writes_disagreement_with_status_validation_failure(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the retry layer exhausts and re-raises PydanticValidationError,
    vision_path must write a disagreement entry with status="validation_failure"
    (primary=None, verifier=None) before the exception propagates."""
    from doc_extractor.exceptions import PydanticValidationError

    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="PaymentReceipt", jurisdiction="CN")
    )
    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)

    err = _pydantic_validation_error()

    async def fake_retry(
        _factory: Any,
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[Any, int]:
        # Simulate retry-exhausted: the primary was already top-tier, so
        # PydanticValidationError propagates without retry. Mirrors the
        # contract that vision_path catches.
        raise err

    monkeypatch.setattr(vision_path, "with_validation_retry", fake_retry)

    with pytest.raises(PydanticValidationError):
        await vision_path.run(PR_SOURCE_KEY)

    # Disagreement was written with the validation_failure status.
    assert len(captured_disagreement_calls) == 1
    call = captured_disagreement_calls[0]
    assert call["source_key"] == PR_SOURCE_KEY
    assert call["primary"] is None
    assert call["verifier"] is None
    assert call["status"] == "validation_failure"
    # No analysis .md was written — the run never produced a valid
    # specialist instance.
    patched_io["write"].assert_not_called()


@pytest.mark.asyncio
async def test_retry_count_propagates_to_result_dict(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When with_validation_retry returns retry_count=1 (escalated success),
    the result dict surfaces it for downstream observability."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="PaymentReceipt", jurisdiction="CN")
    )
    verifier_agent, _ = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    receipt = _payment_receipt_fixture()

    async def fake_retry(
        _factory: Any,
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[Any, int]:
        return receipt, 1  # simulated escalation success

    monkeypatch.setattr(vision_path, "with_validation_retry", fake_retry)

    result = await vision_path.run(PR_SOURCE_KEY)

    assert result["retry_count"] == 1
    assert result["doc_type"] == "PaymentReceipt"
    # No disagreement on a successful (post-retry) run with verifier=pass.
    assert captured_disagreement_calls == []


# ---------------------------------------------------------------------------
# Story 4.4 — verifier gates on the four ID document types
# ---------------------------------------------------------------------------


def _driver_licence_fixture() -> DriverLicence:
    return DriverLicence(
        doc_type="DriverLicence",
        jurisdiction="NZL",
        name_latin="DOE, JANE",
        doc_number="DL12345678",
        dob="1992-03-21",
        issue_date="2020-03-21",
        expiry_date="2030-03-20",
        sex="F",
        licence_class="6",
    )


def _national_id_fixture() -> NationalID:
    return NationalID(
        doc_type="NationalID",
        jurisdiction="CN",
        name_cjk="李明",
        doc_number="11010519491231002X",
        dob="1949-12-31",
        sex="M",
    )


def _visa_fixture() -> Visa:
    return Visa(
        doc_type="Visa",
        jurisdiction="NZL",
        name_latin="WANG, WEI",
        doc_number="V987654",
        issue_date="2025-01-10",
        expiry_date="2026-01-09",
        visa_class="L",
    )


@pytest.mark.asyncio
async def test_verifier_runs_on_driver_licence_classification(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="DriverLicence", jurisdiction="NZ")
    )
    dl = _driver_licence_fixture()
    dl_agent, dl_arun = _make_async_agent(dl)
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "DriverLicence", dl_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert result["doc_type"] == "DriverLicence"
    assert result["verifier_audit"]["overall"] == "pass"
    assert dl_arun.await_count == 1
    assert verifier_arun.await_count == 1
    verifier_input = verifier_arun.call_args.args[0]
    assert "doc_number" in verifier_input
    assert "DL12345678" in verifier_input
    assert "licence_class" in verifier_input


@pytest.mark.asyncio
async def test_verifier_runs_on_national_id_classification(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="NationalID", jurisdiction="CN")
    )
    nid = _national_id_fixture()
    nid_agent, nid_arun = _make_async_agent(nid)
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "NationalID", nid_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert result["doc_type"] == "NationalID"
    assert result["verifier_audit"]["overall"] == "pass"
    assert nid_arun.await_count == 1
    assert verifier_arun.await_count == 1
    verifier_input = verifier_arun.call_args.args[0]
    assert "11010519491231002X" in verifier_input
    # CJK name preserved through json.dumps(ensure_ascii=False).
    assert "李明" in verifier_input


@pytest.mark.asyncio
async def test_verifier_runs_on_visa_classification(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="Visa", jurisdiction="NZ")
    )
    visa = _visa_fixture()
    visa_agent, visa_arun = _make_async_agent(visa)
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "Visa", visa_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert result["doc_type"] == "Visa"
    assert result["verifier_audit"]["overall"] == "pass"
    assert visa_arun.await_count == 1
    assert verifier_arun.await_count == 1
    verifier_input = verifier_arun.call_args.args[0]
    assert "V987654" in verifier_input
    assert "visa_class" in verifier_input


@pytest.mark.asyncio
async def test_verifier_failure_on_driver_licence_writes_disagreement(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cross-type sentinel: the disagreement-write trigger generalises beyond
    PaymentReceipt — a failing verifier on any gated type writes the queue
    entry. Sentinel for Story 6.1's expansion to multi-type forensics."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="DriverLicence", jurisdiction="NZ")
    )
    dl_agent, _ = _make_async_agent(_driver_licence_fixture())
    verifier_agent, _ = _make_async_agent(_verifier_audit_fixture("fail"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "DriverLicence", dl_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert len(captured_disagreement_calls) == 1
    call = captured_disagreement_calls[0]
    assert isinstance(call["primary"], DriverLicence)
    assert call["status"] == "disagreement"
    assert result["disagreement_key"] is not None


# ---------------------------------------------------------------------------
# Story 6.1 — raw-response propagation through to record_disagreement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raw_responses_propagate_to_record_disagreement_on_fail(
    patched_io: dict[str, MagicMock],
    captured_disagreement_calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the verifier returns ``overall=='fail'``, vision_path must call
    ``record_disagreement`` with ``primary_raw=...`` and ``verifier_raw=...``
    populated from the agents' ``run_response``. Story 6.1 contract."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="PaymentReceipt", jurisdiction="CN")
    )

    # Build agents whose run_response carries the raw text + metadata
    # vision_path._read_run_response should pull through.
    pr_last_message = MagicMock(content="primary raw text — 张三")
    pr_metrics = MagicMock(
        provider="anthropic",
        model="claude-sonnet-4-6-20260101",
        latency_ms=12.5,
        cost_usd=0.01,
    )
    pr_run_response = MagicMock(
        content=_payment_receipt_fixture(),
        messages=[pr_last_message],
        metrics=pr_metrics,
    )
    pr_agent = MagicMock(spec=Agent)
    pr_agent.arun = AsyncMock(return_value=pr_run_response)
    pr_agent.run_response = pr_run_response

    ver_last_message = MagicMock(content="verifier raw text — disagree on credit")
    ver_metrics = MagicMock(
        provider="anthropic",
        model="claude-sonnet-4-6-20260101",
        latency_ms=8.4,
        cost_usd=0.02,
    )
    ver_run_response = MagicMock(
        content=_verifier_audit_fixture("fail"),
        messages=[ver_last_message],
        metrics=ver_metrics,
    )
    verifier_agent = MagicMock(spec=Agent)
    verifier_agent.arun = AsyncMock(return_value=ver_run_response)
    verifier_agent.run_response = ver_run_response

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "PaymentReceipt", pr_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    await vision_path.run(PR_SOURCE_KEY)

    assert len(captured_disagreement_calls) == 1
    call = captured_disagreement_calls[0]
    # Both raw kwargs populated on the fail path.
    assert "primary_raw" in call
    assert "verifier_raw" in call
    pr_text, pr_meta = call["primary_raw"]
    assert pr_text == "primary raw text — 张三"
    assert pr_meta == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6-20260101",
        "latency_ms": 12.5,
        "cost_usd": 0.01,
    }
    ver_text, ver_meta = call["verifier_raw"]
    assert ver_text == "verifier raw text — disagree on credit"
    assert ver_meta["provider"] == "anthropic"
    assert ver_meta["latency_ms"] == 8.4


# ---------------------------------------------------------------------------
# Code review Round 1 (P2) — FACTORIES dispatch covers all 15 doc-types.
#
# Before the P2 fix, vision_path imported ``create_passport_agent`` (and a
# handful of others) directly and raised ``NotImplementedError`` for any
# non-Passport classification — rendering the Story 4.5 ``FACTORIES``
# table dead code in production. The tests below cover the new dispatch
# for non-Passport types and the verifier-skip path for non-gated types.
# ---------------------------------------------------------------------------


def _bank_statement_fixture() -> BankStatement:
    return BankStatement(
        doc_type="BankStatement",
        jurisdiction="NZ",
        bank_name="ANZ Bank New Zealand Limited",
        account_holder_name="Acme Holdings Limited",
        account_number="02-0248-0242329-02",
        currency="NZD",
        statement_period_start="2026-04-01",
        statement_period_end="2026-04-30",
        closing_balance="NZD 12,345.67",
    )


def _company_extract_fixture() -> CompanyExtract:
    return CompanyExtract(
        doc_type="CompanyExtract",
        jurisdiction="NZ",
        company_name="Acme Holdings Limited",
        registration_number="1234567",
        incorporation_date="2018-04-15",
        directors=["Alice Wong", "Bob Chen"],
        shareholders=["Acme Group Ltd"],
    )


def _other_fixture() -> Other:
    return Other(
        doc_type="Other",
        jurisdiction="NZ",
        description="Handwritten note of unclear provenance",
        extracted_text="Please forward to processing.",
        notes="model uncertain — flagging for human review",
    )


@pytest.mark.asyncio
async def test_dispatches_bank_statement_via_factories_no_verifier(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """BankStatement is non-gated: the FACTORIES dispatch reaches its
    specialist, the analysis MD lands, but the verifier is NOT
    constructed or called."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="BankStatement", jurisdiction="NZ")
    )
    bs_agent, bs_arun = _make_async_agent(_bank_statement_fixture())
    # Bind a verifier mock so we can assert it was NEVER called.
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "BankStatement", bs_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert result["doc_type"] == "BankStatement"
    assert result["verifier_audit"] is None
    assert result["disagreement_key"] is None
    assert bs_arun.await_count == 1
    assert verifier_arun.await_count == 0
    patched_io["write"].assert_called_once()
    body = patched_io["write"].call_args.args[1]
    assert "doc_type: BankStatement" in body
    assert "ANZ Bank New Zealand Limited" in body
    assert "02-0248-0242329-02" in body


@pytest.mark.asyncio
async def test_dispatches_company_extract_via_factories_no_verifier(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """CompanyExtract — first non-gated test that exercises a list[str]
    schema field through the dispatch path."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="CompanyExtract", jurisdiction="NZ")
    )
    ce_agent, ce_arun = _make_async_agent(_company_extract_fixture())
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "CompanyExtract", ce_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert result["doc_type"] == "CompanyExtract"
    assert result["verifier_audit"] is None
    assert ce_arun.await_count == 1
    assert verifier_arun.await_count == 0
    body = patched_io["write"].call_args.args[1]
    assert "doc_type: CompanyExtract" in body
    assert "Alice Wong" in body
    assert "Acme Group Ltd" in body


@pytest.mark.asyncio
async def test_dispatches_other_via_factories_no_verifier(
    patched_io: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Story 5.5 — ``Other`` is the catch-all specialist. Before P2 it
    raised ``NotImplementedError``; now it dispatches via FACTORIES, the
    analysis MD lands, and the verifier is NOT called (Other is outside
    the safety-critical gated set)."""
    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="Other", jurisdiction="NZ")
    )
    other_agent, other_arun = _make_async_agent(_other_fixture())
    verifier_agent, verifier_arun = _make_async_agent(_verifier_audit_fixture("pass"))

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda: classifier_agent)
    _patch_factory(monkeypatch, "Other", other_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda: verifier_agent)

    result = await vision_path.run(SOURCE_KEY)

    assert result["doc_type"] == "Other"
    assert result["verifier_audit"] is None
    assert result["disagreement_key"] is None
    assert other_arun.await_count == 1
    assert verifier_arun.await_count == 0
    patched_io["write"].assert_called_once()
    body = patched_io["write"].call_args.args[1]
    assert "doc_type: Other" in body
    assert "Handwritten note of unclear provenance" in body


def test_specialist_meta_covers_all_15_doc_types() -> None:
    """Drift sentinel: ``_SPECIALIST_META`` MUST cover every ``DOC_TYPES``
    literal. A missing entry would surface at runtime as a ``KeyError`` on
    the very first request that classifies into the new type — failing
    here keeps the gate tight at PR time instead.
    """
    expected = set(get_args(DOC_TYPES))
    actual = set(vision_path._SPECIALIST_META.keys())
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"_SPECIALIST_META missing entries: {sorted(missing)}"
    assert not extra, f"_SPECIALIST_META has stale entries: {sorted(extra)}"


def test_factories_and_specialist_meta_keys_align() -> None:
    """``FACTORIES`` and ``_SPECIALIST_META`` are looked up with the same
    ``classification.doc_type`` key in ``vision_path.run`` — their key
    sets must match or one of the two lookups raises ``KeyError`` at
    runtime."""
    assert set(vision_path.FACTORIES.keys()) == set(
        vision_path._SPECIALIST_META.keys()
    )


def test_verifier_gated_types_is_subset_of_specialist_meta() -> None:
    """The verifier gate operates on ``classification.doc_type`` — every
    name in the gated set must be a real specialist, otherwise a typo'd
    entry silently never matches and the verifier never runs for that
    doc-type in production."""
    assert vision_path._VERIFIER_GATED_TYPES.issubset(
        set(vision_path._SPECIALIST_META.keys())
    )
