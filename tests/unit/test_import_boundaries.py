"""Architectural-import-boundary CI test (Story 2.9, AR2 / AR3).

Walks every ``.py`` under ``src/doc_extractor/`` and parses it with ``ast``
to extract its imports, then checks each import against the layer's
forbidden-target set. A violation surfaces as a single failed test with a
clear message naming the source file + the forbidden import path so the
diff is obvious in CI output.

The six layer rules (digest from architecture.md "Architectural
Boundaries", ~line 760):

- **schemas/** — pure data contract. May import from ``schemas/`` and
  external (pydantic, stdlib). MUST NOT import from any other internal
  layer. External consumers (merlin, cny-flow) re-import these schemas
  to validate ``.md`` frontmatter; pulling agent / pipeline / I/O imports
  into schemas would force them to install Agno + boto3 transitively.
- **agents/** — Agno ``Agent`` factories. May import schemas, prompts,
  config, exceptions, leaves (s3_io / markdown_io / telemetry / etc.).
  MUST NOT import from pipelines, cli, extract, or eval.
- **pipelines/** — orchestration. May import schemas, agents, leaves.
  MUST NOT import from cli, extract, or eval.
- **eval/** — peer to extract; CI / dev surface only. May import schemas,
  extract, pipelines/batch, leaves. MUST NOT import directly from
  ``agents/`` (eval consumes via the extract orchestrator).
- **cli** — top entry-point. May import anything; nothing else imports cli.
- **leaves** (``s3_io``, ``markdown_io``, ``disagreement``, ``corrections``,
  ``telemetry``, ``exceptions``, ``body_parse/``, ``pdf/``, ``prompts/``,
  ``config/``) — narrow utilities. May import from each other and from
  schemas. MUST NOT import from agents, pipelines, cli, extract, or eval.

The package's ``__init__.py`` is treated as ``package_top`` — it's the
public-API re-exporter, controlled by hand, and allowed to import from
extract / telemetry / corrections / etc.
"""
from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "doc_extractor"

# ---------------------------------------------------------------------------
# Layer classification
# ---------------------------------------------------------------------------

# Source-file → layer. Path is relative to ``src/doc_extractor``.
_DIRECTORY_LAYERS: dict[str, str] = {
    "schemas": "schemas",
    "agents": "agents",
    "pipelines": "pipelines",
    "eval": "eval",
    "body_parse": "leaf",
    "pdf": "leaf",
    "prompts": "leaf",
    "config": "leaf",
}

_TOP_LEVEL_FILE_LAYERS: dict[str, str] = {
    "cli.py": "cli",
    "extract.py": "extract",
    "__init__.py": "package_top",
    "s3_io.py": "leaf",
    "markdown_io.py": "leaf",
    "disagreement.py": "leaf",
    "corrections.py": "leaf",
    "telemetry.py": "leaf",
    "exceptions.py": "leaf",
}

# Forbidden import-target layers per source layer. Anything not in the set
# is allowed. ``external`` (anything outside ``doc_extractor``) is always
# allowed.
_FORBIDDEN_TARGETS: dict[str, frozenset[str]] = {
    # Schema is the public output contract — pure data, no upward deps.
    "schemas": frozenset({"agents", "pipelines", "cli", "extract", "eval", "leaf"}),
    # Agents are ignorant of orchestration; eval imports via extract.
    "agents": frozenset({"pipelines", "cli", "extract", "eval"}),
    # Pipelines orchestrate but don't know about CLI or eval.
    "pipelines": frozenset({"cli", "extract", "eval"}),
    # Eval is peer to extract; it goes through extract, not directly into
    # agents (per architecture Decision 6).
    "eval": frozenset({"agents", "cli"}),
    # Leaves are narrow utilities — no awareness of orchestration.
    "leaf": frozenset({"agents", "pipelines", "cli", "extract", "eval"}),
    # CLI is top — may import anything. Nothing else imports cli; that's
    # checked separately below as a reverse-edge rule.
    "cli": frozenset(),
    # extract.py is the top-level orchestrator (architecture treats it as
    # peer to cli for invocation surface). Allowed to reach all layers.
    "extract": frozenset(),
    # __init__.py re-exports the public API. Controlled by hand.
    "package_top": frozenset(),
}


def _classify_source(rel_path: Path) -> str:
    """Map ``src/doc_extractor`` relative path → layer name."""
    parts = rel_path.parts
    if len(parts) == 1:
        return _TOP_LEVEL_FILE_LAYERS.get(parts[0], "leaf")
    return _DIRECTORY_LAYERS.get(parts[0], "leaf")


def _classify_import_target(import_path: str) -> str:
    """Map a fully-qualified ``doc_extractor.*`` import path → layer name.

    External modules (pydantic, stdlib, agno, boto3, etc.) classify as
    ``external`` and are always allowed.
    """
    if not (import_path == "doc_extractor" or import_path.startswith("doc_extractor.")):
        return "external"
    if import_path == "doc_extractor":
        return "package_top"

    rest = import_path[len("doc_extractor."):]
    head = rest.split(".", 1)[0]

    if head in _DIRECTORY_LAYERS:
        return _DIRECTORY_LAYERS[head]
    file_name = f"{head}.py"
    if file_name in _TOP_LEVEL_FILE_LAYERS:
        return _TOP_LEVEL_FILE_LAYERS[file_name]
    # Unknown attr — treat as package_top (likely a public API name re-exported
    # from __init__.py, which is itself ``package_top``).
    return "package_top"


# ---------------------------------------------------------------------------
# AST walk
# ---------------------------------------------------------------------------


def _python_files() -> Iterable[Path]:
    for path in SRC_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _imports_from_file(path: Path) -> list[tuple[str, int]]:
    """Return ``(import_path, lineno)`` pairs for every internal import.

    For ``import doc_extractor.X`` and ``from doc_extractor.X import Y``
    we surface ``doc_extractor.X``. For ``from doc_extractor import a, b``
    we surface ``doc_extractor.a`` and ``doc_extractor.b`` (each name
    becomes its own potential target, which is the right granularity for
    the boundary check — a single import line can hit multiple submodules).

    External imports (stdlib, pydantic, agno, boto3, ...) are filtered out
    here because the boundary rules don't constrain them.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "doc_extractor" or alias.name.startswith(
                    "doc_extractor."
                ):
                    out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # ``from . import x`` / ``from .. import y`` — relative imports
            # inside doc_extractor; reconstruct the absolute path.
            if node.level > 0:
                # We don't currently use relative imports anywhere; conservatively
                # treat the absolute equivalent as ``doc_extractor.<module>`` so
                # any future relative import still gets boundary-checked.
                module = module if module else ""
            if not module:
                continue
            if module == "doc_extractor":
                # Each imported name becomes its own target candidate.
                for alias in node.names:
                    out.append((f"doc_extractor.{alias.name}", node.lineno))
            elif module.startswith("doc_extractor."):
                out.append((module, node.lineno))

    return out


# ---------------------------------------------------------------------------
# The actual test
# ---------------------------------------------------------------------------


# Narrowly-scoped exceptions where the production code knowingly crosses a
# boundary for documented reasons. Each entry pairs a source path (relative
# to ``src/doc_extractor``) with the import path it's allowed to reach. Add
# one only with an inline comment explaining the rationale; the goal is for
# this set to shrink over time as the code converges on the architecture.
_KNOWN_EXCEPTIONS: set[tuple[str, str]] = {
    # Story 8.5 — ``pipelines/batch.py`` is a batch-orchestration shim,
    # not a "pipeline" in the vision_path / body_parse_path sense. It
    # wraps :func:`doc_extractor.extract.extract` per-key with a
    # rate-limit-retry shell, while ``extract.py`` re-exports
    # ``extract_batch`` for the public API. The cyclic shape (batch ↔
    # extract) is acknowledged in batch.py's docstring; a future
    # cleanup should either lift batch.py out of ``pipelines/`` to a
    # top-level orchestrator file (alongside ``extract.py``) or move
    # the wrapper into ``extract.py`` directly.
    ("pipelines/batch.py", "doc_extractor.extract"),
}


def test_no_internal_import_violates_layer_boundaries() -> None:
    """Walk the production source tree and assert every internal import
    obeys the source-layer's forbidden-target rule."""
    violations: list[str] = []

    for file_path in _python_files():
        rel = file_path.relative_to(SRC_ROOT)
        source_layer = _classify_source(rel)
        forbidden = _FORBIDDEN_TARGETS.get(source_layer, frozenset())

        for import_path, lineno in _imports_from_file(file_path):
            target_layer = _classify_import_target(import_path)
            if target_layer not in forbidden:
                continue
            if (str(rel), import_path) in _KNOWN_EXCEPTIONS:
                continue
            violations.append(
                f"{rel}:{lineno}: layer {source_layer!r} forbids importing "
                f"from layer {target_layer!r} (offending path: {import_path!r})"
            )

    assert not violations, (
        "Architectural boundary violation(s) detected — see "
        "tests/unit/test_import_boundaries.py docstring for the rule "
        "digest:\n  " + "\n  ".join(sorted(violations))
    )


def test_cli_is_not_imported_by_any_other_module() -> None:
    """``cli.py`` is the top-level entry point; nothing else imports from it.
    A reverse-edge rule (boundary 5 in the docstring) — caught here as a
    separate sentinel because the per-file check above is forward-only."""
    importers: list[str] = []
    cli_module_targets = {"doc_extractor.cli"}

    for file_path in _python_files():
        rel = file_path.relative_to(SRC_ROOT)
        if str(rel) == "cli.py":
            continue
        for import_path, lineno in _imports_from_file(file_path):
            head = import_path.split(".", 2)
            if len(head) >= 2 and head[0] == "doc_extractor" and head[1] == "cli":
                importers.append(f"{rel}:{lineno}: imports from {import_path!r}")
            elif import_path in cli_module_targets:
                importers.append(f"{rel}:{lineno}: imports from {import_path!r}")

    assert not importers, (
        "cli.py is the top entry-point; nothing else may import it. "
        "Offending imports:\n  " + "\n  ".join(sorted(importers))
    )


# ---------------------------------------------------------------------------
# Self-tests for the layer classifier (catches bugs in the test logic itself)
# ---------------------------------------------------------------------------


def test_classifier_layer_assignment_for_known_paths() -> None:
    cases: list[tuple[str, str]] = [
        ("schemas/base.py", "schemas"),
        ("schemas/payment_receipt.py", "schemas"),
        ("agents/passport.py", "agents"),
        ("agents/factory.py", "agents"),
        ("pipelines/vision_path.py", "pipelines"),
        ("pipelines/body_parse_path.py", "pipelines"),
        ("eval/matchers.py", "eval"),
        ("body_parse/chinese_labels.py", "leaf"),
        ("pdf/converter.py", "leaf"),
        ("prompts/loader.py", "leaf"),
        ("config/precedence.py", "leaf"),
        ("cli.py", "cli"),
        ("extract.py", "extract"),
        ("__init__.py", "package_top"),
        ("s3_io.py", "leaf"),
        ("markdown_io.py", "leaf"),
        ("disagreement.py", "leaf"),
        ("telemetry.py", "leaf"),
        ("exceptions.py", "leaf"),
    ]
    for rel_str, expected in cases:
        actual = _classify_source(Path(rel_str))
        assert actual == expected, f"{rel_str}: expected {expected!r}, got {actual!r}"


def test_target_classifier_resolves_known_import_paths() -> None:
    cases: list[tuple[str, str]] = [
        ("doc_extractor.schemas.base", "schemas"),
        ("doc_extractor.schemas.payment_receipt", "schemas"),
        ("doc_extractor.agents.passport", "agents"),
        ("doc_extractor.agents", "agents"),
        ("doc_extractor.pipelines.vision_path", "pipelines"),
        ("doc_extractor.eval.matchers", "eval"),
        ("doc_extractor.eval", "eval"),
        ("doc_extractor.cli", "cli"),
        ("doc_extractor.extract", "extract"),
        ("doc_extractor.s3_io", "leaf"),
        ("doc_extractor.markdown_io", "leaf"),
        ("doc_extractor.body_parse.chinese_labels", "leaf"),
        ("doc_extractor.pdf.converter", "leaf"),
        ("doc_extractor.config.precedence", "leaf"),
        ("doc_extractor", "package_top"),
        ("pydantic", "external"),
        ("agno.agent", "external"),
        ("boto3", "external"),
    ]
    for path, expected in cases:
        actual = _classify_import_target(path)
        assert actual == expected, f"{path!r}: expected {expected!r}, got {actual!r}"
