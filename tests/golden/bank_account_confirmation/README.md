# Golden corpus — BankAccountConfirmation

Hand-labelled bank account-confirmation letters and their expected
extraction output. The eval harness iterates these pairs to score the
`BankAccountConfirmation` agent against real documents.

## File-naming convention

Each example is a **pair** with the same basename:

```
example_01.jpeg          # source image
example_01.expected.md   # ground-truth Markdown (Frontmatter + BankAccountConfirmation body)
```

Lowercase, snake-case, three-digit padding once the corpus exceeds
nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets

≥10 examples spread across format families:

- **NZ banks** — at least one each of ANZ, Westpac, BNZ, Kiwibank.
- **CN banks** — at least one each of ICBC, BOC, CCB. CN confirmation
  letters are commonly bilingual (English account holder + Chinese
  letter body); include at least one bilingual example.
- **Signing-authority variations** — at least one with a printed name +
  title in the signature block, one with only a stamp + role
  (`"Branch Operations Officer"` without a person), one with a
  handwritten signature whose printed name is illegible (the agent
  should capture the printed name, not the signature scribble).
- **Account-number masking** — at least one with a printed mask and
  one with the full unmasked number; both round-trip verbatim.

## What this directory does NOT contain

- No PII in committed `.expected.md` files when anonymised — redact
  `account_holder_name` and `account_number` with `XXXXXXX`.
- No model-generated outputs. Human-written ground truth only.

## Single-page assumption

These letters are nearly always single-page. If you do encounter a
multi-page example, label only the page that carries the confirmation
body — subsequent pages are typically attachments and don't carry
fields the schema captures.
