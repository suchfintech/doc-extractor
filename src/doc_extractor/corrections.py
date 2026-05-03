"""Corrections-overlay reader (FR15, architecture Decision 2).

Manual overrides land in a parallel ``corrections/<source_key>.md``
namespace inside the analysis bucket — deliberately separate from the
canonical ``<source_key>.md`` so re-extraction never overwrites them.
``read_corrected_or_canonical`` HEADs the corrections key first; if it
exists, that wins. Otherwise the canonical extraction is returned. If
neither exists, a ``FileNotFoundError`` surfaces.

Note: merlin's existing ``frontmatter_io.py`` is OUT OF SCOPE for this
story — a separate PR will migrate merlin to call this helper. Story 6.2
ships the helper and its test only.
"""

from __future__ import annotations

from doc_extractor import markdown_io, s3_io
from doc_extractor.schemas.base import Frontmatter

CORRECTIONS_PREFIX = "corrections/"


def _corrections_key_for(source_key: str) -> str:
    return f"{CORRECTIONS_PREFIX}{source_key}.md"


def _canonical_key_for(source_key: str) -> str:
    return f"{source_key}.md"


def _read_and_parse(key: str) -> Frontmatter:
    text = s3_io.read_analysis(key).decode("utf-8")
    return markdown_io.parse_md(text)


async def read_corrected_or_canonical(source_key: str) -> Frontmatter:
    """Return the manual override if present, else the canonical extraction.

    Order of operations:

    1. ``HEAD corrections/<source_key>.md`` — if 200, read + parse + return.
    2. ``HEAD <source_key>.md`` — if 200, read + parse + return.
    3. Otherwise raise ``FileNotFoundError``.

    Step 1 is unconditional and runs first so the corrections-take-priority
    invariant cannot be reordered by accident.
    """
    corrections_key = _corrections_key_for(source_key)
    if s3_io.head_analysis(corrections_key):
        return _read_and_parse(corrections_key)

    canonical_key = _canonical_key_for(source_key)
    if s3_io.head_analysis(canonical_key):
        return _read_and_parse(canonical_key)

    raise FileNotFoundError(f"no extraction or correction for {source_key}")
