"""Integration tests for ``eval.harness.run_eval`` (Story 2.4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from doc_extractor import markdown_io
from doc_extractor.eval import harness
from doc_extractor.eval.harness import run_eval
from doc_extractor.extract import ExtractedDoc
from doc_extractor.schemas.base import Frontmatter
from doc_extractor.schemas.ids import Passport


def _passport(name_latin: str = "DOE, JANE", jurisdiction: str = "NZL") -> Passport:
    return Passport(
        doc_type="Passport",
        passport_number="X9988776",
        nationality=jurisdiction,
        doc_number="X9988776",
        dob="1985-09-12",
        issue_date="2022-09-12",
        expiry_date="2032-09-11",
        sex="F",
        mrz_line_1="P<NZLDOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
        mrz_line_2="X9988776<NZL8509121F3209118<<<<<<<<<<<<<<00",
        name_latin=name_latin,
        jurisdiction=jurisdiction,
    )


def _write_pair(
    golden_dir: Path,
    *,
    doc_type: str,
    stem: str,
    expected: Frontmatter,
) -> str:
    """Drop a synthetic <doc_type>/<stem>.jpeg + <stem>.expected.md pair."""
    type_dir = golden_dir / doc_type
    type_dir.mkdir(parents=True, exist_ok=True)
    image_path = type_dir / f"{stem}.jpeg"
    image_path.write_bytes(b"\xff\xd8\xff\xe0FAKE-JPEG")
    expected_path = type_dir / f"{stem}.expected.md"
    expected_path.write_text(markdown_io.render_to_md(expected), encoding="utf-8")
    return str(image_path)


def _make_extract_batch(
    keys_to_doc: dict[str, ExtractedDoc],
) -> Any:
    """Return an async stub that mimics extract_batch and returns docs in order."""

    async def _fake(keys: list[str], *, max_concurrent: int) -> list[ExtractedDoc]:
        return [keys_to_doc[k] for k in keys]

    return _fake


def _patch_loader(
    monkeypatch: pytest.MonkeyPatch, content: dict[str, Frontmatter]
) -> None:
    """Patch ``_load_extracted_content`` to return a per-key Frontmatter."""
    monkeypatch.setattr(
        harness,
        "_load_extracted_content",
        lambda analysis_key: content[analysis_key],
    )


@pytest.mark.asyncio
async def test_empty_corpus_returns_empty_scorecard(tmp_path: Path) -> None:
    (tmp_path / "Passport").mkdir()
    (tmp_path / "Passport" / "README.md").write_text("# corpus dir", encoding="utf-8")

    scorecard = await run_eval(golden_dir=tmp_path)

    assert scorecard.total_examples == 0
    assert scorecard.total_cost_usd == 0.0
    assert scorecard.per_agent == {}
    parsed = json.loads(scorecard.to_json())
    assert parsed["total_examples"] == 0


@pytest.mark.asyncio
async def test_single_passport_pair_scores_perfect_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected = _passport()
    image_key = _write_pair(tmp_path, doc_type="Passport", stem="case_001", expected=expected)
    analysis_key = f"{image_key}.md"

    extracted = ExtractedDoc(
        key=image_key, skipped=False, analysis_key=analysis_key, doc_type="Passport"
    )
    _patch_loader(monkeypatch, {analysis_key: expected})

    scorecard = await run_eval(
        golden_dir=tmp_path,
        extract_batch_fn=_make_extract_batch({image_key: extracted}),
    )

    assert "Passport" in scorecard.per_agent
    metrics = scorecard.per_agent["Passport"]
    assert metrics.examples > 0
    # All non-empty fields matched → precision 1.0
    assert metrics.precision == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_mismatch_reduces_precision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected = _passport(name_latin="DOE, JANE")
    actual = _passport(name_latin="WRONG")  # one field disagrees
    image_key = _write_pair(tmp_path, doc_type="Passport", stem="case_002", expected=expected)
    analysis_key = f"{image_key}.md"

    extracted = ExtractedDoc(
        key=image_key, skipped=False, analysis_key=analysis_key, doc_type="Passport"
    )
    _patch_loader(monkeypatch, {analysis_key: actual})

    scorecard = await run_eval(
        golden_dir=tmp_path,
        extract_batch_fn=_make_extract_batch({image_key: extracted}),
    )

    metrics = scorecard.per_agent["Passport"]
    assert metrics.precision < 1.0


@pytest.mark.asyncio
async def test_doc_type_filter_only_walks_one_subdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    passport_expected = _passport()
    p_key = _write_pair(tmp_path, doc_type="Passport", stem="p1", expected=passport_expected)
    # A DriverLicence pair shaped as a Passport for fixture simplicity — the
    # filter should skip its directory entirely so its content never matters.
    dl_key = _write_pair(tmp_path, doc_type="DriverLicence", stem="dl1", expected=_passport())

    p_doc = ExtractedDoc(
        key=p_key, skipped=False, analysis_key=f"{p_key}.md", doc_type="Passport"
    )
    dl_doc = ExtractedDoc(
        key=dl_key, skipped=False, analysis_key=f"{dl_key}.md", doc_type="DriverLicence"
    )
    _patch_loader(
        monkeypatch,
        {f"{p_key}.md": passport_expected, f"{dl_key}.md": _passport()},
    )

    scorecard = await run_eval(
        doc_type="Passport",
        golden_dir=tmp_path,
        extract_batch_fn=_make_extract_batch({p_key: p_doc, dl_key: dl_doc}),
    )

    assert list(scorecard.per_agent.keys()) == ["Passport"]


@pytest.mark.asyncio
async def test_jurisdiction_filter_only_scores_matching_pairs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cn_expected = _passport(jurisdiction="CN")
    nz_expected = _passport(jurisdiction="NZ")
    cn_key = _write_pair(tmp_path, doc_type="Passport", stem="cn1", expected=cn_expected)
    nz_key = _write_pair(tmp_path, doc_type="Passport", stem="nz1", expected=nz_expected)

    cn_doc = ExtractedDoc(
        key=cn_key, skipped=False, analysis_key=f"{cn_key}.md", doc_type="Passport"
    )
    _patch_loader(monkeypatch, {f"{cn_key}.md": cn_expected})

    scorecard = await run_eval(
        jurisdiction="CN",
        golden_dir=tmp_path,
        extract_batch_fn=_make_extract_batch({cn_key: cn_doc}),
    )

    # Only the CN pair landed; the NZ pair was filtered before extract_batch.
    assert scorecard.total_examples > 0
    cn_bucket = scorecard.per_jurisdiction.get("CN", {})
    assert cn_bucket, "per_jurisdiction must include the CN bucket"
    assert "NZ" not in scorecard.per_jurisdiction
    assert nz_key not in (cn_doc.key,)  # sentinel — NZ key never reached extract


@pytest.mark.asyncio
async def test_total_cost_aggregates_per_extract_costs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected_a = _passport()
    expected_b = _passport(name_latin="DOE, JOHN")
    key_a = _write_pair(tmp_path, doc_type="Passport", stem="a", expected=expected_a)
    key_b = _write_pair(tmp_path, doc_type="Passport", stem="b", expected=expected_b)

    doc_a = ExtractedDoc(
        key=key_a, skipped=False, analysis_key=f"{key_a}.md", doc_type="Passport"
    )
    doc_b = ExtractedDoc(
        key=key_b, skipped=False, analysis_key=f"{key_b}.md", doc_type="Passport"
    )
    _patch_loader(
        monkeypatch,
        {f"{key_a}.md": expected_a, f"{key_b}.md": expected_b},
    )

    cost_table = {key_a: 0.012, key_b: 0.034}
    monkeypatch.setattr(
        harness, "_resolve_cost", lambda extracted: cost_table[extracted.key]
    )

    scorecard = await run_eval(
        golden_dir=tmp_path,
        extract_batch_fn=_make_extract_batch({key_a: doc_a, key_b: doc_b}),
    )

    # Each EvalResult carries its per-extract cost; total_cost_usd sums all rows.
    # Field count per Passport is the same, so the expected total is
    # cost_a * field_count + cost_b * field_count.
    metrics = scorecard.per_agent["Passport"]
    field_count_per_pair = metrics.examples // 2
    expected_total = (cost_table[key_a] + cost_table[key_b]) * field_count_per_pair
    assert scorecard.total_cost_usd == pytest.approx(expected_total)
