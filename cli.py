"""
Entry point · Story analysis
Runs stages 1 to 3 on every .txt in input/, or on one file with --file.

Reads:   input/*.txt
Writes:  output/<story>.json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from llm_base import BaseLLMClient, Usage
from normalize import NormalizationParams
from providers import add_provider_args, make_client, resolve_provider
from pipeline import analyze


ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
CHECKPOINT_DIR = OUTPUT_DIR / ".checkpoints"


async def analyze_one(
    input_path: Path,
    output_path: Path,
    llm: BaseLLMClient,
    detect_concurrency: int,
    annotate_concurrency: int,
    context: str,
    normalization: NormalizationParams,
    embedding_model: str,
) -> None:
    print(f"→ Analyzing {input_path.name}")
    story = input_path.read_text(encoding="utf-8")
    result = await analyze(
        story,
        input_path.name,
        llm,
        detect_concurrency=detect_concurrency,
        annotate_concurrency=annotate_concurrency,
        context=context,
        normalization=normalization,
        embedding_model=embedding_model,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        result.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    print(f"  wrote {output_path}")
    print(
        f"  segments={len(result.segments)} "
        f"lines={len(result.lines)} "
        f"targets_in_inventory={len(result.target_inventory)}"
    )


async def _main() -> None:
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
        help="Model id: an OpenAI model (e.g. gpt-5.6-luna) or a Claude model "
             "(e.g. claude-opus-5-5).",
    )
    parser.add_argument(
        "--no-temperature",
        action="store_true",
        help="OpenAI only: omit the temperature parameter. Needed for models that "
             "reject it. Claude is never sent a temperature.",
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
             "after the first call. 'local': only the segment text (detection) "
             "or a 5-line window plus a 'story so far' built from the "
             "segment descriptions (annotation); fewer tokens, less context.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore saved checkpoints and call the model again for every "
             "step (new results are still checkpointed).",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Use OpenAI's Batch API: discounted, but each stage can take "
             "up to 24 hours. All stories run together, so each stage is "
             "one batch. If stopped while waiting, re-run the same command "
             "to resume.",
    )
    defaults = NormalizationParams()
    parser.add_argument(
        "--normalize",
        choices=["embeddings", "string"],
        default=None,
        help="How situation phrases and new targets are grouped into "
             "canonical labels: OpenAI embeddings (default with OpenAI; falls "
             "back to string similarity if the call fails) or string "
             "similarity (no API call; default with Claude, which has no "
             "embeddings API).",
    )
    parser.add_argument(
        "--embedding-model",
        default="text-embedding-3-small",
        help="Embedding model for --normalize embeddings.",
    )
    parser.add_argument(
        "--situation-threshold",
        type=float,
        default=defaults.situation_threshold,
        help="Minimum similarity (0-1) for two situation phrases to share a "
             "canonical label.",
    )
    parser.add_argument(
        "--target-threshold",
        type=float,
        default=defaults.target_threshold,
        help="Minimum similarity (0-1) for a new target to be merged with an "
             "inventory entry or another new target.",
    )
    add_provider_args(parser)
    args = parser.parse_args()

    provider = resolve_provider(args)
    llm = make_client(args, CHECKPOINT_DIR, batch=args.batch,
                      temperature=None if args.no_temperature else 0.0)
    if args.normalize is None:
        args.normalize = "embeddings" if provider == "openai" else "string"
    print(f"Provider: {provider}, model {args.model}"
          + (f", effort {args.effort}" if provider == "claude" else ""))
    run_opts = (
        args.detect_concurrency,
        args.annotate_concurrency,
        args.context,
        NormalizationParams(
            method=args.normalize,
            situation_threshold=args.situation_threshold,
            target_threshold=args.target_threshold,
        ),
        args.embedding_model,
    )
    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.file:
        if not args.file.exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        jobs = [(args.file, args.out or (OUTPUT_DIR / (args.file.stem + ".json")))]
    else:
        if not INPUT_DIR.exists():
            print(f"Input directory does not exist: {INPUT_DIR}", file=sys.stderr)
            sys.exit(1)
        files = sorted(INPUT_DIR.glob("*.txt"))
        if not files:
            print(f"No .txt files in {INPUT_DIR}. Drop one in and re-run.")
            return
        jobs = [(f, OUTPUT_DIR / (f.stem + ".json")) for f in files]

    if args.batch:
        # All stories together, so each stage is a single batch.
        outcomes = await asyncio.gather(
            *[analyze_one(i, o, llm, *run_opts) for i, o in jobs],
            return_exceptions=True,
        )
        for (input_path, _), outcome in zip(jobs, outcomes):
            if isinstance(outcome, BaseException):
                print(f"  ✗ failed on {input_path.name}: {outcome}", file=sys.stderr)
        print(f"  total: {llm.usage.summary()}")
        return

    for input_path, output_path in jobs:
        llm.usage = Usage()
        try:
            await analyze_one(input_path, output_path, llm, *run_opts)
        except Exception as exc:  # noqa: BLE001
            if args.file:
                raise
            print(f"  ✗ failed on {input_path.name}: {exc}", file=sys.stderr)
        print(f"  {llm.usage.summary()}")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
