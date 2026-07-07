"""Stage 1 — narrative segmentation."""

from __future__ import annotations

from llm import LLMClient, load_prompt
from schemas import NarrativeSegment, SegmentationResult


async def segment_narrative(
    story_text_numbered: str,
    llm: LLMClient,
) -> list[NarrativeSegment]:
    """Partition a line-numbered story into narrative segments."""
    result = await llm.call_structured(
        system_prompt=load_prompt("segment"),
        user_message=story_text_numbered,
        response_model=SegmentationResult,
    )
    return result.segments
