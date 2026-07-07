# GTVH Humor Analyzer

A multi-stage LLM pipeline for annotating humorous short stories by computationally operationalizing the General Theory of Verbal Humor (Attardo 1994, 2001, 2020) and the
Semantic-Script Theory of Humor (Raskin 1985).

Each humorous instance ("line") in a story is located, classified as
`jab` / `punch` / `register_clash` / `irony`, and annotated with:

- **SO** — Script Opposition (Raskin's full framework: script labels,
  real/unreal situations, opposition type, binary category, overlap
  degree, trigger type)
- **SI** — Situation
- **TA** — Target
- **NS** — Narrative Strategy
- **LA** — Language

Logical Mechanism (LM) is intentionally not included because of it's controversial nature.

## Folder structure

```
gtvh-analyzer/
├── input/                    # drop .txt story files here
├── output/                   # analysis JSON lands here
├── prompts/
│   ├── segment.md            # Stage 1
│   ├── detect_lines.md       # Stage 2
│   └── annotate_krs.md       # Stage 3
├── stages/
│   ├── segment.py
│   ├── detect.py
│   └── annotate.py
├── schemas.py                # Pydantic schemas
├── llm.py                    # OpenAI structured-output wrapper
├── pipeline.py               # end-to-end orchestration
├── cli.py                    # entry point
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste your OpenAI API key
```

## Run

**Batch mode:** process every `.txt` in `input/`:

```bash
python cli.py
```

**Single file mode:**

```bash
python cli.py --file path/to/story.txt --out path/to/analysis.json
```

**Options:**

```bash
python cli.py --model gpt-4.1 --detect-concurrency 5 --annotate-concurrency 10
```

Output JSON validates against `schemas.Analysis`.

## Pipeline stages

1. **Segmentation** — partitions the story into narrative segments
   (level_0 main storyline, level_-1 embedded narratives, etc.) using
   metatextual markers, setting changes, character entries/exits.
   One LLM call per story.

2. **Line detection** — for each segment, locates candidate humorous
   spans and classifies them as `discrete` (single-trigger), `register_clash`
   (diffuse register humor), or `irony`. One LLM call per segment,
   fanned out concurrently.

3. **KR annotation** — for each detected line, fills in the full KR
   bundle with local context. One LLM call per line, heavily
   parallelized.

Prompts are versioned as `.md` files in `prompts/`. Edit them without
touching the code.

## Iterating on prompts

The interesting work is prompt iteration. To rerun just Stage 3
against an existing Stage 1 + 2 result, you can call the stages
directly from a Python shell — they're pure `async` functions taking
Pydantic objects.

## Theoretical grounding

- Raskin, V. (1985). *Semantic Mechanisms of Humor.* D. Reidel.
- Attardo, S. (1994). *Linguistic theories of humor.* Mouton de Gruyter.
- Attardo, S. (2001). *Humorous Texts: A Semantic and Pragmatic Analysis.* Walter de Gruyter.
- Attardo, S. (2020). *The Linguistics of Humor: An Introduction.* Oxford University Press.

Script opposition types (actual/non-actual, normal/abnormal,
possible/impossible), the eight-way trigger typology, and the
overlap-degree distinction come from Raskin (1985). The
jab/punch distinction, narrative-level notation, and diffuse-disjunctor
categories (register clash, irony) come from Attardo (2001). The
local-antonymy refinement (scripts share most structure, differ in
one crucial characteristic) is Tinholt (2007) via Attardo (2020).
