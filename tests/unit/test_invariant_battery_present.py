"""Architectural-invariant battery presence sentinel (Story 2.9, AR3).

The architecture commits to FIVE CI tests that together enforce structural
invariants the code review can't reliably catch — accidental deletion of any
one of them silently weakens the safety net. This sentinel lists the five by
path and asserts each file exists. If a contributor renames or removes a test
without updating this list, CI fails loudly with the AR3 commitment cited.

Adding a sixth invariant test requires updating both this list AND the
corresponding ``Architectural Invariants`` section in ``architecture.md``.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Per architecture.md "Architectural Invariants" / AR3. The path strings are
# repo-relative; the sentinel resolves them against ``REPO_ROOT`` below.
INVARIANT_TESTS: tuple[str, ...] = (
    "tests/unit/test_import_boundaries.py",  # Story 2.9 (this story)
    "tests/unit/test_prompt_versioning.py",  # Story 7.3
    "tests/unit/test_provider_terms_documented.py",  # Story 7.4
    "tests/unit/test_schema_byte_stability.py",  # Stories 1.2 / 3.1 / 4.1-4.3 / 5.1+
    "tests/unit/test_telemetry_no_pii.py",  # Story 8.2
)


def test_all_five_invariant_tests_present_in_repo() -> None:
    missing = [
        rel for rel in INVARIANT_TESTS if not (REPO_ROOT / rel).is_file()
    ]
    assert not missing, (
        "Architectural-invariant test(s) missing from the repo. AR3 commits "
        "the codebase to the FIVE invariant tests below; deleting / renaming "
        "any of them silently weakens the safety net. Restore or update both "
        "this sentinel and the architecture.md `Architectural Invariants` "
        "section before merging.\n\nMissing:\n  " + "\n  ".join(missing)
    )


def test_invariant_list_has_no_duplicates() -> None:
    """Defensive: the list is a tuple of paths; duplicates would still resolve
    to the same file but signal an editing mistake. This catches a copy-paste
    where the contributor adds a sixth slot but forgets to update the path."""
    assert len(set(INVARIANT_TESTS)) == len(INVARIANT_TESTS), (
        "INVARIANT_TESTS contains duplicates: "
        f"{[p for p in INVARIANT_TESTS if INVARIANT_TESTS.count(p) > 1]}"
    )


def test_invariant_list_size_matches_ar3() -> None:
    """AR3 commits to FIVE invariant tests in v1. A change in this count is
    a real architectural decision — the test fails loudly so the contributor
    updates architecture.md alongside this list (rather than silently
    expanding the battery)."""
    expected_count = 5
    assert len(INVARIANT_TESTS) == expected_count, (
        f"AR3 commits to {expected_count} invariant tests; this list now has "
        f"{len(INVARIANT_TESTS)}. If this is intentional, update both this "
        f"assertion and the `Architectural Invariants` section in architecture.md."
    )
