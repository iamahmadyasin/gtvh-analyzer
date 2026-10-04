"""
Stage 1 · Segmentation
Splits the story into narrative segments with their levels and line ranges.

Reads:   the numbered story
Writes:  a list of NarrativeSegment
"""

from __future__ import annotations

from llm_base import BaseLLMClient
from promptlib import load_prompt
from schemas import NarrativeSegment, SegmentationResult


async def segment_narrative(
    story_text_numbered: str,
    llm: BaseLLMClient,
) -> list[NarrativeSegment]:
    prompt = load_prompt("segment")
    result = await llm.call_structured(
        system_prompt=prompt.system,
        user_message=prompt.render("task", story=story_text_numbered),
        response_model=SegmentationResult,
    )
    return result.segments
