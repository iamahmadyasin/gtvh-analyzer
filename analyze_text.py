"""
Text-level stage, run on saved analyses (no need to re-run the per-line
pipeline).

    python analyze_text.py --model gpt-5.6-luna            # every output/*.json
    python analyze_text.py --json output/story.json --no-interpret

For each analysis it computes the deterministic metrics (textlevel.py),
then, unless --no-interpret, makes one interpretive call per story
(stages/interpret.py). Results go to output/text_level/<story>.json, which
make_report.py turns into the Strands, Distribution and Plot sheets.

If the story's report workbook exists (output/<story>.xlsx), corrected
Canonical Target / Canonical Situation values in it are used.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import fields
from pathlib import Path

from schemas import TextLevelReport
from stages.interpret import interpret_story
from textlevel import TextLevelParams, compute_metrics, load_analysis

ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
TEXT_LEVEL_DIR = OUTPUT_DIR / "text_level"
CHECKPOINT_DIR = OUTPUT_DIR / ".checkpoints"


def _add_param_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group(
        "text-level parameters (Attardo gives no numeric thresholds; these are "
        "documented defaults, recorded in every output file)")
    for f in fields(TextLevelParams):
        group.add_argument(
            f"--{f.name.replace('_', '-')}", dest=f.name, type=type(f.default),
            default=f.default, help=f"{f.metadata['help']} (default: {f.default})")


async def _run(args, params: TextLevelParams) -> int:
    llm = None
    if not args.no_interpret:
        from llm import LLMClient
        # GPT-5.6 models reject a temperature parameter: never send one.
        llm = LLMClient(model=args.model, temperature=None,
                        checkpoint_dir=CHECKPOINT_DIR, fresh=args.fresh)

    jobs = [args.json] if args.json else sorted(OUTPUT_DIR.glob("*.json"))
    if not jobs:
        print(f"No analysis JSON in {OUTPUT_DIR}. Run cli.py first.")
        return 1
    failures = 0
    for json_path in jobs:  # one story at a time: low tokens-per-minute limit
        print(f"→ Text-level analysis of {json_path.name}")
        try:
            analysis, raw = load_analysis(json_path)
            story_path = args.story or (INPUT_DIR / analysis.source_filename)
            if not story_path.exists():
                raise FileNotFoundError(f"story text not found: {story_path} (use --story)")
            review = None
            if not args.no_review:
                review = args.review or json_path.with_suffix(".xlsx")
                review = review if review.exists() else None
            metrics = compute_metrics(
                analysis, story_path.read_text(encoding="utf-8"), params,
                analysis_json=raw, review_path=review)
            report = TextLevelReport(metrics=metrics)
            if llm is not None:
                report.interpretation, report.citation_warnings = await interpret_story(
                    metrics, analysis.segments, llm, max_strands=args.max_strands)
                report.interpretation_model = args.model
            out = args.out or (TEXT_LEVEL_DIR / f"{json_path.stem}.json")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(report.model_dump_json(indent=2), encoding="utf-8")

            d = metrics.distribution
            print(f"  wrote {out}")
            print(f"  words={d.n_words} lines={d.n_lines} words/line={d.words_per_line} "
                  f"strands={len(metrics.strands)} combs={len(metrics.combs)} "
                  f"bridges={len(metrics.bridges)} waves={len(d.waves)} "
                  f"reliefs={len(d.serious_reliefs)}"
                  + (f" reviewer_overrides={metrics.reviewer_overrides}" if review else ""))
            for t in d.tests:
                print(f"  {t.null_hypothesis} null: {t.conclusion}")
            if report.interpretation is not None:
                print(f"  plot type: {report.interpretation.plot_type.value} "
                      f"({report.interpretation.plot_type_confidence.value})")
            for w in report.citation_warnings:
                print(f"  ! citation: {w}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ✗ failed on {json_path.name}: {exc}", file=sys.stderr)
            if args.json:
                raise
    if llm is not None:
        print(f"  {llm.usage.summary()}")
    return 1 if failures else 0


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Text-level GTVH analysis (distribution, strands, combs, "
                    "bridges, plot type) of saved analysis JSONs.")
    parser.add_argument("--json", type=Path, help="One analysis JSON (default: every JSON in output/).")
    parser.add_argument("--story", type=Path, help="Story text, if not input/<source_filename>.")
    parser.add_argument("--review", type=Path,
                        help="Report workbook with reviewer corrections (default: the JSON's .xlsx, if present).")
    parser.add_argument("--no-review", action="store_true",
                        help="Ignore reviewer corrections in the workbook.")
    parser.add_argument("--out", type=Path, help="Output path when using --json "
                        "(default: output/text_level/<story>.json).")
    parser.add_argument("--model", help="OpenAI model for the interpretive call. "
                        "Required unless --no-interpret.")
    parser.add_argument("--no-interpret", action="store_true",
                        help="Deterministic metrics only; no API call.")
    parser.add_argument("--max-strands", type=int, default=20,
                        help="Largest strands shown to the interpretive call (default: 20).")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore the saved checkpoint for the interpretive call.")
    _add_param_flags(parser)
    args = parser.parse_args()

    if not args.no_interpret and not args.model:
        parser.error("--model is required unless --no-interpret is given")
    if args.json and not args.json.exists():
        parser.error(f"file not found: {args.json}")
    try:
        params = TextLevelParams(**{f.name: getattr(args, f.name) for f in fields(TextLevelParams)})
    except ValueError as exc:
        parser.error(str(exc))
    sys.exit(asyncio.run(_run(args, params)))


if __name__ == "__main__":
    main()
