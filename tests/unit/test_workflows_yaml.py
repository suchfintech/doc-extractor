"""Story 2.10 — GitHub Actions workflow validation.

Asserts ``ci.yml`` and ``eval.yml`` parse as YAML, expose the gates the
project relies on (ruff / mypy / pytest / cost-ceiling), and that
``eval.yml`` keeps the path-filter trigger glob set the maintainers
agreed on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast  # noqa: F401  — `cast` retained for the typed `_job_steps` return

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
EVAL_PATH = REPO_ROOT / ".github" / "workflows" / "eval.yml"

REQUIRED_CI_STEP_NAMES: tuple[str, ...] = (
    "Ruff check",
    "Ruff format check",
    "Mypy strict",
    "Pytest with coverage",
    "Cost-ceiling check",
)

EXPECTED_EVAL_PATHS: tuple[str, ...] = (
    "src/doc_extractor/agents/**",
    "src/doc_extractor/prompts/**",
    "src/doc_extractor/schemas/**",
    "src/doc_extractor/config/**",
    "tests/golden/**",
)


def _load_workflow(path: Path) -> dict[Any, Any]:
    """Return the parsed YAML root.

    Annotated as ``dict[Any, Any]`` because PyYAML 1.1 parses bare ``on:``
    as Python ``True`` (it's a YAML 1.1 boolean), so the trigger block
    ends up under a non-string key. We tolerate either form below.
    """
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), f"{path.name} root must be a mapping, got {type(data).__name__}"
    return data


def _job_steps(workflow: dict[Any, Any], job_name: str) -> list[dict[str, Any]]:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), f"workflow has no `jobs:` mapping (got {type(jobs).__name__})"
    job = jobs.get(job_name)
    assert isinstance(job, dict), f"job {job_name!r} missing from workflow"
    steps = job.get("steps")
    assert isinstance(steps, list), f"job {job_name!r} has no `steps:` list"
    return cast(list[dict[str, Any]], steps)


def test_ci_yaml_is_well_formed() -> None:
    workflow = _load_workflow(CI_PATH)
    assert workflow.get("name") == "CI"
    # PyYAML parses bare `on:` as Python boolean True (YAML 1.1) — accept either.
    triggers = workflow.get("on") or workflow.get(True)
    assert isinstance(triggers, dict), (
        "ci.yml `on:` block must be a mapping (push/pull_request keys)"
    )
    assert "pull_request" in triggers
    push = triggers.get("push")
    assert isinstance(push, dict) and push.get("branches") == ["main"]


def test_ci_yaml_exposes_required_gate_steps() -> None:
    workflow = _load_workflow(CI_PATH)
    steps = _job_steps(workflow, "test")
    step_names = [str(s.get("name", "")) for s in steps]

    for required in REQUIRED_CI_STEP_NAMES:
        assert required in step_names, (
            f"ci.yml step {required!r} missing. Got: {step_names}"
        )


def test_ci_yaml_pins_python_312_and_uses_uv() -> None:
    workflow = _load_workflow(CI_PATH)
    steps = _job_steps(workflow, "test")
    setup_python = next(
        (s for s in steps if str(s.get("uses", "")).startswith("actions/setup-python")),
        None,
    )
    assert setup_python is not None, "ci.yml must use actions/setup-python"
    with_block = setup_python.get("with") or {}
    assert str(with_block.get("python-version")) == "3.12"

    uv_step = next((s for s in steps if s.get("name") == "Install uv"), None)
    assert uv_step is not None, "ci.yml must install uv (project convention)"


def test_eval_yaml_is_well_formed_and_path_triggered() -> None:
    workflow = _load_workflow(EVAL_PATH)
    assert workflow.get("name") == "Eval"

    triggers = workflow.get("on") or workflow.get(True)
    assert isinstance(triggers, dict)
    pr = triggers.get("pull_request")
    assert isinstance(pr, dict), "eval.yml must trigger on pull_request only"
    paths = pr.get("paths")
    assert isinstance(paths, list)
    for expected in EXPECTED_EVAL_PATHS:
        assert expected in paths, (
            f"eval.yml `paths:` missing {expected!r}. Got: {paths}"
        )


def test_eval_yaml_exposes_eval_job() -> None:
    workflow = _load_workflow(EVAL_PATH)
    steps = _job_steps(workflow, "eval")
    step_names = [str(s.get("name", "")) for s in steps]
    # Stories 2.4/2.5/2.6 will replace the placeholder step body but the
    # job + the install-deps prelude must stay so the workflow stays
    # green during the transition.
    assert any("Install" in n for n in step_names)
    assert any(s.get("uses", "").startswith("actions/checkout") for s in steps)
