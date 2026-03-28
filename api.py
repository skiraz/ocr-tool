#!/usr/bin/env python3
"""
OCR Document Converter
Uses the Datalab API to convert images/PDFs to markdown text.
"""

import os
import sys
import argparse
from pathlib import Path

from datalab_sdk import DatalabClient, ConvertOptions


def get_api_key(cli_key=None):
    """Retrieve API key from CLI argument, environment variable, or .env file."""
    if cli_key:
        return cli_key

    api_key = os.environ.get("DATALAB_API_KEY")

    if not api_key:
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DATALAB_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip("'\"")
                        break

    if not api_key:
        print("Error: DATALAB_API_KEY not found.", file=sys.stderr)
        print("Set it via:", file=sys.stderr)
        print("  1. Environment variable: export DATALAB_API_KEY='your-key'", file=sys.stderr)
        print("  2. CLI argument: --api-key your-key", file=sys.stderr)
        print("  3. .env file: DATALAB_API_KEY=your-key", file=sys.stderr)
        sys.exit(1)

    return api_key


def convert_file(file_path, output_path=None, output_format="markdown", mode="balanced", paginate=True, api_key=None):
    """
    Convert a file using the Datalab API.

    Args:
        file_path: Path to the input file (image or PDF).
        output_path: Optional path to save the output. If None, prints to stdout.
        output_format: Output format (default: "markdown").
        mode: Conversion mode - "fast", "balanced", or "accurate" (default: "balanced").
        paginate: Whether to paginate output (default: True).

    Returns:
        The markdown string result.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    api_key = get_api_key(api_key)
    client = DatalabClient(api_key)

    options = ConvertOptions(
        output_format=output_format,
        mode=mode,
        paginate=paginate,
    )

    try:
        print(f"Converting: {file_path}", file=sys.stderr)
        result = client.convert(str(file_path), options=options)
        markdown = result.markdown

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            print(f"Saved to: {output_path}", file=sys.stderr)
        else:
            print(markdown)

        return markdown

    except Exception as e:
        print(f"Error converting {file_path}: {e}", file=sys.stderr)
        sys.exit(1)


def batch_convert(input_dir, output_dir, output_format="markdown", mode="balanced", paginate=True, api_key=None):
    """
    Batch convert all supported files in a directory.

    Args:
        input_dir: Directory containing input files.
        output_dir: Directory to save output files.
        output_format: Output format.
        mode: Conversion mode.
        paginate: Whether to paginate.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    if not input_dir.is_dir():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    supported_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
    files = [f for f in input_dir.iterdir() if f.suffix.lower() in supported_extensions]

    if not files:
        print(f"No supported files found in {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} file(s) to convert.", file=sys.stderr)

    for file_path in files:
        md_filename = file_path.stem + ".md"
        output_path = output_dir / md_filename
        convert_file(file_path, output_path, output_format, mode, paginate, api_key)


def main():
    parser = argparse.ArgumentParser(
        description="OCR Document Converter - Convert images/PDFs to markdown using Datalab API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert a single image to markdown and print to stdout
  python api.py page_1.png

  # Convert a single image and save to file
  python api.py page_1.png -o output/page_1.md

  # Convert a PDF with accurate mode
  python api.py document.pdf -m accurate -o output/document.md

  # Batch convert all files in a directory
  python api.py --batch input_folder/ -o output_folder/
        """,
    )

    parser.add_argument(
        "input",
        nargs="?",
        help="Input file path (image or PDF)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path or directory (for batch mode)",
        default=None,
    )
    parser.add_argument(
        "-f", "--format",
        help="Output format (default: markdown)",
        default="markdown",
        choices=["markdown", "json", "text"],
    )
    parser.add_argument(
        "-m", "--mode",
        help="Conversion mode: fast, balanced, accurate (default: balanced)",
        default="balanced",
        choices=["fast", "balanced", "accurate"],
    )
    parser.add_argument(
        "--no-paginate",
        help="Disable pagination in output",
        action="store_true",
    )
    parser.add_argument(
        "--batch",
        metavar="INPUT_DIR",
        help="Batch mode: convert all files in the specified directory",
    )
    parser.add_argument(
        "--api-key",
        help="Datalab API key (overrides DATALAB_API_KEY env var and .env file)",
        default=None,
    )

    args = parser.parse_args()

    paginate = not args.no_paginate

    if args.batch:
        output_dir = args.output or "output"
        batch_convert(args.batch, output_dir, args.format, args.mode, paginate, args.api_key)
    elif args.input:
        convert_file(args.input, args.output, args.format, args.mode, paginate, args.api_key)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
