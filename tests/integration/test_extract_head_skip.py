"""Integration tests for HEAD-skip lift + extract_batch (Story 8.4)."""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from doc_extractor import s3_io
from doc_extractor.extract import ExtractedDoc, extract, extract_batch
from doc_extractor.pipelines import vision_path

extract_module = importlib.import_module("doc_extractor.extract")

KEY_FRESH = "passports/fresh.jpeg"
KEY_SKIPPED_1 = "passports/already-1.jpeg"
KEY_SKIPPED_2 = "passports/already-2.jpeg"
KEY_SKIPPED_3 = "passports/already-3.jpeg"


def _pipeline_result(key: str) -> dict[str, Any]:
    return {
        "analysis_key": f"{key}.md",
        "skipped": False,
        "doc_type": "Passport",
    }


@pytest.fixture
def mocked_pipeline(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Mock head_analysis (default False) and vision_path.run.

    P13 (code review Round 3) — extract.py no longer imports ``Image`` or
    constructs one. The previous fixture booby-trapped ``extract_module.Image``
    to assert "extract() never builds an Image" — moot now that the
    inline path is gone (extract() always delegates to vision_path.run).
    """
    head = MagicMock(return_value=False)
    image_calls = MagicMock()

    async def fake_run(key: str, **_: Any) -> dict[str, Any]:
        # Accept **kwargs because P13 added provider/model/verbose/dry_run/
        # show_image to vision_path.run's signature.
        image_calls(key)
        return _pipeline_result(key)

    pipeline_run = AsyncMock(side_effect=fake_run)

    monkeypatch.setattr(s3_io, "head_analysis", head)
    monkeypatch.setattr(vision_path, "run", pipeline_run)
    return {"head": head, "pipeline": pipeline_run, "image_count": image_calls}


@pytest.mark.asyncio
async def test_extract_head_skip_returns_typed_skipped_doc(
    mocked_pipeline: dict[str, MagicMock],
) -> None:
    mocked_pipeline["head"].return_value = True

    result = await extract(KEY_SKIPPED_1)

    assert isinstance(result, ExtractedDoc)
    assert result.key == KEY_SKIPPED_1
    assert result.skipped is True
    assert result.analysis_key == f"{KEY_SKIPPED_1}.md"
    assert result.doc_type is None

    mocked_pipeline["head"].assert_called_once_with(f"{KEY_SKIPPED_1}.md")
    mocked_pipeline["pipeline"].assert_not_awaited()
    mocked_pipeline["image_count"].assert_not_called()


@pytest.mark.asyncio
async def test_extract_proceeds_when_head_returns_false(
    mocked_pipeline: dict[str, MagicMock],
) -> None:
    mocked_pipeline["head"].return_value = False

    result = await extract(KEY_FRESH)

    assert isinstance(result, ExtractedDoc)
    assert result.key == KEY_FRESH
    assert result.skipped is False
    assert result.analysis_key == f"{KEY_FRESH}.md"
    assert result.doc_type == "Passport"

    mocked_pipeline["head"].assert_called_once_with(f"{KEY_FRESH}.md")
    assert mocked_pipeline["pipeline"].await_count == 1
    # P13 — vision_path.run takes provider/model/verbose/dry_run/show_image
    # kwargs (defaulting to None/False); extract() forwards them all.
    call_args = mocked_pipeline["pipeline"].call_args
    assert call_args.args == (KEY_FRESH,)


@pytest.mark.asyncio
async def test_extract_batch_all_skipped_makes_zero_pipeline_calls(
    mocked_pipeline: dict[str, MagicMock],
) -> None:
    mocked_pipeline["head"].return_value = True
    keys = [KEY_SKIPPED_1, KEY_SKIPPED_2, KEY_SKIPPED_3]

    results = await extract_batch(keys)

    assert [r.key for r in results] == keys
    assert all(r.skipped for r in results)
    assert all(r.doc_type is None for r in results)
    assert mocked_pipeline["head"].call_count == 3
    assert mocked_pipeline["pipeline"].await_count == 0


@pytest.mark.asyncio
async def test_extract_batch_mixed_only_runs_pipeline_for_fresh_keys(
    mocked_pipeline: dict[str, MagicMock],
) -> None:
    skip_keys = {f"{KEY_SKIPPED_1}.md", f"{KEY_SKIPPED_3}.md"}

    def head_side_effect(analysis_key: str) -> bool:
        return analysis_key in skip_keys

    mocked_pipeline["head"].side_effect = head_side_effect

    keys = [KEY_SKIPPED_1, KEY_FRESH, KEY_SKIPPED_3]
    results = await extract_batch(keys)

    assert [r.key for r in results] == keys
    assert [r.skipped for r in results] == [True, False, True]
    assert results[1].doc_type == "Passport"
    assert results[0].doc_type is None
    assert results[2].doc_type is None

    assert mocked_pipeline["head"].call_count == 3
    assert mocked_pipeline["pipeline"].await_count == 1
    # P13 — match positional source_key only; kwargs default through.
    pipeline_call = mocked_pipeline["pipeline"].call_args
    assert pipeline_call.args == (KEY_FRESH,)


@pytest.mark.asyncio
async def test_extract_batch_rejects_non_positive_concurrency() -> None:
    with pytest.raises(ValueError, match="max_concurrent"):
        await extract_batch(["a", "b"], max_concurrent=0)
