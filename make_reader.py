"""
Readable story view: one self-contained HTML file per story.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Optional

from review_workbook import matching, read_review
from schemas import Analysis, AnnotatedLine, TextLevelReport
from textlevel import load_analysis

ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
TEXT_LEVEL_DIR = OUTPUT_DIR / "text_level"

BINARY = {
    "good_bad": "good and bad", "life_death": "life and death",
    "obscene_nonobscene": "the sexual and the innocent", "money_nomoney": "wealth and poverty",
    "high_low_stature": "high and low status",
}
OPPOSITION = {
    "actual_vs_nonactual": "what is really the case against what is not",
    "normal_vs_abnormal": "what you would expect against something odd",
    "possible_vs_impossible": "what could happen against what could not",
}
STRATEGY = {
    "narration": "the narrator's own description",
    "narrator_aside": "an aside from the narrator",
    "free_indirect_thought": "a character's thoughts, in the narrator's voice",
    "single_utterance": "a single remark by a character",
    "dialogue_exchange": "an exchange between characters",
    "question_and_answer": "a question and its answer",
    "embedded_text": "a letter, sign or document quoted in the story",
    "list": "a list that ends somewhere unexpected",
    "repetition_pattern": "a pattern set up and then broken",
    "other": "a form of its own",
}
LINE_TYPE = {
    "discrete": "One word or phrase flips the meaning.",
    "register_clash": "The style of the language clashes with what it describes.",
    "irony": "Something is said in a way the reader knows is wrong for the moment.",
}
ORIENTATION = {
    "self": "aimed at the speaker themselves", "hearer": "aimed at the person being addressed",
    "other": "aimed at someone else", "situation": "aimed at the situation itself",
}
WORDPLAY = {
    "phonological": "plays on sounds", "morphological": "plays on how words are formed",
    "lexical": "plays on a word's double meaning", "syntactic": "plays on sentence structure",
}
PLOT_TYPE = {
    "serious_plot_with_jab_lines": ("Serious plot, with jab lines",
        "The plot itself is not comic; the humor comes in passing."),
    "humorous_plot_with_punch_line": ("Humorous plot, with punch line",
        "The story builds to a final punch line that makes you reread what came before."),
    "humorous_plot_with_metanarrative_disruption": ("Humorous plot, with metanarrative disruption",
        "The humor comes from breaking the conventions of how stories are told."),
    "humorous_plot_with_humorous_central_complication": ("Humorous plot, with humorous central complication",
        "The event that sets the story in motion is itself funny."),
}
FEATURE_NAME = {
    "target": "At {v}'s expense", "situation": "Set in {v}",
    "so_binary_category": "{v}", "target_social_class": "{v}-class targets",
}
READABLE_FEATURES = ("target", "situation", "so_binary_category", "target_social_class")
GLOSSARY = {
    "jab": "A joke in the middle of the story that does not interrupt it. Most of a story's humor comes as jab lines.",
    "punch": "A joke that ends a part of the story (a scene, a letter, the whole text) and makes you see what came before differently.",
    "strand": "A set of jokes that have something in common, such as the same target or the same setting.",
    "relief": "A long stretch with little or no humor inside an otherwise funny story. Attardo calls this serious relief.",
    "wave": "A stretch where jokes come much faster than usual.",
    "comb": "Several jokes of one strand packed close together.",
    "bridge": "Two related jokes far apart, linking distant parts of the story.",
}


def _sentence(label: str) -> str:
    """'DEVOTION TO A WIFE (?)' -> 'devotion to a wife'"""
    return " ".join(label.replace("(?)", "").split()).lower()


def _mid_sentence(name: str) -> str:
    """'The curate' -> 'the curate' when it follows other words."""
    return "the " + name[4:] if name.startswith("The ") else name


def _strand_name(key: str) -> Optional[str]:
    parts = [p.split("=", 1) for p in key.split("+")]
    if len(parts) != 1 or parts[0][0] not in READABLE_FEATURES:
        return None
    feature, value = parts[0]
    if feature == "so_binary_category":
        value = BINARY.get(value, value).capitalize()
    if feature == "target_social_class":
        value = value.capitalize()
    if feature == "target":
        value = _mid_sentence(value)
    return FEATURE_NAME[feature].format(v=value)


# ---------- locating the marks in the text ----------

def _spans(line: AnnotatedLine, paragraphs: dict[int, str]) -> list[tuple[int, int, int]]:
    """(paragraph number, start char, end char) pieces covered by a line:
    the quoted text where it can be found, else the whole paragraphs."""
    nums = [n for n in range(line.span.line_start, line.span.line_end + 1) if n in paragraphs]
    if not nums:
        return []
    joined, starts = "", []
    for n in nums:
        starts.append(len(joined))
        joined += paragraphs[n] + " "
    pos = joined.find(line.span.text.strip()) if line.span.text.strip() else -1
    if pos < 0:
        return [(n, 0, len(paragraphs[n])) for n in nums]
    end = pos + len(line.span.text.strip())
    pieces = []
    for n, s in zip(nums, starts):
        a, b = max(pos, s), min(end, s + len(paragraphs[n]))
        if a < b:
            pieces.append((n, a - s, b - s))
    return pieces


def _paint(text: str, ranges: list[tuple[int, int, str]], kinds: dict[str, str],
           numbers: dict[str, int]) -> str:
    """HTML for one paragraph with nested or overlapping marks flattened
    into runs; each run lists every line covering it."""
    cuts = sorted({0, len(text), *[a for a, _, _ in ranges], *[b for _, b, _ in ranges]})
    ends = {}
    for a, b, lid in ranges:
        ends.setdefault(b, []).append(lid)
    out = []
    for a, b in zip(cuts, cuts[1:]):
        ids = [lid for s, e, lid in ranges if s <= a and b <= e]
        chunk = html.escape(text[a:b])
        if ids:
            # innermost (shortest) line first: that's what a click opens
            ids.sort(key=lambda x: next(e - s for s, e, lid in ranges if lid == x))
            kind = "punch" if any(kinds[i] == "punch" for i in ids) else "jab"
            chunk = (f'<mark class="hl {kind}" data-ids="{" ".join(ids)}" tabindex="0" '
                     f'role="button">{chunk}</mark>')
        out.append(chunk)
        for lid in ends.get(b, []):
            out.append(f'<sup class="ref" aria-hidden="true">{numbers[lid]}</sup>')
    return "".join(out)


# ---------- page ----------

def _card_data(line: AnnotatedLine, target: Optional[str], situation: Optional[str],
               seg_label: str, number: int, strands: list[str]) -> dict:
    a = line.annotation
    so, lang = a.script_opposition, a.language
    words = []
    if lang.is_wordplay:
        words.append(f"Yes: it {WORDPLAY.get(lang.wordplay_level.value if lang.wordplay_level else '', 'plays on words')}"
                     + (f" ({lang.wordplay_subtype})" if lang.wordplay_subtype else "") + ".")
    if lang.is_register_effect:
        words.append("Yes: the style of the language is part of the joke"
                     + (f" ({lang.register_effect_subtype})" if lang.register_effect_subtype else "") + ".")
    sit = situation or ""
    sit_text = ("It continues the scene around it." if sit == "cotext"
                else "The setting doesn't matter to it." if sit in ("irr", "")
                else sit[0].upper() + sit[1:] + ".")
    return {
        "n": number, "id": line.line_id, "kind": a.classification.value,
        "level": a.narrative_level_of_classification.value, "segment": seg_label,
        "text": line.span.text,
        "one": _sentence(so.script_1), "two": _sentence(so.script_2),
        "clash": BINARY.get(so.essential_binary_category.value),
        "opposition": OPPOSITION[so.opposition_type.value],
        "butt": target, "orientation": ORIENTATION[a.orientation.value],
        "where": sit_text,
        "told": STRATEGY[a.narrative_strategy.value] if a.narrative_strategy.value != "other"
                else (a.narrative_strategy_note or STRATEGY["other"]),
        "how": LINE_TYPE[line.line_type.value], "turn": line.disjunctor,
        "words": " ".join(words) or "No: it would still be funny if reworded.",
        "why": a.reasoning or line.brief_reason or "",
        "strands": strands,
        "tech": {
            "Line": line.line_id, "Lines in story": f"{line.span.line_start}-{line.span.line_end}",
            "Classification": f"{a.classification.value} ({a.narrative_level_of_classification.value})",
            "Line type": line.line_type.value, "Detection confidence": line.confidence or "",
            "Script opposition": f"{so.script_1} / {so.script_2}",
            "Binary category": so.essential_binary_category.value,
            "Opposition type": so.opposition_type.value,
            "Situation": a.situation, "Target": a.target or "none",
            "Orientation": a.orientation.value, "Narrative strategy": a.narrative_strategy.value,
            "Wordplay": lang.wordplay_level.value if lang.wordplay_level else "none",
            "Register effect": lang.register_effect_subtype or ("yes" if lang.is_register_effect else "none"),
        },
    }


def _note_html(c: dict) -> str:
    butt = f"At {html.escape(_mid_sentence(c['butt']))}'s expense. " if c["butt"] else ""
    one = c["one"][:1].upper() + c["one"][1:]
    return (f'<aside class="note" data-for="{c["id"]}"><span class="note-n">{c["n"]}</span>'
            f'<span class="note-kind {c["kind"]}">{c["kind"].capitalize()}</span> '
            f'{butt}<em>{html.escape(one)}</em> against <em>{html.escape(c["two"])}</em>. '
            f'Told through {html.escape(c["told"])}.</aside>')


def build_reader(analysis: Analysis, story_text: str, title: str,
                 text_level: Optional[TextLevelReport] = None,
                 review_path: Optional[Path] = None, fragment: bool = False) -> str:
    raw_lines = story_text.splitlines()
    paragraphs = {i + 1: t for i, t in enumerate(raw_lines) if t.strip()}
    word_at, total = {}, 0
    for i, t in enumerate(raw_lines, start=1):
        word_at[i] = total
        total += len(t.split())

    review = read_review(review_path) if review_path else {}
    seg_by_id = {s.segment_id: s for s in analysis.segments}
    lines = sorted(analysis.lines, key=lambda ln: (ln.span.line_start, ln.line_id))
    numbers = {ln.line_id: i for i, ln in enumerate(lines, start=1)}
    kinds = {ln.line_id: ln.annotation.classification.value for ln in lines}

    metrics = text_level.metrics if text_level else None
    readable = []
    if metrics:
        for s in metrics.strands:
            name = _strand_name(s.key)
            if name:
                readable.append({"id": s.strand_id, "name": name, "lines": s.line_ids, "n": s.n_lines,
                                 "share": s.share, "centrality": s.centrality,
                                 "combs": len(s.comb_ids), "bridges": len(s.bridge_ids)})
        readable = readable[:8]
    strands_of = {}
    for s in readable:
        for lid in s["lines"]:
            strands_of.setdefault(lid, []).append(s["id"])

    cards, ranges, note_at = {}, {}, {}
    for ln in lines:
        target, situation = ln.canonical_target or ln.annotation.target, ln.canonical_situation
        row = matching(review, ln.line_id, ln.span.text)
        if row:
            edits = row.edited_canonical()
            target = edits.get("Canonical Target", target)
            situation = edits.get("Canonical Situation", situation)
        seg = seg_by_id.get(ln.segment_id)
        cards[ln.line_id] = _card_data(ln, target, situation, seg.label if seg else "",
                                       numbers[ln.line_id], strands_of.get(ln.line_id, []))
        pieces = _spans(ln, paragraphs)
        for n, a, b in pieces:
            ranges.setdefault(n, []).append((a, b, ln.line_id))
        if pieces:  # the margin note sits beside the paragraph where the joke starts
            note_at.setdefault(pieces[0][0], []).append(ln.line_id)

    # Story body: top-level segments open with a small label; embedded
    # ones (letters, speeches) are set as an inset block.
    def innermost(n: int):
        found = [s for s in analysis.segments if s.line_start <= n <= s.line_end]
        return min(found, key=lambda s: s.line_end - s.line_start) if found else None

    body, open_inset, seen_top = [], None, set()
    for n, text in paragraphs.items():
        seg = innermost(n)
        embedded = seg is not None and seg.narrative_level.value in ("level_-1", "level_-2")
        top = seg
        while top is not None and top.narrative_level.value in ("level_-1", "level_-2") and top.parent_segment_id:
            top = seg_by_id.get(top.parent_segment_id)
        if open_inset and (not embedded or seg.segment_id != open_inset):
            body.append("</div>")
            open_inset = None
        if top is not None and top.segment_id not in seen_top:
            seen_top.add(top.segment_id)
            body.append(f'<p class="seg-label" id="{top.segment_id}">{html.escape(top.label)}</p>')
        if embedded and open_inset != seg.segment_id:
            body.append(f'<div class="inset" id="{seg.segment_id}"><p class="inset-label">{html.escape(seg.label)}</p>')
            open_inset = seg.segment_id
        notes = "".join(_note_html(cards[lid]) for lid in note_at.get(n, []))
        para = _paint(text, ranges.get(n, []), kinds, numbers)
        body.append(f'<div class="para" data-w="{word_at[n]}"><p>{para}</p>'
                    f'<div class="notes">{notes}</div></div>')
    if open_inset:
        body.append("</div>")

    # Overview, density strip and filters (only with text-level results)
    n_lines, n_punch = len(lines), sum(k == "punch" for k in kinds.values())
    per = round(total / n_lines) if n_lines else None
    stats = [f"{total:,} words", f"{n_lines} humorous lines",
             f"one every {per} words" if per else "no humorous lines",
             f"{n_punch} <abbr class='term' data-term='punch'>punch</abbr> line{'s' if n_punch != 1 else ''}"]
    overview, rail, sections = "", "", []
    if metrics:
        d = metrics.distribution
        marks = {}
        for st in d.waves:
            for i in range(st.first_section, st.last_section + 1):
                marks[i] = "wave"
        for st in d.serious_reliefs:
            for i in range(st.first_section, st.last_section + 1):
                marks[i] = "relief"
        top_count = max((s.n_lines for s in d.sections), default=0) or 1
        for s in d.sections:
            sections.append({"i": s.index, "w": s.word_start, "n": s.n_lines,
                             "heat": round(s.n_lines / top_count, 3), "mark": marks.get(s.index, "")})
        cells = "".join(
            f'<button class="cell {c["mark"]}" style="--h:{c["heat"]}" data-w="{c["w"]}" '
            f'title="Part {c["i"]} of {len(sections)}: {c["n"]} joke{"s" if c["n"] != 1 else ""}'
            f'{", a wave" if c["mark"] == "wave" else ", serious relief" if c["mark"] == "relief" else ""}">'
            f'<span class="sr">Part {c["i"]}, {c["n"]} jokes</span></button>' for c in sections)
        rail = (f'<nav class="rail" aria-label="Humor density"><p class="rail-label">Humor</p>'
                f'<div class="cells">{cells}</div>'
                f'<p class="rail-key"><span class="k wave"></span><abbr class="term" data-term="wave">wave</abbr>'
                f'<span class="k relief"></span><abbr class="term" data-term="relief">quiet</abbr></p></nav>')

        it = text_level.interpretation
        if it:
            name, gloss = PLOT_TYPE[it.plot_type.value]
            runner = PLOT_TYPE[it.runner_up_plot_type.value][0] if it.runner_up_plot_type else None
            findings = "".join(f"<li>{html.escape(f.statement)} <span class='fig'>"
                               f"{html.escape('; '.join(e.figure for e in f.evidence))}</span></li>"
                               for f in it.pattern_findings)
            readings = "".join(f"<li>{html.escape(r.reading)} <span class='caveat'>{html.escape(r.caveat)}</span></li>"
                               for r in it.readings)
            overview = f"""
<section class="overview" aria-label="The story as a whole">
  <div class="ov-plot">
    <p class="eyebrow">Plot type (Attardo)</p>
    <h2>{html.escape(name)}</h2>
    <p>{html.escape(gloss)}</p>
    <p class="muted">Confidence: {it.plot_type_confidence.value}{f'. Could also be read as: {html.escape(runner)}' if runner else ''}.</p>
    <p class="eyebrow">Central complication</p>
    <p>{html.escape(it.central_complication.description)}</p>
    <p class="caveat">{html.escape(it.central_complication.caveat)}</p>
  </div>
  <div class="ov-patterns">
    <p class="eyebrow">Patterns in the humor</p>
    <ul class="findings">{findings}</ul>
    {f'<p class="eyebrow">One reading <span class="pill">interpretation</span></p><ul class="readings">{readings}</ul>' if readings else ''}
  </div>
</section>"""

    chips = "".join(
        f'<button class="chip" data-strand="{s["id"]}" aria-pressed="false">{html.escape(s["name"])}'
        f'<span class="count">{s["n"]}</span></button>' for s in readable)
    filters = f"""
<div class="toolbar" role="toolbar" aria-label="Show">
  <div class="chips">
    <button class="chip" data-filter="all" aria-pressed="true">All jokes<span class="count">{n_lines}</span></button>
    <button class="chip" data-filter="punch" aria-pressed="false"><abbr class="term" data-term="punch">Punch</abbr> lines<span class="count">{n_punch}</span></button>
    {('<span class="chip-sep" aria-hidden="true"></span><span class="chip-label"><abbr class="term" data-term="strand">Strands</abbr></span>' + chips) if chips else ''}
  </div>
</div>"""

    data = json.dumps({"cards": cards, "strands": {s["id"]: s for s in readable},
                       "glossary": GLOSSARY, "order": [ln.line_id for ln in lines]},
                      ensure_ascii=False).replace("</", "<\\/")
    content = PAGE.format(
        title=html.escape(title), stats=" · ".join(stats), overview=overview,
        filters=filters, rail=rail, body="\n".join(body), data=data,
        modes=MODES, css=CSS, js=JS,
        source=html.escape(analysis.source_filename),
        model=html.escape(text_level.interpretation_model) if text_level and text_level.interpretation else "",
    )
    if fragment:
        return content
    return f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n' \
           f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n' \
           f'{content}\n</html>\n'


MODES = """<div class="modes" role="radiogroup" aria-label="View">
  <button role="radio" aria-checked="true" data-mode="read" id="mode-read">Reading</button>
  <button role="radio" aria-checked="false" data-mode="margin" id="mode-margin">Margin notes</button>
</div>"""

PAGE = """<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&family=Instrument+Sans:wght@400;500;600&display=swap">
<style>{css}</style>
<div class="page" id="page" data-mode="read">
<header class="masthead">
  <div class="mast-text">
    <p class="eyebrow">Annotated with the General Theory of Verbal Humor</p>
    <h1>{title}</h1>
    <p class="stats">{stats}</p>
  </div>
  {modes}
</header>
{overview}
{filters}
<div class="layout">
  {rail}
  <article class="story" id="story">
{body}
  </article>
  <aside class="sidebar" id="sidebar" aria-live="polite">
    <div class="side-empty" id="side-empty">
      <p class="eyebrow">How to read this page</p>
      <p>Highlighted passages are the jokes. Hover over one for a summary, or click it for the full explanation.</p>
      <p class="legend"><mark class="hl jab sample">jab line</mark> <mark class="hl punch sample">punch line</mark></p>
      <p class="muted">Use the arrow keys to step through the jokes in order. Choose a strand above to see one thread of humor across the whole story.</p>
    </div>
    <div class="card" id="card" hidden></div>
  </aside>
</div>
<footer class="colophon">
  <p>Generated by GTVH Analyzer from {source}. Annotations are model output and may contain errors.{model_note}</p>
  <p class="print-hint">Margin notes is the view your browser prints.</p>
</footer>
</div>
<div class="tip" id="tip" role="tooltip" hidden></div>
<div class="pop" id="pop" role="dialog" aria-modal="false" hidden></div>
<script type="application/json" id="data">{data}</script>
<script>{js}</script>""".replace("{model_note}", "{model}")

CSS = r"""
/* A printed page: white paper, black ink, two highlighters (yellow for jabs,
   pink for punch lines). Humor density is drawn as ink darkness. Layout:
   masthead and whole-story overview on top; below, the density rail, the
   story at reading width, and a sticky explanation panel. Margin-notes view
   and print put a short note beside each paragraph instead. */
:root {
  --paper:
  --accent:
  --jab: rgba(255, 213, 0, .40); --jab-line:
  --punch: rgba(255, 64, 160, .20); --punch-line:
  --heat:
  --dim: .28;
  --font-story: "Literata", "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --font-ui: "Instrument Sans", "Segoe UI", system-ui, -apple-system, sans-serif;
  --step--1: .8125rem; --step-0: 1rem; --step-1: 1.1875rem; --step-2: 1.5rem; --step-3: 2.25rem;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper:
  --accent:
  --jab: rgba(255, 213, 0, .22); --jab-line:
  --punch: rgba(255, 92, 175, .22); --punch-line:
  --heat:
:root[data-theme="dark"] {
  --paper:
  --accent:
  --jab: rgba(255, 213, 0, .22); --jab-line:
  --punch: rgba(255, 92, 175, .22); --punch-line:
  --heat:

* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 400 var(--step-0)/1.5 var(--font-ui); }
.page { max-width: 76rem; margin: 0 auto; padding-inline: 1rem; padding-block: 1.5rem 3rem; }
.eyebrow { font: 600 var(--step--1)/1.3 var(--font-ui); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 0 0 .4rem; }
.muted { color: var(--muted); }
h1, h2 { font-family: var(--font-story); font-weight: 600; text-wrap: balance; margin: 0; }
h1 { font-size: var(--step-3); line-height: 1.1; }
h2 { font-size: var(--step-2); line-height: 1.2; margin-bottom: .4rem; }
abbr.term { text-decoration: underline dotted var(--muted); text-underline-offset: 3px; cursor: help; }
button { font: inherit; color: inherit; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.masthead { display: flex; flex-wrap: wrap; gap: 1rem 2rem; align-items: end; justify-content: space-between;
  padding-bottom: 1.25rem; border-bottom: 1px solid var(--rule); }
.stats { margin: .5rem 0 0; color: var(--muted); font-variant-numeric: tabular-nums; }
.modes { display: inline-flex; border: 1px solid var(--rule); border-radius: 999px; padding: 3px; background: var(--sheet); }
.modes button { border: 0; background: none; padding: .35rem .9rem; border-radius: 999px; cursor: pointer; font-size: var(--step--1); font-weight: 500; }
.modes button[aria-checked="true"] { background: var(--ink); color: var(--sheet); }

.overview { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr); gap: 1.5rem 3rem;
  padding-block: 1.5rem; border-bottom: 1px solid var(--rule); }
.overview p { margin: 0 0 .75rem; max-width: 60ch; }
.overview .eyebrow { margin-top: .25rem; }
.findings, .readings { margin: 0 0 1rem; padding-left: 1.1rem; display: grid; gap: .5rem; max-width: 68ch; }
.fig { display: block; font-size: var(--step--1); color: var(--muted); font-variant-numeric: tabular-nums; }
.caveat { display: block; font-size: var(--step--1); color: var(--muted); font-style: italic; }
.pill { display: inline-block; margin-left: .4rem; padding: 0 .45rem; border-radius: 3px; border: 1px solid var(--muted);
  color: var(--muted); letter-spacing: .02em; text-transform: none; font-weight: 600; }

.toolbar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; background: var(--paper);
  padding-block: .75rem; border-bottom: 1px solid var(--rule); }
.chips { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.chip { display: inline-flex; gap: .45rem; align-items: center; border: 1px solid var(--rule); background: var(--sheet);
  border-radius: 999px; padding: .3rem .75rem; font-size: var(--step--1); cursor: pointer; }
.chip .count { color: var(--muted); font-variant-numeric: tabular-nums; }
.chip[aria-pressed="true"] { border-color: var(--ink); background: var(--ink); color: var(--paper); }
.chip[aria-pressed="true"] .count { color: inherit; }
.chip-sep { width: 1px; height: 1.4rem; background: var(--rule); margin-inline: .3rem; }
.chip-label { font-size: var(--step--1); color: var(--muted); margin-right: .1rem; }

.layout { display: grid; grid-template-columns: 2.5rem minmax(0, 40rem) minmax(0, 22rem); gap: 2.5rem; padding-top: 2rem; justify-content: center; }
.rail { position: sticky; top: 4.5rem; align-self: start; display: grid; gap: .5rem; justify-items: center; }
.rail-label { margin: 0; font-size: var(--step--1); color: var(--muted); writing-mode: vertical-rl; transform: rotate(180deg); }
.cells { display: grid; gap: 3px; width: 1.1rem; }
.cell { height: 1.6rem; width: 100%; padding: 0; border: 0; border-radius: 3px; cursor: pointer;
  background: color-mix(in srgb, var(--heat) calc(var(--h, 0) * 85% + 6%), var(--rule)); }
.cell.wave { box-shadow: 0 0 0 2px var(--jab-line); }
.cell.relief { background: repeating-linear-gradient(135deg, var(--rule) 0 3px, transparent 3px 6px); }
.cell.here { outline: 2px solid var(--ink); outline-offset: 1px; }
.rail-key { margin: 0; display: grid; gap: .3rem; justify-items: center; font-size: .7rem; color: var(--muted); }
.k { display: block; width: .9rem; height: .5rem; border-radius: 2px; }
.k.wave { box-shadow: 0 0 0 2px var(--jab-line); background: var(--heat); }
.k.relief { background: repeating-linear-gradient(135deg, var(--rule) 0 2px, transparent 2px 4px); outline: 1px solid var(--rule); }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

.story { font: 400 var(--step-1)/1.7 var(--font-story); min-width: 0; }
.story p { margin: 0 0 1em; }
.seg-label { font: 600 var(--step--1)/1.3 var(--font-ui) !important; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); margin: 2.2em 0 1em !important; display: flex; align-items: center; gap: .75rem; }
.seg-label::after { content: ""; flex: 1; height: 1px; background: var(--rule); }
.story > .seg-label:first-child { margin-top: 0 !important; }
.inset { margin: .5em 0 1.4em; padding: 1rem 1.25rem .25rem; background: var(--sheet); border: 1px solid var(--rule);
  border-radius: 4px; font-style: italic; }
.inset-label { font: 600 var(--step--1)/1.3 var(--font-ui); font-style: normal; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.para { display: grid; grid-template-columns: minmax(0, 1fr); }
.notes { display: none; }
sup.ref { display: none; }

mark.hl { color: inherit; background: var(--jab); border-radius: 2px; padding: 0 1px; cursor: pointer;
  box-decoration-break: clone; -webkit-box-decoration-break: clone; transition: background .15s, opacity .15s; }
mark.hl.jab { text-decoration: underline 1.5px dotted var(--jab-line); text-underline-offset: 4px; }
mark.hl.punch { background: var(--punch); text-decoration: underline 2px solid var(--punch-line); text-underline-offset: 4px; }
mark.hl:hover, mark.hl.active { background: color-mix(in srgb, var(--jab-line) 35%, transparent); }
mark.hl.punch:hover, mark.hl.punch.active { background: color-mix(in srgb, var(--punch-line) 35%, transparent); }
.page[data-mode="read"] .story.filtering mark.hl:not(.on) { background: transparent; text-decoration-color: var(--rule); opacity: .75; }
.page[data-mode="read"] .story.filtering mark.hl.on { box-shadow: 0 2px 0 var(--ink); }
mark.sample { cursor: default; }
.legend { display: flex; gap: .75rem; font-family: var(--font-story); }

.sidebar { position: sticky; top: 4.5rem; align-self: start; max-height: calc(100vh - 6rem); overflow: auto; min-width: 0; }
.side-empty p { margin: 0 0 .75rem; }
.card { background: var(--sheet); border: 1px solid var(--rule); border-radius: 6px; padding: 1.1rem 1.2rem; display: grid; gap: .9rem; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: .5rem; }
.kind { font-size: var(--step--1); font-weight: 600; padding: .1rem .55rem; border-radius: 999px; }
.kind.jab { background: var(--jab); } .kind.punch { background: var(--punch); }
.card-nav { display: flex; gap: .25rem; }
.card-nav button { border: 1px solid var(--rule); background: var(--paper); border-radius: 4px; padding: .15rem .5rem; cursor: pointer; }
.quote { font: italic 400 var(--step-0)/1.5 var(--font-story); margin: 0; padding-left: .8rem; border-left: 3px solid var(--jab-line); }
.card.punch .quote { border-left-color: var(--punch-line); }
.q { display: grid; gap: .2rem; }
.q dt { font-size: var(--step--1); font-weight: 600; color: var(--muted); }
.q dd { margin: 0; }
.clash { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: .5rem; align-items: center; }
.clash span { background: var(--paper); border: 1px solid var(--rule); border-radius: 4px; padding: .35rem .5rem; font-family: var(--font-story); text-align: center; }
.clash b { color: var(--muted); font-weight: 500; font-size: var(--step--1); }
.card .chips .chip { font-size: .75rem; }
details { border-top: 1px solid var(--rule); padding-top: .6rem; }
summary { cursor: pointer; font-size: var(--step--1); color: var(--muted); }
.tech { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .2rem .8rem; font-size: var(--step--1); margin: .6rem 0 0; }
.tech dt { color: var(--muted); } .tech dd { margin: 0; overflow-wrap: anywhere; }
.close { display: none; }

.tip, .pop { position: fixed; z-index: 20; max-width: 18rem; background: var(--ink); color: var(--sheet);
  font-size: var(--step--1); line-height: 1.4; padding: .45rem .65rem; border-radius: 4px; pointer-events: none; }
.pop { pointer-events: auto; background: var(--sheet); color: var(--ink); border: 1px solid var(--rule); box-shadow: 0 6px 20px rgba(0,0,0,.12); }

.colophon { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--rule); font-size: var(--step--1); color: var(--muted); }
.colophon p { margin: 0 0 .3rem; }

/* Margin notes view (B): a note beside each paragraph with jokes. */
.page[data-mode="margin"] .layout { grid-template-columns: 2.5rem minmax(0, 58rem); }
.page[data-mode="margin"] .sidebar, .page[data-mode="margin"] .toolbar { display: none; }
.page[data-mode="margin"] .para { grid-template-columns: minmax(0, 38rem) minmax(0, 17rem); column-gap: 2rem; }
.page[data-mode="margin"] .notes { display: grid; gap: .6rem; align-content: start; font: 400 .8125rem/1.45 var(--font-ui); color: var(--muted); padding-top: .25rem; }
.page[data-mode="margin"] sup.ref { display: inline; font: 600 .65rem var(--font-ui); color: var(--muted); margin-left: 1px; }
.page[data-mode="margin"] mark.hl { cursor: default; }
.note { display: block; break-inside: avoid; }
.note em { color: var(--ink); font-style: normal; font-weight: 500; }
.note-n { font-weight: 600; color: var(--ink); margin-right: .35rem; font-variant-numeric: tabular-nums; }
.note-kind { font-weight: 600; padding: 0 .35rem; border-radius: 3px; }
.note-kind.jab { background: var(--jab); color: var(--ink); } .note-kind.punch { background: var(--punch); color: var(--ink); }
.print-hint { display: none; }
.page[data-mode="margin"] .print-hint { display: block; }

@media (max-width: 64rem) {
  .layout { grid-template-columns: 2rem minmax(0, 1fr); gap: 1.25rem; }
  .sidebar { position: fixed; left: 0; right: 0; bottom: 0; top: auto; max-height: 70vh; z-index: 10;
    background: var(--paper); border-top: 1px solid var(--rule); padding: 1rem 1rem calc(1rem + env(safe-area-inset-bottom, 0px));
    box-shadow: 0 -8px 24px rgba(0,0,0,.12); display: none; }
  .sidebar.open { display: block; }
  .side-empty { display: none; }
  .close { display: inline-block; }
  .page[data-mode="margin"] .layout { grid-template-columns: 2rem minmax(0, 1fr); }
  .page[data-mode="margin"] .para { grid-template-columns: minmax(0, 1fr); }
  .page[data-mode="margin"] .notes { padding: 0 0 1rem .9rem; border-left: 2px solid var(--rule); }
}
@media (max-width: 44rem) {
  .overview { grid-template-columns: minmax(0, 1fr); }
  .toolbar { margin-inline: -1rem; padding-inline: 1rem; }
  .chips { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; padding-bottom: 2px; }
  .chip, .chip-label { flex: none; }
  .story { font-size: var(--step-0); }
  .layout { grid-template-columns: 1.4rem minmax(0, 1fr); gap: .9rem; }
  .cells { width: .8rem; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; scroll-behavior: auto !important; } }

@media print {
  @page { margin: 18mm 16mm; }
  :root { --paper: #fff; --sheet: #fff; --ink: #000; --muted: #444; --rule: #bbb; }
  body { background: #fff; }
  .modes, .toolbar, .rail, .sidebar, .tip, .pop { display: none !important; }
  .page { max-width: none; padding: 0; }
  .layout { display: block; padding-top: 1rem; }
  .story { font-size: 10.5pt; }
  .para { grid-template-columns: minmax(0, 1fr) 15rem !important; column-gap: 1.2rem; }
  .notes { display: grid !important; gap: .4rem; align-content: start; font: 8pt/1.35 var(--font-ui); color: #333; }
  sup.ref { display: inline !important; font: 600 6.5pt var(--font-ui); }
  mark.hl { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .overview { break-after: page; grid-template-columns: 1fr 1fr; }
  .print-hint { display: none !important; }
}
"""

JS = r"""
(function () {
  const data = JSON.parse(document.getElementById('data').textContent);
  const page = document.getElementById('page');
  const story = document.getElementById('story');
  const sidebar = document.getElementById('sidebar');
  const card = document.getElementById('card');
  const empty = document.getElementById('side-empty');
  const tip = document.getElementById('tip');
  const pop = document.getElementById('pop');
  const marks = Array.from(story.querySelectorAll('mark.hl'));
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  let current = null;

  // View mode (remembered per browser when storage is available)
  function setMode(mode) {
    page.dataset.mode = mode;
    document.querySelectorAll('.modes button').forEach(b => b.setAttribute('aria-checked', String(b.dataset.mode === mode)));
    try { localStorage.setItem('gtvh-reader-mode', mode); } catch (e) {}
    hideTip();
  }
  document.querySelectorAll('.modes button').forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));
  try { const m = localStorage.getItem('gtvh-reader-mode'); if (m === 'margin') setMode(m); } catch (e) {}

  // One-line summary on hover
  function summary(c) {
    const who = c.butt ? `at ${c.butt.replace(/^The /, 'the ')}'s expense` : 'no particular butt';
    return `${c.kind === 'punch' ? 'Punch line' : 'Jab'} · ${who} · ${c.one} against ${c.two}`;
  }
  function placeTip(el, text) {
    tip.textContent = text; tip.hidden = false;
    const r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
    let x = Math.min(Math.max(8, r.left), window.innerWidth - t.width - 8);
    let y = r.top - t.height - 8; if (y < 8) y = r.bottom + 8;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function hideTip() { tip.hidden = true; }
  marks.forEach(m => {
    m.addEventListener('mouseenter', () => { if (page.dataset.mode === 'read' && matchMedia('(hover: hover)').matches) placeTip(m, summary(data.cards[m.dataset.ids.split(' ')[0]])); });
    m.addEventListener('mouseleave', hideTip);
    m.addEventListener('click', () => { if (page.dataset.mode === 'read') open(m.dataset.ids.split(' ')[0]); });
    m.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(m.dataset.ids.split(' ')[0]); } });
  });

  // The explanation card
  function open(id) {
    const c = data.cards[id]; if (!c) return;
    current = id; hideTip();
    marks.forEach(m => m.classList.toggle('active', m.dataset.ids.split(' ').includes(id)));
    const strands = c.strands.map(s => `<button class="chip" data-strand="${s}">${esc(data.strands[s].name)}<span class="count">${data.strands[s].n}</span></button>`).join('');
    const tech = Object.entries(c.tech).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
    const i = data.order.indexOf(id);
    card.className = 'card ' + c.kind;
    card.innerHTML = `
      <div class="card-head">
        <span class="kind ${c.kind}">${c.kind === 'punch' ? 'Punch line' : 'Jab line'} ${c.n} of ${data.order.length}</span>
        <span class="card-nav">
          <button data-step="-1" aria-label="Previous joke" ${i === 0 ? 'disabled' : ''}>&larr;</button>
          <button data-step="1" aria-label="Next joke" ${i === data.order.length - 1 ? 'disabled' : ''}>&rarr;</button>
          <button class="close" aria-label="Close">&times;</button>
        </span>
      </div>
      <p class="quote">${esc(c.text)}</p>
      <dl class="q"><dt>Two ideas collide</dt><dd><div class="clash"><span>${esc(c.one)}</span><b>against</b><span>${esc(c.two)}</span></div></dd>
        <dd class="muted">${c.clash ? `A clash of ${esc(c.clash)}: ` : ''}${esc(c.opposition)}.</dd></dl>
      <dl class="q"><dt>Who it's aimed at</dt><dd>${c.butt ? esc(c.butt) : 'No one in particular'} <span class="muted">(${esc(c.orientation)})</span></dd></dl>
      <dl class="q"><dt>How it works</dt><dd>${esc(c.how)}${c.turn ? ` The turn comes at <i>“${esc(c.turn)}”</i>.` : ''}</dd>
        <dd class="muted">Told through ${esc(c.told)}.</dd></dl>
      <dl class="q"><dt>Where it happens</dt><dd>${esc(c.where)}</dd></dl>
      <dl class="q"><dt>Does it depend on the exact words?</dt><dd>${esc(c.words)}</dd></dl>
      ${strands ? `<dl class="q"><dt>Part of these strands</dt><dd class="chips">${strands}</dd></dl>` : ''}
      <details><summary>Why the model tagged it this way, and the technical tags</summary>
        <p>${esc(c.why)}</p><dl class="tech">${tech}</dl></details>`;
    card.hidden = false; empty.hidden = true; sidebar.classList.add('open');
    card.querySelectorAll('[data-step]').forEach(b => b.addEventListener('click', () => step(+b.dataset.step)));
    card.querySelector('.close').addEventListener('click', close);
    card.querySelectorAll('[data-strand]').forEach(b => b.addEventListener('click', () => setStrand(b.dataset.strand)));
    bindTerms(card);
  }
  function close() { current = null; card.hidden = true; empty.hidden = false; sidebar.classList.remove('open'); marks.forEach(m => m.classList.remove('active')); }
  function step(d) {
    const ids = visibleOrder(); if (!ids.length) return;
    const i = current ? ids.indexOf(current) : -1;
    const next = ids[Math.min(Math.max(i + d, 0), ids.length - 1)] ?? ids[0];
    open(next);
    const m = marks.find(x => x.dataset.ids.split(' ')[0] === next);
    if (m) { m.scrollIntoView({ block: 'center', behavior: 'smooth' }); m.focus({ preventScroll: true }); }
  }
  document.addEventListener('keydown', e => {
    if (page.dataset.mode !== 'read' || e.target.closest('input,textarea')) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
    if (e.key === 'Escape') { close(); pop.hidden = true; }
  });

  // Filters: all, punch lines only, or one strand
  let filter = { kind: 'all', strand: null };
  function visibleOrder() {
    return data.order.filter(id => (filter.kind !== 'punch' || data.cards[id].kind === 'punch')
      && (!filter.strand || data.strands[filter.strand].lines.includes(id)));
  }
  function applyFilter() {
    const on = new Set(visibleOrder());
    const filtering = filter.kind !== 'all' || filter.strand;
    story.classList.toggle('filtering', !!filtering);
    marks.forEach(m => m.classList.toggle('on', m.dataset.ids.split(' ').some(id => on.has(id))));
    document.querySelectorAll('.toolbar .chip').forEach(b => {
      const pressed = b.dataset.strand ? b.dataset.strand === filter.strand
        : b.dataset.filter === 'punch' ? filter.kind === 'punch' : !filter.strand && filter.kind === 'all';
      b.setAttribute('aria-pressed', String(pressed));
    });
  }
  function setStrand(id) { filter = { kind: 'all', strand: filter.strand === id ? null : id }; applyFilter(); }
  document.querySelectorAll('.toolbar .chip').forEach(b => b.addEventListener('click', () => {
    if (b.dataset.strand) return setStrand(b.dataset.strand);
    filter = { kind: b.dataset.filter, strand: null }; applyFilter();
  }));

  // Density rail: jump to a part of the story; mark where you are
  const paras = Array.from(story.querySelectorAll('.para'));
  const cells = Array.from(document.querySelectorAll('.cell'));
  cells.forEach(c => c.addEventListener('click', () => {
    const w = +c.dataset.w; const target = paras.find(p => +p.dataset.w >= w) || paras[paras.length - 1];
    target.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }));
  function here() {
    if (!cells.length) return;
    const top = paras.find(p => p.getBoundingClientRect().bottom > window.innerHeight * .3) || paras[0];
    const w = +top.dataset.w; let idx = 0;
    cells.forEach((c, i) => { if (+c.dataset.w <= w) idx = i; });
    cells.forEach((c, i) => c.classList.toggle('here', i === idx));
  }
  window.addEventListener('scroll', here, { passive: true }); here();

  // Glossary popovers
  function bindTerms(root) {
    root.querySelectorAll('abbr.term').forEach(a => {
      a.tabIndex = 0;
      const show = e => {
        e.stopPropagation();
        pop.innerHTML = `<strong>${esc(a.textContent)}</strong><br>${esc(data.glossary[a.dataset.term])}`;
        pop.hidden = false;
        const r = a.getBoundingClientRect(), t = pop.getBoundingClientRect();
        pop.style.left = Math.min(Math.max(8, r.left), window.innerWidth - t.width - 8) + 'px';
        pop.style.top = (r.bottom + 6 + t.height > window.innerHeight ? r.top - t.height - 6 : r.bottom + 6) + 'px';
      };
      a.addEventListener('click', show);
      a.addEventListener('keydown', e => { if (e.key === 'Enter') show(e); });
    });
  }
  bindTerms(document);
  document.addEventListener('click', e => { if (!e.target.closest('#pop')) pop.hidden = true; });
  window.addEventListener('scroll', () => { hideTip(); pop.hidden = true; }, { passive: true });
})();
"""


def _run_one(json_path: Path, story_path: Optional[Path], out_path: Optional[Path],
             title: Optional[str], text_level_path: Optional[Path]) -> None:
    analysis, _ = load_analysis(json_path)
    story_path = story_path or (INPUT_DIR / analysis.source_filename)
    if not story_path.exists():
        print(f"  ✗ story text not found: {story_path} (use --story)", file=sys.stderr)
        return
    text_level_path = text_level_path or (TEXT_LEVEL_DIR / f"{json_path.stem}.json")
    text_level = (TextLevelReport.model_validate_json(text_level_path.read_text(encoding="utf-8"))
                  if text_level_path.exists() else None)
    review = json_path.with_suffix(".xlsx")
    title = title or Path(analysis.source_filename).stem.replace("_", " ").title()
    page = build_reader(analysis, story_path.read_text(encoding="utf-8"), title, text_level,
                        review if review.exists() else None)
    out_path = out_path or json_path.with_suffix(".html")
    out_path.write_text(page, encoding="utf-8")
    print(f"  wrote {out_path}" + ("" if text_level else " (run analyze_text.py for the whole-story summary)"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a readable HTML view of an annotated story.")
    parser.add_argument("--json", type=Path, help="One analysis JSON (default: every JSON in output/).")
    parser.add_argument("--story", type=Path, help="Story text, if not input/<source_filename>.")
    parser.add_argument("--text-level", type=Path, help="Text-level results (default: output/text_level/<story>.json).")
    parser.add_argument("--title", help="Story title (default: from the file name).")
    parser.add_argument("--out", type=Path, help="Output .html (default: next to the JSON).")
    args = parser.parse_args()
    jobs = [args.json] if args.json else sorted(OUTPUT_DIR.glob("*.json"))
    if not jobs:
        print(f"No analysis JSON in {OUTPUT_DIR}. Run cli.py first.")
        return
    for jp in jobs:
        print(f"→ Building reader for {jp.name}")
        _run_one(jp, args.story, args.out if args.json else None,
                 args.title if args.json else None, args.text_level if args.json else None)


if __name__ == "__main__":
    main()
