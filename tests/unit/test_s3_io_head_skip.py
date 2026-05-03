"""Mock-driven coverage for the S3 wrapper: HEAD 200/404 and presigned URLs."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from doc_extractor import s3_io


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the module-singleton boto3 client with a MagicMock for one test."""
    client = MagicMock()
    monkeypatch.setattr(s3_io, "_client", client)
    return client


def _client_error(status: int, code: str) -> ClientError:
    response: dict[str, Any] = {
        "Error": {"Code": code, "Message": "stubbed"},
        "ResponseMetadata": {"HTTPStatusCode": status},
    }
    return ClientError(response, "HeadObject")


def test_head_analysis_returns_true_on_200(mock_client: MagicMock) -> None:
    mock_client.head_object.return_value = {"ContentLength": 42}

    assert s3_io.head_analysis("passport/abc.md") is True
    mock_client.head_object.assert_called_once_with(
        Bucket=s3_io.ANALYSIS_BUCKET, Key="passport/abc.md"
    )


def test_head_analysis_returns_false_on_404(mock_client: MagicMock) -> None:
    mock_client.head_object.side_effect = _client_error(404, "404")

    assert s3_io.head_analysis("passport/missing.md") is False


def test_head_analysis_returns_false_on_no_such_key(mock_client: MagicMock) -> None:
    mock_client.head_object.side_effect = _client_error(404, "NoSuchKey")

    assert s3_io.head_analysis("passport/missing.md") is False


def test_head_analysis_propagates_other_errors(mock_client: MagicMock) -> None:
    mock_client.head_object.side_effect = _client_error(500, "InternalError")

    with pytest.raises(ClientError):
        s3_io.head_analysis("passport/abc.md")


def test_get_presigned_url_returns_non_empty_string(mock_client: MagicMock) -> None:
    mock_client.generate_presigned_url.return_value = (
        "https://golden-mountain-storage.s3.ap-southeast-2.amazonaws.com/foo?X-Amz-Signature=stub"
    )

    url = s3_io.get_presigned_url(s3_io.SOURCE_BUCKET, "foo/bar.pdf")

    assert isinstance(url, str)
    assert url
    mock_client.generate_presigned_url.assert_called_once_with(
        ClientMethod="get_object",
        Params={"Bucket": s3_io.SOURCE_BUCKET, "Key": "foo/bar.pdf"},
        ExpiresIn=s3_io.DEFAULT_PRESIGN_TTL_SECONDS,
    )


def test_get_presigned_url_passes_custom_ttl(mock_client: MagicMock) -> None:
    mock_client.generate_presigned_url.return_value = "https://example/x"

    s3_io.get_presigned_url(s3_io.SOURCE_BUCKET, "foo", ttl=60)

    _, kwargs = mock_client.generate_presigned_url.call_args
    assert kwargs["ExpiresIn"] == 60


def test_write_analysis_encodes_str_as_utf8(mock_client: MagicMock) -> None:
    s3_io.write_analysis("passport/张三.md", "hello — 世界")

    _, kwargs = mock_client.put_object.call_args
    assert kwargs["Bucket"] == s3_io.ANALYSIS_BUCKET
    assert kwargs["Key"] == "passport/张三.md"
    assert kwargs["Body"] == "hello — 世界".encode()


def test_write_analysis_passes_bytes_through(mock_client: MagicMock) -> None:
    raw = b"prebuilt bytes"
    s3_io.write_analysis("passport/raw.md", raw)

    _, kwargs = mock_client.put_object.call_args
    assert kwargs["Body"] is raw


def test_get_client_pins_region_to_ap_southeast_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(s3_io, "_client", None)
    captured: dict[str, Any] = {}

    def fake_boto3_client(service: str, region_name: str) -> MagicMock:
        captured["service"] = service
        captured["region_name"] = region_name
        return MagicMock()

    monkeypatch.setattr(s3_io.boto3, "client", fake_boto3_client)
    s3_io._get_client()

    assert captured == {"service": "s3", "region_name": "ap-southeast-2"}


def test_get_client_is_module_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(s3_io, "_client", None)
    monkeypatch.setattr(s3_io.boto3, "client", lambda *a, **kw: MagicMock())

    first = s3_io._get_client()
    second = s3_io._get_client()

    assert first is second
