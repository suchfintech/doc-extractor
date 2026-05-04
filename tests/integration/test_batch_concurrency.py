"""Story 8.5 integration tests.

Covers the four moving parts:

- ``pipelines.batch.extract_batch`` honours the ``max_concurrent``
  semaphore (no more than N keys in-flight at once) and stays within
  NFR2's 10-minute envelope on a 100-key batch when ``extract`` is
  effectively instant.
- The CLI ``--keys-file`` reader filters blanks + ``#`` comments and
  forwards the cleaned list to ``extract_batch``.
- The CLI mutual exclusion between ``--key`` and ``--keys-file`` exits
  via ``SystemExit`` from argparse.
- ``with_rate_limit_retry`` retries on rate-limit errors with backoff
  and re-raises after ``max_retries``.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.exceptions import ModelRateLimitError

from doc_extractor import cli
from doc_extractor.agents import retry as retry_module
from doc_extractor.extract import ExtractedDoc
from doc_extractor.pipelines import batch as batch_module

batch_runtime = importlib.import_module("doc_extractor.pipelines.batch")


def _doc(key: str, *, skipped: bool = False) -> ExtractedDoc:
    return ExtractedDoc(
        key=key,
        skipped=skipped,
        analysis_key=f"{key}.md",
        doc_type=None if skipped else "Passport",
    )


@pytest.mark.asyncio
async def test_extract_batch_honours_max_concurrent_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At most ``max_concurrent`` extract() calls are in flight simultaneously."""
    in_flight = 0
    max_observed = 0
    lock = asyncio.Lock()

    async def fake_extract(key: str) -> ExtractedDoc:
        nonlocal in_flight, max_observed
        async with lock:
            in_flight += 1
            max_observed = max(max_observed, in_flight)
        # Yield the loop a few times so other coroutines can stack up.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        async with lock:
            in_flight -= 1
        return _doc(key)

    monkeypatch.setattr(batch_runtime, "extract", fake_extract)
    # Skip the rate-limit retry shell so we can isolate the semaphore behaviour.
    monkeypatch.setattr(
        batch_runtime,
        "with_rate_limit_retry",
        lambda factory, **_: factory(),
    )

    keys = [f"k-{i}" for i in range(100)]
    results = await batch_module.extract_batch(keys, max_concurrent=10)

    assert len(results) == 100
    assert [r.key for r in results] == keys
    assert max_observed <= 10, f"observed {max_observed} concurrent calls, limit 10"
    assert max_observed >= 5, (
        f"observed only {max_observed} concurrent — semaphore may not be saturating"
    )


@pytest.mark.asyncio
async def test_extract_batch_completes_well_under_nfr2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """100 instant-extract calls complete in well under 10 min — asyncio overhead bounded."""

    async def instant_extract(key: str) -> ExtractedDoc:
        return _doc(key)

    monkeypatch.setattr(batch_runtime, "extract", instant_extract)
    monkeypatch.setattr(
        batch_runtime,
        "with_rate_limit_retry",
        lambda factory, **_: factory(),
    )

    keys = [f"k-{i}" for i in range(100)]
    start = time.monotonic()
    results = await batch_module.extract_batch(keys, max_concurrent=10)
    elapsed = time.monotonic() - start

    assert len(results) == 100
    assert elapsed < 5.0, (
        f"extract_batch wall-clock {elapsed:.2f}s exceeds the 5s overhead budget "
        "for 100 instant-extracts (NFR2 dominated by real provider latency)"
    )


def test_cli_keys_file_filters_blanks_and_comments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    keys_file = tmp_path / "batch.txt"
    keys_file.write_text(
        "# this is a comment header\n"
        "passports/a.jpeg\n"
        "\n"
        "  passports/b.jpeg  \n"
        "# inline directive\n"
        "passports/c.jpeg\n"
        "passports/d.jpeg\n"
        "passports/e.jpeg\n",
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    async def fake_extract_batch(
        keys: list[str], *, max_concurrent: int
    ) -> list[ExtractedDoc]:
        captured["keys"] = list(keys)
        captured["max_concurrent"] = max_concurrent
        return [_doc(k) for k in keys]

    monkeypatch.setattr(cli, "extract_batch", fake_extract_batch)

    rc = cli.main(
        ["extract", "--keys-file", str(keys_file), "--max-concurrent", "3"]
    )

    assert rc == cli.EXIT_OK
    assert captured["keys"] == [
        "passports/a.jpeg",
        "passports/b.jpeg",
        "passports/c.jpeg",
        "passports/d.jpeg",
        "passports/e.jpeg",
    ]
    assert captured["max_concurrent"] == 3


def test_cli_key_and_keys_file_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    extract_calls = MagicMock()
    monkeypatch.setattr(cli, "extract", extract_calls)
    monkeypatch.setattr(cli, "extract_batch", extract_calls)

    keys_file = tmp_path / "batch.txt"
    keys_file.write_text("passports/a.jpeg\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        cli.main(
            ["extract", "--key", "passports/x.jpeg", "--keys-file", str(keys_file)]
        )

    assert exc_info.value.code != 0
    extract_calls.assert_not_called()


@pytest.mark.asyncio
async def test_with_rate_limit_retry_succeeds_after_two_429s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    async def flaky() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise ModelRateLimitError("rate limited", model_id="claude-haiku")
        return "ok"

    factory: Callable[[], Awaitable[str]] = flaky
    result = await retry_module.with_rate_limit_retry(
        factory, max_retries=3, base_delay=0.001
    )

    assert result == "ok"
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_with_rate_limit_retry_exhausts_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    async def always_429() -> str:
        attempts.append(1)
        raise ModelRateLimitError("rate limited", model_id="claude-haiku")

    with pytest.raises(ModelRateLimitError):
        await retry_module.with_rate_limit_retry(
            always_429, max_retries=3, base_delay=0.001
        )

    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_with_rate_limit_retry_propagates_non_rate_limit_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-rate-limit exceptions must surface immediately (no retry)."""
    attempts: list[int] = []

    async def bad() -> str:
        attempts.append(1)
        raise RuntimeError("not a rate limit")

    with pytest.raises(RuntimeError, match="not a rate limit"):
        await retry_module.with_rate_limit_retry(bad, max_retries=3, base_delay=0.001)

    assert len(attempts) == 1


# ---------------------------------------------------------------------------
# P9 (code review Round 3) — per-key rate-limit isolation in extract_batch
#
# Pre-fix, ``asyncio.gather`` without ``return_exceptions=True`` tore down
# the whole batch when any single key exhausted ``with_rate_limit_retry``.
# Decision 6 says route to disagreement queue with status="rate_limited"
# — these tests pin both sides: the gather completes, the ratelimited key
# surfaces as a sentinel, and the disagreement entry was written.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_batch_isolates_rate_limit_failure_to_one_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One rate-limited key in a batch of three must NOT fail the other
    two — the gather completes, the ratelimited key returns a sentinel
    ExtractedDoc(skipped=False, doc_type=None), and the surrounding
    successes pass through intact."""
    rate_limited_key = "passports/rate-limited.jpeg"

    async def fake_extract(key: str) -> ExtractedDoc:
        if key == rate_limited_key:
            raise ModelRateLimitError("rate limited", model_id="claude-sonnet")
        return _doc(key)

    monkeypatch.setattr(batch_runtime, "extract", fake_extract)
    # Use a real with_rate_limit_retry with max_retries=1 so the rate-limit
    # error propagates immediately (no backoff sleep in tests).
    monkeypatch.setattr(
        batch_runtime,
        "with_rate_limit_retry",
        lambda factory, **_: factory(),
    )

    disagreement_calls: list[dict[str, Any]] = []

    def fake_record(**kwargs: Any) -> str:
        disagreement_calls.append(kwargs)
        return f"disagreements/{kwargs['source_key']}.json"

    monkeypatch.setattr(batch_runtime, "record_disagreement", fake_record)

    keys = ["passports/ok-1.jpeg", rate_limited_key, "passports/ok-2.jpeg"]
    results = await batch_module.extract_batch(keys, max_concurrent=3)

    # All three results returned in input order (gather didn't tear down).
    assert [r.key for r in results] == keys
    assert results[0].skipped is False and results[0].doc_type == "Passport"
    assert results[2].skipped is False and results[2].doc_type == "Passport"

    # The rate-limited key surfaces as a sentinel (Decision 6 shape).
    sentinel = results[1]
    assert sentinel.key == rate_limited_key
    assert sentinel.skipped is False
    assert sentinel.doc_type is None
    assert sentinel.cost_usd == 0.0

    # And the disagreement queue captured the rate_limited event.
    assert len(disagreement_calls) == 1
    call = disagreement_calls[0]
    assert call["source_key"] == rate_limited_key
    assert call["status"] == "rate_limited"
    assert call["primary"] is None
    assert call["verifier"] is None


@pytest.mark.asyncio
async def test_extract_batch_handles_all_keys_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When EVERY key in the batch hits the rate-limit ceiling, the gather
    still completes — every result is a sentinel ExtractedDoc, every key
    routed to the disagreement queue. The batch as a whole is recoverable
    via re-run after backoff (each key independently HEAD-skip-evaluates)."""

    async def always_rate_limited(key: str) -> ExtractedDoc:
        raise ModelRateLimitError("rate limited", model_id="claude-sonnet")

    monkeypatch.setattr(batch_runtime, "extract", always_rate_limited)
    monkeypatch.setattr(
        batch_runtime,
        "with_rate_limit_retry",
        lambda factory, **_: factory(),
    )

    queue_calls: list[str] = []
    monkeypatch.setattr(
        batch_runtime,
        "record_disagreement",
        lambda **kw: queue_calls.append(kw["source_key"]) or f"d/{kw['source_key']}.json",
    )

    keys = [f"k-{i}" for i in range(5)]
    results = await batch_module.extract_batch(keys, max_concurrent=3)

    assert len(results) == 5
    # Every result is a sentinel (skipped=False, doc_type=None).
    for r in results:
        assert r.skipped is False
        assert r.doc_type is None
    # Every key got a queue entry.
    assert sorted(queue_calls) == sorted(keys)
