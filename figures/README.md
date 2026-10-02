# Figures

Vector figures for papers, written in TikZ. Each `.tex` file compiles on
its own to a tightly cropped PDF:

```bash
cd figures
pdflatex pipeline.tex        # -> pipeline.pdf
```

No LaTeX installed? Upload the `.tex` file to Overleaf and compile it
there. Both figures are black and grey only, so they survive greyscale
printing, and they use Helvetica to sit well beside most journal text
faces. Include them at full text width:

```latex
\includegraphics[width=\textwidth]{pipeline}
```

## Figure 1: method overview (`pipeline.tex`)

Hand-drawn TikZ; edit labels directly in the file.

Draft caption:

> **Figure 1.** Overview of the GTVH Analyzer. (A) Each story is divided
> into narrative units and levels, and an inventory of likely targets is
> extracted. Humorous lines are then detected and annotated for five
> Knowledge Resources (SO script opposition, SI situation, TA target, NS
> narrative strategy, LA language; the logical mechanism is not annotated)
> and classified as jab or punch lines, and targets and situations are
> normalised to canonical labels. (B) Text-level measures (Attardo 2001)
> are computed deterministically from the annotations, using corrections
> made by an expert reviewer; a single model call interprets these
> aggregates and assigns one of Attardo's four humorous plot types.
> Shaded boxes are LLM calls, white boxes deterministic code, and the
> dashed box a human step.

## Figure 2: a story as a text vector (`text_figure.py`)

Generated from a story's analysis and text-level results, so it can be
redrawn for every story in a corpus:

```bash
python figures/text_figure.py --json output/story.json            # -> output/story_vector.tex and .pdf
python figures/text_figure.py --json output/story.json --strands 4 --features target,so_binary_category
```

`text_vector.tex`/`.pdf` here is drawn from the example in `example/`:
an original short story written for testing, with **hand-written
illustrative annotations**, not model output. Use a real story's results
in a paper.

Draft caption (adapt the counts to your story):

> **Figure 2.** *The Vicar's Bicycle* as a text vector, after Attardo
> (2002, Figs. 1 and 2). Top: humorous lines in each of ten sections of
> equal word count; hatched, a serious-relief stretch. Middle: the
> narrative segments (the Bishop's letter, NS-02, is embedded at level −1)
> and every humorous line. Bottom: the five largest strands, with the
> number of lines and their classification; shaded, combs; dashed arcs,
> bridges.

Thresholds for waves, relief, combs, bridges and centrality are the
documented defaults of `analyze_text.py` and are recorded in each
generated `.tex` file; report the values you used in the paper.
