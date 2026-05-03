"""CI gate (NFR11): every provider in PROVIDERS must have a vendor-data-handling row.

Walks ``src/doc_extractor/agents/factory.py`` with ``ast`` (no import — that
would trigger Agno's heavy import graph and the env-var validation paths)
to extract the keys of ``VisionModelFactory.PROVIDERS``, then parses the
markdown table in ``docs/vendor-data-handling.md`` and asserts every key
has a row with non-empty ``Source URL`` / ``Retrieval date`` / ``Reviewer``
columns. Adding a provider without documenting it fails this test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FACTORY_PATH = REPO_ROOT / "src" / "doc_extractor" / "agents" / "factory.py"
DOC_PATH = REPO_ROOT / "docs" / "vendor-data-handling.md"

REQUIRED_COLUMNS = ("Provider", "Source URL", "Retrieval date", "Reviewer")


def _normalise(value: str) -> str:
    """Lower-case, strip, and treat ``_`` / ``-`` / spaces as equivalent."""
    return (
        value.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _extract_provider_keys() -> list[str]:
    """Return the literal keys of ``VisionModelFactory.PROVIDERS`` via AST."""
    tree = ast.parse(FACTORY_PATH.read_text(encoding="utf-8"))
    for cls_node in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        if cls_node.name != "VisionModelFactory":
            continue
        for stmt in cls_node.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            if not (isinstance(stmt.target, ast.Name) and stmt.target.id == "PROVIDERS"):
                continue
            if not isinstance(stmt.value, ast.Dict):
                pytest.fail("VisionModelFactory.PROVIDERS is not a dict literal")
            keys: list[str] = []
            for key_node in stmt.value.keys:
                if key_node is None or not isinstance(key_node, ast.Constant) or not isinstance(
                    key_node.value, str
                ):
                    pytest.fail(
                        f"PROVIDERS contains a non-string-literal key: "
                        f"{ast.dump(key_node) if key_node is not None else 'None (dict unpacking)'}"
                    )
                keys.append(key_node.value)
            return keys
    pytest.fail("Could not find VisionModelFactory.PROVIDERS in factory.py")
    return []  # unreachable, satisfies type checker


def _parse_markdown_table(text: str) -> list[dict[str, str]]:
    """Parse the first GFM-style pipe table in ``text`` to a list of row dicts."""
    rows: list[list[str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 3:
        pytest.fail(
            "Markdown table in vendor-data-handling.md must have a header, "
            f"separator, and at least one data row (got {len(rows)} pipe lines)"
        )

    header = rows[0]
    for column in REQUIRED_COLUMNS:
        if column not in header:
            pytest.fail(
                f"Markdown table is missing required column {column!r}. "
                f"Got columns: {header}"
            )

    return [dict(zip(header, row, strict=False)) for row in rows[2:]]


def test_every_provider_has_a_documented_row() -> None:
    provider_keys = _extract_provider_keys()
    assert provider_keys, "PROVIDERS must declare at least one provider"

    table_rows = _parse_markdown_table(DOC_PATH.read_text(encoding="utf-8"))
    documented = {_normalise(row["Provider"]) for row in table_rows}

    missing = [key for key in provider_keys if _normalise(key) not in documented]
    assert not missing, (
        f"Providers in factory.py without a row in docs/vendor-data-handling.md: "
        f"{missing}. Add a row before merging (NFR11)."
    )


def test_every_documented_row_has_required_fields() -> None:
    table_rows = _parse_markdown_table(DOC_PATH.read_text(encoding="utf-8"))
    assert table_rows, "vendor-data-handling.md table must have at least one row"

    incomplete: list[tuple[str, str]] = []
    for row in table_rows:
        for column in ("Source URL", "Retrieval date", "Reviewer"):
            value = row.get(column, "").strip()
            if not value:
                incomplete.append((row.get("Provider", "<unknown>"), column))

    assert not incomplete, (
        "vendor-data-handling.md rows missing required cells "
        f"[(Provider, MissingColumn), ...]: {incomplete}"
    )


def test_dashscope_remains_deferred_per_fr33() -> None:
    """DashScope must NOT have a PROVIDERS entry until its row is reviewed."""
    provider_keys = _extract_provider_keys()
    assert "dashscope" not in provider_keys, (
        "DashScope is deferred per FR33 / architecture Decision 5. "
        "Add its row to vendor-data-handling.md and update the FR33 TODO "
        "in factory.py before adding it to PROVIDERS."
    )
