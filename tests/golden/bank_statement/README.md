# Golden corpus — BankStatement

Hand-labelled bank-statement images and PDFs and their expected
extraction output. The eval harness iterates these pairs to score the
`BankStatement` agent against real documents.

## File-naming convention

Each example is a **pair** with the same basename:

```
example_01.pdf           # source PDF (multi-page) OR .jpeg for single-page bank renderings
example_01.expected.md   # ground-truth Markdown (Frontmatter + BankStatement body, header-only)
```

PDFs are pre-rendered to per-page images via
`pdf/converter.py:pdf_to_images(mode="all_pages")` (Story 3.3) before
the agent sees them. The ground-truth `.expected.md` describes the
**header + summary** — no transaction-row data.

Lowercase, snake-case, three-digit padding (`example_001`) once the
corpus exceeds nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets

≥10 examples spread across format families plus the **multi-page
requirement**:

- **NZ banks** — at least one each of ANZ, Westpac, BNZ, Kiwibank.
  Multi-page PDF on at least one (NZ statements are commonly
  3-5 pages with the header on page 1 and transactions on later pages).
- **CN banks** — at least one each of ICBC, BOC, CCB, CMB. Include at
  least one where the **header lives on page 2 or 3** (some CN bank
  statement formats put a cover sheet first) — this exercises the
  prompt's "search subsequent pages for the header" rule.
- **NZ-bank multi-currency** — at least one where the statement covers
  both `NZD` and `USD` columns; the agent must pick the primary
  account's currency.
- **Account-number masking** — at least one with a printed mask
  (`02-0248-XXXXXX-02`) and one with the full unmasked number; both
  round-trip verbatim.

**Multi-page PDF requirement (≥1 example):** at least one of the above
must be a multi-page PDF — that's the only way to exercise the
`mode="all_pages"` rendering path end-to-end.

## What this directory does NOT contain

- No transaction-row data in any `.expected.md` (out of scope for v1).
- No PII in committed `.expected.md` files when anonymised — redact
  `account_holder_name` and `account_number` with `XXXXXXX`.
- No model-generated outputs. Human-written ground truth only.
