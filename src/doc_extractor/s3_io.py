"""Thin boto3 wrapper for the source / analysis buckets.

Centralises every S3 call so idempotency (HEAD-skip) and presigned-URL TTLs
are configured in exactly one place. The boto3 client is a module-level
singleton, instantiated lazily.

Region is pinned to ``ap-southeast-2`` per FR43 (data residency).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
else:
    S3Client = object  # runtime placeholder; boto3 returns an opaque client

AWS_REGION = "ap-southeast-2"

SOURCE_BUCKET = "golden-mountain-storage"
ANALYSIS_BUCKET = "golden-mountain-analysis"

DEFAULT_PRESIGN_TTL_SECONDS = 3600

_client: S3Client | None = None


def _get_client() -> S3Client:
    """Return the module-singleton S3 client, creating it on first use."""
    global _client
    if _client is None:
        _client = boto3.client("s3", region_name=AWS_REGION)
    return _client


def get_presigned_url(bucket: str, key: str, ttl: int = DEFAULT_PRESIGN_TTL_SECONDS) -> str:
    """Issue a time-limited GET URL usable with ``agno.media.Image(url=...)``.

    ``ttl`` is in seconds; default 1 hour matches AR5.
    """
    url: str = _get_client().generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=ttl,
    )
    return url


def head_source(key: str) -> dict[str, str | int]:
    """Return source-object metadata for the MIME-detection pre-step.

    Returns ``{"content_type": <str>, "size": <int>}`` with empty / zero
    values when S3 omits the corresponding response field. Errors propagate;
    a missing object surfaces as ``ClientError`` so the caller can decide.
    """
    response = _get_client().head_object(Bucket=SOURCE_BUCKET, Key=key)
    content_type = str(response.get("ContentType") or "")
    size = int(response.get("ContentLength") or 0)
    return {"content_type": content_type, "size": size}


def get_source_bytes(key: str) -> bytes:
    """Fetch the full body of ``s3://golden-mountain-storage/<key>`` as bytes.

    Used when a source needs local preprocessing (currently: PDFs rendered
    to PNGs by ``pdf.converter.pdf_to_images``) instead of being handed to
    the model as a presigned URL.
    """
    response = _get_client().get_object(Bucket=SOURCE_BUCKET, Key=key)
    body: bytes = response["Body"].read()
    return body


def head_analysis(key: str) -> bool:
    """Return True iff ``s3://golden-mountain-analysis/<key>`` exists.

    The caller passes the full key including any ``.md`` suffix; this function
    does not append anything. 404 / NoSuchKey returns False; any other error
    propagates so it can be observed.
    """
    try:
        _get_client().head_object(Bucket=ANALYSIS_BUCKET, Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if error_code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return False
        raise
    return True


def read_analysis(key: str) -> bytes:
    """Read ``s3://golden-mountain-analysis/<key>`` and return the raw bytes.

    The caller decodes (typically UTF-8). Errors propagate; in particular a
    missing object surfaces as ``ClientError`` with code ``NoSuchKey`` so the
    caller can decide between treating that as a 404 or a hard failure.
    """
    response = _get_client().get_object(Bucket=ANALYSIS_BUCKET, Key=key)
    body: bytes = response["Body"].read()
    return body


def write_analysis(key: str, body: str | bytes) -> None:
    """Write a Markdown analysis blob, UTF-8 encoded, to the analysis bucket.

    Strings are encoded as UTF-8 verbatim (no ASCII escaping) so CJK and other
    non-Latin glyphs round-trip — the ``allow_unicode=True`` semantics carried
    over from the YAML serialiser into the storage layer.
    """
    payload = body.encode("utf-8") if isinstance(body, str) else body
    _get_client().put_object(
        Bucket=ANALYSIS_BUCKET,
        Key=key,
        Body=payload,
        ContentType="text/markdown; charset=utf-8",
    )


def write_disagreement(key: str, body: str | bytes) -> None:
    """Write a disagreement-queue JSON entry to the analysis bucket.

    Lives alongside ``write_analysis`` because the disagreement queue shares
    the same bucket — only the key prefix differs (``disagreements/...``).
    Bucket layout (Decision 1):

    - ``<source_key>.md``                       — extracted analysis (write_analysis).
    - ``disagreements/<source_key>.json``       — disagreement-queue entry.
    - ``corrections/<source_key>.md``           — human corrections overlay (Story 6.2).
    """
    payload = body.encode("utf-8") if isinstance(body, str) else body
    _get_client().put_object(
        Bucket=ANALYSIS_BUCKET,
        Key=key,
        Body=payload,
        ContentType="application/json; charset=utf-8",
    )
