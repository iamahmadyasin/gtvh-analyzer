"""Stage 3: KR annotation.

One LLM call per detected line, fanned out with a concurrency cap. Each call sees the line, its containing segment, and a local context window.
"""

from __future__ import annotations

import asyncio

from llm import LLMClient, load_prompt
from schemas import DetectedLine, KRAnnotation, NarrativeSegment


def _context_window(
    story_lines: list[str],
    line: DetectedLine,
    window: int = 5,
) -> str:
    start_idx = max(0, line.span.line_start - 1 - window)
    end_idx = min(len(story_lines), line.span.line_end + window)
    return "\n".join(story_lines[start_idx:end_idx])


async def annotate_line(
    line: DetectedLine,
    segment: NarrativeSegment,
    story_lines: list[str],
    llm: LLMClient,
) -> KRAnnotation:
    ctx = _context_window(story_lines, line)
    user_msg = (
        f"Containing segment:\n"
        f"- segment_id: {segment.segment_id}\n"
        f"- label: {segment.label}\n"
        f"- narrative_level: {segment.narrative_level.value}\n"
        f"- line_range: [{segment.line_start}, {segment.line_end}]\n"
        f"- terminal line of segment: {segment.line_end}\n"
        f"- description: {segment.description}\n\n"
        f"Line to annotate:\n"
        f"- line_id: {line.line_id}\n"
        f"- line_type: {line.line_type.value}\n"
        f"- span: lines {line.span.line_start}-{line.span.line_end}\n"
        f"- text: {line.span.text!r}\n"
        f"- disjunctor: {line.disjunctor!r}\n"
        f"- setup: {line.setup!r}\n"
        f"- brief_reason: {line.brief_reason!r}\n\n"
        f"Local context (surrounding lines with global numbers):\n"
        f"{ctx}\n\n"
        f"Produce the full KR annotation for this line. Use line_id "
        f"{line.line_id!r} exactly."
    )
    return await llm.call_structured(
        system_prompt=load_prompt("annotate_krs"),
        user_message=user_msg,
        response_model=KRAnnotation,
    )


async def annotate_all_lines(
    lines: list[DetectedLine],
    segments: list[NarrativeSegment],
    story_lines: list[str],
    llm: LLMClient,
    concurrency: int = 10,
) -> list[KRAnnotation]:
    seg_by_id = {s.segment_id: s for s in segments}
    sem = asyncio.Semaphore(concurrency)

    async def _one(line: DetectedLine) -> KRAnnotation:
        async with sem:
            segment = seg_by_id.get(line.segment_id)
            if segment is None:
                # Fall back to the first segment; shouldn't happen if detection is well-behaved
                segment = segments[0]
            return await annotate_line(line, segment, story_lines, llm)

    return await asyncio.gather(*[_one(l) for l in lines])
