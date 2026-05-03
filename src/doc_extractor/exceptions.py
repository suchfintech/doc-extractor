"""Domain exceptions for doc-extractor."""

from __future__ import annotations


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
