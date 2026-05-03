from __future__ import annotations

import argparse
import asyncio
import sys

from doc_extractor import __version__
from doc_extractor.exceptions import ConfigurationError
from doc_extractor.extract import extract

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIGURATION_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc-extractor",
        description="Vision-based document analyzer.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"doc-extractor {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    extract_parser = subparsers.add_parser(
        "extract",
        help="Run the vision pipeline against a single source key.",
    )
    extract_parser.add_argument("--key", required=True, help="S3 source key to extract.")
    extract_parser.add_argument(
        "--provider", default=None, help="Override the provider (e.g. anthropic, openai)."
    )
    extract_parser.add_argument(
        "--model", default=None, help="Override the model identifier."
    )
    extract_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Emit prompt / raw response / validation / rendered .md / cost sections (FR51).",
    )
    extract_parser.add_argument(
        "--show-image",
        action="store_true",
        dest="show_image",
        help="Print the presigned URL of the source image.",
    )
    extract_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Render but do not write to S3; print the .md to stdout instead.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "extract":
        print(f"doc-extractor {__version__}")
        print("Run `doc-extractor extract --key <s3-key>` to extract a document.")
        return EXIT_OK

    try:
        asyncio.run(
            extract(
                key=args.key,
                provider=args.provider,
                model=args.model,
                verbose=args.verbose,
                show_image=args.show_image,
                dry_run=args.dry_run,
            )
        )
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIGURATION_ERROR
    except Exception as exc:  # noqa: BLE001 — CLI top-level catches everything for exit-code mapping
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
