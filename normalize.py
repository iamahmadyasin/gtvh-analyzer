"""
Pipeline · Normalization
Gives every line a canonical target and situation, so lines about the same
thing can be grouped into strands.

Reads:   annotated lines and the target inventory
Writes:  canonical_target, canonical_target_id and canonical_situation on each
         line
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Awaitable, Callable, Optional, Sequence

from schemas import Analysis, TargetEntry

SITUATION_SENTINELS = {"cotext", "irr"}
_UNCERTAIN = re.compile(r"\(\?\)")
_STOPWORDS = {"a", "an", "the", "of", "at", "in", "on", "to", "and", "for", "with", "'s"}

Embed = Callable[[Sequence[str]], Awaitable[list[list[float]]]]
Similarity = Callable[[str, str], float]


@dataclass(frozen=True)
class NormalizationParams:
    method: str = "embeddings"
    situation_threshold: float = 0.80
    target_threshold: float = 0.80


def clean_label(label: str) -> str:
    return " ".join(_UNCERTAIN.sub("", label).split()).strip(" .,;:")


def label_key(label: str) -> str:
    return clean_label(label).lower()


def _tokens(label: str) -> set[str]:
    words = re.findall(r"[\w']+", label_key(label))
    return {w for w in words if w not in _STOPWORDS}


def string_similarity(a: str, b: str) -> float:
    ka, kb = label_key(a), label_key(b)
    if ka == kb:
        return 1.0
    ratio = SequenceMatcher(None, ka, kb).ratio()
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    return max(ratio, jaccard)


def _cosine(u: Sequence[float], v: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u))
    nv = math.sqrt(sum(y * y for y in v))
    return dot / (nu * nv) if nu and nv else 0.0


async def make_similarity(
    labels: Sequence[str], method: str, embed: Optional[Embed]
) -> tuple[Similarity, str]:
    if method == "embeddings" and embed is not None and labels:
        keys = sorted({label_key(lb) for lb in labels})
        try:
            vectors = dict(zip(keys, await embed(keys)))
        except Exception as exc:  # noqa: BLE001
            print(f"    embeddings unavailable ({exc}); using string similarity")
        else:
            def sim(a: str, b: str) -> float:
                ka, kb = label_key(a), label_key(b)
                if ka == kb:
                    return 1.0
                if ka in vectors and kb in vectors:
                    return _cosine(vectors[ka], vectors[kb])
                return string_similarity(a, b)
            return sim, "embeddings"
    return string_similarity, "string"


def group_labels(
    counts: Counter,
    similarity: Similarity,
    threshold: float,
) -> dict[str, str]:
    order = sorted(counts, key=lambda lb: (-counts[lb], len(lb), lb))
    representatives: list[str] = []
    mapping: dict[str, str] = {}
    for label in order:
        best, best_sim = None, threshold
        for rep in representatives:
            score = similarity(label, rep)
            if score >= best_sim:
                best, best_sim = rep, score
        if best is None:
            representatives.append(label)
            mapping[label] = label
        else:
            mapping[label] = best
    return mapping


def _match_inventory(
    label: str,
    inventory: list[TargetEntry],
    similarity: Similarity,
    threshold: float,
) -> Optional[TargetEntry]:
    key = label_key(label)
    for entry in inventory:
        if key in {label_key(n) for n in [entry.label, *entry.aliases]}:
            return entry
    best, best_sim = None, threshold
    for entry in inventory:
        for name in [entry.label, *entry.aliases]:
            score = similarity(label, name)
            if score >= best_sim:
                best, best_sim = entry, score
    return best


def _labels(analysis: Analysis) -> tuple[Counter, list[str], list[str]]:
    by_id = {e.target_id for e in analysis.target_inventory}
    situations = Counter(
        clean_label(line.annotation.situation)
        for line in analysis.lines
        if label_key(line.annotation.situation) not in SITUATION_SENTINELS
    )
    new_targets = [
        clean_label(line.annotation.target)
        for line in analysis.lines
        if line.annotation.target and line.annotation.target_id not in by_id
    ]
    names = [n for e in analysis.target_inventory for n in [e.label, *e.aliases]]
    return situations, new_targets, names


async def normalize_analysis(
    analysis: Analysis,
    params: NormalizationParams = NormalizationParams(),
    embed: Optional[Embed] = None,
) -> None:
    """Fills in canonical_target, canonical_target_id and canonical_situation on
    every line."""
    situations, new_targets, names = _labels(analysis)
    similarity, used = await make_similarity(
        [*situations, *new_targets, *names], params.method, embed
    )
    _apply(analysis, params, similarity, used)


def normalize_offline(analysis: Analysis, params: NormalizationParams = NormalizationParams()) -> None:
    """Same as normalize_analysis, but with string similarity only: no API call
    and no event loop."""
    _apply(analysis, params, string_similarity, "string")


def _apply(analysis: Analysis, params: NormalizationParams, similarity: Similarity, used: str) -> None:
    inventory = analysis.target_inventory
    by_id = {e.target_id: e for e in inventory}
    situations, new_targets, _ = _labels(analysis)

    situation_map = group_labels(situations, similarity, params.situation_threshold)

    to_entry: dict[str, TargetEntry] = {}
    unmatched: Counter = Counter()
    for label in new_targets:
        entry = _match_inventory(label, inventory, similarity, params.target_threshold)
        if entry is not None:
            to_entry[label] = entry
        else:
            unmatched[label] += 1
    target_map = group_labels(unmatched, similarity, params.target_threshold)

    for line in analysis.lines:
        a = line.annotation
        sit_key = label_key(a.situation)
        line.canonical_situation = (
            sit_key if sit_key in SITUATION_SENTINELS
            else situation_map.get(clean_label(a.situation), clean_label(a.situation))
        )
        if a.target_id in by_id:
            entry = by_id[a.target_id]
            line.canonical_target, line.canonical_target_id = entry.label, entry.target_id
        elif a.target:
            label = clean_label(a.target)
            if label in to_entry:
                entry = to_entry[label]
                line.canonical_target, line.canonical_target_id = entry.label, entry.target_id
            else:
                line.canonical_target = target_map.get(label, label)
                line.canonical_target_id = None
        else:
            line.canonical_target = line.canonical_target_id = None

    analysis.normalization_method = (
        f"{used} (situation>={params.situation_threshold}, "
        f"target>={params.target_threshold})"
    )
