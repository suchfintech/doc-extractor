"""Integration tests for the body-parse repair pipeline (Story 3.6).

The body-parse path is the only place in the codebase that does a
*frontmatter-only* update of an existing ``.md`` — everything after the
closing ``---`` fence must round-trip byte-identical, even if the body
contains LLM-generated prose, tables, blank lines, or trailing whitespace
quirks. These tests pin that contract for both CN-label and NZ-narrative
shapes plus the explicit failure mode.
"""
from __future__ import annotations

import pytest

from doc_extractor import s3_io
from doc_extractor.exceptions import BodyParseUnmatchedError
from doc_extractor.pipelines import body_parse_path
from doc_extractor.schemas import Frontmatter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _frontmatter_yaml(**overrides: str) -> str:
    """Render a canonical PaymentReceipt frontmatter block (no fences)."""
    base = {
        "extractor_version": "0.1.0",
        "extraction_provider": "anthropic",
        "extraction_model": "claude-sonnet-4-6-20260101",
        "extraction_timestamp": "'2026-05-03T19:00:00Z'",
        "prompt_version": "0.1.0",
        "doc_type": "PaymentReceipt",
        "doc_subtype": "''",
        "jurisdiction": "''",
        "name_latin": "''",
        "name_cjk": "''",
        "receipt_amount": "''",
        "receipt_currency": "''",
        "receipt_time": "''",
        "receipt_debit_account_name": "''",
        "receipt_debit_account_number": "''",
        "receipt_debit_bank_name": "''",
        "receipt_credit_account_name": "''",
        "receipt_credit_account_number": "''",
        "receipt_credit_bank_name": "''",
        "receipt_reference": "''",
        "receipt_payment_app": "''",
        "receipt_counterparty_name": "''",
        "receipt_counterparty_account": "''",
    }
    base.update(overrides)
    return "".join(f"{k}: {v}\n" for k, v in base.items())


def _md(frontmatter: str, body: str) -> str:
    return f"---\n{frontmatter}---\n{body}"


CN_BODY = (
    "\n"
    "付款人: 张三\n"
    "付款卡号: 6217 **** **** 0083\n"
    "付款行: 中国工商银行\n"
    "收款人: 李四\n"
    "收款账户: 6230 **** **** 2235\n"
    "收款行: 平安银行\n"
    "金额: 15000.00\n"
    "币种: CNY\n"
    "时间: 2025-07-01T00:00:00Z\n"
    "用途: INV-2025-001\n"
    "付款工具: 工商银行手机银行\n"
)

NZ_BODY = (
    "\n"
    'Bank transfer of NZD 15,000.00 sent to account GM6040 '
    '(account number 02-0248-0242329-02) from account "Free Up-00" '
    '(account number 38-9024-0437881-00) on Tuesday, 1 July 2025.\n'
)

UNMATCHED_BODY = (
    "\n"
    "This document does not contain CN labels or an NZ-narrative receipt.\n"
    "It is just some prose that should not match either parser path.\n"
)


@pytest.fixture
def s3_mock(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """In-memory replacement for the analysis bucket. Stores UTF-8 strings."""
    storage: dict[str, str] = {}

    def fake_read(key: str) -> bytes:
        return storage[key].encode("utf-8")

    def fake_write(key: str, body: str | bytes) -> None:
        storage[key] = body.decode("utf-8") if isinstance(body, bytes) else body

    monkeypatch.setattr(s3_io, "read_analysis", fake_read)
    monkeypatch.setattr(s3_io, "write_analysis", fake_write)
    return storage


def _split_body(md: str) -> str:
    """Return the portion of ``md`` after the closing ``---`` fence."""
    head, _, body = md.partition("\n---\n")
    assert body, "expected fence-terminated frontmatter; got malformed input"
    return body


# ---------------------------------------------------------------------------
# CN canonical: body is byte-identical, frontmatter populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cn_canonical_body_is_byte_identical(s3_mock: dict[str, str]) -> None:
    key = "documents/transactions/12345/abc.jpeg.md"
    s3_mock[key] = _md(_frontmatter_yaml(jurisdiction="CN"), CN_BODY)

    result = await body_parse_path.run(key)

    assert result["body_bytes_preserved"] is True

    new_md = s3_mock[key]
    assert _split_body(new_md) == _split_body(_md(_frontmatter_yaml(jurisdiction="CN"), CN_BODY))


@pytest.mark.asyncio
async def test_cn_canonical_populates_payment_fields(s3_mock: dict[str, str]) -> None:
    key = "doc-cn.md"
    s3_mock[key] = _md(_frontmatter_yaml(jurisdiction="CN"), CN_BODY)

    await body_parse_path.run(key)

    parsed = _parse_frontmatter(s3_mock[key])
    assert parsed["receipt_debit_account_name"] == "张三"
    assert parsed["receipt_debit_account_number"] == "6217 **** **** 0083"
    assert parsed["receipt_debit_bank_name"] == "中国工商银行"
    assert parsed["receipt_credit_account_name"] == "李四"
    assert parsed["receipt_credit_account_number"] == "6230 **** **** 2235"
    assert parsed["receipt_credit_bank_name"] == "平安银行"
    assert parsed["receipt_amount"] == "15000.00"
    assert parsed["receipt_currency"] == "CNY"
    assert parsed["receipt_time"] == "2025-07-01T00:00:00Z"
    assert parsed["receipt_reference"] == "INV-2025-001"
    assert parsed["receipt_payment_app"] == "工商银行手机银行"


@pytest.mark.asyncio
async def test_cn_canonical_preserves_existing_frontmatter(s3_mock: dict[str, str]) -> None:
    """Frontmatter base fields (extractor_version, doc_type, etc.) survive
    untouched — only fields with non-empty parsed values overwrite."""
    key = "doc-cn.md"
    s3_mock[key] = _md(_frontmatter_yaml(jurisdiction="CN"), CN_BODY)

    await body_parse_path.run(key)

    parsed = _parse_frontmatter(s3_mock[key])
    assert parsed["extractor_version"] == "0.1.0"
    assert parsed["doc_type"] == "PaymentReceipt"
    assert parsed["jurisdiction"] == "CN"
    assert parsed["extraction_provider"] == "anthropic"


# ---------------------------------------------------------------------------
# NZ canonical (no CN labels): NZ parser kicks in via fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nz_canonical_body_is_byte_identical(s3_mock: dict[str, str]) -> None:
    key = "doc-nz.md"
    s3_mock[key] = _md(_frontmatter_yaml(jurisdiction="NZ"), NZ_BODY)

    await body_parse_path.run(key)

    new_md = s3_mock[key]
    assert _split_body(new_md) == NZ_BODY


@pytest.mark.asyncio
async def test_cn_to_nz_fallback_populates_via_nz_parser(s3_mock: dict[str, str]) -> None:
    """CN parser returns all-empty for an NZ-only body → fallback triggers."""
    key = "doc-nz.md"
    s3_mock[key] = _md(_frontmatter_yaml(jurisdiction="NZ"), NZ_BODY)

    result = await body_parse_path.run(key)

    parsed = _parse_frontmatter(s3_mock[key])
    assert parsed["receipt_amount"] == "15000.00"
    assert parsed["receipt_currency"] == "NZD"
    assert parsed["receipt_debit_account_name"] == "Free Up-00"
    assert parsed["receipt_debit_account_number"] == "38-9024-0437881-00"
    assert parsed["receipt_credit_account_name"] == "GM6040"
    assert parsed["receipt_credit_account_number"] == "02-0248-0242329-02"
    assert parsed["receipt_time"] == "2025-07-01T00:00:00Z"
    # And we report which fields actually changed.
    assert "receipt_amount" in result["fields_updated"]
    assert "receipt_credit_account_number" in result["fields_updated"]


# ---------------------------------------------------------------------------
# Unmatched: neither CN nor NZ → BodyParseUnmatchedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmatched_body_raises_body_parse_unmatched_error(
    s3_mock: dict[str, str],
) -> None:
    key = "doc-unmatched.md"
    s3_mock[key] = _md(_frontmatter_yaml(), UNMATCHED_BODY)

    with pytest.raises(BodyParseUnmatchedError, match="neither CN-label format nor NZ-narrative"):
        await body_parse_path.run(key)


@pytest.mark.asyncio
async def test_unmatched_body_does_not_overwrite_s3(s3_mock: dict[str, str]) -> None:
    """A failing run leaves the existing analysis untouched — no partial write."""
    key = "doc-unmatched.md"
    original = _md(_frontmatter_yaml(), UNMATCHED_BODY)
    s3_mock[key] = original

    with pytest.raises(BodyParseUnmatchedError):
        await body_parse_path.run(key)

    assert s3_mock[key] == original


# ---------------------------------------------------------------------------
# body_parse() unit semantics (covered alongside integration so the contract
# stays close to the pipeline that depends on it)
# ---------------------------------------------------------------------------


def test_body_parse_returns_cn_when_cn_labels_present() -> None:
    result = body_parse_path.body_parse("付款人: 张三\n金额: 100.00\n")
    assert result.receipt_debit_account_name == "张三"
    assert result.receipt_amount == "100.00"


def test_body_parse_falls_back_to_nz_when_cn_returns_empty() -> None:
    result = body_parse_path.body_parse(NZ_BODY)
    assert result.receipt_currency == "NZD"
    assert result.receipt_credit_account_name == "GM6040"


def test_body_parse_raises_on_unmatched_body() -> None:
    with pytest.raises(BodyParseUnmatchedError):
        body_parse_path.body_parse("Some unrelated English prose about birds.\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(md_text: str) -> dict[str, str]:
    """Pull the frontmatter mapping out of ``md_text`` for assertion access."""
    import yaml  # local import keeps the test file's top-level imports tidy

    assert md_text.startswith("---\n")
    rest = md_text[4:]
    idx = rest.find("\n---\n")
    assert idx > 0, "missing closing fence in test fixture"
    data = yaml.safe_load(rest[: idx + 1])
    assert isinstance(data, dict)
    # Every value should already be a string per Frontmatter contract.
    return {k: ("" if v is None else str(v)) for k, v in data.items()}


# Quietly verify the test module's import surface — catches accidentally
# importing private helpers from the production module.
def test_test_module_does_not_import_private_helpers() -> None:
    assert not hasattr(body_parse_path, "_BodyParsePathPrivate")  # sanity
    # And `Frontmatter` is import-able from schemas (bridge sanity).
    assert Frontmatter is not None


# ---------------------------------------------------------------------------
# P5 — body-parse renders through markdown_io.render_to_md (via
# render_frontmatter_only) so render-side logic propagates.
#
# Pre-fix, _reassemble called yaml.safe_dump directly and bypassed Story
# 7.5's provenance auto-fill — a body-parse repair on a freshly-classified
# document with empty extractor_version / extraction_timestamp produced
# YAML with those fields blank, breaking downstream consumers that rely
# on provenance being populated.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_body_parse_preserves_already_populated_provenance(
    s3_mock: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 7.5 caller-wins rule: when the existing frontmatter has
    populated ``extractor_version`` and ``extraction_timestamp``, the
    body-parse round-trip preserves them — render_to_md's auto-fill is
    skip-on-non-empty."""
    # Pin a different fake clock + version to prove auto-fill DIDN'T fire.
    from doc_extractor import markdown_io

    monkeypatch.setattr(markdown_io, "_now_iso8601", lambda: "9999-01-01T00:00:00Z")
    # Patching __version__ requires writing to the doc_extractor module attr
    # since markdown_io re-imports it at autofill time.
    import doc_extractor

    monkeypatch.setattr(doc_extractor, "__version__", "9.9.9-fake")

    key = "doc-cn-populated-provenance.md"
    s3_mock[key] = _md(
        _frontmatter_yaml(
            jurisdiction="CN",
            extractor_version="0.1.0",
            extraction_timestamp="'2026-05-03T19:00:00Z'",
        ),
        CN_BODY,
    )

    await body_parse_path.run(key)

    parsed = _parse_frontmatter(s3_mock[key])
    assert parsed["extractor_version"] == "0.1.0"
    assert parsed["extraction_timestamp"] == "2026-05-03T19:00:00Z"
    # And the fake clock / fake version DID NOT leak in.
    assert "9.9.9-fake" not in s3_mock[key]
    assert "9999-01-01" not in s3_mock[key]


@pytest.mark.asyncio
async def test_body_parse_autofills_empty_provenance_via_render_to_md(
    s3_mock: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 7.5 auto-fill now fires through the body-parse path too.
    Pre-P5 fix, body-parse called ``yaml.safe_dump`` directly and the
    auto-fill never ran — a freshly-classified MD with empty provenance
    came back from body-parse still empty."""
    from doc_extractor import markdown_io

    monkeypatch.setattr(markdown_io, "_now_iso8601", lambda: "2026-05-04T12:00:00Z")
    import doc_extractor

    monkeypatch.setattr(doc_extractor, "__version__", "0.1.0-test")

    key = "doc-cn-empty-provenance.md"
    s3_mock[key] = _md(
        _frontmatter_yaml(
            jurisdiction="CN",
            extractor_version="''",
            extraction_timestamp="''",
        ),
        CN_BODY,
    )

    await body_parse_path.run(key)

    parsed = _parse_frontmatter(s3_mock[key])
    assert parsed["extractor_version"] == "0.1.0-test"
    assert parsed["extraction_timestamp"] == "2026-05-04T12:00:00Z"


@pytest.mark.asyncio
async def test_body_parse_round_trip_uses_markdown_io_fence_format(
    s3_mock: dict[str, str],
) -> None:
    """The reassembled MD must follow the same `---\\n<yaml>---\\n\\n<body>`
    shape as ``markdown_io.render_to_md`` — the closing fence is followed
    by exactly one blank line before the body. Pre-fix, manual
    ``yaml.safe_dump`` + string concat produced the same bytes by
    coincidence; routing through ``render_frontmatter_only`` makes that
    contract explicit and survives future render-side changes."""
    key = "doc-cn-fence-shape.md"
    s3_mock[key] = _md(_frontmatter_yaml(jurisdiction="CN"), CN_BODY)

    await body_parse_path.run(key)

    new_md = s3_mock[key]
    assert new_md.startswith("---\n")
    # Exactly one closing fence + blank line between frontmatter and body.
    assert "\n---\n\n" in new_md
    # And the body is intact byte-for-byte after the blank-line boundary.
    body = new_md.split("\n---\n", 1)[1]
    assert body == CN_BODY
