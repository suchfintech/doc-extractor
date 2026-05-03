"""ApplicationForm schema — customer-onboarding / credit application forms.

Covers the LEL onboarding form and generic AML customer-onboarding forms.
Both handwritten and digital fields are supported — the agent prompt
handles the OCR variation; the schema is shape-only.

The application's `application_type` is a free-form string because the
list of acceptable types varies per partner / business line; downstream
consumers can normalise / classify against their own enumeration.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class ApplicationForm(Frontmatter):
    application_date: str | None = ""
    applicant_name: str | None = ""
    applicant_dob: str | None = ""
    application_type: str | None = ""
    applicant_address: str | None = ""
    applicant_occupation: str | None = ""
