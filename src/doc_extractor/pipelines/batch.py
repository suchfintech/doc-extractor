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
"""

from __future__ import annotations

import asyncio
from typing import cast

from doc_extractor.agents.retry import with_rate_limit_retry
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
    """
    if max_concurrent <= 0:
        raise ValueError(f"max_concurrent must be positive, got {max_concurrent}")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded(k: str) -> ExtractedDoc:
        async with semaphore:
            # with_rate_limit_retry returns Any; we know extract() yields
            # ExtractedDoc and rate-limit retry is a transparent shell.
            return cast(ExtractedDoc, await with_rate_limit_retry(lambda: extract(k)))

    return await asyncio.gather(*(_bounded(k) for k in keys))
