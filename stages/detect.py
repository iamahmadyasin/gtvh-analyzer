"""Stage 2: humorous instance detection.

One LLM call per segment, fanned out with a concurrency cap. With the
full story, every call starts with the same numbered story text
(served from the prompt cache after the first call) and names the lines
to analyze; without one, each call gets only its segment's text.

Embedded segments (level_-1, level_-2) sit inside their parent's line
range, so every story line is assigned to the innermost segment that
contains it. Each segment is sent only the lines it owns; otherwise the
lines of an embedded letter or speech would be detected (and annotated)
twice: once with the parent and once on their own.
"""

from __future__ import annotations

from llm import LLMClient, run_all
from promptlib import Prompt, load_prompt
from schemas import DetectedLine, DetectionResult, NarrativeSegment


def assign_line_owners(
    segments: list[NarrativeSegment], n_lines: int
) -> dict[str, list[int]]:
    """Map segment_id -> the 1-based line numbers it owns.

    A line belongs to the smallest segment whose range contains it (ties
    go to the later segment, which is the more deeply nested one when the
    model lists parents first). Lines no segment covers are left out.
    """
    owned: dict[str, list[int]] = {s.segment_id: [] for s in segments}
    for line_no in range(1, n_lines + 1):
        best: NarrativeSegment | None = None
        for seg in segments:
            if seg.line_start <= line_no <= seg.line_end:
                if best is None or (
                    seg.line_end - seg.line_start <= best.line_end - best.line_start
                ):
                    best = seg
        if best is not None:
            owned[best.segment_id].append(line_no)
    return owned


def _ranges(line_numbers: list[int]) -> str:
    """[1, 2, 3, 7, 8] -> "1-3, 7-8"."""
    runs: list[list[int]] = []
    for n in line_numbers:
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in runs)


def _segment_text(prompt: Prompt, story_lines: list[str], owned: list[int]) -> str:
    """The numbered lines a segment owns, with a marker where lines were
    handed to an embedded segment."""
    parts: list[str] = []
    prev: int | None = None
    for line_no in owned:
        if prev is not None and line_no != prev + 1:
            parts.append(prompt.render(
                "embedded_marker", start=prev + 1, end=line_no - 1
            ).rstrip("\n"))
        parts.append(story_lines[line_no - 1])
        prev = line_no
    return "\n".join(parts)


async def detect_lines_in_segment(
    story_lines: list[str],
    segment: NarrativeSegment,
    owned: list[int],
    llm: LLMClient,
    full_story: str | None,
) -> list[DetectedLine]:
    prompt = load_prompt("detect_lines")
    segment_info = prompt.render(
        "segment_info",
        segment_id=segment.segment_id,
        label=segment.label,
        narrative_level=segment.narrative_level.value,
        line_start=segment.line_start,
        line_end=segment.line_end,
        description=segment.description,
    )
    owned_set = set(owned)
    if full_story is not None:
        handed_off = [
            n for n in range(segment.line_start, segment.line_end + 1)
            if n not in owned_set
        ]
        note = (
            prompt.render("handed_off_note", handed_off=_ranges(handed_off))
            if handed_off else ""
        )
        messages = [
            prompt.render("story_context", story=full_story),
            prompt.render(
                "task_story",
                segment_info=segment_info,
                lines_to_analyze=_ranges(owned),
                handed_off_note=note,
            ),
        ]
    else:
        messages = [prompt.render(
            "task_local",
            segment_info=segment_info,
            segment_text=_segment_text(prompt, story_lines, owned),
        )]
    result = await llm.call_structured(
        system_prompt=prompt.system,
        user_message=messages,
        response_model=DetectionResult,
    )

    kept: list[DetectedLine] = []
    for line in result.lines:
        # The rest of the pipeline looks segments up by this id; don't
        # trust the model to echo it back correctly.
        line.segment_id = segment.segment_id
        if line.span.line_start not in owned_set:
            print(
                f"    dropped detection outside {segment.segment_id}: "
                f"lines {line.span.line_start}-{line.span.line_end}"
            )
            continue
        kept.append(line)
    return kept


async def detect_all_lines(
    story_lines: list[str],
    segments: list[NarrativeSegment],
    llm: LLMClient,
    concurrency: int = 5,
    full_story: str | None = None,
) -> list[DetectedLine]:
    owners = assign_line_owners(segments, len(story_lines))
    uncovered = len(story_lines) - sum(len(v) for v in owners.values())
    if uncovered:
        print(f"    warning: {uncovered} line(s) fall outside every segment")

    async def _one(seg: NarrativeSegment) -> list[DetectedLine]:
        return await detect_lines_in_segment(
            story_lines, seg, owners[seg.segment_id], llm, full_story
        )

    active = [s for s in segments if owners[s.segment_id]]
    per_segment = await run_all(active, _one, concurrency)

    all_lines: list[DetectedLine] = []
    seen: set[tuple[int, int, str]] = set()
    for line in (line for chunk in per_segment for line in chunk):
        key = (line.span.line_start, line.span.line_end, line.span.text)
        if key in seen:
            continue
        seen.add(key)
        all_lines.append(line)

    # Renumber globally so IDs are unique across the whole story
    for i, line in enumerate(all_lines, start=1):
        line.line_id = f"HL-{i:03d}"

    return all_lines
