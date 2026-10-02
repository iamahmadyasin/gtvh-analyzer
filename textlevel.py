"""
Stage 4a: text-level analysis of one story (deterministic, no API calls).

Turns a saved analysis JSON into the text-level findings of Attardo's
expanded GTVH for longer texts (Humorous Texts, 2001; "Cognitive
stylistics of humorous texts"):

- distribution: the text cut into equal word-count sections, lines per
  section, words-per-line ratios, tests against random and uniform
  placement, peaks ("waves") and serious-relief stretches;
- strands: sets of lines sharing a value on one KR feature or a pair of
  them, classified central / intermediate / peripheral;
- combs and bridges within each strand;
- jab/punch counts by segment and narrative level, plus a few plot
  indicators for the interpretive call.

Attardo gives no numeric thresholds, so every threshold is a field of
TextLevelParams with its rationale, and the values used are written into
the output next to the results.

The output (schemas.TextLevelMetrics) is the per-story record a later
corpus stage will read for stacks and baselines: strand keys are stable
"feature=value" strings, per-line features are included, and the analysis
and story hashes identify exactly what was measured.
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field, fields
from itertools import combinations
from pathlib import Path
from typing import Optional

from normalize import (
    SITUATION_SENTINELS,
    NormalizationParams,
    clean_label,
    label_key,
    normalize_offline,
)
from review_workbook import matching, read_review
from schemas import (
    Analysis,
    AnnotatedLine,
    Bridge,
    Comb,
    Distribution,
    DistributionTest,
    JabPunchCount,
    JabPunchSummary,
    LineFeatures,
    NarrativeStrategy,
    PlotIndicators,
    SectionStat,
    Strand,
    StrandFeature,
    Stretch,
    TargetEntry,
    TextLevelMetrics,
)

SCHEMA_VERSION = "1.0"


def _param(default, help: str):
    return field(default=default, metadata={"help": help})


@dataclass(frozen=True)
class TextLevelParams:
    # Distribution
    n_sections: int = _param(
        20, "Number of equal word-count sections the text is cut into. Attardo "
            "used 100-word sections for a ~12,800-word story; for short stories "
            "a fixed count keeps sections comparable across texts.")
    n_simulations: int = _param(
        5000, "Monte Carlo draws used for the distribution tests' p-values.")
    seed: int = _param(0, "Random seed for the Monte Carlo draws (results are reproducible).")
    alpha: float = _param(0.05, "Significance level used to word the test conclusions.")
    wave_min_ratio: float = _param(
        1.5, "A section belongs to a wave (peak) if it has at least this many "
             "times the mean lines per section.")
    wave_min_lines: int = _param(3, "A wave must contain at least this many lines in total.")
    relief_max_ratio: float = _param(
        0.25, "A section belongs to a serious-relief stretch if it has at most "
              "this many times the mean lines per section.")
    relief_min_fraction: float = _param(
        0.10, "A serious-relief stretch must cover at least this fraction of the "
              "text (Attardo's example was ~1,000 of ~12,800 words).")
    # Strands
    min_strand_lines: int = _param(3, "A strand needs at least this many lines.")
    strand_pairs: str = _param(
        "cross_kr", "Pairwise strands: 'none', 'cross_kr' (every pair of features "
                    "from different KRs), or a comma list such as "
                    "'target+opposition_type,target_social_class+so_binary_category'.")
    central_min_span: float = _param(
        0.60, "A strand is central if its first and last lines are at least this "
              "fraction of the text apart (it 'occurs through most of a text').")
    peripheral_max_span: float = _param(
        0.30, "A strand is peripheral if it is confined to at most this fraction "
              "of the text. Strands in between are reported as intermediate.")
    # Combs and bridges
    comb_min_lines: int = _param(3, "A comb needs at least this many lines of one strand.")
    comb_max_gap: float = _param(
        0.03, "Consecutive lines of a comb are at most this fraction of the text apart.")
    bridge_min_gap: float = _param(
        0.25, "Two consecutive lines of a strand at least this fraction of the "
              "text apart form a bridge.")
    # Plot indicators
    final_punch_window: float = _param(
        0.05, "A punch line ending within this final fraction of the text counts "
              "as a final punch line (a hint of a 'humorous plot with punch line').")

    def __post_init__(self):
        if self.n_sections < 1:
            raise ValueError("n_sections must be at least 1")
        if self.peripheral_max_span > self.central_min_span:
            raise ValueError("peripheral_max_span must not exceed central_min_span")


# Strand features and the KR each belongs to. Pairwise strands under
# 'cross_kr' combine features of different KRs only (target + its own
# attributes would just restate the target strand).
FEATURES: dict[str, str] = {
    "target": "TA",
    "target_kind": "TA",
    "target_social_class": "TA",
    "target_sphere": "TA",
    "orientation": "TA",
    "situation": "SI",
    "so_binary_category": "SO",
    "opposition_type": "SO",
    "narrative_strategy": "NS",
    "wordplay_level": "LA",
    "register_effect": "LA",
}

# Values that mean "nothing shared" and never form a strand.
_NO_STRAND_VALUES = {
    "situation": SITUATION_SENTINELS,
    "so_binary_category": {"none"},
    "narrative_strategy": {NarrativeStrategy.OTHER.value},
    "target_social_class": {"unknown", "not_applicable"},
}


# ---------- positions ----------

def _line_word_offsets(story_text: str) -> tuple[list[str], list[int], int]:
    lines = story_text.splitlines()
    offsets, total = [], 0
    for line in lines:
        offsets.append(total)
        total += len(line.split())
    return lines, offsets, total


def _locate(line: AnnotatedLine, lines: list[str], offsets: list[int], total: int) -> tuple[int, int]:
    """Word range of a humorous line: the quoted span text found within its
    story lines, or the whole lines if the quote can't be found."""
    n = len(lines)
    start = min(max(line.span.line_start, 1), n) if n else 1
    end = min(max(line.span.line_end, start), n) if n else 1
    if not n:
        return 0, 0
    block = "\n".join(lines[start - 1:end])
    base = offsets[start - 1]
    block_end = offsets[end] if end < n else total
    quote = " ".join(line.span.text.split())
    flat = " ".join(block.split())
    pos = flat.find(quote) if quote else -1
    if pos >= 0:
        w0 = base + len(flat[:pos].split())
        return w0, min(w0 + max(len(quote.split()), 1), block_end)
    return base, max(block_end, base + 1)


def _section_bounds(total: int, k: int) -> list[tuple[int, int]]:
    cuts = [round(i * total / k) for i in range(k + 1)]
    return [(cuts[i], cuts[i + 1]) for i in range(k)]


def _section_of(word: float, total: int, k: int) -> int:
    if total <= 0:
        return 0
    return min(int(word * k / total), k - 1)


# ---------- distribution ----------

def _chi2_uniform(counts: list[int]) -> Optional[float]:
    n = sum(counts)
    if n == 0:
        return None
    mean = n / len(counts)
    return sum((c - mean) ** 2 for c in counts) / mean


def _gap_cv(positions: list[float]) -> Optional[float]:
    if len(positions) < 3:
        return None
    gaps = [b - a for a, b in zip(positions, positions[1:])]
    mean = statistics.fmean(gaps)
    return statistics.pstdev(gaps) / mean if mean > 0 else None


def _monte_carlo(n: int, total: int, k: int, params: TextLevelParams) -> tuple[list[float], list[float]]:
    """Statistics under random placement: n lines dropped independently
    and uniformly at random over the text."""
    rng = random.Random(params.seed)
    chi2s, cvs = [], []
    for _ in range(params.n_simulations):
        pos = sorted(rng.random() * total for _ in range(n))
        counts = [0] * k
        for p in pos:
            counts[_section_of(p, total, k)] += 1
        chi2s.append(_chi2_uniform(counts))
        cv = _gap_cv(pos)
        if cv is not None:
            cvs.append(cv)
    return chi2s, cvs


def _p_values(observed: float, simulated: list[float]) -> tuple[float, float]:
    m = len(simulated)
    greater = (sum(s >= observed for s in simulated) + 1) / (m + 1)
    less = (sum(s <= observed for s in simulated) + 1) / (m + 1)
    return round(greater, 4), round(less, 4)


def _tests(counts: list[int], positions: list[float], total: int, params: TextLevelParams) -> list[DistributionTest]:
    n, k = sum(counts), len(counts)
    chi2 = _chi2_uniform(counts)
    cv = _gap_cv(positions)
    if n < 2 or total == 0:
        reason = "too few lines to test"
        return [
            DistributionTest(null_hypothesis="uniform", statistic_name="pearson_chi2_sections",
                             statistic=chi2, expected_under_null=None, p_value_greater=None,
                             p_value_less=None, n_simulations=0, conclusion=reason),
            DistributionTest(null_hypothesis="random", statistic_name="gap_coefficient_of_variation",
                             statistic=cv, expected_under_null=None, p_value_greater=None,
                             p_value_less=None, n_simulations=0, conclusion=reason),
        ]
    sim_chi2, sim_cv = _monte_carlo(n, total, k, params)
    a = params.alpha

    g, l = _p_values(chi2, sim_chi2)
    if g < a:
        uniform = (f"reject: the sections differ more than equal per-section humor "
                   f"would produce (p={g})")
    else:
        uniform = f"not rejected: section counts are compatible with an even spread (p={g})"
    tests = [DistributionTest(
        null_hypothesis="uniform", statistic_name="pearson_chi2_sections",
        statistic=round(chi2, 4), expected_under_null=float(k - 1),
        p_value_greater=g, p_value_less=l, n_simulations=params.n_simulations,
        conclusion=uniform)]

    if cv is None or not sim_cv:
        tests.append(DistributionTest(
            null_hypothesis="random", statistic_name="gap_coefficient_of_variation",
            statistic=cv, expected_under_null=None, p_value_greater=None, p_value_less=None,
            n_simulations=0, conclusion="too few lines to test"))
        return tests
    g, l = _p_values(cv, sim_cv)
    if g < a:
        random_ = f"reject: lines are more clustered than random placement (p={g})"
    elif l < a:
        random_ = f"reject: lines are more evenly spaced than random placement (p={l})"
    else:
        random_ = f"not rejected: spacing is compatible with random placement (p={min(g, l)})"
    tests.append(DistributionTest(
        null_hypothesis="random", statistic_name="gap_coefficient_of_variation",
        statistic=round(cv, 4), expected_under_null=round(statistics.fmean(sim_cv), 4),
        p_value_greater=g, p_value_less=l, n_simulations=params.n_simulations,
        conclusion=random_))
    return tests


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, flag in enumerate(flags + [False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def _ratio(words: int, n_lines: int) -> Optional[float]:
    return round(words / n_lines, 1) if n_lines else None


def _distribution(sections: list[SectionStat], positions: list[float], total: int,
                  n_lines: int, params: TextLevelParams) -> Distribution:
    counts = [s.n_lines for s in sections]
    mean = n_lines / len(sections) if sections else 0
    waves, reliefs = [], []
    if n_lines:
        for a, b in _runs([c > 0 and c >= params.wave_min_ratio * mean for c in counts]):
            lines_in = sum(counts[a:b + 1])
            if lines_in >= params.wave_min_lines:
                words = sections[b].word_end - sections[a].word_start
                waves.append(Stretch(
                    stretch_id=f"W-{len(waves) + 1}", kind="wave",
                    first_section=a + 1, last_section=b + 1,
                    word_start=sections[a].word_start, word_end=sections[b].word_end,
                    n_lines=lines_in, words_per_line=_ratio(words, lines_in)))
        for a, b in _runs([c <= params.relief_max_ratio * mean for c in counts]):
            words = sections[b].word_end - sections[a].word_start
            if total and words >= params.relief_min_fraction * total:
                lines_in = sum(counts[a:b + 1])
                reliefs.append(Stretch(
                    stretch_id=f"R-{len(reliefs) + 1}", kind="serious_relief",
                    first_section=a + 1, last_section=b + 1,
                    word_start=sections[a].word_start, word_end=sections[b].word_end,
                    n_lines=lines_in, words_per_line=_ratio(words, lines_in)))
    return Distribution(
        n_words=total, n_lines=n_lines, n_sections=len(sections),
        words_per_line=_ratio(total, n_lines), sections=sections,
        tests=_tests(counts, sorted(positions), total, params),
        waves=waves, serious_reliefs=reliefs)


# ---------- features ----------

def _entry_for(label: Optional[str], inventory: list[TargetEntry]) -> Optional[TargetEntry]:
    if not label:
        return None
    key = label_key(label)
    for entry in inventory:
        if key in {label_key(n) for n in [entry.label, *entry.aliases]}:
            return entry
    return None


def _line_features(line: AnnotatedLine, target: Optional[str], target_entry: Optional[TargetEntry],
                   situation: Optional[str]) -> dict[str, Optional[str]]:
    a = line.annotation
    feats: dict[str, Optional[str]] = {
        "target": target,
        "target_kind": target_entry.kind.value if target_entry else None,
        "target_social_class": target_entry.social_class.value if target_entry else None,
        "target_sphere": target_entry.sphere.value if target_entry else None,
        "orientation": a.orientation.value,
        "situation": situation,
        "so_binary_category": a.script_opposition.essential_binary_category.value,
        "opposition_type": a.script_opposition.opposition_type.value,
        "narrative_strategy": a.narrative_strategy.value,
        "wordplay_level": a.language.wordplay_level.value if a.language.wordplay_level else None,
        "register_effect": "yes" if a.language.is_register_effect else None,
    }
    return feats


def _strand_value(feature: str, value: Optional[str]) -> Optional[str]:
    if value is None or value in _NO_STRAND_VALUES.get(feature, set()):
        return None
    return value


def _pairs(spec: str) -> list[tuple[str, str]]:
    spec = spec.strip()
    if spec == "none":
        return []
    if spec == "cross_kr":
        return [(f, g) for f, g in combinations(FEATURES, 2) if FEATURES[f] != FEATURES[g]]
    pairs = []
    for item in spec.split(","):
        f, _, g = item.strip().partition("+")
        if f not in FEATURES or g not in FEATURES or f == g:
            raise ValueError(f"unknown strand pair {item!r}; features: {', '.join(FEATURES)}")
        pairs.append(tuple(sorted((f, g), key=list(FEATURES).index)))
    return pairs


# ---------- strands, combs, bridges ----------

def _strands(line_feats: list[LineFeatures], total: int, params: TextLevelParams):
    order = {lf.line_id: i for i, lf in enumerate(sorted(line_feats, key=lambda x: x.position))}
    by_id = {lf.line_id: lf for lf in line_feats}
    groups: dict[tuple, list[str]] = defaultdict(list)
    singles: dict[tuple, frozenset] = {}

    for lf in line_feats:
        for f in FEATURES:
            v = _strand_value(f, lf.features.get(f))
            if v is not None:
                groups[((f, v),)].append(lf.line_id)
    for key, ids in groups.items():
        singles[key[0]] = frozenset(ids)
    for f, g in _pairs(params.strand_pairs):
        for lf in line_feats:
            vf, vg = _strand_value(f, lf.features.get(f)), _strand_value(g, lf.features.get(g))
            if vf is not None and vg is not None:
                groups[((f, vf), (g, vg))].append(lf.line_id)

    kept = []
    for key, ids in groups.items():
        if len(ids) < params.min_strand_lines:
            continue
        if len(key) == 2 and frozenset(ids) in (singles.get(key[0]), singles.get(key[1])):
            continue  # same lines as one of its single-feature strands: adds nothing
        kept.append((key, sorted(ids, key=order.get)))
    feature_rank = {f: i for i, f in enumerate(FEATURES)}
    # Largest first; among equals, fewer features, then the KR order of
    # FEATURES (so "target=X" names a strand rather than an attribute of it).
    kept.sort(key=lambda kv: (-len(kv[1]), len(kv[0]),
                              [feature_rank[f] for f, _ in kv[0]],
                              [v for _, v in kv[0]]))

    # Keys selecting exactly the same lines describe one strand: keep the
    # simplest key and list the others as equivalent, so the same lines
    # don't produce duplicate strands, combs, and bridges.
    merged: dict[frozenset, tuple] = {}
    equivalents: dict[frozenset, list[str]] = defaultdict(list)
    for key, ids in kept:
        lines_key = frozenset(ids)
        if lines_key in merged:
            equivalents[lines_key].append("+".join(f"{f}={v}" for f, v in key))
        else:
            merged[lines_key] = (key, ids)

    n_all = len(line_feats)
    strands, combs, bridges = [], [], []
    for i, (lines_key, (key, ids)) in enumerate(merged.items(), start=1):
        sid = f"S-{i:03d}"
        pos = [by_id[x].position for x in ids]
        span = round(pos[-1] - pos[0], 4)
        centrality = ("central" if span >= params.central_min_span
                      else "peripheral" if span <= params.peripheral_max_span
                      else "intermediate")
        strand = Strand(
            strand_id=sid, key="+".join(f"{f}={v}" for f, v in key),
            features=[StrandFeature(feature=f, value=v) for f, v in key],
            line_ids=ids, n_lines=len(ids), share=round(len(ids) / n_all, 4),
            first_position=round(pos[0], 4), last_position=round(pos[-1], 4),
            span_fraction=span, centrality=centrality,
            equivalent_keys=equivalents.get(lines_key, []))

        # Combs: runs of strand lines with every consecutive gap small.
        run = [ids[0]]
        for prev, cur in zip(ids, ids[1:] + [None]):
            close = cur is not None and (by_id[cur].position - by_id[prev].position) <= params.comb_max_gap
            if close:
                run.append(cur)
                continue
            if len(run) >= params.comb_min_lines:
                w0 = min(by_id[x].word_start for x in run)
                w1 = max(by_id[x].word_end for x in run)
                comb = Comb(comb_id=f"C-{len(combs) + 1}", strand_id=sid, line_ids=list(run),
                            word_start=w0, word_end=w1,
                            span_fraction=round((w1 - w0) / total, 4) if total else 0.0,
                            words_per_line=_ratio(w1 - w0, len(run)))
                combs.append(comb)
                strand.comb_ids.append(comb.comb_id)
            run = [cur] if cur is not None else []

        # Bridges: consecutive strand lines far apart.
        for a, b in zip(ids, ids[1:]):
            gap = by_id[b].position - by_id[a].position
            if gap >= params.bridge_min_gap:
                bridge = Bridge(bridge_id=f"B-{len(bridges) + 1}", strand_id=sid,
                                from_line_id=a, to_line_id=b,
                                gap_words=max(by_id[b].word_start - by_id[a].word_end, 0),
                                gap_fraction=round(gap, 4))
                bridges.append(bridge)
                strand.bridge_ids.append(bridge.bridge_id)
        strands.append(strand)
    return strands, combs, bridges


# ---------- jab / punch ----------

def _jab_punch(analysis: Analysis, line_feats: list[LineFeatures], offsets: list[int],
               total: int, params: TextLevelParams) -> tuple[JabPunchSummary, PlotIndicators]:
    lf_by_id = {lf.line_id: lf for lf in line_feats}

    def count(group, label, items, words=None):
        jabs = sum(lf_by_id[x].classification == "jab" for x in items)
        return JabPunchCount(group=group, label=label, n_lines=len(items), n_jab=jabs,
                             n_punch=len(items) - jabs, words=words,
                             words_per_line=_ratio(words, len(items)) if words else None)

    def words_in(seg) -> int:
        start = offsets[seg.line_start - 1] if 0 < seg.line_start <= len(offsets) else 0
        end = offsets[seg.line_end] if seg.line_end < len(offsets) else total
        return max(end - start, 0)

    by_segment = [
        count(seg.segment_id, f"{seg.label} ({seg.narrative_level.value})",
              [lf.line_id for lf in line_feats if lf.segment_id == seg.segment_id],
              words_in(seg))
        for seg in analysis.segments
    ]
    levels: dict[str, list[str]] = defaultdict(list)
    for lf in line_feats:
        levels[lf.narrative_level].append(lf.line_id)
    by_level = [count(lv, lv, ids) for lv, ids in sorted(levels.items())]
    punches = [lf.line_id for lf in line_feats if lf.classification == "punch"]
    summary = JabPunchSummary(
        n_jab=len(line_feats) - len(punches), n_punch=len(punches),
        by_segment=by_segment, by_level=by_level, punch_line_ids=punches)

    framing = {s.segment_id for s in analysis.segments
               if s.narrative_level.value in ("level_+1", "level_+2")}
    lines_by_id = {ln.line_id: ln for ln in analysis.lines}
    meta = [lf.line_id for lf in line_feats
            if lf.segment_id in framing
            or lf.narrative_level in ("level_+1", "level_+2")
            or lines_by_id[lf.line_id].annotation.narrative_strategy == NarrativeStrategy.NARRATOR_ASIDE]
    final = [x for x in punches
             if total and lf_by_id[x].word_end >= total * (1 - params.final_punch_window)]
    indicators = PlotIndicators(
        final_punch_line_ids=final, n_metanarrative_lines=len(meta),
        metanarrative_share=round(len(meta) / len(line_feats), 4) if line_feats else 0.0,
        n_framing_segments=len(framing))
    return summary, indicators


# ---------- entry point ----------

def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_metrics(
    analysis: Analysis,
    story_text: str,
    params: TextLevelParams = TextLevelParams(),
    analysis_json: Optional[str] = None,
    review_path: Optional[Path] = None,
) -> TextLevelMetrics:
    """Text-level metrics for one story. `review_path` is the story's report
    workbook; reviewer-corrected Canonical Target / Canonical Situation
    values found there replace the pipeline's."""
    notes = {}
    if any(ln.canonical_situation is None for ln in analysis.lines):
        # Analysis from before normalization existed: normalize now with the
        # no-API string method so strands still use consistent labels.
        normalize_offline(analysis, NormalizationParams(method="string"))
        notes["normalization"] = "string similarity applied at text-level time"

    lines, offsets, total = _line_word_offsets(story_text)
    k = params.n_sections
    bounds = _section_bounds(total, k)
    review = read_review(review_path) if review_path else {}
    inventory_by_id = {e.target_id: e for e in analysis.target_inventory}

    overrides = 0
    line_feats: list[LineFeatures] = []
    for ln in sorted(analysis.lines, key=lambda x: _locate(x, lines, offsets, total)):
        target, entry = ln.canonical_target, inventory_by_id.get(ln.canonical_target_id or "")
        situation = ln.canonical_situation
        row = matching(review, ln.line_id, ln.span.text)
        if row is not None:
            edits = row.edited_canonical()
            if "Canonical Target" in edits:
                target = edits["Canonical Target"]
                entry = _entry_for(target, analysis.target_inventory)
                overrides += 1
            if "Canonical Situation" in edits:
                value = edits["Canonical Situation"]
                situation = (label_key(value) if value and label_key(value) in SITUATION_SENTINELS
                             else clean_label(value) if value else None)
                overrides += 1
        w0, w1 = _locate(ln, lines, offsets, total)
        mid = (w0 + w1) / 2
        line_feats.append(LineFeatures(
            line_id=ln.line_id, segment_id=ln.segment_id,
            classification=ln.annotation.classification.value,
            narrative_level=ln.annotation.narrative_level_of_classification.value,
            word_start=w0, word_end=w1,
            position=round(mid / total, 4) if total else 0.0,
            section=_section_of(mid, total, k) + 1,
            features=_line_features(ln, target, entry, situation)))

    sections = []
    for i, (a, b) in enumerate(bounds):
        ids = [lf.line_id for lf in line_feats if lf.section == i + 1]
        sections.append(SectionStat(index=i + 1, word_start=a, word_end=b, n_lines=len(ids),
                                    line_ids=ids, words_per_line=_ratio(b - a, len(ids))))
    distribution = _distribution(
        sections, [(lf.word_start + lf.word_end) / 2 for lf in line_feats], total,
        len(line_feats), params)
    strands, combs, bridges = _strands(line_feats, total, params)
    jab_punch, indicators = _jab_punch(analysis, line_feats, offsets, total, params)

    return TextLevelMetrics(
        schema_version=SCHEMA_VERSION,
        story_id=Path(analysis.source_filename).stem,
        source_filename=analysis.source_filename,
        analysis_sha256=_sha256_text(analysis_json or analysis.model_dump_json()),
        story_sha256=_sha256_text(story_text),
        params={**asdict(params), "features": FEATURES,
                "normalization": analysis.normalization_method, **notes},
        reviewer_overrides=overrides,
        lines=line_feats, distribution=distribution,
        strands=strands, combs=combs, bridges=bridges,
        jab_punch=jab_punch, plot_indicators=indicators)


def param_help() -> list[tuple[str, object, str]]:
    """(name, default, help) for every parameter, for the CLI and docs."""
    return [(f.name, f.default, f.metadata["help"]) for f in fields(TextLevelParams)]


def load_analysis(path: Path) -> tuple[Analysis, str]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    # Analyses written before the reasoning field / fixed narrative
    # strategies / target ids existed still load.
    strategies = {m.value for m in NarrativeStrategy}
    for line in data.get("lines", []):
        a = line.get("annotation", {})
        a.setdefault("reasoning", "")
        a.setdefault("target_id", None)
        a.setdefault("narrative_strategy_note", None)
        if a.get("narrative_strategy") not in strategies:
            a["narrative_strategy_note"] = a.get("narrative_strategy")
            a["narrative_strategy"] = NarrativeStrategy.OTHER.value
    return Analysis.model_validate(data), raw
