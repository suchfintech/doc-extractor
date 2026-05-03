# Golden corpus — PEP_Declaration

Hand-labelled PEP-declaration images and their expected extraction
output. The eval harness iterates these pairs to score the
`PEP_Declaration` agent against real documents.

## File-naming convention

Each example is a **pair** with the same basename:

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + PEP_Declaration body)
```

Lowercase, snake-case, three-digit padding (`example_001`,
`example_002`, …) once the corpus exceeds nine entries.

The basename must match exactly — the harness walks `*.jpeg` and looks
up the sibling `.expected.md` by string substitution.

## Versioning policy

- **Additions are non-breaking.** Append new examples freely.
- **Removals require justification** — link the architectural decision
  in the PR description.
- **Edits to existing `.expected.md` files** require bumping the
  `extractor_version` field in the frontmatter, since the byte contract
  is the gating signal for regression detection.

## Coverage targets

≥10 examples spread across the three formats supported by the prompt:

- **Client-signed self-declaration** — at least one each of
  `is_pep = "yes"`, `"no"`, and `"unknown"`. Include one example where
  the free-text comments contradict the ticked box (the prompt's
  box-tick discipline must hold).
- **Third-party attestation** — at least one lawyer attestation and
  one accountant attestation, both with the *attestor* (not the client)
  as `declarant_name`.
- **AML-officer verification template** — internal compliance template
  showing the `declarant_name` is the AML officer.

For each format include at least one CJK example (CN / HK declarant
name + role) so the CJK-passthrough discipline is exercised.

## Provenance

Source images are provided by Yang as a follow-up — this directory
ships with the README only. When an example is anonymised, redact the
declarant name and any specific role text (the "is PEP yes/no" box and
the format itself are what's being tested, not the identities).

## What this directory does NOT contain

- No PII in committed `.expected.md` files when the example is
  anonymised.
- No model-generated outputs. These are human-written ground truth.
