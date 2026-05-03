"""Unit tests for ``scripts/verify_canonical.py`` (Story 2.7 / AR3)."""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_canonical.py"
CI_YAML_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_script_module() -> Any:
    spec = importlib.util.spec_from_file_location("verify_canonical", SCRIPT_PATH)
    assert spec and spec.loader, f"could not load {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script() -> Any:
    return _load_script_module()


def _write_pair(
    fixtures_dir: Path,
    example_id: str,
    *,
    debit_name: str = "张三",
    debit_account: str = "6217 **** **** 0083",
    credit_name: str = "李四",
    credit_account: str = "6230 **** **** 2235",
    extension: str = ".jpeg",
    image_bytes: bytes = b"\x89PNG\r\n\x1a\nfake-image-bytes",
) -> tuple[Path, Path]:
    """Write an ``(image, expected.md)`` pair under ``fixtures_dir``."""
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    image_path = fixtures_dir / f"{example_id}{extension}"
    expected_path = fixtures_dir / f"{example_id}.expected.md"
    image_path.write_bytes(image_bytes)
    frontmatter = (
        "---\n"
        "doc_type: PaymentReceipt\n"
        f"receipt_debit_account_name: {debit_name}\n"
        f"receipt_debit_account_number: '{debit_account}'\n"
        f"receipt_credit_account_name: {credit_name}\n"
        f"receipt_credit_account_number: '{credit_account}'\n"
        "---\n"
        "\nbody — irrelevant for the gate\n"
    )
    expected_path.write_text(frontmatter, encoding="utf-8")
    return image_path, expected_path


# ---------------------------------------------------------------------------
# Skip paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_fixtures_dir_skips_with_message(
    script: Any, tmp_path: Path
) -> None:
    code, msg = await script.verify_canonical(
        fixtures_dir=tmp_path / "does-not-exist", mocked=True
    )
    assert code == 0
    assert "no canonical fixtures yet" in msg


@pytest.mark.asyncio
async def test_empty_fixtures_dir_skips_with_message(
    script: Any, tmp_path: Path
) -> None:
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    code, msg = await script.verify_canonical(
        fixtures_dir=fixtures_dir, mocked=True
    )
    assert code == 0
    assert "no canonical fixtures yet" in msg


@pytest.mark.asyncio
async def test_real_mode_without_api_key_skips(
    script: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real-provider mode skip-passes when ``ANTHROPIC_API_KEY`` is unset.
    A pair must be present so we exercise the post-discovery skip path."""
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    code, msg = await script.verify_canonical(
        fixtures_dir=fixtures_dir, mocked=False
    )
    assert code == 0
    assert "ANTHROPIC_API_KEY unset" in msg


@pytest.mark.asyncio
async def test_real_mode_default_extractor_yields_skip_pass(
    script: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the API key IS set but the real-mode extractor still raises
    ``NotImplementedError``, the script catches and returns a skip-pass.
    This is the "fixtures + key set, but Story 2.1 hasn't wired the real
    pipeline yet" path."""
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    code, msg = await script.verify_canonical(
        fixtures_dir=fixtures_dir, mocked=False
    )
    assert code == 0
    assert "skipping canonical-4 verification" in msg
    assert "Story 2.1" in msg


# ---------------------------------------------------------------------------
# Mocked happy path (tautological extractor)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mocked_mode_passes_with_synthetic_pairs(
    script: Any, tmp_path: Path
) -> None:
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-1")
    _write_pair(
        fixtures_dir,
        "case-2",
        debit_name="王五",
        debit_account="6228 **** **** 1111",
        credit_name="GM6040",
        credit_account="02-0248-0242329-02",
    )
    code, msg = await script.verify_canonical(
        fixtures_dir=fixtures_dir, mocked=True
    )
    assert code == 0, msg
    assert "Canonical-4 OK" in msg
    assert "2 pair(s)" in msg
    assert "mocked" in msg


@pytest.mark.asyncio
async def test_image_without_expected_md_is_skipped(
    script: Any, tmp_path: Path
) -> None:
    """Half-pairs (image with no .expected.md) are silently dropped from the
    pair list; the canonical-4 gate is opt-in per fixture."""
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-1")
    # Add a stray image with no expected.md.
    (fixtures_dir / "case-2.jpeg").write_bytes(b"orphan-image")

    code, msg = await script.verify_canonical(
        fixtures_dir=fixtures_dir, mocked=True
    )
    assert code == 0
    assert "1 pair(s)" in msg


# ---------------------------------------------------------------------------
# Mocked failure path — injected mismatched extractor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mocked_mode_fails_with_injected_mismatch(
    script: Any, tmp_path: Path
) -> None:
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-1", debit_name="张三", debit_account="6217 **** **** 0083")

    async def mismatched_extractor(
        _image: Path, expected: dict[str, str]
    ) -> dict[str, str]:
        # Mutate one field — the gate must catch this.
        return {**expected, "receipt_debit_account_name": "WRONG_NAME"}

    code, msg = await script.verify_canonical(
        fixtures_dir=fixtures_dir,
        mocked=True,
        extractor=mismatched_extractor,
    )
    assert code == 1
    assert "Canonical-4 failures" in msg
    assert "case-1.receipt_debit_account_name" in msg
    assert "'张三'" in msg
    assert "'WRONG_NAME'" in msg


@pytest.mark.asyncio
async def test_mocked_mode_reports_all_breach_fields(
    script: Any, tmp_path: Path
) -> None:
    """Multiple field mismatches across multiple examples are all reported."""
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-1")
    _write_pair(fixtures_dir, "case-2")

    async def all_wrong(
        _image: Path, _expected: dict[str, str]
    ) -> dict[str, str]:
        return {
            "receipt_debit_account_name": "X",
            "receipt_debit_account_number": "X",
            "receipt_credit_account_name": "X",
            "receipt_credit_account_number": "X",
        }

    code, msg = await script.verify_canonical(
        fixtures_dir=fixtures_dir, mocked=True, extractor=all_wrong
    )
    assert code == 1
    # 4 fields × 2 examples = 8 breaches.
    assert "(8)" in msg
    assert "case-1." in msg
    assert "case-2." in msg


@pytest.mark.asyncio
async def test_extractor_raising_unexpected_error_records_failure(
    script: Any, tmp_path: Path
) -> None:
    """A non-NotImplementedError exception from the extractor surfaces as a
    failure for that example (not a skip) — we don't silently swallow real
    extraction bugs."""
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-1")

    async def boom(_image: Path, _expected: dict[str, str]) -> dict[str, str]:
        raise RuntimeError("simulated provider outage")

    code, msg = await script.verify_canonical(
        fixtures_dir=fixtures_dir, mocked=True, extractor=boom
    )
    assert code == 1
    assert "case-1: extractor raised RuntimeError" in msg
    assert "simulated provider outage" in msg


# ---------------------------------------------------------------------------
# Discovery + parsing primitives
# ---------------------------------------------------------------------------


def test_discover_pairs_sorts_by_example_id(script: Any, tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "z-case")
    _write_pair(fixtures_dir, "a-case")
    _write_pair(fixtures_dir, "m-case")

    pairs = script._discover_pairs(fixtures_dir)
    assert [p[0] for p in pairs] == ["a-case", "m-case", "z-case"]


def test_discover_pairs_recognises_all_image_extensions(
    script: Any, tmp_path: Path
) -> None:
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-jpeg", extension=".jpeg")
    _write_pair(fixtures_dir, "case-png", extension=".png")
    _write_pair(fixtures_dir, "case-pdf", extension=".pdf")

    pairs = script._discover_pairs(fixtures_dir)
    assert {p[0] for p in pairs} == {"case-jpeg", "case-png", "case-pdf"}


def test_parse_expected_returns_only_paired_fields(
    script: Any, tmp_path: Path
) -> None:
    fixtures_dir = tmp_path / "fixtures"
    _write_pair(fixtures_dir, "case-1")
    expected = script._parse_expected(fixtures_dir / "case-1.expected.md")
    assert set(expected.keys()) == {
        "receipt_debit_account_name",
        "receipt_debit_account_number",
        "receipt_credit_account_name",
        "receipt_credit_account_number",
    }
    assert expected["receipt_debit_account_name"] == "张三"
    assert expected["receipt_debit_account_number"] == "6217 **** **** 0083"


def test_parse_expected_missing_fence_raises(
    script: Any, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.expected.md"
    bad.write_text("no frontmatter here", encoding="utf-8")
    with pytest.raises(ValueError, match="missing YAML frontmatter fences"):
        script._parse_expected(bad)


# ---------------------------------------------------------------------------
# CLI subcommand smoke
# ---------------------------------------------------------------------------


def test_cli_verify_canonical_subcommand_dispatches_to_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``doc-extractor verify-canonical --mocked`` calls into the script and
    propagates its exit code.

    We monkeypatch ``_load_verify_canonical_script`` to return a stub module
    so the test doesn't depend on the script being loadable from this
    test's working directory."""
    from doc_extractor import cli

    captured: dict[str, Any] = {}

    async def fake_verify_canonical(*, mocked: bool) -> tuple[int, str]:
        captured["mocked"] = mocked
        return 0, "synthesised pass message from stub"

    class _StubModule:
        verify_canonical = staticmethod(fake_verify_canonical)

    monkeypatch.setattr(
        cli, "_load_verify_canonical_script", lambda: _StubModule
    )

    # Capture stdout/stderr.
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
        rc = cli.main(["verify-canonical", "--mocked"])

    assert rc == 0
    assert captured["mocked"] is True
    assert "synthesised pass message from stub" in stdout.getvalue()


def test_cli_verify_canonical_propagates_failure_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from doc_extractor import cli

    async def fake_verify_canonical(*, mocked: bool) -> tuple[int, str]:
        return 1, "Canonical-4 failures (1):\n  case-1.receipt_debit_account_name: ..."

    class _StubModule:
        verify_canonical = staticmethod(fake_verify_canonical)

    monkeypatch.setattr(
        cli, "_load_verify_canonical_script", lambda: _StubModule
    )

    stderr = io.StringIO()
    with patch.object(sys, "stderr", stderr):
        rc = cli.main(["verify-canonical", "--mocked"])

    assert rc == 1
    assert "Canonical-4 failures" in stderr.getvalue()


# ---------------------------------------------------------------------------
# ci.yml sentinel — gate is unconditional + uses --mocked
# ---------------------------------------------------------------------------


def test_ci_yml_has_unconditional_verify_canonical_step() -> None:
    """The Story 2.7 gate must be wired with ``--mocked`` and NOT guarded
    by ``if [ -f scripts/verify_canonical.py ]`` — that stub was the
    pre-2.7 placeholder. CI must invoke the script every run."""
    raw = CI_YAML_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    steps: list[dict[str, Any]] = parsed["jobs"]["test"]["steps"]
    verify_steps = [s for s in steps if "Verify canonical" in s.get("name", "")]
    assert len(verify_steps) == 1, (
        "expected exactly one 'Verify canonical' step in ci.yml; "
        f"found {len(verify_steps)}"
    )
    step = verify_steps[0]
    run_block = step["run"]
    assert "scripts/verify_canonical.py" in run_block
    assert "--mocked" in run_block
    assert "if [ -f" not in run_block, (
        "Story 2.7 dropped the file-existence guard; the gate runs "
        "unconditionally now."
    )
    assert "stub" not in step.get("name", "").lower(), (
        "step name should no longer carry the (stub — Story 2.7) marker"
    )
