"""Story 8.6 — coverage gate configuration tests (NFR20).

Asserts the wiring is in place:

- ``pyproject.toml`` declares ``pytest-cov`` as a dev dep.
- ``[tool.coverage.run]`` points at ``src/doc_extractor`` and excludes
  prompt bodies, golden fixtures, and ``__init__.py`` shims (those are
  re-exports and have no behaviour to cover).
- ``[tool.coverage.report]`` excludes the standard "should never run"
  lines so abstract / impossibility branches don't drag the percentage.
- ``ci.yml``'s Pytest step actually invokes ``--cov --cov-fail-under=85``
  so a drop below 85 % fails the build (the contract NFR20 enforces).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_pyproject() -> dict[str, Any]:
    with PYPROJECT_PATH.open("rb") as fh:
        return tomllib.load(fh)


def test_pytest_cov_is_a_dev_dependency() -> None:
    config = _load_pyproject()
    dev = (
        config.get("project", {})
        .get("optional-dependencies", {})
        .get("dev", [])
    )
    assert any(item.startswith("pytest-cov") for item in dev), (
        f"pytest-cov must be in [project.optional-dependencies] dev (got {dev})"
    )


def test_coverage_run_section_targets_src_doc_extractor() -> None:
    config = _load_pyproject()
    run = config.get("tool", {}).get("coverage", {}).get("run", {})
    assert run.get("source") == ["src/doc_extractor"], (
        f"[tool.coverage.run] source must be ['src/doc_extractor'] (got {run.get('source')!r})"
    )


def test_coverage_run_omits_expected_globs() -> None:
    config = _load_pyproject()
    run = config.get("tool", {}).get("coverage", {}).get("run", {})
    omit = run.get("omit") or []
    for expected in (
        "src/doc_extractor/prompts/*.md",
        "tests/golden/**",
        "**/__init__.py",
    ):
        assert expected in omit, (
            f"[tool.coverage.run] omit missing {expected!r} (got {omit})"
        )


def test_coverage_report_excludes_standard_uncoverable_lines() -> None:
    config = _load_pyproject()
    report = config.get("tool", {}).get("coverage", {}).get("report", {})
    exclude = report.get("exclude_lines") or []
    for expected in ("pragma: no cover", "raise NotImplementedError", "if TYPE_CHECKING:"):
        assert expected in exclude, (
            f"[tool.coverage.report] exclude_lines missing {expected!r} (got {exclude})"
        )


def test_ci_pytest_step_invokes_coverage_with_85_percent_floor() -> None:
    with CI_PATH.open("r", encoding="utf-8") as fh:
        workflow = yaml.safe_load(fh)
    assert isinstance(workflow, dict)

    steps = workflow["jobs"]["test"]["steps"]
    pytest_step = next(
        (s for s in steps if "pytest" in str(s.get("run", "")).lower()),
        None,
    )
    assert pytest_step is not None, "ci.yml must have a step that runs pytest"

    run_block = str(pytest_step.get("run", ""))
    assert "--cov" in run_block, (
        f"ci.yml pytest step must pass --cov (got: {run_block!r})"
    )
    assert "--cov-fail-under=85" in run_block, (
        f"ci.yml pytest step must enforce --cov-fail-under=85 (got: {run_block!r})"
    )
