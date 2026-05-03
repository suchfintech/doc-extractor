# Golden corpus — EntityOwnership

Hand-labelled beneficial-ownership disclosure forms and their expected
extraction output. The `EntityOwnership` schema carries a nested list
of `UltimateBeneficialOwner` instances (the project's first
nested-object schema).

## File-naming convention

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + EntityOwnership body with nested UBO list)
```

Lowercase, snake-case, three-digit padding once the corpus exceeds
nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets

≥10 examples spread across the two supported formats plus the
ownership-percentage rendering axis:

- **NZ AML/CFT mandatory schedule** — at least 4 examples covering:
  - a single-UBO 100% holder
  - a two-UBO 50/50 split
  - a multi-UBO breakdown (3+ UBOs, with a sum that may or may not
    add to 100% — some declarations include corporate intermediate
    holders that aren't UBOs themselves)
  - one with the `null` vs `[]` distinction at the schedule level
    (a form that explicitly says "no UBOs ≥25%" with no entries)
- **FATF UBO template** — at least 4 examples; same variations.
- **Ownership-percentage formats** — across the corpus, include at
  least one each of: `"25%"`, `"0.25"`, `"25.5%"`,
  `"approximately 25%"` (verbatim qualifier), and one CJK
  representation if available. The agent's job is verbatim
  preservation of whichever format the document uses.
- **Sub-25% inclusion** — at least one example where the document
  voluntarily lists a sub-threshold holder; the agent must still
  capture them (downstream filters apply, not the extractor).

## Provenance

Source images are provided by Yang as a follow-up. When anonymising,
redact UBO names + DOBs with `XXXXXXX` / `1990-01-01` — the test is
about list + nested-object round-trip and ownership-format
preservation.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when anonymised.
- No model-generated outputs. Human-written ground truth only.
- No threshold filtering. Sub-25% UBOs that the document declares are
  preserved in the labels.
