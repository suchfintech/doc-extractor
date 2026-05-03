"""Unit tests for ``scripts/check_eval_thresholds.py`` (Story 2.6 / NFR18).

The script is invoked both as a library (``check_eval_thresholds()`` and
``main()``) and as a subprocess in CI. Tests exercise both surfaces so a
regression in the CLI wiring also fails locally — same test pattern as
worker-2's ``test_cost_ceiling_script.py`` (Story 8.3).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_eval_thresholds.py"


def _load_script_module() -> Any:
    """Import the script as a module so we can call its functions in-process."""
    spec = importlib.util.spec_from_file_location("check_eval_thresholds", SCRIPT_PATH)
    assert spec and spec.loader, f"could not load {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script() -> Any:
    return _load_script_module()


def _scorecard(per_field: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Build a minimal scorecard JSON in the shape ``Scorecard.to_json`` produces."""
    return {
        "extractor_version": "0.1.0",
        "generated_at": "2026-05-03T12:00:00Z",
        "per_agent": {},
        "per_field": per_field,
    }


def _write(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


_BASELINE_THRESHOLDS = """\
_default: 0.90
Passport:
  name_latin: 0.98
  doc_number: 0.98
  expiry_date: 0.98
PaymentReceipt:
  receipt_amount: 0.95
"""


@pytest.fixture
def thresholds_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "thresholds.yaml"
    path.write_text(_BASELINE_THRESHOLDS, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Passing path
# ---------------------------------------------------------------------------


def test_passing_scorecard_returns_exit_zero(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    sc_path = _write(
        tmp_path / "2026-05-03T12-00-00.json",
        _scorecard(
            {
                "Passport": {
                    "name_latin": {"match_rate": 0.99, "examples": 100},
                    "doc_number": {"match_rate": 1.00, "examples": 100},
                    "expiry_date": {"match_rate": 0.985, "examples": 100},
                },
                "PaymentReceipt": {
                    "receipt_amount": {"match_rate": 0.96, "examples": 50},
                },
            }
        ),
    )

    code, msg = script.check_eval_thresholds(
        scorecard_path=sc_path, thresholds_path=thresholds_yaml
    )
    assert code == 0, msg
    assert "passes all per-field floors" in msg


# ---------------------------------------------------------------------------
# Breach paths
# ---------------------------------------------------------------------------


def test_breach_below_explicit_threshold_returns_exit_one(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    sc_path = _write(
        tmp_path / "2026-05-03.json",
        _scorecard(
            {
                "Passport": {
                    # Passport.name_latin floor is 0.98; this is below.
                    "name_latin": {"match_rate": 0.85, "examples": 100},
                    "doc_number": {"match_rate": 0.99, "examples": 100},
                }
            }
        ),
    )

    code, msg = script.check_eval_thresholds(
        scorecard_path=sc_path, thresholds_path=thresholds_yaml
    )
    assert code == 1
    assert "Passport.name_latin" in msg
    assert "0.850" in msg
    assert "0.980" in msg


def test_breach_below_default_fallback_threshold(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    """A field on an unlisted agent uses ``_default`` (0.90). 0.85 trips it."""
    sc_path = _write(
        tmp_path / "2026-05-03.json",
        _scorecard(
            {
                "BankStatement": {
                    "statement_balance": {"match_rate": 0.85, "examples": 50},
                }
            }
        ),
    )

    code, msg = script.check_eval_thresholds(
        scorecard_path=sc_path, thresholds_path=thresholds_yaml
    )
    assert code == 1
    assert "BankStatement.statement_balance" in msg
    assert "0.850" in msg
    assert "0.900" in msg  # _default


def test_default_fallback_passes_at_or_above_threshold(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    """0.92 ≥ 0.90 default → pass for an unlisted agent."""
    sc_path = _write(
        tmp_path / "2026-05-03.json",
        _scorecard(
            {
                "BankStatement": {
                    "statement_balance": {"match_rate": 0.92, "examples": 50},
                }
            }
        ),
    )
    code, _msg = script.check_eval_thresholds(
        scorecard_path=sc_path, thresholds_path=thresholds_yaml
    )
    assert code == 0


def test_listed_agent_with_unlisted_field_uses_default(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    """Passport has explicit thresholds for some fields; an UNLISTED Passport
    field falls through to ``_default``. 0.92 → pass; 0.85 → fail."""
    sc_passing = _write(
        tmp_path / "2026-05-03A.json",
        _scorecard(
            {
                "Passport": {
                    "passport_number": {"match_rate": 0.92, "examples": 100},
                }
            }
        ),
    )
    code_a, _ = script.check_eval_thresholds(
        scorecard_path=sc_passing, thresholds_path=thresholds_yaml
    )
    assert code_a == 0

    sc_failing = _write(
        tmp_path / "2026-05-03B.json",
        _scorecard(
            {
                "Passport": {
                    "passport_number": {"match_rate": 0.85, "examples": 100},
                }
            }
        ),
    )
    code_b, msg_b = script.check_eval_thresholds(
        scorecard_path=sc_failing, thresholds_path=thresholds_yaml
    )
    assert code_b == 1
    assert "Passport.passport_number" in msg_b
    assert "0.900" in msg_b


# ---------------------------------------------------------------------------
# Skip paths — permissive on missing / empty inputs
# ---------------------------------------------------------------------------


def test_missing_scorecard_directory_skips(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    code, msg = script.check_eval_thresholds(
        scorecard_dir=tmp_path / "does-not-exist",
        thresholds_path=thresholds_yaml,
    )
    assert code == 0
    assert "no scorecard yet" in msg


def test_empty_scorecard_directory_skips(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    empty_dir = tmp_path / "empty-scorecards"
    empty_dir.mkdir()
    code, msg = script.check_eval_thresholds(
        scorecard_dir=empty_dir, thresholds_path=thresholds_yaml
    )
    assert code == 0
    assert "no scorecard yet" in msg


def test_empty_per_field_skips(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    sc_path = _write(tmp_path / "2026-05-03.json", _scorecard({}))
    code, msg = script.check_eval_thresholds(
        scorecard_path=sc_path, thresholds_path=thresholds_yaml
    )
    assert code == 0
    assert "no per-field metrics" in msg


# ---------------------------------------------------------------------------
# Discovery — latest-by-filename wins
# ---------------------------------------------------------------------------


def test_latest_scorecard_in_dir_wins(
    script: Any, tmp_path: Path, thresholds_yaml: Path
) -> None:
    """Filenames sort lexicographically; the newest (last) wins. The older
    (passing) file is shadowed by a newer (breaching) one."""
    scorecard_dir = tmp_path / "scorecards"
    scorecard_dir.mkdir()
    _write(
        scorecard_dir / "2026-05-01.json",
        _scorecard(
            {"Passport": {"name_latin": {"match_rate": 0.99, "examples": 100}}}
        ),
    )
    _write(
        scorecard_dir / "2026-05-03.json",
        _scorecard(
            {"Passport": {"name_latin": {"match_rate": 0.50, "examples": 100}}}
        ),
    )

    code, msg = script.check_eval_thresholds(
        scorecard_dir=scorecard_dir, thresholds_path=thresholds_yaml
    )
    assert code == 1
    assert "2026-05-03.json" in msg
    assert "Passport.name_latin" in msg


# ---------------------------------------------------------------------------
# Subprocess end-to-end — CLI wiring smoke
# ---------------------------------------------------------------------------


def test_cli_subprocess_passes_on_clean_scorecard(
    tmp_path: Path, thresholds_yaml: Path
) -> None:
    sc_path = _write(
        tmp_path / "2026-05-03.json",
        _scorecard(
            {"Passport": {"name_latin": {"match_rate": 0.99, "examples": 100}}}
        ),
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--scorecard",
            str(sc_path),
            "--thresholds",
            str(thresholds_yaml),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "passes all per-field floors" in result.stdout


def test_cli_subprocess_fails_on_breaching_scorecard(
    tmp_path: Path, thresholds_yaml: Path
) -> None:
    sc_path = _write(
        tmp_path / "2026-05-03.json",
        _scorecard(
            {"Passport": {"name_latin": {"match_rate": 0.50, "examples": 100}}}
        ),
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--scorecard",
            str(sc_path),
            "--thresholds",
            str(thresholds_yaml),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Passport.name_latin" in result.stderr


# ---------------------------------------------------------------------------
# Threshold lookup primitive — sanity-check the resolver
# ---------------------------------------------------------------------------


def test_resolve_threshold_per_agent_per_field_wins(script: Any) -> None:
    thresholds = {
        "_default": 0.90,
        "Passport": {"name_latin": 0.98},
    }
    assert script._resolve_threshold(thresholds, "Passport", "name_latin") == 0.98
    # Unlisted field on Passport → _default.
    assert script._resolve_threshold(thresholds, "Passport", "passport_number") == 0.90
    # Unlisted agent → _default.
    assert script._resolve_threshold(thresholds, "BankStatement", "balance") == 0.90


def test_resolve_threshold_missing_default_returns_zero(script: Any) -> None:
    """Defensive fallback: a YAML without ``_default`` produces a 0.0 floor.
    The repo YAML always sets ``_default`` so this is a typo-guard."""
    thresholds = {"Passport": {"name_latin": 0.98}}
    assert script._resolve_threshold(thresholds, "BankStatement", "balance") == 0.0


# ---------------------------------------------------------------------------
# Real repo YAML loads cleanly
# ---------------------------------------------------------------------------


def test_repo_thresholds_yaml_loads_and_has_default(script: Any) -> None:
    """Sentinel: the actual ``src/doc_extractor/eval/thresholds.yaml`` parses
    and declares ``_default``. Catches a typo'd YAML that would silently
    weaken the gate (every field would fall through to a 0.0 floor)."""
    repo_yaml = REPO_ROOT / "src" / "doc_extractor" / "eval" / "thresholds.yaml"
    data = script._load_thresholds(repo_yaml)
    assert "_default" in data
    assert isinstance(data["_default"], int | float)
    assert 0.0 < float(data["_default"]) <= 1.0
