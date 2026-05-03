# Golden corpus — National ID

Hand-labelled national identity card images and their expected
extraction output. The eval harness iterates these pairs to score the
`NationalID` agent against real documents.

## File-naming convention

Each example is a **pair** of files with the same basename:

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + NationalID body)
```

- `<basename>.jpeg` — the source image. PNG is also acceptable; the eval
  harness sniffs by extension. Lowercase, snake-case, three-digit padding
  (`example_001`, `example_002`, …) once the corpus exceeds nine entries.
- `<basename>.expected.md` — a byte-stable Pydantic-rendered `NationalID`
  instance: YAML frontmatter (Frontmatter base fields) followed by an
  empty body. All required fields populated; use empty string for
  fields genuinely absent from the source document.

The basename must match exactly (case included) — the harness walks
`*.jpeg` and looks up the sibling `.expected.md` by string substitution.

## Versioning policy

- **Additions are non-breaking.** Append new examples freely.
- **Removals require justification.** Open a PR documenting why the
  example is no longer representative (e.g. issuing authority changed
  format) and link the architectural decision in the PR description.
- **Edits to existing `.expected.md` files** require bumping the
  `extractor_version` field in the file's frontmatter, since the byte
  contract is the gating signal for regression detection.

## Coverage targets (Story 4.2 acceptance)

The Story 4.2 spec calls for ≥10 examples spread across the four
supported formats:

- **CN 居民身份证** (Resident Identity Card) — 18-digit IDs with embedded
  DOB (positions 7–14) and gender (position 17). Mix of cards where the
  printed `dob` / `sex` agree with the embedded encoding and at least
  one card where they disagree (rare but real — the agent must trust
  the printed face, not silently rewrite from the encoding).
- **HK ID** — `A123456(7)` single-letter prefix and the newer
  `WX1234567(8)` double-letter prefix. Include at least one with a
  Chinese name on the card.
- **SG NRIC** — citizen NRIC (`S` / `T` prefix) and at least one
  work-pass card showing `Ministry of Manpower` as issuing authority.
- **TW 身分證** — at least one card to anchor the format.

## Provenance

Source images are provided by Yang as a follow-up to Story 4.2 (this
directory ships with the README only — labelled images live outside the
repo until consent + redaction review is complete). When an example is
anonymised, redact the ID-number digits with `XXXXXXXX` rather than
synthesising a fake sequence — fake IDs that happen to validate against
the encoding rules pollute the embedded-DOB cross-check tests.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when an example is anonymised.
- No model-generated outputs. These are ground-truth labels written by a
  human reviewer; the agent's job is to produce them, not to seed them.
