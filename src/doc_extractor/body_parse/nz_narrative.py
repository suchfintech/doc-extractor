"""Parse NZ-style narrative payment receipts into ``PaymentReceipt``.

NZ banking statements often emit payment receipts as a single descriptive
sentence rather than a labelled body. Canonical shape::

    Bank transfer of NZD 15,000.00 sent to account GM6040
    (account number 02-0248-0242329-02) from account "Free Up-00"
    (account number 38-9024-0437881-00) on Tuesday, 1 July 2025

The parser is **pure**: no module-level mutable state, no ``time.time``,
no ``random``. The compiled regex objects are immutable. Pure-ness is what
lets the eval harness fan-out cheaply (NFR3) and replay deterministically
(architecture §Replayability).

Format choices baked in here:

* Amount strings drop thousand-separator commas (``15,000.00`` → ``15000.00``)
  so they round-trip ``Decimal``. This is the *one* normalisation we apply
  to the value — the canonical contract elsewhere preserves verbatim
  formatting, but ``receipt_amount`` is documented as parsed.
* Account numbers preserve hyphens verbatim (``38-9024-0437881-00``).
* Names are stripped of ASCII *and* Unicode smart quotes; internal
  whitespace and hyphens are preserved.
* The trailing date is always rendered as ISO 8601 ``Z`` (the source
  document is local-NZ but the canonical contract is timezone-stamped UTC
  midnight per Frontmatter conventions).
"""
from __future__ import annotations

import re
from datetime import datetime

from doc_extractor.schemas.payment_receipt import PaymentReceipt

# ASCII apostrophe + double quote, plus the four common Unicode smart quotes.
_QUOTE_CHARS = "\"'“”‘’"

_CURRENCY = r"(?P<ccy>NZD|USD|AUD|GBP|EUR)"
_AMOUNT = r"(?P<amount>[\d,]+(?:\.\d{2})?)"

# "of <CCY> <AMOUNT>" — anchored on "of" so we don't match unrelated 3-letter codes.
_AMOUNT_RE = re.compile(rf"\bof\s+{_CURRENCY}\s+{_AMOUNT}\b", re.IGNORECASE)

# A single account segment: "<from|to> account <NAME> (account number <NUMBER>)".
# The name is non-greedy and may include quotes/hyphens/spaces; (?=\s*\() forces
# the parenthetical to start the very next token, so the name doesn't run on.
_ACCOUNT_RE = re.compile(
    r"\b(?P<direction>from|to)\s+account\s+"
    r"(?P<name>.+?)"
    r"\s*\(account\s+number\s+(?P<number>[\d-]+)\)",
    re.IGNORECASE,
)

# "on Tuesday, 1 July 2025" — capture the date payload (day-of-week is decorative).
_DATE_RE = re.compile(
    r"\bon\s+(?:[A-Za-z]+,\s+)?(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\b"
)


def _strip_quotes(name: str) -> str:
    return name.strip().strip(_QUOTE_CHARS).strip()


def _normalise_amount(raw: str) -> str:
    return raw.replace(",", "")


def _to_iso_z(day: str, month_name: str, year: str) -> str:
    parsed = datetime.strptime(f"{day} {month_name} {year}", "%d %B %Y")
    return parsed.strftime("%Y-%m-%dT00:00:00Z")


def parse_nz(body_md: str) -> PaymentReceipt:
    """Parse one NZ narrative payment receipt sentence.

    Raises:
        ValueError: the body is missing an amount/currency token, the
            ``from``/``to`` account segments, or the trailing date — any of
            which means the body isn't an NZ-narrative receipt and should be
            routed elsewhere rather than silently producing empty fields.
    """
    amount_match = _AMOUNT_RE.search(body_md)
    if amount_match is None:
        raise ValueError("Could not locate currency + amount in NZ narrative body")

    accounts: dict[str, dict[str, str]] = {}
    for m in _ACCOUNT_RE.finditer(body_md):
        accounts[m["direction"].lower()] = {
            "name": _strip_quotes(m["name"]),
            "number": m["number"],
        }

    if "from" not in accounts or "to" not in accounts:
        raise ValueError(
            "NZ narrative body must contain both 'from account ...' and 'to account ...' segments"
        )

    date_match = _DATE_RE.search(body_md)
    if date_match is None:
        raise ValueError("Could not locate trailing 'on <date>' clause in NZ narrative body")

    debit = accounts["from"]
    credit = accounts["to"]

    return PaymentReceipt(
        receipt_amount=_normalise_amount(amount_match["amount"]),
        receipt_currency=amount_match["ccy"].upper(),
        receipt_time=_to_iso_z(date_match["day"], date_match["month"], date_match["year"]),
        receipt_debit_account_name=debit["name"],
        receipt_debit_account_number=debit["number"],
        receipt_credit_account_name=credit["name"],
        receipt_credit_account_number=credit["number"],
    )
