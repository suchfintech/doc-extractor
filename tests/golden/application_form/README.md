# Golden corpus — ApplicationForm

Hand-labelled customer-onboarding / application-form images and their
expected extraction output. The eval harness iterates these pairs to
score the `ApplicationForm` agent against real documents.

## File-naming convention

Each example is a **pair** with the same basename:

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + ApplicationForm body)
```

Lowercase, snake-case, three-digit padding once the corpus exceeds
nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets

≥10 examples spread across the two supported families plus the
handwritten / digital axis:

- **LEL onboarding form** — at least three: one fully digital, one
  fully handwritten, one mixed (printed labels, handwritten values).
- **Generic AML customer-onboarding forms** — at least three from
  different partners so label variations (`"Date of birth"` /
  `"DOB"` / `"Birthday"`) are exercised.
- **Handwriting edge cases** — at least one with a struck-through
  field (must emit `""`), one with a crossed-out correction (must
  capture the un-crossed text), one with a numeric/letter ambiguous
  digit (`O`/`0` in DOB or postcode).

For each family include at least one with a CJK `applicant_name` /
`applicant_occupation` so the CJK passthrough is exercised.

## Provenance

Source images are provided by Yang as a follow-up. When anonymising,
redact the applicant's full name and DOB; the `application_type` and
`applicant_address` city/country can stay (they're testing format
recognition, not identity).

## What this directory does NOT contain

- No PII in committed `.expected.md` files when anonymised.
- No model-generated outputs. Human-written ground truth only.
