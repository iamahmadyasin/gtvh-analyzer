"""
Pipeline · Stages 1 to 3
Segmentation, target inventory, detection, annotation and normalization for one
story.

Reads:   the story text
Writes:  an Analysis, saved by cli.py as output/<story>.json
"""

from __future__ import annotations

import asyncio

from llm_base import BaseLLMClient
from normalize import NormalizationParams, normalize_analysis
from schemas import (
    AnnotatedLine,
    Analysis,
    DetectedLine,
    KRAnnotation,
    NarrativeSegment,
    TargetEntry,
)
from stages.segment import segment_narrative
from stages.detect import detect_all_lines
from stages.annotate import annotate_all_lines
from stages.inventory import build_inventory
from textutils import number_lines


def assemble(
    segments: list[NarrativeSegment],
    detected: list[DetectedLine],
    annotations: list[KRAnnotation],
    filename: str,
    inventory: list[TargetEntry],
) -> Analysis:
    annot_by_id = {a.line_id: a for a in annotations}
    lines: list[AnnotatedLine] = []
    for d in detected:
        annot = annot_by_id[d.line_id]
        lines.append(
            AnnotatedLine(
                line_id=d.line_id,
                span=d.span,
                segment_id=d.segment_id,
                line_type=d.line_type,
                disjunctor=d.disjunctor,
                disjunctor_span=d.disjunctor_span,
                confidence=d.confidence,
                setup=d.setup,
                brief_reason=d.brief_reason,
                annotation=annot,
            )
        )
    return Analysis(
        source_filename=filename, segments=segments, lines=lines,
        target_inventory=inventory,
    )


async def analyze(
    story_text: str,
    filename: str,
    llm: BaseLLMClient,
    detect_concurrency: int = 5,
    annotate_concurrency: int = 10,
    context: str = "story",
    normalization: NormalizationParams = NormalizationParams(),
    embedding_model: str = "text-embedding-3-small",
) -> Analysis:
    """`context="story"` sends stages 2 and 3 the full story as a cached shared
    prefix; `"local"` sends only the nearby text, which costs fewer tokens but
    gives less context."""
    numbered = number_lines(story_text)
    story_lines = numbered.splitlines()
    full_story = numbered if context == "story" else None

    # Independent of each other, so they run together (and share one
    # batch in --batch mode).
    segments, inventory = await asyncio.gather(
        segment_narrative(numbered, llm), build_inventory(numbered, llm)
    )

    detected = await detect_all_lines(
        story_lines, segments, llm, concurrency=detect_concurrency,
        full_story=full_story,
    )

    annotations = await annotate_all_lines(
        detected, segments, story_lines, llm, concurrency=annotate_concurrency,
        full_story=full_story, inventory=inventory,
    )

    analysis = assemble(segments, detected, annotations, filename, inventory)

    async def embed(texts):
        return await llm.embed(texts, model=embedding_model)

    await normalize_analysis(analysis, normalization, embed)
    return analysis