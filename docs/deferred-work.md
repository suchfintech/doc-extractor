# Deferred work

Items that are intentionally not done yet. Each entry says **why now isn't
the right time** so future-Yang doesn't burn cycles re-deciding.

## Story 2.1 — golden corpus population

**Decided:** 2026-05-04
**Status:** infrastructure shipped, content pending; not blocking any
active work stream.

**What's there:** the bootstrap tool (`scripts/seed_golden_corpus.py`)
covers all 14 specialists + Other via the `MAPPERS` registry, validated
through `markdown_io.parse_md` round-trip on every draft. The two
previously-missing golden dirs (`tests/golden/passport/`,
`tests/golden/payment_receipt/`) now exist with READMEs that pin the
coverage targets.

**What's not there:** zero `.expected.md` files committed in any of the
15 golden dirs. The eval harness's regression-detection signal is
therefore vacuous — `doc-extractor eval` runs but scores nothing.

**Why deferred:** the corpus is future infrastructure for prompt /
schema iteration, not present-day blocking work. The DIA submission and
the compliance daemon both ship without it. Auto-generating 75+ drafts
now would commit Yang to a redaction backlog with no immediate payoff.

**When to come back:** at the *next* moment any of these hit —

* a prompt is being tuned (e.g. PaymentReceipt direction-correctness
  edge cases) and a regression signal is wanted before merge
* a schema is being rev'd (the FR27 deprecated-alias overlap expires
  **2026-08-03** — that's the latest natural trigger)
* a new specialist is being added
* the nightly determinism CI test (Story 2.8) wants > 1 reference image

**Pickup recipe (just-in-time, per-doc-type):**

```bash
# 1. Sync legacy analyses (one-off; ~28k md files, ~10 min)
aws s3 sync s3://golden-mountain-analysis/documents/ /tmp/gt-scan/raw/ \
    --include "*.md" --quiet

# 2. Generate 5 drafts for the type you're touching
python scripts/seed_golden_corpus.py \
    --doc-type payment_receipt \
    --legacy-root /tmp/gt-scan/raw \
    --auto 5 \
    --out .local/golden-drafts/payment_receipt

# 3. Review + redact PII per tests/golden/<type>/README.md policy
# 4. Promote cleaned files into tests/golden/<type>/
# 5. Same PR: ship the prompt/schema change + the corresponding corpus update
```

`.local/` is gitignored — drafts contain real customer PII and must not
leave the dev machine until redacted.

## Story 2.8 — determinism CI workflow secrets

**Decided:** 2026-05-04
**Status:** workflow + test shipped; secrets unset, so the nightly
schedule will fail until populated.

`tests/canonical/test_determinism.py` is gated on `RUN_DETERMINISM=1`
and skips cleanly without it. The nightly `.github/workflows/
determinism.yml` runs `RUN_DETERMINISM=1 pytest tests/canonical/` and
will fail with missing-env errors until these GitHub Actions secrets
are populated:

* `DETERMINISM_SOURCE_KEY_A`
* `DETERMINISM_SOURCE_KEY_B` — independent S3 key pointing at the same
  canonical Passport image (avoids HEAD-skip on run 2)
* `ANTHROPIC_API_KEY`
* `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`

Pure ops handoff — no code change required.
