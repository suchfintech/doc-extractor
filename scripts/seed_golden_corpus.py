"""Story 2.1 bootstrap — seed golden-corpus draft `.expected.md` files
from legacy free-text analyses synced from ``s3://golden-mountain-analysis``.

The drafts are written to ``.local/golden-drafts/<doc_type>/`` (gitignored)
so Yang can review and redact PII before promoting committed test
fixtures into ``tests/golden/<doc_type>/``.

Usage:

    python scripts/seed_golden_corpus.py --doc-type passport \\
        --legacy-root /tmp/gt-scan/raw \\
        --picks 2706/3953c3487fd6dd042cd6b3c41bf491d1.jpeg.md \\
                2741/0a5fe56c5155995a5c8bb5758a406ce0.jpeg.md \\
        --out .local/golden-drafts/passport

The script:

1. Reads each legacy ``.md`` analysis.
2. Extracts the ``FIELDS:`` block via regex.
3. Maps to the v2 schema for the doc type (currently Passport only;
   extend the ``MAPPERS`` registry to add more types).
4. Renders the v2 ``.expected.md`` via :func:`markdown_io.render_to_md`
   so it is byte-stable and round-trips through :func:`parse_md`.
5. Validates the round-trip — the script aborts on any draft that fails
   parse, so reviewers never see an invalid candidate.

Drafts include real PII from the legacy analyses; do not commit. Yang
hand-redacts each before promoting to ``tests/golden/``.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

# Ensure the local src/ is importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from doc_extractor.markdown_io import parse_md, render_to_md
from doc_extractor.schemas.ids import Passport

_MONTH = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def _parse_date(s: str) -> str:
    """``30 JUN 1999`` → ``1999-06-30``. Empty string on parse failure."""
    s = s.strip()
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", s)
    if not m:
        return ""
    day, mon, year = m.group(1).zfill(2), m.group(2).upper(), m.group(3)
    if mon not in _MONTH:
        return ""
    return f"{year}-{_MONTH[mon]}-{day}"


def _extract_fields(text: str) -> dict[str, str]:
    """Parse the ``FIELDS:`` block of a legacy analysis into ``{label: value}``."""
    out: dict[str, str] = {}
    in_fields = False
    for line in text.splitlines():
        if line.strip().startswith("FIELDS:"):
            in_fields = True
            continue
        if in_fields:
            if not line.strip():
                continue
            if line.strip().startswith(("RAW_TEXT:", "QUALITY:", "```", "---")):
                break
            m = re.match(r"^\s*-\s*([^:]+):\s*(.+?)\s*$", line)
            if m:
                out[m.group(1).strip()] = m.group(2).strip()
    return out


def _grab(fields: dict[str, str], *labels: str) -> str:
    """Return the first non-empty value among the labels, or empty."""
    for lbl in labels:
        v = fields.get(lbl, "").strip()
        if v:
            return v
    return ""


_CJK_RE = re.compile(r"[一-鿿]+")


def _split_latin_cjk(name: str) -> tuple[str, str]:
    """``SUN, JIAWEI (孙嘉蔚)`` → (``SUN JIAWEI``, ``孙嘉蔚``).

    Strips the parenthetical, keeps everything inside it that is CJK.
    """
    name = name.strip()
    cjk_match = _CJK_RE.findall(name)
    cjk = "".join(cjk_match)
    latin = re.sub(r"\([^)]*\)", "", name)
    latin = re.sub(r"[,/]", " ", latin)
    latin = re.sub(r"\s+", " ", latin).strip()
    return latin, cjk


def _normalise_sex(value: str) -> str:
    v = value.upper()
    if "F" in v.split() or "FEMALE" in v or "女" in value:
        return "F"
    if "M" in v.split() or "MALE" in v or "男" in value:
        return "M"
    return ""


def _normalise_country(value: str) -> str:
    v = value.upper()
    if "CHN" in v or "CHINA" in v or "CHINESE" in v:
        return "CHN"
    if "NZL" in v or "NEW ZEALAND" in v:
        return "NZL"
    if "HKG" in v or "HONG KONG" in v:
        return "HKG"
    return value.strip().upper()


def _strip_paren(value: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", value).strip()


def map_passport(text: str) -> Passport:
    fields = _extract_fields(text)
    full_name = _grab(fields, "Full Name", "Name")
    name_latin, name_cjk = _split_latin_cjk(full_name)

    return Passport(
        extractor_version="0.1.0",
        extraction_provider="anthropic",
        extraction_model="claude-haiku-4-5-20251001",
        extraction_timestamp="2026-03-21T19:17:00Z",
        prompt_version="passport@1.0.0",
        doc_type="Passport",
        doc_subtype="",
        jurisdiction=_normalise_country(
            _grab(fields, "Country Code", "Country of Issue", "Nationality")
        ),
        name_latin=name_latin,
        name_cjk=name_cjk,
        doc_number=_grab(fields, "Document Number", "Passport Number"),
        dob=_parse_date(_grab(fields, "Date of Birth")),
        issue_date=_parse_date(_grab(fields, "Issue Date")),
        expiry_date=_parse_date(_grab(fields, "Expiry Date")),
        place_of_birth=_strip_paren(_grab(fields, "Place of Birth")).upper(),
        sex=_normalise_sex(_grab(fields, "Gender", "Sex", "Sex/Gender")),
        passport_number=_grab(fields, "Passport Number", "Document Number"),
        nationality=_normalise_country(_grab(fields, "Nationality", "Country Code")),
        mrz_line_1="",
        mrz_line_2="",
    )


MAPPERS: dict[str, Callable[[str], object]] = {
    "passport": map_passport,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-type", required=True, choices=sorted(MAPPERS.keys()))
    ap.add_argument("--legacy-root", required=True, type=Path)
    ap.add_argument("--picks", nargs="+", required=True, help="paths relative to legacy-root")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    mapper = MAPPERS[args.doc_type]

    for i, rel in enumerate(args.picks, start=1):
        legacy_path = args.legacy_root / rel
        text = legacy_path.read_text(encoding="utf-8", errors="replace")
        instance = mapper(text)
        rendered = render_to_md(instance)  # type: ignore[arg-type]
        round_tripped = parse_md(rendered)
        assert round_tripped.model_dump() == instance.model_dump(), (
            f"Round-trip mismatch for {legacy_path}"
        )
        out_path = args.out / f"example_{i:02d}.expected.md"
        out_path.write_text(rendered, encoding="utf-8")
        print(f"wrote {out_path} ← {legacy_path.name}")

    print(f"\n{len(args.picks)} drafts produced in {args.out}")
    print("Next: review each .expected.md, redact PII per repo policy, then "
          "promote selected examples (and their source images) into "
          f"tests/golden/{args.doc_type}/.")


if __name__ == "__main__":
    main()
