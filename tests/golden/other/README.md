# Golden corpus — Other (catch-all)

Hand-labelled documents that the classifier routed to `Other` because
none of the 14 typed specialists were a confident fit. The corpus is
deliberately the **safety net** — it includes adversarial cases that
exist precisely to verify the catch-all surface degrades gracefully.

## File-naming convention

```
example_01.jpeg          # source image (or .pdf)
example_01.expected.md   # ground-truth Markdown (Frontmatter + Other body)
```

Lowercase, snake-case, three-digit padding once the corpus exceeds
nine entries. Basename must match exactly.

## Versioning policy

- **Additions are non-breaking.**
- **Removals require justification.**
- **Edits to existing `.expected.md` files** require bumping
  `extractor_version`.

## Coverage targets — adversarial by design

Unlike the typed-specialist golden corpora which test happy-path
recognition, the Other corpus tests **the catch-all's resilience**.
≥10 examples spread across these adversarial categories:

- **Deliberately mis-classified examples** — at least 2 documents
  that *resemble* a typed specialist (e.g. a passport-shaped page from
  a sample/training fake, an unusual bank-letter format that doesn't
  match BankAccountConfirmation). The agent must describe what it
  sees without force-fitting into the typed schema.
- **Partial documents** — at least 2 (page 2 of 3, bottom half cut
  off, etc.). `notes` should flag the missing portion.
- **Foreign-jurisdiction unfamiliar formats** — at least 2 documents
  from jurisdictions outside v1's NZ/CN/HK/AU/US/GB scope (Vietnam,
  Indonesia, Brazil, etc.). `notes` should observe that the format
  is unfamiliar; the agent must not invent extractions.
- **Quality edge cases** — at least 2: low-resolution scan,
  watermark-obscured key fields, image rotated 90°.
- **Genuinely off-list document types** — at least 2 of: insurance
  certificate, employment contract, university transcript, court
  order, medical certificate. These are documents the classifier
  correctly recognised as "not in the 14 specialists" — the agent
  describes them straightforwardly.

## What "ground truth" means for Other

The `.expected.md` files for Other are not byte-stable in the same
sense as the typed specialists. Two reviewers labelling the same
adversarial document might write different but equally-correct
`description` and `notes` strings. The eval harness uses
**`match_normalised`** rather than exact match for `description` /
`notes`; only `extracted_text` is held to a stricter (line-by-line
fuzzy) standard.

## Provenance

Source images are provided by Yang as a follow-up. When anonymising,
redact identity-bearing strings in `extracted_text` but keep the
document-shape signal intact (an account-confirmation letter remains
recognisable as such even with the account number masked).

## What this directory does NOT contain

- No PII in committed `.expected.md` files when anonymised.
- No model-generated outputs. Human-written ground truth only —
  including the `notes` commentary which is the human reviewer's
  "what would I expect a reasonable model to flag here" judgment.
- No fake force-fits. If a document genuinely fits a typed
  specialist, it goes in that specialist's golden directory, not
  here.
