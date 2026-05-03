"""Eval scorecard model and aggregation.

The Scorecard is the JSON-serialisable output of the eval harness. It is
**strictly metric-only** — by design it contains agent / field / jurisdiction
*names* plus floats and counts, and never any extracted *value* (FR38, NFR10).

Aggregation lives on the model itself via :meth:`Scorecard.from_results` so
callers can write::

    Scorecard.from_results(results, extractor_version="0.1.0").to_json()

without reaching into helper modules.

Metric definitions
------------------
Each :class:`EvalResult` is one ``(agent, field)`` comparison for one example.
Without an explicit ``example_id`` the v1 metrics treat each row as one
comparison; this keeps the math local and unambiguous, and the eval harness
emits one EvalResult per ``(extraction, field)`` pair so the row count
already matches "field-comparisons performed".

* ``AgentMetrics.precision`` — matched / non-empty actuals (of the rows the
  model produced a value for, what fraction matched).
* ``AgentMetrics.recall`` — matched / non-empty expecteds (of the rows the
  ground truth has a value for, what fraction the model recovered).
* ``AgentMetrics.field_coverage`` — distinct fields with ≥1 match /
  distinct fields seen for that agent.
* ``AgentMetrics.examples`` — total field-comparisons logged for that agent.
* ``FieldMetrics.match_rate`` — matched / examples for that ``(agent, field)``.

Dividing by zero yields ``0.0`` rather than ``NaN`` so the JSON survives
``json.loads`` round-trips and CI gates can compare numerically.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class EvalResult(BaseModel):
    """One field-level comparison emitted by the eval harness.

    ``expected``/``actual`` are PII (account numbers, names, DOBs). The
    Scorecard consumes them only to derive ``matched`` aggregates and never
    copies them into its own state.
    """

    model_config = ConfigDict(frozen=True)

    agent_name: str
    field_name: str
    expected: str
    actual: str
    matched: bool
    jurisdiction: str = ""
    cost_usd: float = 0.0


class AgentMetrics(BaseModel):
    precision: float = 0.0
    recall: float = 0.0
    field_coverage: float = 0.0
    examples: int = 0


class FieldMetrics(BaseModel):
    match_rate: float = 0.0
    examples: int = 0


def _safe_div(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _utc_now_iso() -> str:
    """ISO 8601 with explicit ``Z`` suffix for UTC."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _aggregate_agent(rows: list[EvalResult]) -> AgentMetrics:
    if not rows:
        return AgentMetrics()
    matched = sum(1 for r in rows if r.matched)
    actuals = sum(1 for r in rows if r.actual)
    expecteds = sum(1 for r in rows if r.expected)

    fields_seen: set[str] = {r.field_name for r in rows}
    fields_with_match: set[str] = {r.field_name for r in rows if r.matched}

    return AgentMetrics(
        precision=_safe_div(matched, actuals),
        recall=_safe_div(matched, expecteds),
        field_coverage=_safe_div(len(fields_with_match), len(fields_seen)),
        examples=len(rows),
    )


class Scorecard(BaseModel):
    """Aggregated metrics for a single eval run. JSON-safe; PII-free by design."""

    per_agent: dict[str, AgentMetrics] = Field(default_factory=dict)
    per_field: dict[str, dict[str, FieldMetrics]] = Field(default_factory=dict)
    per_jurisdiction: dict[str, dict[str, AgentMetrics]] = Field(default_factory=dict)
    total_examples: int = 0
    total_cost_usd: float = 0.0
    extractor_version: str
    run_timestamp: str

    @classmethod
    def from_results(
        cls,
        results: list[EvalResult],
        *,
        extractor_version: str = "0.1.0",
        run_timestamp: str | None = None,
    ) -> Scorecard:
        by_agent: dict[str, list[EvalResult]] = defaultdict(list)
        by_agent_field: dict[str, dict[str, list[EvalResult]]] = defaultdict(
            lambda: defaultdict(list)
        )
        by_jurisdiction_agent: dict[str, dict[str, list[EvalResult]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for r in results:
            by_agent[r.agent_name].append(r)
            by_agent_field[r.agent_name][r.field_name].append(r)
            by_jurisdiction_agent[r.jurisdiction][r.agent_name].append(r)

        per_agent = {agent: _aggregate_agent(rows) for agent, rows in by_agent.items()}

        per_field: dict[str, dict[str, FieldMetrics]] = {}
        for agent, fields in by_agent_field.items():
            per_field[agent] = {
                field: FieldMetrics(
                    match_rate=_safe_div(
                        sum(1 for r in rows if r.matched), len(rows)
                    ),
                    examples=len(rows),
                )
                for field, rows in fields.items()
            }

        per_jurisdiction = {
            jur: {agent: _aggregate_agent(rows) for agent, rows in agents.items()}
            for jur, agents in by_jurisdiction_agent.items()
        }

        return cls(
            per_agent=per_agent,
            per_field=per_field,
            per_jurisdiction=per_jurisdiction,
            total_examples=len(results),
            total_cost_usd=sum(r.cost_usd for r in results),
            extractor_version=extractor_version,
            run_timestamp=run_timestamp or _utc_now_iso(),
        )

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)
