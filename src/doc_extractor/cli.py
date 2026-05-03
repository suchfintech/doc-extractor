from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from doc_extractor import __version__
from doc_extractor.eval import run_eval
from doc_extractor.eval.harness import DEFAULT_EVAL_CONCURRENCY
from doc_extractor.exceptions import BodyParseUnmatchedError, ConfigurationError
from doc_extractor.extract import extract
from doc_extractor.pipelines import body_parse_path
from doc_extractor.pipelines.batch import DEFAULT_BATCH_CONCURRENCY, extract_batch

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
        help="Run the vision pipeline against a single source key or batch.",
    )
    source_group = extract_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--key", default=None, help="Single S3 source key to extract."
    )
    source_group.add_argument(
        "--keys-file",
        dest="keys_file",
        type=Path,
        default=None,
        help=(
            "Path to a newline-separated file of S3 source keys. Blank lines "
            "and lines starting with `#` are skipped. Mutually exclusive "
            "with --key."
        ),
    )
    extract_parser.add_argument(
        "--max-concurrent",
        dest="max_concurrent",
        type=int,
        default=DEFAULT_BATCH_CONCURRENCY,
        help=(
            "Concurrency bound for --keys-file batch runs (default "
            f"{DEFAULT_BATCH_CONCURRENCY})."
        ),
    )
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
    extract_parser.add_argument(
        "--body-parse-only",
        action="store_true",
        dest="body_parse_only",
        help=(
            "Skip the Vision pipeline. Read the existing analysis .md, run "
            "body-parse repair (CN labels first, NZ narrative fallback), and "
            "write back a frontmatter-only update. Body markdown is preserved "
            "byte-identical."
        ),
    )

    eval_parser = subparsers.add_parser(
        "eval",
        help="Run the eval harness against the golden corpus and emit a Scorecard.",
    )
    eval_parser.add_argument(
        "--doc-type",
        dest="doc_type",
        default=None,
        help="Restrict to one DOC_TYPES literal (e.g. Passport, PaymentReceipt).",
    )
    eval_parser.add_argument(
        "--jurisdiction",
        default=None,
        help="Restrict to one ISO-3166-1 alpha-2 jurisdiction (e.g. CN, NZ).",
    )
    eval_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the Scorecard JSON to this path. Stdout when omitted.",
    )
    eval_parser.add_argument(
        "--max-concurrent",
        dest="max_concurrent",
        type=int,
        default=DEFAULT_EVAL_CONCURRENCY,
        help=(
            "Concurrency bound for the eval extract_batch (default "
            f"{DEFAULT_EVAL_CONCURRENCY}; aggressive vs the user-facing "
            f"{DEFAULT_BATCH_CONCURRENCY} because the corpus is bounded)."
        ),
    )

    return parser


def _read_keys_file(path: Path) -> list[str]:
    """Read a newline-separated keys file. Skip blanks and `#` comment lines."""
    keys: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            keys.append(line)
    return keys


def _run_extract(args: argparse.Namespace) -> int:
    if args.body_parse_only:
        if not args.key:
            print(
                "--body-parse-only requires --key (single-key mode only).",
                file=sys.stderr,
            )
            return EXIT_CONFIGURATION_ERROR
        asyncio.run(body_parse_path.run(args.key))
        return EXIT_OK

    if args.keys_file is not None:
        keys = _read_keys_file(args.keys_file)
        results = asyncio.run(
            extract_batch(keys, max_concurrent=args.max_concurrent)
        )
        for r in results:
            status = "skipped" if r.skipped else "extracted"
            print(f"{status}: {r.key}")
        return EXIT_OK

    result = asyncio.run(
        extract(
            key=args.key,
            provider=args.provider,
            model=args.model,
            verbose=args.verbose,
            show_image=args.show_image,
            dry_run=args.dry_run,
        )
    )
    status = "skipped (already extracted)" if result.skipped else "extracted"
    print(f"{status}: {result.analysis_key}")
    return EXIT_OK


def _run_eval(args: argparse.Namespace) -> int:
    scorecard = asyncio.run(
        run_eval(
            doc_type=args.doc_type,
            jurisdiction=args.jurisdiction,
            max_concurrent=args.max_concurrent,
        )
    )
    payload = scorecard.to_json()
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
        print(f"Scorecard written to {args.output}", file=sys.stderr)
    else:
        print(payload)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command not in {"extract", "eval"}:
        print(f"doc-extractor {__version__}")
        print("Subcommands: extract | eval. Try `doc-extractor --help`.")
        return EXIT_OK

    try:
        if args.command == "extract":
            return _run_extract(args)
        return _run_eval(args)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIGURATION_ERROR
    except BodyParseUnmatchedError as exc:
        print(f"body-parse unmatched: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except Exception as exc:  # noqa: BLE001 — CLI top-level catches everything for exit-code mapping
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    sys.exit(main())
