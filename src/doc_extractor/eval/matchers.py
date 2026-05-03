"""Field-level comparison matchers for the eval harness.

Three layers of strictness:

* :func:`match_exact` — byte-identical, the default for things like
  ``passport_number`` where any normalisation hides real failures.
* :func:`match_normalised` — strips trailing whitespace, lowercases, and
  drops Unicode combining marks (NFKD + ``Mn`` filter). Latin diacritics
  collapse; CJK characters pass through unchanged because they aren't
  ``Mn``.
* :func:`match_with_jurisdiction` — adds CN-specific tolerances on top of
  exact match. v1 rule: collapse runs of ``*`` so verbatim masks like
  ``**** ****`` and ``********`` compare equal even though the canonical
  contract preserves the original spelling.

The ``field_name`` argument is reserved for future per-field rules
(date formats, MRZ layouts) — it's plumbed through now so callers don't
need to change signatures later.
"""
from __future__ import annotations

import re
import unicodedata

CN_JURISDICTION = "CN"

# Collapses runs of '*' and any whitespace *between* stars: "**** ****" → "*",
# "********" → "*", but a lone "abc *" stays "abc *" (no following star to bridge).
_STAR_RUN = re.compile(r"\*+(?:\s+\*+)*")


def match_exact(field_name: str, expected: str, actual: str) -> bool:
    """Byte-identical comparison."""
    del field_name  # reserved for future per-field dispatch
    return expected == actual


def _strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def match_normalised(field_name: str, expected: str, actual: str) -> bool:
    """Trailing-whitespace + lowercase + diacritic-insensitive comparison.

    NFKD decomposition splits accented Latin glyphs into base + combining
    mark, and the ``Mn`` filter then removes the marks. CJK ideographs are
    in category ``Lo``, so they survive untouched — see ``test_matchers``.
    """
    del field_name
    return _strip_diacritics(expected.rstrip()).lower() == _strip_diacritics(actual.rstrip()).lower()


def _collapse_star_runs(text: str) -> str:
    return _STAR_RUN.sub("*", text)


def match_with_jurisdiction(
    field_name: str,
    expected: str,
    actual: str,
    jurisdiction: str,
) -> bool:
    """Exact match outside CN; CN adds star-mask collapse for account numbers.

    The canonical extraction preserves the verbatim mask (``**** ****``) so
    downstream redaction logic stays trustworthy. Matching, however, must
    treat that as equivalent to ``********`` since vision providers vary
    in how they render runs of asterisks.
    """
    if jurisdiction != CN_JURISDICTION:
        return match_exact(field_name, expected, actual)
    return _collapse_star_runs(expected) == _collapse_star_runs(actual)
