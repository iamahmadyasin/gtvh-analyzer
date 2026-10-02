"""Stage 3: KR annotation.

One LLM call per detected line, fanned out with a concurrency cap. Each call sees the line
and its containing segment, the story's target inventory, and either the full story or a
local window of surrounding lines plus a "story so far" built from the Stage 1 segment
descriptions. The story and the inventory are the same in every call for a story, so they
come first and are served from the prompt cache after the first call.
"""

from __future__ import annotations

from llm import LLMClient
from promptlib import load_prompt
from schemas import DetectedLine, KRAnnotation, NarrativeSegment, TargetEntry
from stages.inventory import format_inventory


def _context_window(
    story_lines: list[str],
    line: DetectedLine,
    window: int = 5,
) -> str:
    start_idx = max(0, line.span.line_start - 1 - window)
    end_idx = min(len(story_lines), line.span.line_end + window)
    return "\n".join(story_lines[start_idx:end_idx])


def story_so_far(segment: NarrativeSegment, segments: list[NarrativeSegment]) -> str:
    """Summaries of every segment that starts before this one (including the
    segments it is embedded in), in story order. Free longer-range context
    for local mode: no extra model call, just the Stage 1 descriptions."""
    earlier = sorted(
        (s for s in segments
         if s.segment_id != segment.segment_id and s.line_start <= segment.line_start),
        key=lambda s: (s.line_start, -s.line_end),
    )
    if not earlier:
        return "(this is the first segment)"
    return "\n".join(
        f"- {s.segment_id} ({s.narrative_level.value}) {s.label}: {s.description}"
        for s in earlier
    )


async def annotate_line(
    line: DetectedLine,
    segment: NarrativeSegment,
    segments: list[NarrativeSegment],
    story_lines: list[str],
    llm: LLMClient,
    full_story: str | None,
    inventory: list[TargetEntry],
) -> KRAnnotation:
    prompt = load_prompt("annotate_krs")
    local_context = "" if full_story is not None else prompt.render(
        "local_context",
        story_so_far=story_so_far(segment, segments),
        window=_context_window(story_lines, line),
    )
    task = prompt.render(
        "task",
        segment_id=segment.segment_id,
        label=segment.label,
        narrative_level=segment.narrative_level.value,
        line_start=segment.line_start,
        line_end=segment.line_end,
        description=segment.description,
        line_id=line.line_id,
        line_type=line.line_type.value,
        span_start=line.span.line_start,
        span_end=line.span.line_end,
        text=line.span.text,
        disjunctor=line.disjunctor,
        setup=line.setup,
        brief_reason=line.brief_reason,
        local_context=local_context,
    )
    # Shared parts first (story, inventory), call-specific part last.
    messages = [prompt.render("inventory", entries=format_inventory(inventory)), task]
    if full_story is not None:
        messages.insert(0, prompt.render("story_context", story=full_story))
    annotation = await llm.call_structured(
        system_prompt=prompt.system,
        user_message=messages,
        response_model=KRAnnotation,
    )
    # Assembly matches annotations to lines by id; don't trust the echo.
    annotation.line_id = line.line_id
    if annotation.target_id is not None and annotation.target_id not in {
        e.target_id for e in inventory
    }:
        annotation.target_id = None  # not an inventory id: treat as a new target
    return annotation


async def annotate_all_lines(
    lines: list[DetectedLine],
    segments: list[NarrativeSegment],
    story_lines: list[str],
    llm: LLMClient,
    concurrency: int = 10,
    full_story: str | None = None,
    inventory: list[TargetEntry] | None = None,
) -> list[KRAnnotation]:
    seg_by_id = {s.segment_id: s for s in segments}

    async def _one(line: DetectedLine) -> KRAnnotation:
        # detect.py stamps segment_id, so this lookup always succeeds
        segment = seg_by_id[line.segment_id]
        return await annotate_line(
            line, segment, segments, story_lines, llm, full_story, inventory or []
        )

    return await llm.map(lines, _one, concurrency)
