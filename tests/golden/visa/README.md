# Golden corpus — Visa

Hand-labelled visa-document images and their expected extraction
output. The eval harness iterates these pairs to score the `Visa` agent
against real documents.

## File-naming convention

Each example is a **pair** of files with the same basename:

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + Visa body)
```

- `<basename>.jpeg` — the source image. PNG is also acceptable; the
  eval harness sniffs by extension. Lowercase, snake-case, three-digit
  padding (`example_001`, `example_002`, …) once the corpus exceeds
  nine entries.
- `<basename>.expected.md` — a byte-stable Pydantic-rendered `Visa`
  instance: YAML frontmatter (Frontmatter base fields) followed by an
  empty body. All required fields populated; use empty string for
  fields genuinely absent from the source document.

The basename must match exactly (case included) — the harness walks
`*.jpeg` and looks up the sibling `.expected.md` by string substitution.

## Versioning policy

- **Additions are non-breaking.** Append new examples freely.
- **Removals require justification.** Open a PR documenting why the
  example is no longer representative (e.g. the issuing post format
  changed) and link the architectural decision in the PR description.
- **Edits to existing `.expected.md` files** require bumping the
  `extractor_version` field in the file's frontmatter, since the byte
  contract is the gating signal for regression detection.

## Coverage targets (Story 4.3 acceptance)

The Story 4.3 spec calls for ≥10 examples spread across the four
supported formats:

- **NZ visas (Immigration NZ)** — at least one resident visa, one work
  visa, and one visitor visa. NZ uses DD/MM/YYYY (day-first) — at least
  one example with an ambiguous-looking date like `01/02/YYYY` to anchor
  the day-first convention.
- **CN visas (CVASC)** — at least one each of `L` (tourist), `F`
  (business), `M` (commercial trade), and `Z` (work). Include one with
  the `00M` multi-entry abbreviation so the `entries_allowed = "multiple"`
  normalisation is exercised.
- **US B1/B2** — at least one B1/B2 combo stamp and one single B2.
- **Schengen** — at least one short-stay `C` visa with `MULT`
  entries_allowed (must round-trip to `"multiple"`).

For each format, also include at least one example where `valid_from`
/ `valid_to` (travel window) differ from `issue_date` / `expiry_date`
(label window) — that's the hardest case for the agent and the highest
ROI test.

## Provenance

Source images are provided by Yang as a follow-up to Story 4.3 (this
directory ships with the README only — labelled images live outside the
repo until consent + redaction review is complete). When an example is
anonymised, redact the visa-label number and the holder's name with
`XXXXXXX`/`REDACTED` rather than synthesising fake values.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when an example is anonymised.
- No model-generated outputs. These are ground-truth labels written by a
  human reviewer; the agent's job is to produce them, not to seed them.
