from __future__ import annotations

import argparse
import sys

from doc_extractor import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc-extractor",
        description="Vision-based document analyzer (scaffold — pipelines wired in later stories).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"doc-extractor {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    print(f"doc-extractor {__version__}")
    print("scaffold ready — extraction pipeline not yet wired (see Story 1.x).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
