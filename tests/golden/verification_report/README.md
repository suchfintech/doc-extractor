# Golden corpus — VerificationReport

Hand-labelled identity-verification report images and their expected
extraction output. The eval harness iterates these pairs to score the
`VerificationReport` agent against real documents.

## File-naming convention

Each example is a **pair** with the same basename:

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + VerificationReport body)
```

Lowercase, snake-case, three-digit padding once the corpus exceeds
nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets

≥10 examples spread across the three supported formats:

- **NZ EIV (DIA)** — at least one verified outcome and one failed.
  `verifier_name` is `"DIA"` for all.
- **In-person verification certificates** — JP, lawyer, and accountant
  signers; at least one each. `verification_method = "in-person"`.
- **Third-party services** — at least one Trulioo, one Onfido, one
  Jumio if available. The `verification_outcome` should cover all
  three values (`"verified"`, `"failed"`, `"partial"`) across the
  corpus so the outcome-normalisation rules are exercised.

For each format include at least one with a CJK `subject_name` so the
CJK passthrough is exercised.

## Provenance

Source images are provided by Yang as a follow-up. When anonymising,
redact the `subject_id_number` with `XXXXXXXX` rather than synthesising
a fake — fake IDs that happen to validate against ID-encoding rules
pollute downstream cross-checks.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when anonymised.
- No model-generated outputs. Human-written ground truth only.
