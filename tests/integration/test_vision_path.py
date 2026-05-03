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
    """Patch S3 and agent factories. ``head_analysis`` defaults to False."""
    head = MagicMock(return_value=False)
    presign = MagicMock(return_value="https://example.invalid/presigned-url")
    write = MagicMock(return_value=None)
    monkeypatch.setattr(s3_io, "head_analysis", head)
    monkeypatch.setattr(s3_io, "get_presigned_url", presign)
    monkeypatch.setattr(s3_io, "write_analysis", write)
    return {"head": head, "presign": presign, "write": write}


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
