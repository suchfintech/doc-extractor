"""Unit tests for the versioned prompt loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_extractor.exceptions import ConfigurationError
from doc_extractor.prompts import loader


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    loader.load_prompt.cache_clear()


def _write_prompt(dir_: Path, name: str, body: str) -> Path:
    path = dir_ / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_passport_returns_body_and_version() -> None:
    body, version = loader.load_prompt("passport")
    assert version == "0.1.0"
    assert "MRZ" in body
    assert "name_latin" in body
    assert "name_cjk" in body
    assert not body.startswith("---")


def test_passport_prompt_is_focused_size() -> None:
    body, _ = loader.load_prompt("passport")
    size = len(body.encode("utf-8"))
    assert 1500 <= size <= 6000, (
        f"passport prompt body is {size} bytes; AC asks for ~3KB focused prompt"
    )


def test_load_caches_per_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)
    _write_prompt(
        tmp_path,
        "fake",
        '---\nagent: fake\nversion: "0.2.0"\nlast_modified: "2026-05-03"\n---\n\nhello body\n',
    )

    read_calls = 0
    real_read_text = Path.read_text

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal read_calls
        read_calls += 1
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    body1, ver1 = loader.load_prompt("fake")
    body2, ver2 = loader.load_prompt("fake")

    assert (body1, ver1) == (body2, ver2)
    assert ver1 == "0.2.0"
    assert read_calls == 1, "Second call should hit the per-process cache"


def test_missing_file_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)
    with pytest.raises(ConfigurationError, match="not found"):
        loader.load_prompt("nonexistent")


def test_missing_frontmatter_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)
    _write_prompt(tmp_path, "no_fm", "just a body, no frontmatter at all\n")
    with pytest.raises(ConfigurationError, match="missing YAML frontmatter"):
        loader.load_prompt("no_fm")


def test_unclosed_frontmatter_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)
    _write_prompt(
        tmp_path,
        "open_fm",
        '---\nagent: x\nversion: "0.1.0"\nlast_modified: "2026-05-03"\n\nbody never closes the fence\n',
    )
    with pytest.raises(ConfigurationError, match="missing YAML frontmatter"):
        loader.load_prompt("open_fm")


def test_missing_version_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)
    _write_prompt(
        tmp_path,
        "no_ver",
        '---\nagent: x\nlast_modified: "2026-05-03"\n---\n\nbody\n',
    )
    with pytest.raises(ConfigurationError, match="'version'"):
        loader.load_prompt("no_ver")


def test_empty_version_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)
    _write_prompt(
        tmp_path,
        "empty_ver",
        '---\nagent: x\nversion: ""\nlast_modified: "2026-05-03"\n---\n\nbody\n',
    )
    with pytest.raises(ConfigurationError, match="'version'"):
        loader.load_prompt("empty_ver")


def test_missing_agent_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(loader, "_PROMPTS_DIR", tmp_path)
    _write_prompt(
        tmp_path,
        "no_agent",
        '---\nversion: "0.1.0"\nlast_modified: "2026-05-03"\n---\n\nbody\n',
    )
    with pytest.raises(ConfigurationError, match="'agent'"):
        loader.load_prompt("no_agent")
