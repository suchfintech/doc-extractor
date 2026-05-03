# Golden corpus — Driver Licence

Hand-labelled driver licence images and their expected extraction output.
The eval harness iterates these pairs to score the `DriverLicence` agent
on real documents.

## File-naming convention

Each example is a **pair** of files with the same basename:

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + DriverLicence body)
```

- `<basename>.jpeg` — the source image. PNG is also acceptable; the eval
  harness sniffs by extension. Keep filenames lowercase, snake-case, and
  three-digit-padded (`example_001`, `example_002`, …) once the corpus
  exceeds nine entries.
- `<basename>.expected.md` — a byte-stable Pydantic-rendered
  `DriverLicence` instance: YAML frontmatter (Frontmatter base fields)
  followed by an empty body. All required fields populated; use empty
  string (`""` in YAML, rendered without quotes) for fields genuinely
  absent from the source document.

The basename must match exactly (including casing) — the harness walks
`*.jpeg` and looks up the sibling `.expected.md` by string substitution.

## Versioning policy

- **Additions are non-breaking.** Append new examples freely.
- **Removals require justification.** Open a PR that documents why the
  example is no longer representative (e.g. issuing authority changed
  format) and link the architectural decision in the PR description.
- **Edits to existing `.expected.md` files** require bumping the
  `extractor_version` field in the file's frontmatter, since the byte
  contract is the gating signal for regression detection.

## Coverage targets (Story 4.1 acceptance)

The Story 4.1 spec calls for ≥10 examples across both supported
formats:

- **NZ DLA cards** (NZTA Waka Kotahi plastic cards) — front + reverse
  preferably; mix of single-class (`Class 1`) and multi-class
  (`Class 1, 2, 6`) examples.
- **CN driving permits** (机动车驾驶证) — booklet inside-front-page
  scans; mix of A2/B1/C1/D categories; include at least one with the
  combined `A2 + B1` style.

## Provenance

Source images are provided by Yang as a follow-up to Story 4.1 (this
directory ships with the README only — labelled images live outside the
repo until consent + redaction review is complete). Once delivered, drop
them into this directory and run:

```
uv run doc-extractor eval --doc-type DriverLicence
```

to bootstrap the scorecard baseline.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when an example is anonymised
  (use `XXXXXXX` for redacted licence numbers in the test corpus).
- No model-generated outputs. These are ground-truth labels written by a
  human reviewer; the agent's job is to produce them, not to seed them.
