"""Stage 2 — humorous line detection.

One LLM call per segment, fanned out with a concurrency cap.
"""

from __future__ import annotations

import asyncio

from llm import LLMClient, load_prompt
from schemas import DetectedLine, DetectionResult, NarrativeSegment


def _segment_text(story_lines: list[str], seg: NarrativeSegment) -> str:
    """Extract the numbered lines belonging to a segment."""
    # story_lines is already numbered ("Line N: ..."); slice by 1-based inclusive range
    start_idx = seg.line_start - 1
    end_idx = seg.line_end
    return "\n".join(story_lines[start_idx:end_idx])


async def detect_lines_in_segment(
    story_lines: list[str],
    segment: NarrativeSegment,
    llm: LLMClient,
) -> list[DetectedLine]:
    """Detect humorous lines in one segment."""
    segment_text = _segment_text(story_lines, segment)
    user_msg = (
        f"Segment info:\n"
        f"- segment_id: {segment.segment_id}\n"
        f"- label: {segment.label}\n"
        f"- narrative_level: {segment.narrative_level.value}\n"
        f"- line_range: [{segment.line_start}, {segment.line_end}]\n"
        f"- description: {segment.description}\n\n"
        f"Segment text (with global line numbers):\n"
        f"{segment_text}\n\n"
        f"Detect humorous lines in this segment. Use the segment_id above "
        f"in every detected line. Use the global line numbers shown."
    )
    result = await llm.call_structured(
        system_prompt=load_prompt("detect_lines"),
        user_message=user_msg,
        response_model=DetectionResult,
    )
    return result.lines


async def detect_all_lines(
    story_lines: list[str],
    segments: list[NarrativeSegment],
    llm: LLMClient,
    concurrency: int = 5,
) -> list[DetectedLine]:
    """Detect lines across all segments concurrently, then re-number IDs globally."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(seg: NarrativeSegment) -> list[DetectedLine]:
        async with sem:
            return await detect_lines_in_segment(story_lines, seg, llm)

    per_segment = await asyncio.gather(*[_one(s) for s in segments])
    all_lines: list[DetectedLine] = [line for chunk in per_segment for line in chunk]

    # Renumber globally so IDs are unique across the whole story
    for i, line in enumerate(all_lines, start=1):
        line.line_id = f"HL-{i:03d}"

    return all_lines
