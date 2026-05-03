# Vendor data-handling — provider review

This document records the data-handling clauses of each vendor used by
doc-extractor's `VisionModelFactory.PROVIDERS` dict. A new provider added to
`src/doc_extractor/agents/factory.py` MUST land a row here in the same PR
— enforced by `tests/unit/test_provider_terms_documented.py` (NFR11).

The CI gate parses this table by Markdown column and asserts:

- Every key in `PROVIDERS` has a row whose `Provider` cell matches the dict
  key (case-insensitive, with `_` ↔ `-` ↔ space tolerance).
- Every row has a non-empty `Source URL`, `Retrieval date`, and `Reviewer`.

If you change a row's URL or terms, bump the `Retrieval date` to the day
you re-read the vendor's policy.

| Provider | Source URL | Retrieval date | Training on API data? | Retention window | Reviewer |
|---|---|---|---|---|---|
| anthropic | https://www.anthropic.com/legal/commercial-terms `[NEEDS-VERIFICATION]` | 2026-05-03 | No (per commercial terms — confirm specific clause on next review) | 30 days for abuse monitoring | Yang Gao |
| openai | https://openai.com/policies/api-data-usage-policies `[NEEDS-VERIFICATION]` | 2026-05-03 | No (API endpoint default since 2023-03-01) | 30 days | Yang Gao |
| openai_like | n/a — generic OpenAI-compatible slot; the actual upstream provider's terms govern. Caller MUST add a vendor-specific row before defaulting any agent to a concrete OpenAI-compatible vendor. | 2026-05-03 | depends on upstream | depends on upstream | Yang Gao |

## DashScope (Qwen-VL) — DEFERRED

Not in `PROVIDERS` for v1 per FR33 (architecture Decision 5). The Alibaba /
DashScope ToS for Qwen-VL must be reviewed and a row added here before
DashScope can be set as the default for any agent. The `# TODO(Story 7.4)`
comment in `factory.py` references this file as the gate.

## Adding a new provider — checklist

1. Add the provider entry to `VisionModelFactory.PROVIDERS` in
   `src/doc_extractor/agents/factory.py`.
2. Add a row to the table above with all six columns populated.
3. Re-run `pytest tests/unit/test_provider_terms_documented.py` locally
   before pushing — the gate fails CI otherwise.
4. If the vendor's terms change between reviews, bump the `Retrieval date`
   and update the URL / clauses as needed.
