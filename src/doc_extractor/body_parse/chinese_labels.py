"""Deterministic CN-receipt body-parse repair.

Reads a PaymentReceipt body markdown that contains Chinese-labelled lines
(``付款人: 张三`` etc.) and returns a partial ``PaymentReceipt`` populated from
whichever labels were present. Used to repair the ~80 % field-drop tail at
zero LLM cost (see ``receipt-schema-rename-verification-2026-05-02.md``).

Design contract:
- **Pure function** — no I/O, no time, no random, no module-level mutable state.
  Same input → byte-identical output across runs.
- Account-number masks (``6217 **** **** 0083``) are preserved verbatim. No
  whitespace collapse, no normalisation.
- Names are stripped of surrounding ``[ ] ( ) （ ）`` brackets and trailing
  whitespace; CJK characters are preserved. Markdown bold (``**``) wrapping the
  value is also stripped — common in body markdowns and not part of the name.
- Fields not found in the body are left as ``""`` (empty-string-not-null per
  ``Frontmatter``).
"""
from __future__ import annotations

import re

from doc_extractor.schemas import PaymentReceipt

# Label inventory — order within each tuple is irrelevant; the regex below
# sorts longest-first to prevent a shorter variant (``付款方``) from prematurely
# matching a longer one (``付款方银行``).

_DEBIT_NAME_LABELS = ("付款人", "付款户名", "付款方", "汇款人", "汇款方")
_DEBIT_NUMBER_LABELS = ("付款卡号", "付款账号", "付款账户", "付款账户号码")
_DEBIT_BANK_LABELS = ("付款行", "付款银行", "付款方银行", "付款方开户行")

_CREDIT_NAME_LABELS = ("收款人", "收款户名", "收款方")
_CREDIT_NUMBER_LABELS = ("收款卡号", "收款账号", "收款账户", "收款账户号码")
_CREDIT_BANK_LABELS = ("收款行", "收款银行", "收款方银行", "收款方开户行")

_AMOUNT_LABELS = ("金额", "付款金额")
_CURRENCY_LABELS = ("币种", "货币", "币别")
_TIME_LABELS = ("时间", "交易时间", "付款时间")
_REFERENCE_LABELS = ("用途", "备注", "汇款附言")
_PAYMENT_APP_LABELS = ("付款工具", "付款渠道")


def _build_pattern(labels: tuple[str, ...]) -> re.Pattern[str]:
    longest_first = sorted(labels, key=len, reverse=True)
    label_alt = "|".join(re.escape(label) for label in longest_first)
    # Boundary: start-of-line (re.MULTILINE) OR a whitespace / markdown-bold /
    # opening-bracket character. Then label, optional whitespace + asterisks
    # (markdown bold close), the separator (ASCII or fullwidth colon), optional
    # whitespace, and the value to end-of-line.
    pattern = rf"(?:^|[\s\*\(\[（])(?:{label_alt})[\s\*]*[:：]\s*([^\n]+)"
    return re.compile(pattern, re.MULTILINE)


_PATTERNS: dict[str, re.Pattern[str]] = {
    "debit_name": _build_pattern(_DEBIT_NAME_LABELS),
    "debit_number": _build_pattern(_DEBIT_NUMBER_LABELS),
    "debit_bank": _build_pattern(_DEBIT_BANK_LABELS),
    "credit_name": _build_pattern(_CREDIT_NAME_LABELS),
    "credit_number": _build_pattern(_CREDIT_NUMBER_LABELS),
    "credit_bank": _build_pattern(_CREDIT_BANK_LABELS),
    "amount": _build_pattern(_AMOUNT_LABELS),
    "currency": _build_pattern(_CURRENCY_LABELS),
    "time": _build_pattern(_TIME_LABELS),
    "reference": _build_pattern(_REFERENCE_LABELS),
    "payment_app": _build_pattern(_PAYMENT_APP_LABELS),
}


def _first_match(body: str, pattern: re.Pattern[str]) -> str:
    m = pattern.search(body)
    return m.group(1) if m else ""


_NAME_LEAD = re.compile(r"^[\*\s\[\(（]+")
_NAME_TRAIL = re.compile(r"[\*\s\]\)）]+$")


def _clean_name(value: str) -> str:
    """Strip brackets / markdown-bold / surrounding whitespace; keep CJK + interior content."""
    if not value:
        return ""
    value = _NAME_LEAD.sub("", value)
    value = _NAME_TRAIL.sub("", value)
    return value


def _clean_account_number(value: str) -> str:
    """Verbatim preservation of internal whitespace and ``*`` mask characters.

    Only trims trailing whitespace (what the AC explicitly permits). Leading
    asterisks are NOT stripped — fully-masked numbers like ``**** **** 0083``
    must round-trip untouched.
    """
    return value.rstrip()


def parse_chinese(body_md: str) -> PaymentReceipt:
    return PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_amount=_clean_account_number(_first_match(body_md, _PATTERNS["amount"])),
        receipt_currency=_clean_name(_first_match(body_md, _PATTERNS["currency"])),
        receipt_time=_clean_account_number(_first_match(body_md, _PATTERNS["time"])),
        receipt_debit_account_name=_clean_name(_first_match(body_md, _PATTERNS["debit_name"])),
        receipt_debit_account_number=_clean_account_number(
            _first_match(body_md, _PATTERNS["debit_number"])
        ),
        receipt_debit_bank_name=_clean_name(_first_match(body_md, _PATTERNS["debit_bank"])),
        receipt_credit_account_name=_clean_name(_first_match(body_md, _PATTERNS["credit_name"])),
        receipt_credit_account_number=_clean_account_number(
            _first_match(body_md, _PATTERNS["credit_number"])
        ),
        receipt_credit_bank_name=_clean_name(_first_match(body_md, _PATTERNS["credit_bank"])),
        receipt_reference=_clean_name(_first_match(body_md, _PATTERNS["reference"])),
        receipt_payment_app=_clean_name(_first_match(body_md, _PATTERNS["payment_app"])),
    )
