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

- **Concrete**: the specific opposed script pair.
- **Intermediate**: the binary opposition type: good/bad, life/death,
  obscene/non-obscene, money/no-money, high/low stature, or none.
- **Abstract**: the three types of real vs. unreal opposition: actual/non-actual, 
  normal/abnormal, possible/impossible.

Raskin's (1985) theory walks through a symbolic combinatorial search to identify the two scripts. This project does not ask the LLM to replicate that procedure, it asks for the output reached the way a trained human analyst would reach it. This is a project design decision, not a claim about the theory.

#### Trigger / disjunctor

The **disjunctor** i.e. the specific trigger that flips the reader from the first script to the second. Its location and existence are live concepts in the long-text framework Attardo (2001). This project captures that distinction through the `line_type` field (`discrete` / `register_clash` / `irony`) and through disjunctor detection in Stage 2 (`disjunctor`, `disjunctor_span`).

### LM

Logical Mechanism is not implemented. A scoping decision, not a theoretical one. Attardo's (2005) taxonomy of logical mechanisms needs substantially more prompt-engineering, resources and  evaluation work than the other five KRs combined.

### SI

The Situation KR refers to the specific topic or "props" of the joke. It is the collection of objects, participants, instruments, activities, and settings that the text is about (Attardo, 1994). Situation is implemented as a single short phrase, or `"cotext"` or `"irr"`. *"Cotext"* is Attardo's own term, used throughout the case-study annotations in *Humorous Texts* (2001).
Because strands connect lines through shared values, each line also gets a **canonical situation**: the story's paraphrases of one frame are grouped under the most frequent wording (embeddings, or string similarity as a fallback). `cotext` and `irr` are never merged with anything, since they mean "no distinctive frame", not a shared one. Reviewers can correct the canonical value.
Attardo (2020) clarified that ackgrounded incongruities i.e. standing narrative premises the reader
has already accepted (a talking-animal world, an established liar) belong in SI.

### TA

The is the Knowledge Resource within the GTVH that specifies the entity that serves as the butt of the joke (Attardo, 1994). Target identifies who or what the humor aggressively attacks, `null` when non-aggressive. Every joke has an orientation (Attardo, 2020), but only some carry an aggressive target. Orientation identifies the directional orientation in our annotation scheme.

A per-story **target inventory** (one call before annotation) lists the characters, groups, institutions and ideas the story is likely to target. Each entry is tagged with its kind, social class and social sphere. The annotation call reuses an inventory entry whenever one fits, so the same butt carries the same label across lines; new targets are grouped by similarity. The attributes exist because Attardo's own example of a socially meaningful strand is defined by a shared *feature* of the targets, not by an identical target: "a strand of jab lines having TAs that all share certain features, such as 'nobility' or 'upper class'" (Attardo, 2002, p. 243).

### NS

The Narrative Strategy is the Knowledge Resource that accounts for the formal, structural organization of the joke text. It can be understood as the joke's genre or, more precisely, its microgenre (Attardo, 1994). Implemented as a fixed list describing how the humorous line is delivered: narration, narrator aside, free indirect thought, single utterance, dialogue exchange, question and answer, embedded text, list, repetition pattern, or other (with a short description). The list covers form only: wordplay and register belong to LA, and irony is captured by the line type, so NS does not repeat them. A fixed list keeps labels comparable across stories, which a freeform label did not.

### LA

The Language knowledge resource encompasses all the linguistic information required for the complete verbalization of a text (Attardo, 1994). Restricted, by design, to detecting whether humor is verbal as opposed to referential, rather than full stylistic analysis. Two independent blocks:

- **Wordplay**: phonological / morphological / lexical / syntactic levels. The four-way linguistic-level split is this project's own operationalization for LLM annotation, grounded in the GTVH treatment of the Language KR.
- **Register effect**: — a marked register choice.

## Text-level analysis (Stage 4)

Attardo's expanded GTVH treats a long text as a *vector*: humorous lines occur along a text that can only be read in one direction, each line is analyzed for its KRs, and the analysis then looks at how lines relate to one another and where they fall (Attardo, 2001; 2002, pp. 234–236). Stage 4 implements that second step. It is split in two, deliberately: the patterns are computed by code, and only the reading of them is left to a model.

### Distribution

"[T]he text is segmented in an arbitrary number of sections of equal length. The number of lines occurring in each section is computed" (Attardo, 2002, pp. 236–237), and the resulting histogram is compared against two null hypotheses: that the lines are distributed **randomly**, and that they are distributed **uniformly**. Attardo's measure of density is the words-per-line ratio (Wilde's *Lord Arthur Savile's Crime* averages one line every ~50 words, its opening ~18, its serious-relief passage ~367).

Implementation:
- Sections are equal **word-count** sections, a configurable number of them (Attardo used 100-word sections on a ~12,800-word story).
- Each line's position is the midpoint of its quoted text, located by word offset.
- The words-per-line ratio is reported for the text, each section, each wave and relief stretch, and each segment.
- **Uniform null:** Pearson chi-square of the section counts against equal expected counts.
- **Random null:** the coefficient of variation of the gaps between consecutive lines, which is about 1 for random placement, above 1 when lines cluster, and below 1 when they are more evenly spaced than chance. A Peacham-like even text shows up as *more regular than random*; a Wilde-like wavy text as *more clustered*.
- Both p-values come from Monte Carlo simulation of random placement with a fixed seed. Short stories have few lines, so this is more reliable than asymptotic distributions; with few lines the tests have little power, and "not rejected" should be read accordingly.
- **Waves** (the peaks of Attardo's "wave" pattern) are runs of sections well above the mean.
- **Serious relief** is "a stretch of text that presents little or no humour in an otherwise humour-rich environment" (p. 240): runs of sections well below the mean, long enough to matter.

### Strands, centrality, combs and bridges

"These related lines are said to form a strand. Strands may be based on the contents of any of the six KRs and/or combinations thereof" (p. 236). Strands are built from:
- the canonical target and its attributes;
- orientation;
- the canonical situation;
- the **essential binary category**, which is the intermediate level of script opposition (the concrete script labels are kept as annotated, so they are too specific to be shared across lines);
- opposition type, narrative strategy, wordplay level, and register effect;
- pairs of features from different KRs, such as Attardo's own "target plus logical mechanism" example (here target plus opposition type, since LM is not implemented).

Values that mean "nothing shared" never form a strand: no target, `cotext`/`irr`, binary category `none`, narrative strategy `other`, and unknown or not-applicable social class. Keys that select exactly the same lines describe one strand and are reported once.

A **central** strand "occurs through most of a text"; a **peripheral** strand "occurs only in a small part of the text" (p. 241). Centrality is measured by the strand's span (first to last line, as a fraction of the text). Strands between the two thresholds are reported as **intermediate** rather than forced into either class, since Attardo's definitions describe the two ends of a scale. Each strand's share of all lines is reported, Attardo's measure of how much of the humor is at a given target's expense (89 of 253 lines, ~35%, for Lord Arthur).

A **comb** is "the occurrence of several lines in close proximity" and a **bridge** "the occurrence of two related lines far from each other" (p. 236). Both are found within strands. A comb is a run of a strand's lines each within a set fraction of the text of the next; a bridge is two consecutive lines of a strand at least a set fraction apart. Because bridges are found within strands, a two-line bridge appears only if the minimum strand size is lowered to 2.

### Jab and punch lines

Jab and punch lines are counted by segment and by narrative level. A punch line closes a narrative unit, so its position relative to segment ends, and especially to the end of the text, is a hint toward a "humorous plot with punch line". It is reported as a plot indicator, not used as a rule.

### Plot type and interpretation

Attardo distinguishes four kinds of humorous plot (2002, pp. 237–238): a **serious plot with jab lines**, a **humorous plot with a punch line**, a **humorous plot with metanarrative disruption**, and a **humorous plot with a humorous central complication**. The last depends on the "central complication", for which "it is impossible to determine in a non-intuitive fashion" what it is (p. 238). The plot type and the central complication are therefore the job of a single interpretive model call. Its input is the computed aggregates and the segment descriptions, not the per-line data, and its identification of the central complication carries a caveat saying it is intuitive.

The call's output separates **pattern findings** from **readings**, following Attardo's own principle: "the GTVH does not detect social satire as such. It merely detects a strand of jab lines having TAs that all share certain features ... We interpret this finding as representing social satire" (p. 243). Every finding cites the strands, counts or statistics behind it. Every reading names the findings it rests on, is hedged, and carries a caveat. Cited ids are checked against the aggregates.

### Thresholds and baselines

Attardo gives no numeric thresholds for sections, peaks, relief, strand size, centrality, combs or bridges. Every one is therefore a named parameter with a documented default (see README), and the values used are stored in each output file. Attardo names the missing baseline as one of the theory's two main weaknesses: the GTVH "lacks a database containing a significant number of analyses that could provide us with baselines against which to evaluate a given text" (p. 248). The per-story output is designed as the unit of such a database:
- stable `feature=value` strand keys;
- per-line feature values;
- every parameter value used;
- hashes of the analysis and story text.

**Stacks** (strands of strands, p. 236) and corpus baselines are left to a later stage that reads these files.

## Other pipeline-level design decisions

- **Diffuse disjunctors as line types.** `register_clash` and `irony` sit alongside `discrete` as line types because they need different *detection* heuristics before any KR annotation. You can't find a register clash by looking for a single trigger word.
- **Jab vs. punch via narrative position**, and **narrative level** tracking (level_0 main storyline, level_-1/-2 embedded, level_+1/+2 framing).
- **Uncertainty marking with `(?)`.** Attardo's (2001) own case-study annotations mark uncertain values this way rather than forcing an answer; the prompts ask the model to do the same.

## References

- Attardo, S. (1994). *Linguistic theories of humor.* Mouton de Gruyter.
- Attardo, S. (2001). *Humorous texts: A semantic and pragmatic analysis.* Walter de Gruyter.
- Attardo, S. (2002). Cognitive stylistics of humorous texts. In E. Semino & J. Culpeper (Eds.), *Cognitive stylistics: Language and cognition in text analysis* (pp. 231–250). John Benjamins.
- Attardo, S. (2005). *A catalog of logical mechanisms* [Unpublished manuscript].
- Attardo, S. (2020). *The linguistics of humor: An introduction.* Oxford University Press.
- Attardo, S., & Raskin, V. (1991). *Script theory revis(it)ed: Joke similarity and joke representation model.* Humor: International Journal of Humor Research, 4(3-4), 293–347.
- Raskin, V. (1985). *Semantic mechanisms of humor.* D. Reidel.
