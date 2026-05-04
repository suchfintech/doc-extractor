"""Integration tests for the ``doc-extractor extract`` subcommand."""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agno.agent import Agent

from doc_extractor import cli, s3_io
from doc_extractor.pipelines import vision_path
from doc_extractor.schemas.classification import Classification
from doc_extractor.schemas.ids import Passport

# ``from .extract import extract`` in doc_extractor/__init__.py shadows the
# submodule attribute with the function, so reach into ``sys.modules`` for
# the actual module — that is what we need to monkeypatch.
extract_module = importlib.import_module("doc_extractor.extract")

SOURCE_KEY = "passports/cli-sample.jpeg"
EXPECTED_ANALYSIS_KEY = f"{SOURCE_KEY}.md"


def _passport_fixture() -> Passport:
    return Passport(
        doc_type="Passport",
        passport_number="X9988776",
        nationality="NZL",
        doc_number="X9988776",
        dob="1985-09-12",
        issue_date="2022-09-12",
        expiry_date="2032-09-11",
        sex="F",
        mrz_line_1="P<NZLDOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
        mrz_line_2="X9988776<NZL8509121F3209118<<<<<<<<<<<<<<00",
        name_latin="DOE, JANE",
        jurisdiction="NZL",
    )


def _make_async_agent(content: Any) -> tuple[Agent, AsyncMock]:
    arun = AsyncMock(return_value=MagicMock(content=content))
    agent = MagicMock(spec=Agent)
    agent.arun = arun
    return agent, arun


@pytest.fixture
def mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Patch the simple ``vision_path.run`` path so non-verbose tests don't go inline."""
    run_mock = AsyncMock(
        return_value={
            "analysis_key": EXPECTED_ANALYSIS_KEY,
            "skipped": False,
            "doc_type": "Passport",
            "cost_usd": 0.0,
        }
    )
    monkeypatch.setattr(vision_path, "run", run_mock)
    monkeypatch.setattr(s3_io, "head_analysis", MagicMock(return_value=False))
    return {"run": run_mock}


@pytest.fixture
def mock_inline_pipeline(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """P13 (code review Round 3) — extract.py's inline path is gone;
    verbose/dry-run/--provider/--model now flow through ``vision_path.run``.
    This fixture patches vision_path's internal deps so a real run goes
    through end-to-end without touching S3 or a provider."""
    head = MagicMock(return_value=False)
    head_src = MagicMock(return_value={"content_type": "image/jpeg", "size": 1024})
    presign = MagicMock(return_value="https://example.invalid/presigned-url")
    write = MagicMock(return_value=None)
    monkeypatch.setattr(s3_io, "head_analysis", head)
    monkeypatch.setattr(s3_io, "head_source", head_src)
    monkeypatch.setattr(s3_io, "get_presigned_url", presign)
    monkeypatch.setattr(s3_io, "write_analysis", write)

    classifier_agent, _ = _make_async_agent(
        Classification(doc_type="Passport", jurisdiction="NZ")
    )
    passport_agent, _ = _make_async_agent(_passport_fixture())

    # Verifier runs because Passport is in _VERIFIER_GATED_TYPES.
    from doc_extractor.schemas.verifier import VerifierAudit

    verifier_agent, _ = _make_async_agent(
        VerifierAudit(field_audits={"passport_number": "agree"}, notes="ok")
    )

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda **_: classifier_agent)
    monkeypatch.setitem(vision_path.FACTORIES, "Passport", lambda **_: passport_agent)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda **_: verifier_agent)
    # vision_path emits telemetry as a side-effect; tests don't assert on
    # it but the writer would create ``./telemetry/<date>.jsonl``. Stub it.
    monkeypatch.setattr(vision_path, "record_extraction", lambda **_: None)

    return {"head": head, "head_src": head_src, "presign": presign, "write": write}


def test_extract_simple_path_exits_zero(
    mock_pipeline: dict[str, MagicMock], capsys: pytest.CaptureFixture[str]
) -> None:
    """``vision_path.run`` is invoked exactly once with the source key
    plus the (default-None/False) override kwargs. P13 — extract.py
    forwards every CLI flag through verbatim."""
    rc = cli.main(["extract", "--key", SOURCE_KEY])
    assert rc == cli.EXIT_OK
    assert mock_pipeline["run"].await_count == 1
    call = mock_pipeline["run"].call_args
    assert call.args == (SOURCE_KEY,)
    # Defaults forwarded through extract() → vision_path.run().
    assert call.kwargs == {
        "provider": None,
        "model": None,
        "verbose": False,
        "show_image": False,
        "dry_run": False,
    }


def test_extract_verbose_prints_five_sections_in_order(
    mock_inline_pipeline: dict[str, MagicMock], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(["extract", "--key", SOURCE_KEY, "--verbose"])
    assert rc == cli.EXIT_OK

    out = capsys.readouterr().out
    expected_order = [
        "=== 1. Resolved prompt text ===",
        "=== 2. Raw model response ===",
        "=== 3. Pydantic validation result ===",
        "=== 4. Rendered .md content ===",
        "=== 5. Cost telemetry ===",
    ]
    positions = [out.find(marker) for marker in expected_order]
    assert all(p != -1 for p in positions), (
        f"Missing one or more verbose sections. Positions: {positions}\nOutput:\n{out}"
    )
    assert positions == sorted(positions), (
        f"Verbose sections out of order: positions={positions}"
    )

    # P12 — cost_usd no longer hardcoded to 0.000; the verbose section
    # surfaces the rolled-up cost from agent run_response metadata.
    assert "cost_usd=" in out
    assert "latency_ms=" in out
    mock_inline_pipeline["write"].assert_called_once()


def test_extract_dry_run_skips_write(
    mock_inline_pipeline: dict[str, MagicMock], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(["extract", "--key", SOURCE_KEY, "--dry-run"])
    assert rc == cli.EXIT_OK

    mock_inline_pipeline["write"].assert_not_called()

    out = capsys.readouterr().out
    assert out.startswith("---\n") or "---\n" in out
    assert "passport_number: X9988776" in out


def test_extract_missing_key_exits_nonzero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["extract"])
    assert exc_info.value.code != 0
