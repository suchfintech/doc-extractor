"""Sentinel: the layered scaffold imports cleanly."""
from __future__ import annotations


def test_cli_module_imports() -> None:
    from doc_extractor import cli

    assert callable(cli.main)


def test_package_subpackages_import() -> None:
    import importlib

    for sub in (
        "agents",
        "schemas",
        "prompts",
        "pipelines",
        "eval",
        "config",
        "body_parse",
        "pdf",
    ):
        importlib.import_module(f"doc_extractor.{sub}")
