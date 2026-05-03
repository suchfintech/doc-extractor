"""VerificationReport schema — identity-verification outcomes.

Covers NZ EIV (Electronic Identity Verification) reports, in-person
verification certificates, and third-party verification service outputs
(Trulioo, Onfido, Jumio). The shape is deliberately format-agnostic: who
verified whom, when, by what method, and the outcome.

The verified subject's ID-document type and number are captured as plain
strings (`subject_id_type`, `subject_id_number`) — verification reports
typically transcribe these from the source ID rather than carrying the
original document image.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class VerificationReport(Frontmatter):
    verifier_name: str | None = ""
    verification_date: str | None = ""
    verification_method: str | None = ""
    subject_name: str | None = ""
    subject_id_type: str | None = ""
    subject_id_number: str | None = ""
    verification_outcome: str | None = ""
