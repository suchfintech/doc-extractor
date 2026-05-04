# Golden corpus — Passport

Hand-labelled passport images and their expected extraction output.
The eval harness iterates these pairs to score the `Passport` agent
on real documents.

## File-naming convention

Each example is a **pair** of files with the same basename:

```
example_01.jpeg          # source image (or .jpg / .png)
example_01.expected.md   # ground-truth Markdown (Frontmatter + Passport body)
```

- `<basename>.jpeg` — the source image. PNG is also acceptable; the eval
  harness sniffs by extension. Keep filenames lowercase, snake-case, and
  three-digit-padded (`example_001`, `example_002`, …) once the corpus
  exceeds nine entries.
- `<basename>.expected.md` — a byte-stable Pydantic-rendered `Passport`
  instance: YAML frontmatter followed by an empty body. All `Passport`
  fields populated; use empty string for fields genuinely absent from
  the source document (e.g. an MRZ line that isn't visible).

The basename must match exactly (including casing).

## Versioning policy

- **Additions are non-breaking.** Append new examples freely.
- **Removals require justification.** Open a PR that documents why the
  example is no longer representative.
- **Edits to existing `.expected.md` files** require bumping the
  `extractor_version` field in the file's frontmatter, since the byte
  contract is the gating signal for regression detection.

## Coverage targets

The Story 4.1 / Story 1.6 spec calls for ≥10 examples covering the
biographical-page formats Yang ingests in production:

- **CN PRC passports** (中华人民共和国护照) — both pre-2017 issuance
  (10-year red booklet, 9-character `Gxxxxxxxx` document numbers) and
  post-2017 e-passports (`Exxxxxxxx` numbers). Mix of male/female,
  including at least one with a CJK-only signature panel and one with
  the parenthetical CJK-name format (`SUN, JIAWEI (孙嘉蔚)`).
- **NZ passports** (Kiwi navy booklet, `LK` prefix doc numbers) — at
  least two examples to anchor the non-MRZ secondary identifiers.
- **Mixed-jurisdiction** — one passport that exercises the `jurisdiction`
  vs `nationality` distinction (e.g. an HKSAR passport for a CN national).

## Provenance

Source images are picked by Yang from the `golden-mountain-storage` S3
bucket. A bootstrap helper at `scripts/seed_golden_corpus.py` produces
draft `.expected.md` files from the legacy free-text analyses sitting in
`s3://golden-mountain-analysis/`; drafts land in `.local/golden-drafts/`
(gitignored) so PII can be redacted by hand before promotion here.

```
python scripts/seed_golden_corpus.py --doc-type passport \
    --legacy-root /tmp/gt-scan/raw \
    --picks <relative legacy paths> \
    --out .local/golden-drafts/passport
```

## What this directory does NOT contain

- No PII in committed `.expected.md` files when an example is anonymised
  (use `XXXXXXX` / synthetic dates / placeholder names in the test corpus).
- No model-generated outputs without human review. The seeder above
  produces *drafts* — Yang signs off field-by-field before any draft
  becomes a committed ground-truth label.
