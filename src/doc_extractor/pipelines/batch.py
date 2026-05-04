"""Batched extraction with bounded concurrency + rate-limit retry.

Story 8.4 first introduced ``extract_batch`` inside ``extract.py`` as a
thin semaphore wrapper. Story 8.5 lifts it into its own module so the
CLI's ``--keys-file`` surface and the rate-limit retry shell have a
clear home, separate from the single-key library entry point.

The two retry layers stack like this:

- ``with_validation_retry`` (worker-1's, agents/retry.py) is *inside*
  the pipeline — wraps the specialist agent call to escalate one tier
  on Pydantic validation errors.
- ``with_rate_limit_retry`` is *outside* at the batch level — wraps the
  whole per-key ``extract()`` call so a 429 from any provider in the
  pipeline fans out into exponential backoff with jitter.

NFR2 — 100 docs ≤ 10 minutes — is the perf target. Real-provider latency
dominates; the asyncio overhead is bounded by ``max_concurrent``.

P9 (code review Round 3) — when ``with_rate_limit_retry`` exhausts its
budget on a single key, the resulting ``ModelRateLimitError`` is caught
per-key here, routed to the disagreement queue with
``status="rate_limited"`` (Decision 6, Story 6.1's documented status
enum), and the failed key surfaces as a sentinel ``ExtractedDoc`` so
the surrounding ``asyncio.gather`` returns instead of tearing down the
whole batch.
"""

from __future__ import annotations

import asyncio
from typing import cast

from agno.exceptions import ModelRateLimitError

from doc_extractor import __version__
from doc_extractor.agents.retry import with_rate_limit_retry
from doc_extractor.disagreement import record_disagreement
from doc_extractor.extract import ExtractedDoc, extract

DEFAULT_BATCH_CONCURRENCY = 10


async def extract_batch(
    keys: list[str], *, max_concurrent: int = DEFAULT_BATCH_CONCURRENCY
) -> list[ExtractedDoc]:
    """Extract many documents with bounded concurrency + rate-limit retry.

    Each key independently HEAD-skips inside :func:`extract`. A semaphore
    bounds concurrent provider calls so a large batch over a partially
    extracted prefix doesn't hammer the model APIs. Each in-flight call
    is wrapped in :func:`with_rate_limit_retry` (exponential backoff with
    jitter) so a transient 429 doesn't fail the whole batch. Results
    return in input order.

    Per-key rate-limit isolation (P9): when a single key exhausts the
    ``with_rate_limit_retry`` budget, it routes to the disagreement
    queue (``status="rate_limited"``) and surfaces as a sentinel
    ``ExtractedDoc(skipped=False, doc_type=None)`` rather than
    propagating ``ModelRateLimitError`` up through ``asyncio.gather``.
    Pre-P9, one rate-limited key would abort the entire batch via
    gather's tear-down semantics — a 99-document run could lose all
    99 successes if the 100th key got rate-limited.
    """
    if max_concurrent <= 0:
        raise ValueError(f"max_concurrent must be positive, got {max_concurrent}")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded(k: str) -> ExtractedDoc:
        async with semaphore:
            try:
                # with_rate_limit_retry returns Any; we know extract()
                # yields ExtractedDoc and rate-limit retry is a
                # transparent shell.
                return cast(
                    ExtractedDoc, await with_rate_limit_retry(lambda: extract(k))
                )
            except ModelRateLimitError:
                # Decision 6 — exhausted retry budget routes to the
                # disagreement queue. The sentinel ExtractedDoc keeps
                # gather's positional return shape so the caller can
                # correlate which keys failed without losing the
                # surrounding successful results.
                record_disagreement(
                    source_key=k,
                    primary=None,
                    verifier=None,
                    status="rate_limited",
                    extractor_version=__version__,
                )
                return ExtractedDoc(
                    key=k,
                    skipped=False,
                    analysis_key=f"{k}.md",
                    doc_type=None,
                    cost_usd=0.0,
                )

    return await asyncio.gather(*(_bounded(k) for k in keys))
