"""Stage 1: narrative segmentation."""

from __future__ import annotations

from llm import LLMClient
from promptlib import load_prompt
from schemas import NarrativeSegment, SegmentationResult


async def segment_narrative(
    story_text_numbered: str,
    llm: LLMClient,
) -> list[NarrativeSegment]:
    prompt = load_prompt("segment")
    result = await llm.call_structured(
        system_prompt=prompt.system,
        user_message=prompt.render("task", story=story_text_numbered),
        response_model=SegmentationResult,
    )
    return result.segments
