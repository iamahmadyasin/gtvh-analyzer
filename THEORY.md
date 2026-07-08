# Theoretical Choices

This document records what this project implements from the Semantic
Script Theory of Humor (SSTH) and the General Theory of Verbal Humor
(GTVH), what it deliberately leaves out, and where each choice is
sourced from. It exists so that later contributors — including future
us — don't have to reverse-engineer *why* a field exists by reading
prompt history.

The prompts themselves are written as task specifications, not as
theory. All theoretical justification lives here, so the prompts can
stay lean.

**A note on sourcing.** Some content below comes from source chapters
read in full during development (cited with book + chapter). Some comes
from prompt edits that carry their own citations to sources not directly
supplied; those are marked **[cited in prompt, not independently
verified]**. APA-formatted references will be added separately.

## Lineage of the theory

The framework this project applies evolved across four main stages:

1. **The original GTVH (Attardo & Raskin, 1991).** The GTVH is first
   proposed in a 1991 paper, extending Raskin's earlier Semantic Script
   Theory of Humor (SSTH; Raskin, 1985) by adding the six ordered
   Knowledge Resources.

2. **The full theory (Attardo, 1994).** The complete framework is laid
   out in Attardo's 1994 book.

3. **Extension to longer texts (Attardo, 2001).** *Humorous Texts: A
   Semantic and Pragmatic Analysis* extends the theory from single
   jokes to arbitrary-length narrative texts, introducing the machinery
   this project depends on most heavily: jab lines, punch lines,
   narrative levels, and the discrete-vs-diffuse disjunctor distinction.

4. **Modern update (Attardo, 2020).** *The Linguistics of Humor: An
   Introduction* does not extend the theory to new text types so much as
   *update* it with contemporary empirical research — refining
   individual Knowledge Resources (for example, the treatment of Target
   as orientation, and the treatment of Language) in light of newer
   findings.

This project draws its core annotation scheme from the 2001 long-text
framework and folds in specific 2020-era refinements where they improve
the annotation (noted per-KR below).

## Foundational hypothesis

**SSTH (Raskin, 1985).** A text carries a single joke if and only if
(1) it is compatible, fully or in part, with two different scripts, and
(2) the two scripts are *opposite*. This necessary-and-sufficient core
underlies the whole pipeline.

**GTVH Knowledge Resources.** The GTVH organizes humor analysis around
six ordered Knowledge Resources: Script Opposition (SO), Logical
Mechanism (LM), Situation (SI), Target (TA), Narrative Strategy (NS),
and Language (LA). This project implements five of the six (LM is
excluded — see below).

## What we implement, Knowledge Resource by Knowledge Resource

### SO — Script Opposition

Implemented at three levels of abstraction, annotated concrete-up:

- **Concrete** — the specific opposed script pair (`script_1`,
  `script_2`), labeled so a reader can reconstruct the opposition from
  the labels alone.
- **Intermediate** — the essential binary category
  (`essential_binary_category`): good/bad, life/death,
  obscene/non-obscene, money/no-money, high/low stature, or none.
- **Abstract** — the opposition type (`opposition_type`): Raskin's
  three types, actual/non-actual, normal/abnormal, possible/impossible.

**Local antonymy.** Script 1 and Script 2 are not opposites in the
ordinary sense; they share most of their content and differ in one
crucial respect, opposed only for the purposes of this text. The prompt
states this in plain language without citation. *Source: Tinholt (2007),
as presented in Attardo (2020), Ch. 6.*

**Heuristic, not symbolic, reasoning.** Raskin's original worked example
walks through a symbolic combinatorial search to recover the two scripts.
This project does not ask the LLM to replicate that procedure — it asks
for the same output (identified scripts, identified opposition) reached
the way a trained human analyst would reach it. This is a project design
decision, not a claim about the theory.

**Deliberately cut from SO.** Three sub-features present in the source
theory were removed because they carry little signal for this project's
goal — extracting thematic and stylistic insight from stories, not
answering theoretical questions about GTVH:

- **Overlap degree** (full / partial / truly-partial) — a measure of how
  cleanly the two scripts co-exist in the text. Raskin tracks this for a
  theory of joke *structure*; it says little about what a story is about,
  who it targets, or how it builds humor. Reintroducible as a single
  field if a downstream insight ever needs it.
- **Real/unreal situation descriptions** (the paired one-sentence
  descriptions of the actual vs. opposed situation) — removed as
  low-value per-line overhead. Note that "real vs. unreal" persists at
  the abstract level: the three opposition types are themselves flavors
  of the real/unreal dichotomy, so the concept is retained where it does
  analytical work.
- **Shadow opposition** (a secondary reversed opposition running
  alongside the main one) — niche, rarely fires, cut as overhead.

### Trigger / disjunctor — location kept, typology cut

The **disjunctor** — the specific element that flips the reader from the
first script to the second — is retained. Its *location and existence*
are live concepts in the 2001 long-text framework: Attardo opens the
long-text treatment with the discrete-vs-diffuse disjunctor distinction
(*Humorous Texts*, §6.0.1, "Discrete or diffuse disjunctors"). This
project captures that distinction through the `line_type` field
(`discrete` / `register_clash` / `irony`) and through disjunctor
detection in Stage 2 (`disjunctor`, `disjunctor_span`).

Raskin's fine-grained **eight-way typology** of the trigger (the
ambiguity / contradiction subtypes) was cut. It is a joke-level
mechanism detail from the SSTH, not one of the six Knowledge Resources,
and — as far as the case studies reviewed show — not applied as a
per-line annotation field in the *Humorous Texts* long-text analyses.
For this project's insight-extraction goal it is close to inert, and
the analytically useful part (verbal technique) is already captured by
the Language KR's wordplay level. *Basis: Raskin (1985) §5, in Attardo
(2001), Ch. 4, for the typology itself; the discrete/diffuse distinction
from Attardo (2001), Ch. 6.*

### LM — Logical Mechanism (excluded)

Not implemented — a scoping decision, not a theoretical one. Raskin
himself flags LM as the most contested KR, and Attardo's taxonomy of
logical mechanisms (Di Maio's ~27-item list: garden path, figure-ground
reversal, false analogy, chiasmus, and so on) needs substantially more
prompt-engineering and evaluation work than the other five KRs combined.
Reserved for a future version.

### SI — Situation

Implemented as a single short phrase, or `"cotext"` (situation inherited
from surrounding narrative) or `"irr"`. *"Cotext"* is Attardo's own term,
used throughout the case-study annotations in *Humorous Texts* (2001).

**Backgrounded incongruities** — standing narrative premises the reader
has already accepted (a talking-animal world, an established liar) belong
in SI, not in the current line's SO; a line's opposition uses the world
SI has built rather than re-opening a settled premise. **[cited in prompt
as Hempelmann & Attardo (2011) and Attardo (2020) §7.1.4; not
independently verified]**.

### TA — Target (+ Orientation)

- **Target** (who or what the humor aggressively attacks, `null` when
  non-aggressive) is the original GTVH Target KR. *Source: Attardo
  (2001), throughout the case-study annotations.*
- **Orientation** (self / hearer / other / situation — where the humor
  points, independent of aggression) is a 2020-era refinement: every
  humorous line has a directional orientation, but only some carry an
  aggressive target. **[cited in prompt as Priego-Valverde et al. (2018),
  via Attardo (2020) §7.1.3; not independently verified]**.

### NS — Narrative Strategy

A freeform label from a suggested menu (joke, pun, riddle, dialogue,
speech, etc.), with the model free to supply its own closest fit.
*Source: Attardo (2001).*

Two structural patterns are named when present:

- **`three_step_sequence`** (AAB — two parallel setups, breaking third)
  **[cited in prompt as Rozin et al. (2006); not independently
  verified]**.
- **`compound`** (multiple punch lines in one segment, each with its own
  opposition) **[cited in prompt as Hockett (1977) and Norrick (2010);
  not independently verified]**. Note: Attardo (2001), Ch. 4, independently
  discusses multi-opposition "compound jokes" under the SSTH — consistent
  with, but a separate source from, the Hockett/Norrick citation.

### LA — Language

Restricted, by design, to detecting whether humor is wording-dependent,
rather than full stylistic analysis. Two independent blocks:

- **Wordplay** — phonological / morphological / lexical / syntactic
  levels, diagnosed by a paraphrase test (does the humor survive
  rewording?). The four-way linguistic-level split is this project's own
  operationalization for LLM annotation, grounded in the GTVH treatment
  of the Language KR as covering verbal vs. referential humor (*Source:
  Attardo (2001)*).
- **Register effect** — a marked register choice (elevated diction on a
  low subject, jargon for triviality, sacred vocabulary for the profane),
  diagnosed by a register-neutralizing paraphrase test. *Source: register
  humor as a diffuse disjunctor, Attardo (2001), §6.1 ("Register humor").*

## Other pipeline-level design decisions

- **Diffuse disjunctors as line types.** `register_clash` and `irony`
  sit alongside `discrete` as line types because they need different
  *detection* heuristics before any KR annotation — you can't find a
  register clash by looking for a single trigger word. *Source: Attardo
  (2001), Ch. 6, "Register humor" and "Irony and Humor."*
- **Jab vs. punch via narrative position**, and **narrative level**
  tracking (level_0 main storyline, level_-1/-2 embedded, level_+1/+2
  framing) — *Source: Attardo (2001), the segmentation and classification
  machinery across the Ch. 7 case studies.*
- **Uncertainty marking with `(?)`.** Attardo's own case-study
  annotations mark uncertain values this way rather than forcing a
  confident answer; the prompts ask the model to do the same. *Source:
  Attardo (2001), Ch. 7 case-study annotations.*

## References

APA-formatted references to be added by the maintainer. Works cited
above:

- Attardo, S., & Raskin, V. (1991).
- Attardo, S. (1994).
- Attardo, S. (2001). *Humorous Texts: A Semantic and Pragmatic
  Analysis.*
- Attardo, S. (2020). *The Linguistics of Humor: An Introduction.*
- Raskin, V. (1985). *Semantic Mechanisms of Humor.*
- Tinholt, H. W. (2007). — as presented in Attardo (2020), Ch. 6.
- Hempelmann, C. F., & Attardo, S. (2011). — cited in prompt; not
  independently verified.
- Priego-Valverde, B., et al. (2018). — cited in prompt via Attardo
  (2020); not independently verified.
- Rozin, P., et al. (2006). — cited in prompt; not independently
  verified.
- Hockett, C. F. (1977). — cited in prompt; not independently verified.
- Norrick, N. R. (2010). — cited in prompt; not independently verified.
