"""Stage 3: KR annotation.

One LLM call per detected line, fanned out with a concurrency cap. Each call sees the line and its containing segment, plus either the full story (the same first message in every call, so it is served from the prompt cache after the first call) or a local window of surrounding lines.
"""

from __future__ import annotations

from llm import LLMClient, run_all
from promptlib import load_prompt
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
    full_story: str | None,
) -> KRAnnotation:
    prompt = load_prompt("annotate_krs")
    local_context = "" if full_story is not None else prompt.render(
        "local_context", window=_context_window(story_lines, line)
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
    messages = [task] if full_story is None else [
        prompt.render("story_context", story=full_story), task
    ]
    annotation = await llm.call_structured(
        system_prompt=prompt.system,
        user_message=messages,
        response_model=KRAnnotation,
    )
    # Assembly matches annotations to lines by id; don't trust the echo.
    annotation.line_id = line.line_id
    return annotation


async def annotate_all_lines(
    lines: list[DetectedLine],
    segments: list[NarrativeSegment],
    story_lines: list[str],
    llm: LLMClient,
    concurrency: int = 10,
    full_story: str | None = None,
) -> list[KRAnnotation]:
    seg_by_id = {s.segment_id: s for s in segments}

    async def _one(line: DetectedLine) -> KRAnnotation:
        # detect.py stamps segment_id, so this lookup always succeeds
        segment = seg_by_id[line.segment_id]
        return await annotate_line(line, segment, story_lines, llm, full_story)

    return await run_all(lines, _one, concurrency)
