"""VerifierAudit — auditor's per-field verdict on a specialist's claim.

The verifier agent receives the source image plus the specialist's claimed
Pydantic instance dumped to JSON, and returns this structured response. The
``overall`` field is deterministically derived from ``field_audits`` (any
disagree → ``fail``; no disagree but ≥1 abstain → ``uncertain``; otherwise
``pass``) — a ``model_validator`` enforces the derivation post-output, so a
verifier model that contradicts itself ("pass" alongside a disagree field)
gets normalised before the audit reaches the disagreement queue (Story 3.9).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

FieldVerdict = Literal["agree", "disagree", "abstain"]
OverallVerdict = Literal["pass", "fail", "uncertain"]


def _derive_overall(field_audits: dict[str, FieldVerdict]) -> OverallVerdict:
    """Deterministic rollup of per-field verdicts.

    - any ``disagree`` → ``fail``
    - no ``disagree`` but ≥1 ``abstain`` → ``uncertain``
    - all ``agree`` (or empty) → ``pass``
    """
    if any(v == "disagree" for v in field_audits.values()):
        return "fail"
    if any(v == "abstain" for v in field_audits.values()):
        return "uncertain"
    return "pass"


class VerifierAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_audits: dict[str, FieldVerdict]
    overall: OverallVerdict = "pass"
    notes: str = ""

    @model_validator(mode="after")
    def _pin_overall_to_field_audits(self) -> VerifierAudit:
        # Override the model's self-reported overall with the deterministic
        # derivation. Catches verifier-model drift where it claims `pass` while
        # also reporting a `disagree` field. ``object.__setattr__`` bypasses
        # validate_assignment so we don't recurse through this validator.
        object.__setattr__(self, "overall", _derive_overall(self.field_audits))
        return self
