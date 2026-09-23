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

from llm import LLMClient, Usage
from pipeline import analyze


ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
CHECKPOINT_DIR = OUTPUT_DIR / ".checkpoints"


async def analyze_one(
    input_path: Path,
    output_path: Path,
    llm: LLMClient,
    detect_concurrency: int,
    annotate_concurrency: int,
    context: str,
) -> None:
    print(f"→ Analyzing {input_path.name}")
    llm.usage = Usage()
    story = input_path.read_text(encoding="utf-8")
    result = await analyze(
        story,
        input_path.name,
        llm,
        detect_concurrency=detect_concurrency,
        annotate_concurrency=annotate_concurrency,
        context=context,
    )
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
    print(f"  {llm.usage.summary()}")


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
        required=True,
        help="OpenAI model id, e.g. gpt-5.6-luna.",
    )
    parser.add_argument(
        "--no-temperature",
        action="store_true",
        help="Omit the temperature parameter. Needed for some reasoning models "
             "that reject it.",
    )
    parser.add_argument(
        "--detect-concurrency",
        type=int,
        default=1,
        help="Max concurrent segment-detection calls. "
             "Lower this if you hit rate limits.",
    )
    parser.add_argument(
        "--annotate-concurrency",
        type=int,
        default=1,
        help="Max concurrent line-annotation calls. "
             "Lower this if you hit rate limits.",
    )
    parser.add_argument(
        "--context",
        choices=["story", "local"],
        default="story",
        help="What detection and annotation calls see besides their own "
             "segment/line. 'story' (default): the full story, sent as a "
             "shared prefix that the prompt cache bills at the cached rate "
             "after the first call. 'local': only the segment text or a "
             "5-line window; fewer tokens but less context.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore saved checkpoints and call the model again for every "
             "step (new results are still checkpointed).",
    )
    args = parser.parse_args()

    llm = LLMClient(
        model=args.model,
        temperature=None if args.no_temperature else 0.0,
        checkpoint_dir=CHECKPOINT_DIR,
        fresh=args.fresh,
    )
    run_opts = (args.detect_concurrency, args.annotate_concurrency, args.context)
    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.file:
        input_path = args.file
        if not input_path.exists():
            print(f"File not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        output_path = args.out or (OUTPUT_DIR / (input_path.stem + ".json"))
        await analyze_one(input_path, output_path, llm, *run_opts)
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
            await analyze_one(input_path, output_path, llm, *run_opts)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ failed on {input_path.name}: {exc}", file=sys.stderr)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
