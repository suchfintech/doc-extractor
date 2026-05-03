"""Coverage for the eval Scorecard aggregator + the no-PII contract."""
from __future__ import annotations

import json
import re

import pytest

from doc_extractor.eval.scorecard import (
    AgentMetrics,
    EvalResult,
    FieldMetrics,
    Scorecard,
)


def _result(
    agent: str,
    field: str,
    matched: bool,
    *,
    expected: str = "exp",
    actual: str = "act",
    jurisdiction: str = "AU",
    cost_usd: float = 0.001,
) -> EvalResult:
    return EvalResult(
        agent_name=agent,
        field_name=field,
        expected=expected,
        actual=actual,
        matched=matched,
        jurisdiction=jurisdiction,
        cost_usd=cost_usd,
    )


# 3 agents × 2 fields × 2 jurisdictions = 12 EvalResults; matched pattern crafted
# so each per-agent / per-field / per-jurisdiction bucket has a known answer.
@pytest.fixture
def synthetic_results() -> list[EvalResult]:
    return [
        # Passport / passport_number — both jurisdictions match
        _result("Passport", "passport_number", True, jurisdiction="AU"),
        _result("Passport", "passport_number", True, jurisdiction="CN"),
        # Passport / dob — AU matches, CN does not
        _result("Passport", "dob", True, jurisdiction="AU"),
        _result("Passport", "dob", False, jurisdiction="CN"),
        # PaymentReceipt / amount — AU match, CN match
        _result("PaymentReceipt", "amount", True, jurisdiction="AU"),
        _result("PaymentReceipt", "amount", True, jurisdiction="CN"),
        # PaymentReceipt / payee — both miss
        _result("PaymentReceipt", "payee", False, jurisdiction="AU"),
        _result("PaymentReceipt", "payee", False, jurisdiction="CN"),
        # DriverLicence / licence_number — AU match, CN miss
        _result("DriverLicence", "licence_number", True, jurisdiction="AU"),
        _result("DriverLicence", "licence_number", False, jurisdiction="CN"),
        # DriverLicence / dob — both match
        _result("DriverLicence", "dob", True, jurisdiction="AU"),
        _result("DriverLicence", "dob", True, jurisdiction="CN"),
    ]


def test_top_level_counts_and_totals(synthetic_results: list[EvalResult]) -> None:
    sc = Scorecard.from_results(
        synthetic_results,
        extractor_version="0.1.0",
        run_timestamp="2026-05-03T00:00:00Z",
    )

    assert sc.total_examples == 12
    assert sc.total_cost_usd == pytest.approx(12 * 0.001)
    assert sc.extractor_version == "0.1.0"
    assert sc.run_timestamp == "2026-05-03T00:00:00Z"


def test_per_agent_metrics(synthetic_results: list[EvalResult]) -> None:
    sc = Scorecard.from_results(synthetic_results, extractor_version="0.1.0")

    # Passport: 4 rows, 3 matched. All actuals + all expecteds non-empty.
    passport = sc.per_agent["Passport"]
    assert isinstance(passport, AgentMetrics)
    assert passport.examples == 4
    assert passport.precision == pytest.approx(3 / 4)
    assert passport.recall == pytest.approx(3 / 4)
    # Both fields had at least one match → field_coverage == 1.0
    assert passport.field_coverage == pytest.approx(1.0)

    # PaymentReceipt: 4 rows, 2 matched (amount × 2). payee never matched.
    pr = sc.per_agent["PaymentReceipt"]
    assert pr.examples == 4
    assert pr.precision == pytest.approx(2 / 4)
    assert pr.recall == pytest.approx(2 / 4)
    # Only 1 of 2 fields had a match → coverage = 0.5
    assert pr.field_coverage == pytest.approx(0.5)


def test_per_field_match_rates(synthetic_results: list[EvalResult]) -> None:
    sc = Scorecard.from_results(synthetic_results, extractor_version="0.1.0")

    assert sc.per_field["Passport"]["passport_number"] == FieldMetrics(
        match_rate=1.0, examples=2
    )
    assert sc.per_field["Passport"]["dob"] == FieldMetrics(match_rate=0.5, examples=2)
    assert sc.per_field["PaymentReceipt"]["payee"] == FieldMetrics(
        match_rate=0.0, examples=2
    )


def test_per_jurisdiction_buckets(synthetic_results: list[EvalResult]) -> None:
    sc = Scorecard.from_results(synthetic_results, extractor_version="0.1.0")

    # AU: 6 rows total, 5 matched. Per-agent split: Passport(2/2), PaymentReceipt(1/2), DriverLicence(2/2).
    au_passport = sc.per_jurisdiction["AU"]["Passport"]
    assert au_passport.examples == 2
    assert au_passport.precision == pytest.approx(1.0)
    assert au_passport.recall == pytest.approx(1.0)

    cn_pr = sc.per_jurisdiction["CN"]["PaymentReceipt"]
    assert cn_pr.examples == 2
    assert cn_pr.precision == pytest.approx(0.5)


def test_to_json_round_trips_through_stdlib_json(
    synthetic_results: list[EvalResult],
) -> None:
    sc = Scorecard.from_results(synthetic_results, extractor_version="0.1.0")
    payload = sc.to_json()

    parsed = json.loads(payload)
    assert parsed["total_examples"] == 12
    assert "per_agent" in parsed
    assert "Passport" in parsed["per_agent"]


def test_to_json_excludes_pii_strings() -> None:
    pii_account = "6217 **** **** 0083"
    pii_name = "陳大文"
    pii_dob = "1985-07-12"

    results = [
        EvalResult(
            agent_name="Passport",
            field_name="account_number",
            expected=pii_account,
            actual=pii_account,
            matched=True,
            jurisdiction="HK",
            cost_usd=0.002,
        ),
        EvalResult(
            agent_name="Passport",
            field_name="name_cjk",
            expected=pii_name,
            actual=pii_name,
            matched=True,
            jurisdiction="HK",
        ),
        EvalResult(
            agent_name="Passport",
            field_name="dob",
            expected=pii_dob,
            actual="1985-07-13",
            matched=False,
            jurisdiction="HK",
        ),
    ]

    payload = Scorecard.from_results(results, extractor_version="0.1.0").to_json()

    for pii in (pii_account, pii_name, pii_dob, "1985-07-13"):
        assert pii not in payload, f"PII string {pii!r} leaked into scorecard JSON"


def test_empty_results_yields_zeroed_scorecard() -> None:
    sc = Scorecard.from_results([], extractor_version="0.1.0")

    assert sc.total_examples == 0
    assert sc.total_cost_usd == 0.0
    assert sc.per_agent == {}
    assert sc.per_field == {}
    assert sc.per_jurisdiction == {}


def test_run_timestamp_defaults_to_iso8601_z() -> None:
    sc = Scorecard.from_results([], extractor_version="0.1.0")
    # Pattern: 2026-05-03T12:34:56Z
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", sc.run_timestamp)


def test_safe_division_when_all_actuals_or_expecteds_are_empty() -> None:
    """precision/recall must be 0.0 (not NaN) when their denominator is 0."""
    results = [
        EvalResult(
            agent_name="Passport",
            field_name="dob",
            expected="",
            actual="",
            matched=False,
        ),
        EvalResult(
            agent_name="Passport",
            field_name="dob",
            expected="",
            actual="",
            matched=False,
        ),
    ]
    sc = Scorecard.from_results(results, extractor_version="0.1.0")

    metrics = sc.per_agent["Passport"]
    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    # JSON survives stdlib parsing — no NaN slipped through.
    json.loads(sc.to_json())
