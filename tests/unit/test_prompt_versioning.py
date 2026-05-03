"""Story 7.3 — prompt versioning CI gate (AR7).

Walks every ``src/doc_extractor/prompts/*.md`` and asserts the
SHA-256 of the body (post-frontmatter) matches the baseline in
``tests/unit/prompt_hashes.json``. Bodies that change without a
``version`` bump fail loudly; intentional edits land in the same PR as
a re-baseline via ``scripts/rebaseline_prompts.py``. New prompt files
must also land a baseline entry — the gate names them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from doc_extractor.prompts import loader

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "src" / "doc_extractor" / "prompts"
BASELINE_PATH = REPO_ROOT / "tests" / "unit" / "prompt_hashes.json"
REBASELINE_HINT = "Run `python scripts/rebaseline_prompts.py` to update."


def _load_baseline() -> dict[str, dict[str, str]]:
    with BASELINE_PATH.open("r", encoding="utf-8") as fh:
        return cast(dict[str, dict[str, str]], json.load(fh))


def _hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _discover_prompts() -> list[str]:
    return sorted(p.name for p in PROMPTS_DIR.glob("*.md"))


def test_baseline_file_is_well_formed() -> None:
    baseline = _load_baseline()
    assert baseline, "prompt_hashes.json is empty"
    for name, entry in baseline.items():
        assert name.endswith(".md"), f"baseline key {name!r} must be a .md file name"
        assert "version" in entry, f"baseline {name} missing 'version'"
        assert "body_sha256" in entry, f"baseline {name} missing 'body_sha256'"
        assert isinstance(entry["body_sha256"], str)
        assert len(entry["body_sha256"]) == 64, (
            f"baseline {name} body_sha256 must be 64 hex chars (got "
            f"{len(entry['body_sha256'])})"
        )


def test_every_prompt_has_a_baseline_entry() -> None:
    """A brand-new prompt file must land a baseline row in the same PR."""
    baseline = _load_baseline()
    discovered = _discover_prompts()

    missing = [name for name in discovered if name not in baseline]
    assert not missing, (
        f"Prompts present on disk but missing from {BASELINE_PATH.name}: "
        f"{missing}. {REBASELINE_HINT}"
    )


def test_baseline_does_not_reference_deleted_prompts() -> None:
    """Sentinel: a baseline row whose prompt was deleted is dead weight."""
    baseline = _load_baseline()
    discovered = set(_discover_prompts())

    orphaned = [name for name in baseline if name not in discovered]
    assert not orphaned, (
        f"Baseline rows reference prompts that no longer exist: {orphaned}. "
        f"Remove the rows or restore the files."
    )


@pytest.mark.parametrize("prompt_name", _discover_prompts())
def test_prompt_body_hash_matches_baseline(prompt_name: str) -> None:
    """Body changes without a version bump fail this test loudly."""
    baseline = _load_baseline()
    if prompt_name not in baseline:
        pytest.fail(
            f"{prompt_name} is not in the baseline. {REBASELINE_HINT}"
        )

    expected = baseline[prompt_name]
    loader.load_prompt.cache_clear()
    body, version = loader.load_prompt(Path(prompt_name).stem)
    actual_hash = _hash_body(body)

    hash_changed = actual_hash != expected["body_sha256"]
    version_changed = version != expected["version"]

    if hash_changed and not version_changed:
        pytest.fail(
            f"{prompt_name} body changed without a version bump "
            f"(expected sha256={expected['body_sha256'][:16]}…, "
            f"actual sha256={actual_hash[:16]}…, "
            f"version still {version!r}). "
            "Either bump `version` in the frontmatter and re-baseline, "
            "or revert the body change."
        )

    if version_changed and hash_changed:
        pytest.fail(
            f"{prompt_name} version bumped from {expected['version']!r} to "
            f"{version!r} — re-run `python scripts/rebaseline_prompts.py` "
            "to update the baseline JSON in this PR."
        )

    if version_changed and not hash_changed:
        pytest.fail(
            f"{prompt_name} version bumped from {expected['version']!r} to "
            f"{version!r} but the body is unchanged. Either revert the "
            "version bump or re-baseline so the JSON matches."
        )

    assert actual_hash == expected["body_sha256"]
    assert version == expected["version"]
