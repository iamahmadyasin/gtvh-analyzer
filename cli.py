"""
CLI entry point.

Default behavior: analyze every .txt in ./input, write .json into ./output.
With --file <path>: analyze one file, write beside it (or to --out).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from llm import LLMClient
from pipeline import analyze


ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"


async def analyze_one(input_path: Path, output_path: Path, llm: LLMClient) -> None:
    print(f"→ Analyzing {input_path.name}")
    story = input_path.read_text(encoding="utf-8")
    result = await analyze(story, input_path.name, llm)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        result.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    print(f"  wrote {output_path}")
    print(
        f"  segments={len(result.segments)} "
        f"lines={len(result.lines)}"
    )


async def _main() -> None:
    # Load .env if python-dotenv is installed and .env exists
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="GTVH humor analysis of short stories."
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Single input .txt file (default: process every .txt in ./input).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output .json path when using --file (default: ./output/<stem>.json).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1",
        help="OpenAI model name (default: gpt-4.1).",
    )
    parser.add_argument(
        "--detect-concurrency",
        type=int,
        default=5,
        help="Max concurrent segment-detection calls.",
    )
    parser.add_argument(
        "--annotate-concurrency",
        type=int,
        default=10,
        help="Max concurrent line-annotation calls.",
    )
    args = parser.parse_args()

    llm = LLMClient(model=args.model)
    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.file:
        input_path = args.file
        if not input_path.exists():
            print(f"File not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        output_path = args.out or (OUTPUT_DIR / (input_path.stem + ".json"))
        await analyze_one(input_path, output_path, llm)
        return

    # Batch mode: everything in input/
    if not INPUT_DIR.exists():
        print(f"Input directory does not exist: {INPUT_DIR}", file=sys.stderr)
        sys.exit(1)
    files = sorted(INPUT_DIR.glob("*.txt"))
    if not files:
        print(f"No .txt files in {INPUT_DIR}. Drop one in and re-run.")
        return
    for input_path in files:
        output_path = OUTPUT_DIR / (input_path.stem + ".json")
        try:
            await analyze_one(input_path, output_path, llm)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ failed on {input_path.name}: {exc}", file=sys.stderr)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
