"""Versioned prompt loader.

Reads ``src/doc_extractor/prompts/<name>.md``, parses YAML frontmatter
(``agent``, ``version``, ``last_modified``), and returns
``(prompt_text, prompt_version)``. Results are cached per process so repeated
loads don't re-read the file (Decision 3, AR7).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from doc_extractor.exceptions import ConfigurationError

_PROMPTS_DIR = Path(__file__).resolve().parent
_FENCE = "---"
_REQUIRED_KEYS: tuple[str, ...] = ("agent", "version", "last_modified")


def _split_frontmatter(raw: str) -> tuple[str, str] | None:
    """Return ``(yaml_text, body)`` if the file opens with a ``---`` fence, else None."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == _FENCE:
            yaml_text = "\n".join(lines[1:idx])
            body = "\n".join(lines[idx + 1 :])
            return yaml_text, body.lstrip("\n")
    return None


@cache
def load_prompt(name: str) -> tuple[str, str]:
    """Load a versioned prompt by name.

    Returns:
        ``(prompt_text, prompt_version)`` — body without the frontmatter
        fences, plus the semver string from the frontmatter ``version`` key.

    Raises:
        ConfigurationError: file is missing, frontmatter is absent or
            malformed, or any required key (``agent``, ``version``,
            ``last_modified``) is missing or empty.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise ConfigurationError(f"Prompt file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    split = _split_frontmatter(raw)
    if split is None:
        raise ConfigurationError(
            f"Prompt {name!r} is missing YAML frontmatter "
            f"(expected leading '---' fence at {path})."
        )
    yaml_text, body = split

    try:
        meta = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Prompt {name!r} has malformed YAML frontmatter: {exc}"
        ) from exc

    if not isinstance(meta, dict):
        raise ConfigurationError(
            f"Prompt {name!r} frontmatter must be a YAML mapping, got {type(meta).__name__}."
        )

    for key in _REQUIRED_KEYS:
        value = meta.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ConfigurationError(
                f"Prompt {name!r} frontmatter is missing required key {key!r}."
            )

    return body, str(meta["version"])
