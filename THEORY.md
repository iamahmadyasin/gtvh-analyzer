# Theoretical Choices

This document records what this project implements from the Semantic Script Theory of Humor (SSTH) and the General Theory of Verbal Humor (GTVH), what it deliberately leaves out, and where each choice is sourced from. It exists so that later contributors, including future us, don't have to reverse-engineer why a field exists by reading prompt history.

The prompts themselves are written as task specifications, not as theory. All theoretical justification lives here, so the prompts can stay lean.


## Lineage of the theory

The framework this project applies evolved over time. Semantic Script Theory of Humor (Raskin, 1985)
originally proposed the hypothesis that laid out the necessary linguistic conditions for a text to be funny. General Theory of Verbal Humor (GTVH), proposed by Attardo and Raskin (1991) was an extension of SSTH by adding the six hierarchical Knowledge Resources. Attardo (2001) extended the theory from single jokes to arbitrary-length narrative texts, introducing the machinery this project depends on most heavily: jab lines, punch lines, narrative levels, and the discrete-vs-diffuse disjunctor distinction. Attardo (2020) updated it with contemporary empirical research, refining individual Knowledge Resources in light of newer findings.
This project draws its core annotation scheme from the long-text framework.

## Foundational hypothesis

Raskin (1985) hypothesized that a text is humorous if and only if:
(1) it is compatible, fully or in part, with two different scripts, and
(2) the two scripts are opposite.

The GTVH (Attardo, 1994) organizes humor analysis around six ordered Knowledge Resources: Script Opposition (SO), Logical Mechanism (LM), Situation (SI), Target (TA), Narrative Strategy (NS), and Language (LA). This project implements five of the six (LM is excluded).

## What we implement

### SO

Implemented at three levels of abstraction, annotated hierarchically:

- **Concrete** — the specific opposed script pair.
- **Intermediate** — the binary opposition type: good/bad, life/death,
  obscene/non-obscene, money/no-money, high/low stature, or none.
- **Abstract** — the three types of real vs. unreal opposition: actual/non-actual, 
  normal/abnormal, possible/impossible.

Raskin's (1985) theory walks through a symbolic combinatorial search to identify the two scripts. This project does not ask the LLM to replicate that procedure, it asks for the output reached the way a trained human analyst would reach it. This is a project design decision, not a claim about the theory.

#### Trigger / disjunctor

The **disjunctor** i.e. the specific trigger that flips the reader from the first script to the second. Its location and existence are live concepts in the long-text framework Attardo (2001). This project captures that distinction through the `line_type` field (`discrete` / `register_clash` / `irony`) and through disjunctor detection in Stage 2 (`disjunctor`, `disjunctor_span`).

### LM

Logical Mechanism is not implemented. A scoping decision, not a theoretical one. Attardo's (2005) taxonomy of logical mechanisms needs substantially more prompt-engineering, resources and  evaluation work than the other five KRs combined.

### SI

The Situation KR refers to the specific topic or "props" of the joke. It is the collection of objects, participants, instruments, activities, and settings that the text is about (Attardo, 1994). Situation is implemented as a single short phrase, or `"cotext"` or `"irr"`. *"Cotext"* is Attardo's own term, used throughout the case-study annotations in *Humorous Texts* (2001).
Attardo (2020) clarified that ackgrounded incongruities i.e. standing narrative premises the reader
has already accepted (a talking-animal world, an established liar) belong in SI.

### TA

The is the Knowledge Resource within the GTVH that specifies the entity that serves as the butt of the joke (Attardo, 1994). Target identifies who or what the humor aggressively attacks, `null` when non-aggressive. Every joke has an orientation (Attardo, 2020), but only some carry an aggressive target. Orientation identifies the directional orientation in our annotation scheme.

### NS

The Narrative Strategy is the Knowledge Resource that accounts for the formal, structural organization of the joke text. It can be understood as the joke's genre or, more precisely, its microgenre (Attardo, 1994). A freeform label from a suggested menu (joke, pun, riddle, dialogue, speech, etc.), with the model free to supply its own closest fit.

### LA

The Language knowledge resource encompasses all the linguistic information required for the complete verbalization of a text (Attardo, 1994). Restricted, by design, to detecting whether humor is verbal as opposed to referential, rather than full stylistic analysis. Two independent blocks:

- **Wordplay** — phonological / morphological / lexical / syntactic levels. The four-way linguistic-level split is this project's own operationalization for LLM annotation, grounded in the GTVH treatment of the Language KR.
- **Register effect** — a marked register choice.

## Other pipeline-level design decisions

- **Diffuse disjunctors as line types.** `register_clash` and `irony` sit alongside `discrete` as line types because they need different *detection* heuristics before any KR annotation. You can't find a register clash by looking for a single trigger word.
- **Jab vs. punch via narrative position**, and **narrative level** tracking (level_0 main storyline, level_-1/-2 embedded, level_+1/+2 framing).
- **Uncertainty marking with `(?)`.** Attardo's (2001) own case-study annotations mark uncertain values this way rather than forcing an answer; the prompts ask the model to do the same.

## References

- Attardo, S. (1994). *Linguistic theories of humor.* Mouton de Gruyter.
- Attardo, S. (2001). *Humorous texts: A semantic and pragmatic analysis.* Walter de Gruyter.
- Attardo, S. (2005). *A catalog of logical mechanisms* [Unpublished manuscript].
- Attardo, S. (2020). *The linguistics of humor: An introduction.* Oxford University Press.
- Attardo, S., & Raskin, V. (1991). *Script theory revis(it)ed: Joke similarity and joke representation model.* Humor: International Journal of Humor Research, 4(3-4), 293–347.
- Raskin, V. (1985). Semantic mechanisms of humor. D. Reidel.
