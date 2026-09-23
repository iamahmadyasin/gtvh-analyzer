"""Stage 3: KR annotation.

One LLM call per detected line, fanned out with a concurrency cap. Each call sees the line and its containing segment, plus either the full story (the same first message in every call, so it is served from the prompt cache after the first call) or a local window of surrounding lines.
"""

from __future__ import annotations

from llm import LLMClient, load_prompt, run_all
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
    story_context: str | None,
) -> KRAnnotation:
    if story_context is not None:
        context = ""
    else:
        context = (
            f"Local context (surrounding lines with global numbers):\n"
            f"{_context_window(story_lines, line)}\n\n"
        )
    task = (
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
        f"{context}"
        f"Produce the full KR annotation for this line. Use line_id "
        f"{line.line_id!r} exactly."
    )
    annotation = await llm.call_structured(
        system_prompt=load_prompt("annotate_krs"),
        user_message=[story_context, task] if story_context is not None else task,
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
    story_context: str | None = None,
) -> list[KRAnnotation]:
    seg_by_id = {s.segment_id: s for s in segments}

    async def _one(line: DetectedLine) -> KRAnnotation:
        # detect.py stamps segment_id, so this lookup always succeeds
        segment = seg_by_id[line.segment_id]
        return await annotate_line(line, segment, story_lines, llm, story_context)

    return await run_all(lines, _one, concurrency)
