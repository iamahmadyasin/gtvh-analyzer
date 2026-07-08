from __future__ import annotations

from llm import LLMClient
from schemas import (
    AnnotatedLine,
    Analysis,
    DetectedLine,
    KRAnnotation,
    NarrativeSegment,
)
from stages.segment import segment_narrative
from stages.detect import detect_all_lines
from stages.annotate import annotate_all_lines


def number_lines(text: str) -> str:
    return "\n".join(
        f"Line {i + 1}: {line}" for i, line in enumerate(text.splitlines())
    )


def assemble(
    segments: list[NarrativeSegment],
    detected: list[DetectedLine],
    annotations: list[KRAnnotation],
    filename: str,
) -> Analysis:
    annot_by_id = {a.line_id: a for a in annotations}
    lines: list[AnnotatedLine] = []
    for d in detected:
        annot = annot_by_id.get(d.line_id)
        if annot is None:
            continue
        lines.append(
            AnnotatedLine(
                line_id=d.line_id,
                span=d.span,
                segment_id=d.segment_id,
                line_type=d.line_type,
                disjunctor=d.disjunctor,
                disjunctor_span=d.disjunctor_span,
                annotation=annot,
            )
        )
    return Analysis(source_filename=filename, segments=segments, lines=lines)


async def analyze(
    story_text: str,
    filename: str,
    llm: LLMClient,
    detect_concurrency: int = 5,
    annotate_concurrency: int = 10,
) -> Analysis:
    numbered = number_lines(story_text)
    story_lines = numbered.splitlines()

    segments = await segment_narrative(numbered, llm)

    detected = await detect_all_lines(
        story_lines, segments, llm, concurrency=detect_concurrency
    )

    annotations = await annotate_all_lines(
        detected, segments, story_lines, llm, concurrency=annotate_concurrency
    )

    return assemble(segments, detected, annotations, filename)
