"""Domain exceptions for doc-extractor."""

from __future__ import annotations

# Story 3.8 — re-export Pydantic's ValidationError under a project-local
# alias so the retry layer / pipeline can catch one symbol without dragging
# pydantic into every call-site's import surface.
from pydantic import ValidationError as PydanticValidationError

__all__ = [
    "AuthenticationError",
    "BodyParseUnmatchedError",
    "ConfigurationError",
    "DocExtractorError",
    "PDFConversionError",
    "PydanticValidationError",
]


class DocExtractorError(Exception):
    """Base for all doc-extractor errors."""


class AuthenticationError(DocExtractorError):
    """Raised when a provider's required API key env var is missing or empty."""


class ConfigurationError(DocExtractorError):
    """Raised when configuration is malformed, missing, or fails validation."""


class BodyParseUnmatchedError(DocExtractorError):
    """Raised when neither parse_chinese nor parse_nz can extract anything from a body.

    Carries the (truncated) body for diagnostic logs without exposing PII to
    callers that have already filtered the message.
    """


class PDFConversionError(DocExtractorError):
    """Raised when a PDF cannot be parsed or rendered to images.

    Wraps PyMuPDF errors so callers can catch one project-local exception
    instead of importing fitz / pymupdf to inspect upstream errors.
    """
