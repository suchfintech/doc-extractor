# Golden corpus — ProofOfAddress

Hand-labelled proof-of-address documents and their expected extraction
output.

## File-naming convention

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + ProofOfAddress body)
```

Lowercase, snake-case, three-digit padding once the corpus exceeds
nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets

≥10 examples spread across the four supported formats:

- **NZ utility bills** — at least one each of Mercury, Powerco, Vector,
  and a telco (Spark / 2Degrees). Include one with a co-branded
  billing-service vendor so the issuer-priority rule (utility wins
  over vendor) is exercised.
- **NZ council rates notices** — at least one each of Auckland Council
  and one regional council. `issuer` is the council; `document_type`
  is `"council rates notice"`.
- **Bank statement (front page used as POA)** — at least one each of
  ANZ, Westpac, Kiwibank. The address in the salutation block is
  what gets extracted (NOT the branch address).
- **CN 户口本** — at least one residency-booklet scan with CJK address
  and `issuer` as the local 公安局.

## The 3-month freshness rule (downstream concern)

Document age is **not** filtered during extraction — the `.expected.md`
captures `document_date` verbatim regardless of how old. Include at
least one example dated > 3 months ago to anchor that the agent does
not silently skip stale documents.

## Provenance

Source images are provided by Yang as a follow-up. When anonymising,
redact `holder_name` and any account numbers in the body — the test
is about format recognition + issuer priority + date verbatim.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when anonymised.
- No model-generated outputs. Human-written ground truth only.
- No freshness filtering. Stale documents stay in the corpus.
