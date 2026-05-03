# Golden corpus — TaxResidency

Hand-labelled tax-residency documents and their expected extraction
output.

## File-naming convention

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + TaxResidency body)
```

Lowercase, snake-case, three-digit padding once the corpus exceeds
nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets

≥10 examples spread across the four supported formats plus the
TIN-format axis:

- **NZ IRD residency-status letter** — at least 2; include both 8- and
  9-digit IRD-number formats (`"123-456-78"` and `"123-456-789"`).
- **NZ IR3 residency declaration** — at least 1 with each of
  `"resident"`, `"non-resident"`, `"transitional resident"` ticked.
- **FATCA W-9** (US person) — at least 2 covering both SSN and EIN
  TIN formats. `tax_jurisdiction = "US"`,
  `residency_status = "resident"`.
- **FATCA W-8BEN** (non-US individual) — at least 2 with different
  declared `tax_jurisdiction` values (`"NZ"`, `"AU"`, `"GB"`). TIN
  may be empty — that's fine.
- **CRS self-certification** — at least 3 from different jurisdictions
  (CN, HK, SG, AU). Include one where the form lists multiple
  jurisdictions of tax residence — capture the primary one only.

## TIN-format coverage

Across the corpus, exercise these TIN formats verbatim:

- NZ IRD: `"123-456-78"` / `"123-456-789"` (hyphens preserved)
- US SSN: `"123-45-6789"` (hyphens preserved)
- US EIN: `"12-3456789"` (single hyphen)
- US ITIN: `"9XX-XX-XXXX"` (starts with 9)
- HK: `"A123456(7)"` (parentheses preserved)
- SG NRIC: `"S1234567A"`
- CN entity USCC: `"91110000XXXXXXXXXX"` (18 chars)

The `.expected.md` for each example must reproduce the printed string
byte-for-byte.

## Provenance

Source images are provided by Yang as a follow-up. When anonymising,
redact the holder name and replace the TIN with the same letter/digit
shape (e.g. `"123-456-78"` → `"XXX-XXX-XX"`) so the format-coverage
goal is preserved.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when anonymised.
- No model-generated outputs. Human-written ground truth only.
- No multi-jurisdiction CRS captures (out of scope for v1's flat schema).
