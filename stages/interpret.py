"""
Stage 4b · Interpretation
One model call per story: plot type, central complication, pattern findings and
readings.

Reads:   the text-level metrics and segment descriptions, never the per-line
         annotations
Writes:  a PlotInterpretation, plus a warning for every cited id that doesn't
         exist
"""

from __future__ import annotations

import json

from llm_base import BaseLLMClient
from promptlib import load_prompt
from schemas import (
    EvidenceKind,
    NarrativeSegment,
    PlotInterpretation,
    TextLevelMetrics,
)


def _indicators(metrics: TextLevelMetrics) -> dict:
    pi = metrics.plot_indicators
    position = {lf.line_id: lf.position for lf in metrics.lines}
    return {
        "final_punch_lines": len(pi.final_punch_line_ids),
        "final_punch_positions": [position[x] for x in pi.final_punch_line_ids],
        "metanarrative_lines": pi.n_metanarrative_lines,
        "metanarrative_share": pi.metanarrative_share,
        "framing_segments": pi.n_framing_segments,
    }


def build_aggregates(
    metrics: TextLevelMetrics,
    segments: list[NarrativeSegment],
    max_strands: int = 20,
    max_combs: int = 10,
    max_bridges: int = 10,
) -> dict:
    d = metrics.distribution
    density = {c.group: c for c in metrics.jab_punch.by_segment}
    return {
        "story": {
            "words": d.n_words, "humorous_lines": d.n_lines,
            "words_per_line": d.words_per_line, "n_sections": d.n_sections,
        },
        "sections": [
            {"section": s.index, "words": f"{s.word_start}-{s.word_end}",
             "lines": s.n_lines, "words_per_line": s.words_per_line}
            for s in d.sections
        ],
        "distribution_tests": [
            {"null": t.null_hypothesis, "statistic": t.statistic_name, "value": t.statistic,
             "expected_if_null": t.expected_under_null, "p_greater": t.p_value_greater,
             "p_less": t.p_value_less, "conclusion": t.conclusion}
            for t in d.tests
        ],
        "waves": [w.model_dump() for w in d.waves],
        "serious_reliefs": [r.model_dump() for r in d.serious_reliefs],
        "strands_total": len(metrics.strands),
        "strands": [
            {"id": s.strand_id, "key": s.key, "same_lines_as": s.equivalent_keys,
             "lines": s.n_lines, "share": s.share,
             "centrality": s.centrality, "span": s.span_fraction,
             "first": s.first_position, "last": s.last_position,
             "combs": s.comb_ids, "bridges": s.bridge_ids}
            for s in metrics.strands[:max_strands]
        ],
        "combs": [
            {"id": c.comb_id, "strand": c.strand_id, "lines": len(c.line_ids),
             "words": f"{c.word_start}-{c.word_end}", "words_per_line": c.words_per_line}
            for c in sorted(metrics.combs, key=lambda c: -len(c.line_ids))[:max_combs]
        ],
        "bridges": [
            {"id": b.bridge_id, "strand": b.strand_id, "gap_words": b.gap_words,
             "gap_fraction": b.gap_fraction}
            for b in sorted(metrics.bridges, key=lambda b: -b.gap_fraction)[:max_bridges]
        ],
        "jab_punch": {
            "overall": {"jab": metrics.jab_punch.n_jab, "punch": metrics.jab_punch.n_punch},
            "by_level": [c.model_dump(exclude_none=True) for c in metrics.jab_punch.by_level],
        },
        "plot_indicators": _indicators(metrics),
        "segments": [
            {"id": s.segment_id, "label": s.label, "level": s.narrative_level.value,
             "lines": f"{s.line_start}-{s.line_end}", "parent": s.parent_segment_id,
             "description": s.description,
             "humorous_lines": density[s.segment_id].n_lines if s.segment_id in density else 0,
             "jab": density[s.segment_id].n_jab if s.segment_id in density else 0,
             "punch": density[s.segment_id].n_punch if s.segment_id in density else 0,
             "words_per_line": density[s.segment_id].words_per_line if s.segment_id in density else None}
            for s in segments
        ],
    }


def _valid_refs(aggregates: dict, metrics: TextLevelMetrics) -> dict[EvidenceKind, set[str]]:
    seg_ids = {s["id"] for s in aggregates["segments"]}
    return {
        # Every strand, comb, and bridge in the metrics is a real id, even
        # those beyond the top N shown to the model.
        EvidenceKind.STRAND: {s.strand_id for s in metrics.strands},
        EvidenceKind.COMB: {c.comb_id for c in metrics.combs},
        EvidenceKind.BRIDGE: {b.bridge_id for b in metrics.bridges},
        EvidenceKind.WAVE: {w["stretch_id"] for w in aggregates["waves"]},
        EvidenceKind.SERIOUS_RELIEF: {r["stretch_id"] for r in aggregates["serious_reliefs"]},
        EvidenceKind.DISTRIBUTION_TEST: {"uniform", "random"},
        EvidenceKind.SEGMENT: seg_ids,
        EvidenceKind.JAB_PUNCH: seg_ids | {"overall"} | {c["group"] for c in aggregates["jab_punch"]["by_level"]},
        EvidenceKind.PLOT_INDICATOR: set(aggregates["plot_indicators"]),
    }


def check_citations(result: PlotInterpretation, aggregates: dict, metrics: TextLevelMetrics) -> list[str]:
    valid = _valid_refs(aggregates, metrics)
    warnings = []
    cited = [("plot_type_evidence", e) for e in result.plot_type_evidence]
    cited += [("central_complication", e) for e in result.central_complication.evidence]
    for f in result.pattern_findings:
        cited += [(f.finding_id, e) for e in f.evidence]
    for where, e in cited:
        if e.ref_id not in valid[e.kind]:
            warnings.append(f"{where}: {e.kind.value} {e.ref_id!r} is not in the aggregates")
    finding_ids = {f.finding_id for f in result.pattern_findings}
    for r in result.readings:
        for fid in r.based_on:
            if fid not in finding_ids:
                warnings.append(f"reading rests on unknown finding {fid!r}")
    seg_ids = valid[EvidenceKind.SEGMENT]
    for sid in result.central_complication.segment_ids:
        if sid not in seg_ids:
            warnings.append(f"central_complication: unknown segment {sid!r}")
    return warnings


async def interpret_story(
    metrics: TextLevelMetrics,
    segments: list[NarrativeSegment],
    llm: BaseLLMClient,
    max_strands: int = 20,
) -> tuple[PlotInterpretation, list[str]]:
    prompt = load_prompt("interpret_plot")
    aggregates = build_aggregates(metrics, segments, max_strands=max_strands)
    result = await llm.call_structured(
        system_prompt=prompt.system,
        user_message=prompt.render(
            "task", story_id=metrics.story_id,
            aggregates=json.dumps(aggregates, ensure_ascii=False, indent=1),
        ),
        response_model=PlotInterpretation,
    )
    return result, check_citations(result, aggregates, metrics)
