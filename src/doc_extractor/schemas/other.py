"""Other — catch-all schema for documents not matching any specialist.

The classifier (Story 1.7) routes any image that doesn't fit the 14 typed
specialists here. The output is intentionally loose: a description, an
OCR-style raw dump, and free-text notes for the model's commentary.

**Low confidence is acceptable.** Other is the graceful-degradation surface
— the contract is "don't crash" rather than "extract correctly". The
verifier (Story 3.7) does not run on Other; downstream consumers know to
treat Other documents as needing human review.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class Other(Frontmatter):
    description: str | None = ""
    extracted_text: str | None = ""
    notes: str | None = ""
