"""
Draw one story as a text vector, in the manner of Attardo's figures for
Lord Arthur Savile's Crime and Sexton's "Cinderella" (Attardo 2001; 2002,
Figures 1 and 2): the text runs left to right, and four aligned panels
show where its humour falls.

  1. Humorous lines per equal word-count section, with serious-relief
     stretches hatched and waves marked.
  2. The narrative segments (embedded ones, such as letters, below).
  3. Every humorous line: jab lines as ticks, punch lines as triangles.
  4. The largest strands, one row each: combs are shaded, bridges arc
     between the two lines they join.

Writes a standalone TikZ file and, if pdflatex is installed, compiles it
to a cropped vector PDF ready for \\includegraphics.

    python figures/text_figure.py --json output/story.json
    python figures/text_figure.py --json figures/example/the_vicars_bicycle.json \\
        --story figures/example/the_vicars_bicycle.txt \\
        --text-level figures/example/the_vicars_bicycle.text_level.json \\
        --out figures/text_vector.tex

Greyscale-safe: everything is told apart by shape, hatching and line style.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from schemas import Analysis, TextLevelReport  # noqa: E402
from textlevel import load_analysis  # noqa: E402

# Strand rows: which single-feature strands to draw, and how to label them.
FEATURE_LABEL = {
    "target": "TA", "situation": "SI", "so_binary_category": "SO",
    "opposition_type": "SO type", "narrative_strategy": "NS",
    "target_social_class": "TA class", "target_sphere": "TA sphere",
    "target_kind": "TA kind", "orientation": "TA orientation",
    "wordplay_level": "LA wordplay", "register_effect": "LA register",
}
VALUE_LABEL = {
    "good_bad": "good/bad", "life_death": "life/death", "obscene_nonobscene": "obscene/non-obscene",
    "money_nomoney": "money/no money", "high_low_stature": "high/low stature",
    "actual_vs_nonactual": "actual/non-actual", "normal_vs_abnormal": "normal/abnormal",
    "possible_vs_impossible": "possible/impossible",
}

WIDTH = 11.6     # cm, the text axis
LEFT = 0.0       # x of word 0
BAR_H = 1.6      # cm, tallest bar


def tex(s: str) -> str:
    """Escape text for LaTeX."""
    out = []
    for ch in s:
        out.append({"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
                    "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}.get(ch, ch))
    return "".join(out)


def _nice_step(total: int) -> int:
    for step in (50, 100, 200, 250, 500, 1000, 2000, 2500, 5000):
        if total / step <= 8:
            return step
    return 10000


def build(analysis: Analysis, report: TextLevelReport, story_text: str, title: str | None,
          features: list[str], max_strands: int) -> str:
    m = report.metrics
    d = m.distribution
    total = max(d.n_words, 1)
    x = lambda w: LEFT + WIDTH * w / total  # noqa: E731
    lf = {line.line_id: line for line in m.lines}
    out: list[str] = []
    emit = out.append

    # ---------- panel 1: lines per section ----------
    top = max((s.n_lines for s in d.sections), default=1) or 1
    y0 = 0.0
    emit(f"% panel 1: humorous lines per section ({d.n_sections} sections)")
    for st in d.serious_reliefs:
        emit(rf"\fill[pattern=north east lines, pattern color=black!45] ({x(st.word_start):.3f},{y0}) "
             rf"rectangle ({x(st.word_end):.3f},{y0 + BAR_H:.3f});")
    for s in d.sections:
        if s.n_lines:
            h = BAR_H * s.n_lines / top
            emit(rf"\filldraw[fill=black!22, draw=black!80, line width=0.4pt] "
                 rf"({x(s.word_start) + 0.03:.3f},{y0}) rectangle ({x(s.word_end) - 0.03:.3f},{y0 + h:.3f});")
    for w in d.waves:
        emit(rf"\node[font=\scriptsize\bfseries, anchor=south] at ({(x(w.word_start) + x(w.word_end)) / 2:.3f},{y0 + BAR_H + 0.02:.3f}) "
             rf"{{wave}};")
    for st in d.serious_reliefs:
        emit(rf"\node[font=\scriptsize\itshape, fill=white, inner sep=1pt] at ({(x(st.word_start) + x(st.word_end)) / 2:.3f},{y0 + BAR_H * 0.55:.3f}) "
             rf"{{serious relief}};")
    emit(rf"\draw[black!70] ({LEFT},{y0}) -- ({LEFT + WIDTH},{y0});")
    emit(rf"\draw[black!70] ({LEFT},{y0}) -- ({LEFT},{y0 + BAR_H});")
    for v in sorted({0, top}):
        emit(rf"\node[font=\tiny, anchor=east] at ({LEFT - 0.05},{y0 + BAR_H * v / top:.3f}) {{{v}}};")
    summary = (rf"\\\textcolor{{black!60}}{{{d.n_lines} lines, one per {d.words_per_line:.0f} words}}"
               if d.words_per_line else "")
    emit(rf"\node[rowlabel] at ({LEFT - 0.45},{y0 + BAR_H / 2}) {{Lines per section{summary}}};")

    # ---------- panel 2: segments ----------
    y = -0.85
    emit("% panel 2: narrative segments")
    offsets = _segment_words(story_text)
    top_level = [s for s in analysis.segments if s.narrative_level.value in ("level_0", "level_+1", "level_+2")]
    embedded = [s for s in analysis.segments if s not in top_level]
    for seg in top_level:
        a, b = offsets(seg.line_start, seg.line_end)
        emit(rf"\draw[thick, fill=white] ({x(a):.3f},{y - 0.22}) rectangle ({x(b):.3f},{y + 0.22});")
        emit(rf"\node[font=\scriptsize, text width={max(x(b) - x(a) - 0.1, 0.3):.2f}cm, align=center] "
             rf"at ({(x(a) + x(b)) / 2:.3f},{y}) {{{tex(seg.segment_id)}}};")
    for seg in embedded:
        a, b = offsets(seg.line_start, seg.line_end)
        emit(rf"\draw[thick, densely dashed, fill=black!8] ({x(a):.3f},{y - 0.62}) rectangle ({x(b):.3f},{y - 0.32});")
        emit(rf"\node[font=\tiny] at ({(x(a) + x(b)) / 2:.3f},{y - 0.47}) {{{tex(seg.segment_id)}}};")
    emit(rf"\node[rowlabel] at ({LEFT - 0.45},{y - (0.2 if embedded else 0)}) {{Segments}};")

    # ---------- panel 3: all lines ----------
    y = -2.0 if embedded else -1.6
    emit("% panel 3: every humorous line")
    emit(rf"\draw[black!35] ({LEFT},{y}) -- ({LEFT + WIDTH},{y});")
    for line in m.lines:
        px = LEFT + WIDTH * line.position
        if line.classification == "punch":
            emit(rf"\fill ({px:.3f},{y - 0.02}) -- ++(-0.09,0.24) -- ++(0.18,0) -- cycle;")
        else:
            emit(rf"\draw[thick] ({px:.3f},{y - 0.14}) -- ({px:.3f},{y + 0.14});")
    emit(rf"\node[rowlabel] at ({LEFT - 0.45},{y}) {{All lines}};")

    # ---------- panel 4: strands ----------
    chosen = [s for s in m.strands
              if len(s.features) == 1 and s.features[0].feature in features][:max_strands]
    combs = {c.comb_id: c for c in m.combs}
    bridges = {b.bridge_id: b for b in m.bridges}
    emit("% panel 4: strands")
    for i, s in enumerate(chosen):
        y = (-2.75 if embedded else -2.35) - 0.7 * i
        f = s.features[0]
        value = VALUE_LABEL.get(f.value, f.value)
        value = "the " + value[4:] if value.startswith("The ") else value
        label = f"{FEATURE_LABEL.get(f.feature, f.feature)}: {value}"
        emit(rf"\draw[black!25] ({LEFT},{y}) -- ({LEFT + WIDTH},{y});")
        for cid in s.comb_ids:
            c = combs[cid]
            emit(rf"\fill[black!14, rounded corners=2pt] ({x(c.word_start) - 0.08:.3f},{y - 0.17}) "
                 rf"rectangle ({x(c.word_end) + 0.08:.3f},{y + 0.17});")
        for bid in s.bridge_ids:
            b = bridges[bid]
            xa, xb = LEFT + WIDTH * lf[b.from_line_id].position, LEFT + WIDTH * lf[b.to_line_id].position
            emit(rf"\draw[densely dashed, thick] ({xa:.3f},{y + 0.08}) .. controls ({xa:.3f},{y + 0.42}) "
                 rf"and ({xb:.3f},{y + 0.42}) .. ({xb:.3f},{y + 0.08});")
        for lid in s.line_ids:
            px = LEFT + WIDTH * lf[lid].position
            style = "fill=black" if lf[lid].classification == "punch" else "fill=white, draw=black, thick"
            emit(rf"\filldraw[{style}] ({px:.3f},{y}) circle (0.075);")
        emit(rf"\node[rowlabel] at ({LEFT - 0.45},{y}) "
             rf"{{{tex(label)} \textcolor{{black!60}}{{({s.n_lines}, {s.centrality})}}}};")
    y_axis = (-2.75 if embedded else -2.35) - 0.7 * max(len(chosen), 1) + 0.15

    # ---------- axis ----------
    step = _nice_step(total)
    emit(rf"\draw[black!70] ({LEFT},{y_axis}) -- ({LEFT + WIDTH},{y_axis});")
    for w in range(0, total + 1, step):
        emit(rf"\draw[black!70] ({x(w):.3f},{y_axis}) -- ++(0,-0.08) node[below, font=\tiny] {{{w}}};")
    emit(rf"\node[font=\scriptsize, anchor=north] at ({LEFT + WIDTH / 2},{y_axis - 0.32}) "
         rf"{{Position in text (words)}};")

    # ---------- legend ----------
    ly = y_axis - 1.0
    emit("% legend")
    emit(rf"\draw[thick] ({LEFT},{ly - 0.12}) -- ({LEFT},{ly + 0.12}); "
         rf"\node[legend] at ({LEFT + 0.12},{ly}) {{jab line}};")
    emit(rf"\fill ({LEFT + 1.55},{ly - 0.1}) -- ++(-0.09,0.22) -- ++(0.18,0) -- cycle; "
         rf"\node[legend] at ({LEFT + 1.7},{ly}) {{punch line}};")
    emit(rf"\filldraw[fill=white, draw=black, thick] ({LEFT + 3.4},{ly}) circle (0.075); "
         rf"\filldraw[fill=black] ({LEFT + 3.62},{ly}) circle (0.075); "
         rf"\node[legend] at ({LEFT + 3.8},{ly}) {{line in a strand (jab, punch)}};")
    emit(rf"\fill[black!14, rounded corners=2pt] ({LEFT + 7.1},{ly - 0.15}) rectangle ({LEFT + 7.6},{ly + 0.15}); "
         rf"\node[legend] at ({LEFT + 7.7},{ly}) {{comb}};")
    emit(rf"\draw[densely dashed, thick] ({LEFT + 8.6},{ly - 0.08}) .. controls ({LEFT + 8.6},{ly + 0.2}) "
         rf"and ({LEFT + 9.1},{ly + 0.2}) .. ({LEFT + 9.1},{ly - 0.08}); "
         rf"\node[legend] at ({LEFT + 9.2},{ly}) {{bridge}};")
    emit(rf"\fill[pattern=north east lines, pattern color=black!45] ({LEFT + 10.1},{ly - 0.15}) rectangle ({LEFT + 10.6},{ly + 0.15}); "
         rf"\node[legend] at ({LEFT + 10.7},{ly}) {{serious relief}};")

    heading = (rf"\node[font=\footnotesize\bfseries, anchor=south west] at ({LEFT - 3.0},{BAR_H + 0.35}) "
               rf"{{{tex(title)}}};") if title else ""
    p = m.params
    note = (f"% Parameters: {d.n_sections} sections; strands of >= {p.get('min_strand_lines')} lines; "
            f"central span >= {p.get('central_min_span')}, peripheral <= {p.get('peripheral_max_span')}; "
            f"comb gap <= {p.get('comb_max_gap')}; bridge gap >= {p.get('bridge_min_gap')} of the text.")
    return TEMPLATE.replace("%BODY%", "\n".join([note, heading, *out]))


def _segment_words(story_text: str):
    """Word range (start, end) covered by story lines a..b, inclusive."""
    starts, total = [], 0
    for line in story_text.splitlines():
        starts.append(total)
        total += len(line.split())

    def span(a: int, b: int) -> tuple[int, int]:
        a0 = starts[a - 1] if 0 < a <= len(starts) else 0
        b1 = starts[b] if b < len(starts) else total
        return a0, b1
    return span


TEMPLATE = r"""% Figure: a story as a text vector (Attardo 2001, 2002).
% Generated by figures/text_figure.py; edit the script, not this file.
% Compile: pdflatex <this file>   Include: \includegraphics[width=\textwidth]{<pdf>}
\documentclass[border=4pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage[scaled=0.92]{helvet}
\renewcommand{\familydefault}{\sfdefault}
\usepackage{xcolor}
\usepackage{tikz}
\usetikzlibrary{patterns}
\hyphenpenalty=10000 \exhyphenpenalty=10000
\begin{document}
\begin{tikzpicture}[
  rowlabel/.style={font=\scriptsize, anchor=east, align=right, text width=3.3cm},
  legend/.style={font=\scriptsize, anchor=west, inner sep=1pt},
]
%BODY%
\end{tikzpicture}
\end{document}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Draw a story as a text vector (TikZ).")
    ap.add_argument("--json", type=Path, required=True, help="Analysis JSON of one story.")
    ap.add_argument("--story", type=Path, help="Story text (default: input/<source_filename>).")
    ap.add_argument("--text-level", type=Path,
                    help="Text-level results (default: output/text_level/<story>.json).")
    ap.add_argument("--out", type=Path, help="Output .tex (default: next to the analysis, *_vector.tex).")
    ap.add_argument("--title", help="Heading drawn above the figure (default: none; use the caption).")
    ap.add_argument("--features", default="target,situation,so_binary_category",
                    help="Strand features to draw, comma-separated (default: target,situation,so_binary_category).")
    ap.add_argument("--strands", type=int, default=5, help="How many strand rows (default: 5).")
    ap.add_argument("--no-compile", action="store_true", help="Write the .tex only.")
    args = ap.parse_args()

    analysis, _ = load_analysis(args.json)
    tl_path = args.text_level or (ROOT / "output" / "text_level" / f"{args.json.stem}.json")
    if not tl_path.exists():
        sys.exit(f"text-level results not found: {tl_path} (run analyze_text.py first)")
    report = TextLevelReport.model_validate_json(tl_path.read_text(encoding="utf-8"))
    story_path = args.story or (ROOT / "input" / analysis.source_filename)
    if not story_path.exists():
        sys.exit(f"story text not found: {story_path} (use --story)")
    out = args.out or args.json.with_name(f"{args.json.stem}_vector.tex")
    out.write_text(build(analysis, report, story_path.read_text(encoding="utf-8"), args.title,
                         args.features.split(","), args.strands), encoding="utf-8")
    print(f"wrote {out}")
    if not args.no_compile:
        try:
            subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", out.name],
                           cwd=out.parent, check=True, capture_output=True)
            print(f"wrote {out.with_suffix('.pdf')}")
        except FileNotFoundError:
            print("pdflatex not found: compile the .tex yourself (or on Overleaf)")
        except subprocess.CalledProcessError as exc:
            sys.exit(f"pdflatex failed; see {out.with_suffix('.log')}\n{exc.stdout.decode()[-800:]}")


if __name__ == "__main__":
    main()
