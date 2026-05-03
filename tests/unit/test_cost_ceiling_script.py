"""Unit tests for ``scripts/check_cost_ceiling.py`` (Story 8.3, FR22 / NFR5).

The script is invoked both as a library (``check_cost_ceiling()`` and
``main()``) and as a subprocess in CI. Tests exercise both surfaces so a
regression in the CLI wiring also fails locally.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_cost_ceiling.py"


def _load_script_module() -> Any:
    """Import the script as a module so we can call its functions in-process."""
    spec = importlib.util.spec_from_file_location("check_cost_ceiling", SCRIPT_PATH)
    assert spec and spec.loader, f"could not load {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script() -> Any:
    return _load_script_module()


def _make_record(cost_usd: float, *, success: bool = True) -> dict[str, Any]:
    return {
        "timestamp": "2026-05-03T12:00:00Z",
        "source_key": "passports/sample.jpeg",
        "doc_type": "Passport",
        "agent": "passport",
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "cost_usd": cost_usd,
        "latency_ms": 1234.5,
        "retry_count": 0,
        "success": success,
        "prompt_version": "0.1.0",
        "extractor_version": "0.1.0",
    }


def _seed_window(
    telemetry_dir: Path,
    *,
    days: int,
    records_per_day: int,
    cost_usd: float,
    end_date: date | None = None,
) -> None:
    """Write ``days`` daily JSONL files with ``records_per_day`` rows each."""
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    end = end_date or date(2026, 5, 3)
    for offset in range(days):
        day = end - timedelta(days=offset)
        path = telemetry_dir / f"{day.isoformat()}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for _ in range(records_per_day):
                fh.write(json.dumps(_make_record(cost_usd)) + "\n")


def _seed_mixed(telemetry_dir: Path) -> None:
    """One day, 9 cheap records (median-friendly) + 1 expensive outlier."""
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    path = telemetry_dir / "2026-05-03.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for _ in range(9):
            fh.write(json.dumps(_make_record(0.01)) + "\n")
        fh.write(json.dumps(_make_record(0.20)) + "\n")  # outlier well above ceiling


def test_passing_case_below_ceiling(script: Any, tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    _seed_window(telemetry_dir, days=7, records_per_day=10, cost_usd=0.025)

    exit_code, message = script.check_cost_ceiling(telemetry_dir, 0.03)

    assert exit_code == 0
    assert "Cost ceiling OK" in message
    assert "$0.0250" in message


def test_breaching_case_above_ceiling(script: Any, tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    _seed_window(telemetry_dir, days=7, records_per_day=10, cost_usd=0.05)

    exit_code, message = script.check_cost_ceiling(telemetry_dir, 0.03)

    assert exit_code == 1
    assert "Cost ceiling breached" in message
    assert "$0.0500" in message
    assert "limit $0.03" in message


def test_mixed_case_median_below_ceiling_passes(script: Any, tmp_path: Path) -> None:
    """Median is the metric — a single high-cost outlier must not break the gate."""
    telemetry_dir = tmp_path / "telemetry"
    _seed_mixed(telemetry_dir)

    exit_code, message = script.check_cost_ceiling(telemetry_dir, 0.03)

    assert exit_code == 0
    assert "Cost ceiling OK" in message


def test_empty_directory_skips(script: Any, tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    telemetry_dir.mkdir()
    exit_code, message = script.check_cost_ceiling(telemetry_dir, 0.03)

    assert exit_code == 0
    assert "no telemetry data" in message


def test_missing_directory_skips(script: Any, tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "does-not-exist"

    exit_code, message = script.check_cost_ceiling(telemetry_dir, 0.03)

    assert exit_code == 0
    assert "no telemetry data" in message


def test_failed_records_excluded_from_window(script: Any, tmp_path: Path) -> None:
    """``success=False`` rows must not influence the median."""
    telemetry_dir = tmp_path / "telemetry"
    telemetry_dir.mkdir()
    path = telemetry_dir / "2026-05-03.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for _ in range(5):
            fh.write(json.dumps(_make_record(0.02)) + "\n")
        for _ in range(20):
            fh.write(json.dumps(_make_record(1.00, success=False)) + "\n")

    exit_code, message = script.check_cost_ceiling(telemetry_dir, 0.03)

    assert exit_code == 0
    assert "5 successful records" in message


def test_window_caps_at_seven_days(script: Any, tmp_path: Path) -> None:
    """Older files outside the 7-day window must not be read."""
    telemetry_dir = tmp_path / "telemetry"
    _seed_window(telemetry_dir, days=7, records_per_day=10, cost_usd=0.025)
    older = telemetry_dir / "2026-04-01.jsonl"
    with older.open("w", encoding="utf-8") as fh:
        for _ in range(50):
            fh.write(json.dumps(_make_record(0.50)) + "\n")

    exit_code, message = script.check_cost_ceiling(telemetry_dir, 0.03)

    assert exit_code == 0
    assert "across 7 day(s)" in message


def test_subprocess_invocation_passing(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    _seed_window(telemetry_dir, days=3, records_per_day=4, cost_usd=0.01)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--telemetry-dir", str(telemetry_dir)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Cost ceiling OK" in result.stdout


def test_subprocess_invocation_breaching(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    _seed_window(telemetry_dir, days=3, records_per_day=4, cost_usd=0.10)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--telemetry-dir",
            str(telemetry_dir),
            "--ceiling",
            "0.03",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Cost ceiling breached" in result.stdout
