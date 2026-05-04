"""Disagreement-queue durability integration test (Story 6.4 / NFR14).

The disagreement queue lives at ``s3://golden-mountain-analysis/disagreements/<source_key>.json``.
Once S3 acknowledges the PutObject, the bytes are durable — a process kill
mid-call does NOT corrupt the bucket. This file pins that contract by
simulating a runtime crash *after* the mock S3 backend has accepted the
payload and confirming a "restart" can read the full 10-field forensic
JSON (Story 6.1 shape).

Conceptually tagged ``integration`` (uses real ``record_disagreement`` +
``s3_io.read_analysis`` against an in-memory S3 stub). Pytest's marker
registry is not yet configured for the project, so the tag is documented
in this docstring rather than applied via ``@pytest.mark.integration`` —
applying an unregistered marker would emit a per-test warning. Move to a
real marker once ``[tool.pytest.ini_options].markers`` adds an entry.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from doc_extractor import s3_io
from doc_extractor.disagreement import record_disagreement
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.verifier import VerifierAudit

# ---------------------------------------------------------------------------
# In-memory S3 stub — durable across simulated runtime restarts
# ---------------------------------------------------------------------------


class _MockS3Bucket:
    """Persistent state for the simulated S3 backend.

    Outlives any individual ``_MockS3Client`` instance — the analogue of S3
    objects surviving when a process dies. New "runtime restarts" build a
    fresh client over the SAME bucket so durability shows through.
    """

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}


class _BytesStream:
    """boto3 ``Body`` shim — a single ``.read()`` returns the captured bytes."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MockS3Client:
    """Records every PutObject body BEFORE optionally raising a simulated
    runtime error. The pre-raise capture is the key durability simulation:
    the bytes are on S3 first, then the runtime dies."""

    def __init__(
        self,
        bucket: _MockS3Bucket,
        *,
        raise_after_put: bool = False,
        raise_message: str = "simulated process kill — bytes already on S3",
    ) -> None:
        self._bucket = bucket
        self._raise_after_put = raise_after_put
        self._raise_message = raise_message
        self.put_count = 0

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: str | bytes,
        **_kwargs: Any,
    ) -> dict[str, str]:
        body_bytes = Body if isinstance(Body, bytes) else Body.encode("utf-8")
        # Capture FIRST — durability invariant.
        self._bucket.objects[(Bucket, Key)] = body_bytes
        self.put_count += 1
        if self._raise_after_put:
            raise RuntimeError(self._raise_message)
        return {"ETag": f"etag-{self.put_count}"}

    def get_object(
        self,
        *,
        Bucket: str,
        Key: str,
        **_kwargs: Any,
    ) -> dict[str, _BytesStream]:
        return {"Body": _BytesStream(self._bucket.objects[(Bucket, Key)])}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SOURCE_KEY = "documents/transactions/12345/abc.jpeg"
EXPECTED_DISAGREEMENT_KEY = f"disagreements/{SOURCE_KEY}.json"


def _payment_receipt() -> PaymentReceipt:
    return PaymentReceipt(
        doc_type="PaymentReceipt",
        jurisdiction="CN",
        receipt_amount="15000.00",
        receipt_currency="CNY",
        receipt_debit_account_name="张三",
        receipt_debit_account_number="6217 **** **** 0083",
        receipt_credit_account_name="李四",
    )


def _failing_audit(*, on_field: str = "receipt_credit_account_name") -> VerifierAudit:
    audits = {"receipt_debit_account_name": "agree", on_field: "disagree"}
    return VerifierAudit(field_audits=audits, notes=f"image disagrees on {on_field}")


def _primary_raw() -> tuple[str, dict[str, Any]]:
    return (
        "primary raw — 张三 / 李四 / 6217 **** **** 0083",
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6-20260101",
            "latency_ms": 1234.5,
            "cost_usd": 0.0123,
        },
    )


def _verifier_raw() -> tuple[str, dict[str, Any]]:
    return (
        "verifier raw — disagree on credit (image shows 王五)",
        {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6-20260101",
            "latency_ms": 987.6,
            "cost_usd": 0.0234,
        },
    )


def _install_s3_client(
    monkeypatch: pytest.MonkeyPatch, client: _MockS3Client
) -> None:
    """Make ``s3_io._get_client()`` return ``client`` and clear the singleton.

    Resetting ``s3_io._client`` to None alongside is what simulates a
    "runtime restart" — the next call would normally instantiate a fresh
    boto3 client; here ``_get_client`` is patched to hand back our mock.
    """
    monkeypatch.setattr(s3_io, "_client", None)
    monkeypatch.setattr(s3_io, "_get_client", lambda: client)


# ---------------------------------------------------------------------------
# Test 1 — Mid-write crash; bytes survive; restart reads full payload
# ---------------------------------------------------------------------------


def test_disagreement_bytes_survive_mid_write_runtime_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket = _MockS3Bucket()

    # === Simulated runtime #1: crashes after S3 captures the bytes. ===
    crashing_client = _MockS3Client(bucket, raise_after_put=True)
    _install_s3_client(monkeypatch, crashing_client)

    with pytest.raises(RuntimeError, match="simulated process kill"):
        record_disagreement(
            source_key=SOURCE_KEY,
            primary=_payment_receipt(),
            verifier=_failing_audit(),
            status="disagreement",
            extractor_version="0.1.0",
            primary_raw=_primary_raw(),
            verifier_raw=_verifier_raw(),
        )

    # The bytes hit S3 BEFORE the simulated kill — that's the NFR14 contract.
    assert (s3_io.ANALYSIS_BUCKET, EXPECTED_DISAGREEMENT_KEY) in bucket.objects
    assert crashing_client.put_count == 1

    # === Simulated runtime restart: fresh client, same bucket. ===
    fresh_client = _MockS3Client(bucket, raise_after_put=False)
    _install_s3_client(monkeypatch, fresh_client)

    body = s3_io.read_analysis(EXPECTED_DISAGREEMENT_KEY).decode("utf-8")
    entry: dict[str, Any] = json.loads(body)

    # All 10 forensic fields (Story 6.1 shape) survived the crash.
    assert set(entry.keys()) == {
        "source_key",
        "primary",
        "verifier",
        "agreement_status",
        "timestamp",
        "extractor_version",
        "primary_raw_response_text",
        "primary_raw_response_metadata",
        "verifier_raw_response_text",
        "verifier_raw_response_metadata",
    }
    assert entry["source_key"] == SOURCE_KEY
    assert entry["agreement_status"] == "disagreement"
    assert entry["extractor_version"] == "0.1.0"
    assert entry["primary"]["receipt_debit_account_name"] == "张三"
    assert entry["verifier"]["overall"] == "fail"
    primary_text, primary_meta = _primary_raw()
    assert entry["primary_raw_response_text"] == primary_text
    assert entry["primary_raw_response_metadata"] == primary_meta
    verifier_text, verifier_meta = _verifier_raw()
    assert entry["verifier_raw_response_text"] == verifier_text
    assert entry["verifier_raw_response_metadata"] == verifier_meta


# ---------------------------------------------------------------------------
# Test 2 — Stable identity: same source_key → same path → overwrite
# ---------------------------------------------------------------------------


def test_repeat_writes_with_same_source_key_target_same_s3_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket = _MockS3Bucket()
    client = _MockS3Client(bucket)
    _install_s3_client(monkeypatch, client)

    # First write: verifier failed on debit name.
    record_disagreement(
        source_key=SOURCE_KEY,
        primary=_payment_receipt(),
        verifier=_failing_audit(on_field="receipt_debit_account_name"),
        status="disagreement",
        extractor_version="0.1.0",
        primary_raw=_primary_raw(),
        verifier_raw=_verifier_raw(),
    )

    # Second write: verifier failed on credit name (different audit, same source_key).
    record_disagreement(
        source_key=SOURCE_KEY,
        primary=_payment_receipt(),
        verifier=_failing_audit(on_field="receipt_credit_account_name"),
        status="disagreement",
        extractor_version="0.1.0",
        primary_raw=_primary_raw(),
        verifier_raw=_verifier_raw(),
    )

    # Two writes targeted the SAME S3 key — the bucket has exactly one object
    # for the disagreement, and the second write overwrote the first.
    assert client.put_count == 2
    assert len(bucket.objects) == 1
    assert (s3_io.ANALYSIS_BUCKET, EXPECTED_DISAGREEMENT_KEY) in bucket.objects

    # The persisted body is the SECOND write (post-overwrite). The verdict
    # against `receipt_credit_account_name` is the surviving record.
    body = bucket.objects[(s3_io.ANALYSIS_BUCKET, EXPECTED_DISAGREEMENT_KEY)].decode(
        "utf-8"
    )
    entry: dict[str, Any] = json.loads(body)
    assert entry["verifier"]["field_audits"]["receipt_credit_account_name"] == "disagree"
    # First write's audit on debit name is gone (overwrite, not accumulate).
    assert entry["verifier"]["field_audits"]["receipt_debit_account_name"] == "agree"


# ---------------------------------------------------------------------------
# Test 3 — Path is independent of extractor_version
# ---------------------------------------------------------------------------


def test_disagreement_path_is_stable_across_extractor_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same source_key with two different ``extractor_version`` values must
    target the same S3 path. The version is forensic content; it must not
    change the queue identity (otherwise replays would shadow the original
    queue entry under a different path)."""
    bucket = _MockS3Bucket()
    client = _MockS3Client(bucket)
    _install_s3_client(monkeypatch, client)

    record_disagreement(
        source_key=SOURCE_KEY,
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
        extractor_version="0.1.0",
        primary_raw=_primary_raw(),
        verifier_raw=_verifier_raw(),
    )
    record_disagreement(
        source_key=SOURCE_KEY,
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
        extractor_version="0.2.0-beta",  # ← different content, same identity
        primary_raw=_primary_raw(),
        verifier_raw=_verifier_raw(),
    )

    assert client.put_count == 2
    assert list(bucket.objects.keys()) == [
        (s3_io.ANALYSIS_BUCKET, EXPECTED_DISAGREEMENT_KEY)
    ]

    body = bucket.objects[(s3_io.ANALYSIS_BUCKET, EXPECTED_DISAGREEMENT_KEY)].decode(
        "utf-8"
    )
    entry: dict[str, Any] = json.loads(body)
    # Surviving record reflects the second write's version (last-writer-wins).
    assert entry["extractor_version"] == "0.2.0-beta"


# ---------------------------------------------------------------------------
# Test 4 — Different source_keys must NOT collide (negative sentinel)
# ---------------------------------------------------------------------------


def test_distinct_source_keys_target_distinct_s3_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sentinel for the path-derivation rule: differing source_keys produce
    differing S3 keys — no shared path → no accidental overwrite. Pairs
    with the stable-identity test above to bracket the contract from
    both sides."""
    bucket = _MockS3Bucket()
    client = _MockS3Client(bucket)
    _install_s3_client(monkeypatch, client)

    record_disagreement(
        source_key="documents/a/foo.jpeg",
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
    )
    record_disagreement(
        source_key="documents/b/bar.jpeg",
        primary=_payment_receipt(),
        verifier=_failing_audit(),
        status="disagreement",
    )

    keys = {key for (_bucket, key) in bucket.objects}
    assert keys == {
        "disagreements/documents/a/foo.jpeg.json",
        "disagreements/documents/b/bar.jpeg.json",
    }
    assert client.put_count == 2


# ---------------------------------------------------------------------------
# Test 5 — Forensic payload is the FULL 10-field shape, not a partial subset
# ---------------------------------------------------------------------------


def test_persisted_payload_matches_full_forensic_shape_post_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mid-write interruption must not yield a partially-serialised JSON
    body. ``json.dumps(entry, ...)`` either succeeds-then-writes or raises
    locally; there's no in-between. This test pins that contract by
    parsing the persisted body and checking every field is present and
    well-typed."""
    bucket = _MockS3Bucket()
    crashing_client = _MockS3Client(bucket, raise_after_put=True)
    _install_s3_client(monkeypatch, crashing_client)

    with pytest.raises(RuntimeError):
        record_disagreement(
            source_key=SOURCE_KEY,
            primary=_payment_receipt(),
            verifier=_failing_audit(),
            status="disagreement",
            extractor_version="0.1.0",
            primary_raw=_primary_raw(),
            verifier_raw=_verifier_raw(),
        )

    # Restart and parse.
    fresh_client = _MockS3Client(bucket)
    _install_s3_client(monkeypatch, fresh_client)
    entry: dict[str, Any] = json.loads(
        s3_io.read_analysis(EXPECTED_DISAGREEMENT_KEY).decode("utf-8")
    )

    # All four "block" fields are populated with the right types.
    assert isinstance(entry["primary"], dict)
    assert isinstance(entry["verifier"], dict)
    assert isinstance(entry["primary_raw_response_text"], str)
    assert isinstance(entry["primary_raw_response_metadata"], dict)
    assert isinstance(entry["verifier_raw_response_text"], str)
    assert isinstance(entry["verifier_raw_response_metadata"], dict)
    # Metadata blocks have all four sub-fields.
    for meta_field in ("primary_raw_response_metadata", "verifier_raw_response_metadata"):
        meta = entry[meta_field]
        assert set(meta.keys()) == {"provider", "model", "latency_ms", "cost_usd"}
        assert isinstance(meta["provider"], str)
        assert isinstance(meta["model"], str)
        assert isinstance(meta["latency_ms"], (int, float))
        assert isinstance(meta["cost_usd"], (int, float))
    # ISO-8601 Z timestamp.
    assert isinstance(entry["timestamp"], str)
    assert entry["timestamp"].endswith("Z")


# ---------------------------------------------------------------------------
# P7 (code review Round 3) — write order: disagreement BEFORE analysis
#
# Pre-fix vision_path.run wrote ``analysis_key`` first and
# ``record_disagreement`` second. If ``record_disagreement`` failed
# (network blip, IAM glitch, etc.), the next idempotent retry would see
# the analysis on S3, head_analysis would short-circuit, and the
# disagreement entry would be permanently lost. P7 reverses the order.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_path_writes_disagreement_before_analysis_on_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end ordering invariant: ``record_disagreement`` runs
    BEFORE ``write_analysis`` when the verifier returns ``overall=='fail'``.
    Pre-P7, the order was reversed and a partial-write could orphan the
    disagreement entry across an idempotent retry."""
    from unittest.mock import AsyncMock, MagicMock

    from agno.agent import Agent

    from doc_extractor.pipelines import vision_path
    from doc_extractor.schemas.classification import Classification

    # Single recorder ledger captures both writes in observed order.
    write_order: list[str] = []

    def fake_write_analysis(key: str, body: str | bytes) -> None:
        write_order.append(f"analysis:{key}")

    def fake_record(*, source_key: str, **_: Any) -> str:
        write_order.append(f"disagreement:{source_key}")
        return f"disagreements/{source_key}.json"

    head = MagicMock(return_value=False)
    head_src = MagicMock(return_value={"content_type": "image/jpeg", "size": 1024})
    presign = MagicMock(return_value="https://example.invalid/url")
    monkeypatch.setattr(s3_io, "head_analysis", head)
    monkeypatch.setattr(s3_io, "head_source", head_src)
    monkeypatch.setattr(s3_io, "get_presigned_url", presign)
    monkeypatch.setattr(s3_io, "write_analysis", fake_write_analysis)
    monkeypatch.setattr(vision_path, "record_disagreement", fake_record)
    monkeypatch.setattr(vision_path, "record_extraction", lambda **_: None)

    # Build mocks for classifier / specialist / verifier (verifier returns
    # overall=='fail' so the disagreement path triggers).
    def _agent(content: Any) -> Agent:
        agent = MagicMock(spec=Agent)
        agent.arun = AsyncMock(return_value=MagicMock(content=content))
        agent.run_response = None
        return agent

    classifier = _agent(Classification(doc_type="PaymentReceipt", jurisdiction="CN"))
    pr = _agent(_payment_receipt())
    verifier = _agent(_failing_audit())

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda **_: classifier)
    monkeypatch.setitem(vision_path.FACTORIES, "PaymentReceipt", lambda **_: pr)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda **_: verifier)

    await vision_path.run(SOURCE_KEY)

    # Disagreement MUST land first; if it doesn't, a partial write that
    # corrupts the second step orphans the disagreement entry.
    assert write_order == [
        f"disagreement:{SOURCE_KEY}",
        f"analysis:{SOURCE_KEY}.md",
    ], write_order


@pytest.mark.asyncio
async def test_partial_write_failure_keeps_disagreement_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``write_analysis`` raises after ``record_disagreement`` succeeds,
    the next idempotent retry sees no analysis (HEAD-skip doesn't fire),
    re-runs the pipeline, and re-writes the disagreement (last-writer-wins
    per Story 6.4). Pre-P7, the order was reversed so write_analysis
    landed first; a record_disagreement failure orphaned the entry under
    a HEAD-skip that fired on retry."""
    from unittest.mock import AsyncMock, MagicMock

    from agno.agent import Agent

    from doc_extractor.pipelines import vision_path
    from doc_extractor.schemas.classification import Classification

    disagreement_calls: list[str] = []

    def fake_record(*, source_key: str, **_: Any) -> str:
        disagreement_calls.append(source_key)
        return f"disagreements/{source_key}.json"

    def crashing_write_analysis(key: str, body: str | bytes) -> None:
        raise RuntimeError("S3 write_analysis failed mid-call")

    head = MagicMock(return_value=False)
    head_src = MagicMock(return_value={"content_type": "image/jpeg", "size": 1024})
    presign = MagicMock(return_value="https://example.invalid/url")
    monkeypatch.setattr(s3_io, "head_analysis", head)
    monkeypatch.setattr(s3_io, "head_source", head_src)
    monkeypatch.setattr(s3_io, "get_presigned_url", presign)
    monkeypatch.setattr(s3_io, "write_analysis", crashing_write_analysis)
    monkeypatch.setattr(vision_path, "record_disagreement", fake_record)
    monkeypatch.setattr(vision_path, "record_extraction", lambda **_: None)

    def _agent(content: Any) -> Agent:
        agent = MagicMock(spec=Agent)
        agent.arun = AsyncMock(return_value=MagicMock(content=content))
        agent.run_response = None
        return agent

    classifier = _agent(Classification(doc_type="PaymentReceipt", jurisdiction="CN"))
    pr = _agent(_payment_receipt())
    verifier = _agent(_failing_audit())

    monkeypatch.setattr(vision_path, "create_classifier_agent", lambda **_: classifier)
    monkeypatch.setitem(vision_path.FACTORIES, "PaymentReceipt", lambda **_: pr)
    monkeypatch.setattr(vision_path, "create_verifier_agent", lambda **_: verifier)

    with pytest.raises(RuntimeError, match="write_analysis failed"):
        await vision_path.run(SOURCE_KEY)

    # The disagreement was recorded BEFORE write_analysis crashed — so even
    # though the run aborted, the queue entry persisted. The next retry
    # will not see an analysis (it never landed), so HEAD-skip won't fire
    # and the run will execute again — re-writing the same disagreement
    # entry under the stable source_key path.
    assert disagreement_calls == [SOURCE_KEY]
