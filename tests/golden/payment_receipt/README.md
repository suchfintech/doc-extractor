# Golden corpus — Payment Receipt

Hand-labelled payment-receipt images and their expected extraction
output. The eval harness iterates these pairs to score the
`PaymentReceipt` agent on real documents.

## File-naming convention

Each example is a **pair** of files with the same basename:

```
example_01.jpeg          # source image (or .jpg / .png)
example_01.expected.md   # ground-truth Markdown (Frontmatter + PaymentReceipt body)
```

- `<basename>.jpeg` — the source image. PNG is also acceptable; the eval
  harness sniffs by extension. Keep filenames lowercase, snake-case, and
  three-digit-padded once the corpus exceeds nine entries.
- `<basename>.expected.md` — a byte-stable Pydantic-rendered
  `PaymentReceipt` instance: YAML frontmatter followed by an empty body.
  All `PaymentReceipt` fields populated; debit/credit account fields use
  empty strings when only one side is visible (the single-side fallback
  documented in `prompts/payment_receipt.md`).

The basename must match exactly (including casing).

## Coverage targets

Story 3.3 acceptance calls for the four canonical bank-app receipt
formats Yang sees in production:

- **CN banking apps** — 工商银行 (ICBC), 中国银行 (BOC), 招商银行 (CMB),
  支付宝 (Alipay), 微信支付 (WeChat Pay). Mix of `付款人 / 收款人`
  Chinese labels and bilingual layouts.
- **NZ banking apps / online banking** — ANZ, ASB, BNZ, Westpac,
  Kiwibank. Particular attention to how each renders the debit/credit
  sides — some bank apps invert the English `Payer/Payee` label vs the
  flow on the screen, which is the well-known direction-correctness
  edge case (see Story 3.2 prompt).
- **Single-side fallback** — at least one USD Collinson receipt where
  only the credit (payee) side is visible.

## Versioning policy

- **Additions are non-breaking.** Append new examples freely.
- **Edits to existing `.expected.md` files** require bumping the
  `extractor_version` field per the byte-contract regression rule.

## Provenance

Source images are drawn from the `golden-mountain-storage` S3 bucket.
The seeder script `scripts/seed_golden_corpus.py` (currently passport-
only) will be extended to produce `PaymentReceipt` drafts from legacy
`s3://golden-mountain-analysis/` extractions; drafts land in
`.local/golden-drafts/payment_receipt/` (gitignored) for hand-redaction
before promotion to this directory.

## What this directory does NOT contain

- No real account numbers or transaction amounts in committed
  `.expected.md` files. Use redacted masks (`6217 **** **** 0083`) and
  synthetic amounts that preserve format characteristics (decimals,
  currency code) without leaking real customer movements.
- No model-generated outputs without human review.
