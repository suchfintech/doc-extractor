"""Purity guarantees for the body_parse module.

The body-parse layer is fed thousands of times per eval run, so callers
rely on it being a *function* in the mathematical sense — same input,
same output, no observable side effects. Worker-1's 3.4 (CN labels) and
worker-3's 3.5 (NZ narrative) both contribute parsers; this file covers
each one as it lands. Adding a new parser? Append a section.
"""
from __future__ import annotations

import pytest

from doc_extractor.body_parse.nz_narrative import parse_nz

NZ_CANONICAL = (
    'Bank transfer of NZD 15,000.00 sent to account GM6040 '
    '(account number 02-0248-0242329-02) from account "Free Up-00" '
    '(account number 38-9024-0437881-00) on Tuesday, 1 July 2025'
)
NZ_VARIANT_USD = (
    "Bank transfer of USD 250.00 sent to account Acme "
    "(account number 12-3456-7890123-00) from account Payer "
    "(account number 98-7654-3210987-99) on Friday, 5 December 2025"
)


# ----- parse_nz (Story 3.5) -----


def test_parse_nz_is_idempotent() -> None:
    """Calling twice with the same input yields equal results."""
    a = parse_nz(NZ_CANONICAL)
    b = parse_nz(NZ_CANONICAL)
    assert a == b
    # Distinct instances (no aliased global cache returning the same object).
    assert a is not b


def test_parse_nz_does_not_leak_state_across_calls() -> None:
    """Interleaving with a different input must not perturb either result."""
    first = parse_nz(NZ_CANONICAL)
    other = parse_nz(NZ_VARIANT_USD)
    again = parse_nz(NZ_CANONICAL)

    assert first == again
    assert other.receipt_currency == "USD"
    assert again.receipt_currency == "NZD"


def test_parse_nz_does_not_mutate_input() -> None:
    body = NZ_CANONICAL
    snapshot = body
    parse_nz(body)
    assert body == snapshot


def test_parse_nz_module_has_no_mutable_module_state() -> None:
    """No mutable globals — only the compiled regex pattern objects + constants."""
    import doc_extractor.body_parse.nz_narrative as nz

    forbidden_types = (list, dict, set)
    for name in dir(nz):
        if name.startswith("_") and name.endswith("_"):
            continue  # dunders
        value = getattr(nz, name)
        if name == "_QUOTE_CHARS":
            continue  # immutable str constant
        assert not isinstance(value, forbidden_types), (
            f"Module-level mutable state at {name!r}: {type(value).__name__}"
        )


# ----- parse_cn (Story 3.4 — populated when worker-1's parser lands) -----


@pytest.mark.skip(reason="parse_cn lands with Story 3.4 (worker-1)")
def test_parse_cn_purity_placeholder() -> None:
    pass
