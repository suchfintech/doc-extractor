"""Classification schema — the canonical 15-way DOC_TYPES enumeration.

The classifier is the entry point for the vision pipeline (FR2): it routes
each input image to one of fifteen document types, and downstream the router
dispatches to a specialist agent (or, for v1, only the Passport specialist
exists; the rest return ``NotImplementedError`` per Story 1.10).
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field

# Kept as `TypeAlias` (not PEP 695 `type`) so ``typing.get_args(DOC_TYPES)``
# returns the 15-string tuple — the canonical-list invariant test depends on it.
DOC_TYPES: TypeAlias = Literal[  # noqa: UP040
    "Passport",
    "DriverLicence",
    "NationalID",
    "Visa",
    "PEP_Declaration",
    "VerificationReport",
    "ApplicationForm",
    "BankStatement",
    "BankAccountConfirmation",
    "CompanyExtract",
    "EntityOwnership",
    "ProofOfAddress",
    "TaxResidency",
    "PaymentReceipt",
    "Other",
]


class Classification(BaseModel):
    """Structured-output contract for the ClassifierAgent."""

    doc_type: DOC_TYPES
    jurisdiction: str = Field(
        default="OTHER",
        description="ISO-3166-1 alpha-2 country code (e.g. CN, NZ, AU) or 'OTHER' if unclear.",
    )
    doc_subtype: str = Field(
        default="",
        description="Free-form subtype hint (e.g. 'P' for ordinary passport); empty if unknown.",
    )
