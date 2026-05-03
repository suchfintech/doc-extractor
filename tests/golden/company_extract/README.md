# Golden corpus — CompanyExtract

Hand-labelled corporate-registry extracts and their expected
extraction output.

## File-naming convention

```
example_01.jpeg          # source image (or .pdf for multi-page extracts)
example_01.expected.md   # ground-truth Markdown (Frontmatter + CompanyExtract body)
```

Lowercase, snake-case, three-digit padding once the corpus exceeds
nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets

≥10 examples spread across the three formats:

- **NZ Companies Office Extract** — at least 3, including one with
  ≥5 directors (long-list rendering test) and one with `shareholders`
  explicitly empty (`[]`, not `null`).
- **UK Companies House extract (CS01)** — at least 3, including one
  where shareholders are not listed at all (`null`, not `[]`).
- **CN 工商档案** — at least 3, including one with the 18-character
  USCC and CJK names. Include one with both Chinese and Latin name
  renderings of the company.

## Provenance

Source images / PDFs are provided by Yang as a follow-up. When
anonymising, redact director / shareholder names with `XXXXXXX` —
the test is about format recognition + list-ordering preservation,
not specific identities.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when anonymised.
- No model-generated outputs. Human-written ground truth only.
