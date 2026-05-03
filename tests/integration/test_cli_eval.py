"""Integration tests for ``doc-extractor eval`` CLI subcommand (Story 2.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from doc_extractor import cli
from doc_extractor.eval.scorecard import Scorecard


def _scorecard_fixture() -> Scorecard:
    """Empty Scorecard with deterministic provenance — JSON is byte-stable."""
    return Scorecard(
        per_agent={},
        per_field={},
        per_jurisdiction={},
        total_examples=0,
        total_cost_usd=0.0,
        extractor_version="0.1.0",
        run_timestamp="2026-05-03T12:00:00Z",
    )


@pytest.fixture
def mock_run_eval(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the cli's ``run_eval`` to record the invocation kwargs."""
    captured: dict[str, Any] = {}
    fixture_card = _scorecard_fixture()

    async def fake_run_eval(
        doc_type: str | None = None,
        jurisdiction: str | None = None,
        *,
        max_concurrent: int = 20,
    ) -> Scorecard:
        captured["doc_type"] = doc_type
        captured["jurisdiction"] = jurisdiction
        captured["max_concurrent"] = max_concurrent
        return fixture_card

    monkeypatch.setattr(cli, "run_eval", fake_run_eval)
    return {"captured": captured, "scorecard": fixture_card}


def test_eval_no_args_prints_scorecard_json_to_stdout(
    mock_run_eval: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(["eval"])
    assert rc == cli.EXIT_OK

    out = capsys.readouterr().out.strip()
    assert out.startswith("{"), f"expected JSON on stdout, got: {out!r}"
    assert out == mock_run_eval["scorecard"].to_json()

    captured = mock_run_eval["captured"]
    assert captured["doc_type"] is None
    assert captured["jurisdiction"] is None
    assert captured["max_concurrent"] == 20  # default per AC


def test_eval_passes_doc_type_and_jurisdiction_filters(
    mock_run_eval: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(
        ["eval", "--doc-type", "Passport", "--jurisdiction", "CN"]
    )
    assert rc == cli.EXIT_OK

    captured = mock_run_eval["captured"]
    assert captured["doc_type"] == "Passport"
    assert captured["jurisdiction"] == "CN"


def test_eval_output_flag_writes_to_file_and_announces_on_stderr(
    mock_run_eval: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "run.json"
    rc = cli.main(["eval", "--output", str(out_path)])
    assert rc == cli.EXIT_OK

    captured_io = capsys.readouterr()
    assert captured_io.out == "", "stdout must be empty when --output is used"
    assert f"Scorecard written to {out_path}" in captured_io.err

    written = out_path.read_text(encoding="utf-8")
    assert written == mock_run_eval["scorecard"].to_json()


def test_eval_max_concurrent_flag_overrides_default(
    mock_run_eval: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main(["eval", "--max-concurrent", "50"])
    assert rc == cli.EXIT_OK
    assert mock_run_eval["captured"]["max_concurrent"] == 50


def test_eval_output_payload_matches_scorecard_to_json(
    mock_run_eval: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Sanity: the bytes written to --output round-trip via Scorecard.to_json()."""
    out_path = tmp_path / "card.json"
    rc = cli.main(["eval", "--output", str(out_path)])
    assert rc == cli.EXIT_OK

    expected_json = mock_run_eval["scorecard"].to_json()
    assert out_path.read_text(encoding="utf-8") == expected_json


def test_eval_subcommand_does_not_break_existing_extract_help() -> None:
    """Two-subparser layout — extract help still exposes the extract flags."""
    parser = cli.build_parser()
    # argparse raises SystemExit on --help; assert parsing 'extract --help' is fine.
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["extract", "--help"])
    assert exc_info.value.code == 0
