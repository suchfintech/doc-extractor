"""Story 8.2 — telemetry no-PII regression test.

Worker-1's :func:`record_extraction` (Story 8.1) takes only operational
metrics via a keyword-only signature. The signature itself is the
PII-exclusion filter (NFR10 / FR38) — adding any extracted-content field
is a schema migration, not a callsite change. This test layers a
defence-in-depth regex sweep on top of that contract:

1. The standard 11-field call writes a line with zero matches against the
   PII pattern list below — proves the call shape itself is clean.
2. A PaymentReceipt instance carrying CJK names + masked account numbers
   sits in the same Python scope as the ``record_extraction`` call. The
   instance never reaches the JSONL because the function physically cannot
   accept it (no ``**kwargs``, no positional-after-* fall-through).
3. Passing a forbidden kwarg (``name=``) raises ``TypeError`` from
   Python's keyword-only enforcement.
4. Determinism: with ``_utcnow`` pinned, two calls produce byte-identical
   JSONL lines.

The PII patterns are local to this test — telemetry's clean signature is
the contract; this is a tripwire, not a runtime sanitiser.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from doc_extractor import telemetry
from doc_extractor.schemas.ids import Passport
from doc_extractor.schemas.payment_receipt import PaymentReceipt

# Strings that should never appear in a telemetry line — pattern source.
PII_REGEX_PATTERNS: tuple[str, ...] = (
    r"[一-鿿]",                        # CJK Unified Ideographs
    r"\*{2,}",                         # account-number masks always carry runs of `*`
    r"\d{2}-\d{4}-\d{7}-\d{2}",        # NZ-style hyphenated bank account
    r"\d{3}-\d{2}-\d{4}",              # SSN-like
    r"\d{18}",                         # CN national ID number
    r"\d{4}-\d{2}-\d{2}(?!T)",         # DOB-like, NOT followed by `T` (so ISO timestamps slip through)
    r"P<[A-Z]{3}",                     # MRZ line 1 prefix (TD3)
)

# Field names from extracted Pydantic schemas that must never appear as
# JSON keys in telemetry. If any leaks, a future call-site change has
# bypassed the keyword-only signature contract.
PII_FIELD_NAMES: tuple[str, ...] = (
    "name_latin",
    "name_cjk",
    "dob",
    "id_card_number",
    "passport_number",
    "mrz_line_1",
    "mrz_line_2",
    "receipt_debit_account_name",
    "receipt_debit_account_number",
    "receipt_credit_account_name",
    "receipt_credit_account_number",
    "receipt_counterparty_name",
    "receipt_counterparty_account",
    "place_of_birth",
)


def _standard_call_kwargs(**overrides: Any) -> dict[str, Any]:
    """The canonical 11-field record_extraction kwargs — overridable per test."""
    base: dict[str, Any] = {
        "source_key": "passports/case-001.jpeg",
        "doc_type": "Passport",
        "agent": "passport",
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "cost_usd": 0.0023,
        "latency_ms": 1234.5,
        "retry_count": 0,
        "success": True,
        "prompt_version": "0.1.0",
        "extractor_version": "0.1.0",
    }
    base.update(overrides)
    return base


def _assert_no_pii(line: str) -> None:
    for pattern in PII_REGEX_PATTERNS:
        assert not re.search(pattern, line), (
            f"PII regex {pattern!r} matched telemetry line: {line!r}"
        )
    for field in PII_FIELD_NAMES:
        assert field not in line, (
            f"PII field name {field!r} appeared in telemetry line: {line!r}"
        )


def _read_telemetry_lines(directory: Path) -> list[str]:
    files = sorted(directory.glob("*.jsonl"))
    assert files, f"no telemetry files written under {directory}"
    contents: list[str] = []
    for path in files:
        contents.extend(path.read_text(encoding="utf-8").splitlines())
    return contents


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Pin ``_utcnow`` to a deterministic instant."""
    fixed = datetime(2026, 5, 3, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(telemetry, "_utcnow", lambda: fixed)
    return fixed


@pytest.fixture
def telemetry_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Redirect telemetry writes into a fresh tmp directory per test."""
    directory = tmp_path / "telemetry"
    monkeypatch.setattr(telemetry, "_TELEMETRY_DIR", directory)
    monkeypatch.setattr(telemetry, "_files_written_this_process", set())
    return directory


def test_direct_call_writes_no_pii_patterns(
    telemetry_dir: Path, fixed_clock: datetime
) -> None:
    telemetry.record_extraction(**_standard_call_kwargs())
    lines = _read_telemetry_lines(telemetry_dir)
    assert len(lines) == 1
    _assert_no_pii(lines[0])


def test_pii_instance_in_scope_does_not_leak(
    telemetry_dir: Path, fixed_clock: datetime
) -> None:
    """A PaymentReceipt full of PII sits in the same scope as the call.

    The function's keyword-only signature physically cannot consume the
    instance — there is no ``**kwargs`` slot for it to slip through.
    """
    receipt = PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_debit_account_name="张三",
        receipt_debit_account_number="6217 **** **** 0083",
        receipt_credit_account_name="李四",
        receipt_credit_account_number="02-0248-0242329-02",
        receipt_amount="100.00",
    )
    passport = Passport(
        doc_type="Passport",
        passport_number="X9988776",
        name_latin="DOE, JANE",
        name_cjk="多伊",
        dob="1985-09-12",
        mrz_line_1="P<NZLDOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
    )
    # Reference both so static analysis knows they are intentionally in scope.
    assert receipt.receipt_debit_account_name == "张三"
    assert passport.name_latin == "DOE, JANE"

    telemetry.record_extraction(
        **_standard_call_kwargs(
            source_key="receipts/r001.jpeg",
            doc_type="PaymentReceipt",
            agent="payment_receipt",
            model="claude-sonnet-4-6-20260101",
        )
    )

    lines = _read_telemetry_lines(telemetry_dir)
    assert len(lines) == 1
    _assert_no_pii(lines[0])


def test_forbidden_kwargs_raise_type_error(
    telemetry_dir: Path, fixed_clock: datetime
) -> None:
    """Python's keyword-only signature rejects unknown kwargs at call time."""
    standard = _standard_call_kwargs()
    with pytest.raises(TypeError):
        telemetry.record_extraction(  # type: ignore[call-arg]
            name="张三",
            **standard,
        )

    with pytest.raises(TypeError):
        telemetry.record_extraction(  # type: ignore[call-arg]
            account_number="6217 **** **** 0083",
            **standard,
        )

    with pytest.raises(TypeError):
        telemetry.record_extraction(  # type: ignore[call-arg]
            dob="1985-09-12",
            **standard,
        )


def test_fixed_clock_yields_byte_identical_lines(
    telemetry_dir: Path, fixed_clock: datetime
) -> None:
    telemetry.record_extraction(**_standard_call_kwargs())
    telemetry.record_extraction(**_standard_call_kwargs())

    lines = _read_telemetry_lines(telemetry_dir)
    assert len(lines) == 2
    assert lines[0] == lines[1]


def test_pattern_list_self_check_against_known_pii_strings() -> None:
    """Sanity-check the regex set itself catches the PII it is meant to.

    A regression here means the patterns silently stopped matching real PII
    — without this guard, the no-PII tests above would still pass even if
    every pattern were broken.
    """
    pii_samples: Iterable[str] = (
        "张三",
        "6217 **** **** 0083",
        "02-0248-0242329-02",
        "123-45-6789",
        "110101199003078123",
        "1985-09-12",
        "P<NZLDOE<<JANE",
    )
    for sample in pii_samples:
        assert any(re.search(p, sample) for p in PII_REGEX_PATTERNS), (
            f"sample {sample!r} should match at least one PII regex"
        )
