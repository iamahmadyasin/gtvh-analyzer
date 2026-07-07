# Stage 3 — GTVH Knowledge Resource Annotation

You are annotating a single humorous line from a short story with the Knowledge Resources
of the General Theory of Verbal Humor (GTVH). Theoretical grounding:
Raskin (1985) *Semantic Mechanisms of Humor*; Attardo (2001)
*Humorous Texts*; Attardo (2020) *The Linguistics of Humor*.

Reason heuristically, as a trained humor analyst would, informed
by the theory. Weigh the evidence, pick
the best fit, and mark uncertainty explicitly.

## Input you receive

- The containing narrative segment (label, level, line range).
- A local context window (~2–3 paragraphs around the line).
- The line itself: text, span, disjunctor (if discrete), line type.
- The terminal line number of the segment.

## KR hierarchy

KRs form a hierarchy: **SO → SI → TA → NS → LA**. Higher KRs constrain
lower ones. When a lower KR contributes nothing, use `"irr"` or
`null`. Do not force-fill.

## Classification (jab vs punch)

- **`punch`** — the line ends at (or immediately before) the segment's
  terminal line. Allow a small tolerance for trailing punctuation or
  a stage direction.
- **`jab`** — the line occurs anywhere else within the segment.

## `narrative_level_of_classification`

The `narrative_level` of the segment in which the line qualifies. A
punch line of a level_-1 speech is a punch AT level_-1 even though it
sits mid-storyline from level_0's perspective.

## SO — Script Opposition (Raskin core; full detail required)

SO is captured at three levels of abstraction: text-specific (the
concrete script pair, `script_1` / `script_2`), intermediate binary
(`essential_binary_category`), and abstract (`opposition_type`,
Raskin's three types). Work concrete-up — pin down the specific
scripts the line evokes first, then let the binary and abstract
type follow. Trying to name the abstract type in the void is the
most common failure mode.

### Script labels

- `script_1`: UPPERCASE noun phrase naming the setup script (e.g.,
  `DOCTOR_HOUSE_CALL`, `POLITE_HOST`, `MECHANICAL_FAILURE`).
- `script_2`: UPPERCASE noun phrase naming the opposed script (e.g.,
  `LOVER_VISIT`, `MURDEROUS_HOST`, `PRESIDENT_ROBBING_STORE`).

**Local antonymy (Attardo 2020 via Tinholt 2007):** Script 1 and
Script 2 are *local antonyms* — they share most nodes and links in
the semantic graph, differing in one crucial characteristic that is
opposed *for the purposes of this text only*. This is not general
antonymy. Two randomly chosen scripts (say `DOG` and `PIANO`) are not
local antonyms — they share too little. Two scripts that share most
of their structure but flip one crucial fact (a doctor's house visit
vs. a lover's house visit — same setting, same actors, one crucial
purpose reversed) are.

Prefer labels specific enough that a reader could reconstruct the
opposition from the labels alone.

### Real/Unreal situations

- `real_situation`: one sentence, present tense, describing what is
  actually the case under Script 1.
- `unreal_situation`: one sentence, present tense, describing the
  opposed situation evoked by Script 2.
- `shadow_opposition`: if a complementary reversed pair runs through
  the line, note it; else `null`. Example (Raskin's church/sex joke):
  main opposition is *archdeacon involved in debauchery* vs *involved
  in honest toil*, with a shadow *Saint Peter involved in honest
  toil* vs *involved in debauchery*.

### `opposition_type` — Raskin's three abstract types (1985 §4)

Boundaries are not watertight (Raskin p.112). Pick the best fit and,
if genuinely borderline, add `(?)` in the justification.

**`actual_vs_nonactual`** — actual situation vs. a non-actual,
non-existing situation that is not compatible with the actual setting.

- **Diagnostic construction:** "It IS the case that X, and it is NOT
  the case that Y." If you can fill both blanks with two opposing
  propositions involving the hero(es) and/or the actual setting, this
  is the type.
- Choose this when the opposition is between what obtains in the
  story world and what simply doesn't obtain.
- Raskin example (doctor's wife joke): It IS the case that the
  patient comes to see the doctor, and it is NOT the case that the
  patient comes to see the doctor (he comes to see the wife).

**`normal_vs_abnormal`** — normal, expected state of affairs vs.
abnormal, unexpected state of affairs.

- The normal is what convention, custom, social role, or expectation
  dictates. The abnormal violates that expectation.
- Best fit for stereotypes, role reversals, decorum breaches,
  hypocrisy, gaps between expected and actual behavior.
- Raskin example (senator/gentleman joke): The NORMAL expectation is
  that a senator, an elected representative of the public, is the
  best kind of person available and therefore a gentleman. The
  ABNORMAL state introduced by the joke is that senators are, in
  fact, not gentlemen.

**`possible_vs_impossible`** — possible, plausible situation vs. fully
or partially impossible / much less plausible situation.

- Choose this when Script 2 is physically impossible, logically
  impossible, or wildly implausible on its own terms.
- Raskin examples: A patient cannot literally sell an illness
  (impossible). Samson cannot lift himself by his own hair
  (physically impossible). A lady calling her chauffeur "darling" is
  highly implausible unless they are lovers (implausibility, not
  outright impossibility).

**Borderline guidance (from Raskin p.112):**

- If Script 2 is implausible but not altogether impossible → tends
  toward `possible_vs_impossible` based on where it sits on the
  plausibility scale.
- If Script 1 constitutes a norm or expectation (not merely an
  actual state) → tends toward `normal_vs_abnormal`.
- Raskin: "boundaries between the three types are not watertight,
  and there is a certain amount of mutual penetration and diffusion."
- If you are genuinely torn between two types, pick the one that best
  captures what the joke is *doing*, and note the tension in the
  `justification` with `(?)`.

### `essential_binary_category`

Only invoke a category when it is genuinely activated by the SO. Do
not force-fill.

- `good_bad` — evaluative/judgmental
- `life_death` — including age-related
- `obscene_nonobscene` — sex-related
- `money_nomoney` — economic
- `high_low_stature` — social status, intelligence
- `none` — no basic binary invoked

### `overlap_degree` (Raskin §3)

- **`full`** — both scripts perfectly compatible with the entire
  text; nothing odd, redundant, or missing under either script. Rare
  — like equiprobable ambiguity. Example: sharp two-sentence jokes
  where a negation makes both readings equally viable.
- **`partial`** — one script fits the text more easily than the
  other. Some elements favor one; the text as a whole leans one way.
  Example: Raskin's bishop-and-vicar note (the clerical vocabulary
  slants the text toward the CHURCH script despite the sexual reading
  being available).
- **`truly_partial`** — both scripts are evoked but some parts of the
  text are clearly incompatible with one of them. Most common. Example:
  Raskin's TV-in-color joke — the COLOR script is incompatible with
  the second sentence, the ethical script with the first.

## `trigger_type` (Raskin §5)

For `discrete` lines, pick one. For `register_clash` and `irony`, use
`not_applicable`.

**Ambiguity triggers** — the disjunctor is ambiguous between Script 1
and Script 2.

- **`ambiguity_regular`** — polysemy or homonymy: one word/phrase with
  two lexical meanings. Raskin examples: *gentleman* ('man' vs. 'man
  of quality'); *going* ('going out' vs. 'going away'); *offer*
  ('say' vs. 'give').

- **`ambiguity_figurative`** — figurative/idiomatic expression with
  literal + non-literal readings. Borders on regular ambiguity.
  Raskin examples: *toil* ('work hard' vs. sexual sense); *catch*
  ('catch' vs. 'become infected'); *ass* ('donkey' vs. 'fool');
  *strikes* ('hit' vs. 'impress'); *out of one's head* (physical vs.
  mental).

- **`ambiguity_syntactic`** — structural ambiguity: attachment, scope,
  case, or deep-syntactic. Raskin examples: *substitute* (attachment
  ambiguity — refers to the vicar or the vicar's wife?); *with*
  (agent vs. instrument); *directions* (for taking the medicine vs.
  for keeping the medicine — deep-syntactic).

- **`ambiguity_situational`** — the situation itself permits two
  readings; the disjunctor introduces Script 2 while preceding text
  is near-neutral. Raskin example: *comfort* — neutral preceding text
  becomes ironic in retrospect.

- **`ambiguity_quasi`** — phonetic similarity, not semantic. Words
  are misused, garbled, or near-homophones. Raskin examples:
  knock-knock jokes, malapropisms, jokes where sound similarity (not
  meaning) creates the crossover.

**Contradiction triggers** — the disjunctor contradicts an element
established by Script 1.

- **`contradiction_regular`** — a single word or phrase contradicts an
  established element of Script 1. Raskin example (Monday execution
  joke): *beginning* is compatible with *Monday* and *week*, but
  contradicts the fact that a beginning implies an ending distinct
  from it — and for a man about to be executed on Monday, the
  beginning IS the ending. Doctor's wife joke: *no* (doctor absent)
  in conjunction with *come in* (invitation) creates a contradiction
  under Script 1.

- **`contradiction_sentential`** — a whole clause or sentence creates
  the contradiction, not just an individual word.

- **`contradiction_dichotomizing`** — a built-in antonym pair whose
  expected roles are reversed. Raskin example: *wise man / fool* — in
  a bona-fide text, the wise man remains wise and the fool a fool;
  in a joke, the roles are reversed and the "fool" delivers the
  wisdom.

## SI — Situation

The background macro-script for the line — the mental space the
narrator has built for the reader by this point, including props,
participants, activities, and world-premises. Not the physical
setting alone: the full inferential frame the line lands in.

**Backgrounded incongruities live here** (Hempelmann and Attardo
2011; Attardo 2020 §7.1.4). Talking animals in a folktale, a
character established pages ago as a habitual liar, an office
where everyone shouts — these are premises the reader has already
suspended disbelief about. They are part of SI; they are not
themselves the SO of the current line. A line's SO uses the world
SI has built; it does not re-open questions SI has already closed.

One short phrase. Include the world-premise if the line's humor
depends on it, not just the physical setting.

- Specific: `"newsroom"`, `"confessional"`, `"parade planning"`,
  `"talking-animal folktale world"`, `"dinner party where the host
  is visibly drunk"`.
- `"cotext"` — the line inherits its situation from the
  immediately surrounding narrative and adds nothing distinctive
  of its own; the line's humor doesn't lean on any background
  premise beyond what the previous few sentences establish.
- `"irr"` — situation contributes nothing (rare).

## TA — Target

Two things: **target** (who the aggression is aimed at, if any)
and **orientation** (who or what the humor is pointed at,
aggression or not). Per Priego-Valverde et al. (2018) via Attardo
(2020, §7.1.3), every humorous line has an orientation; only some
lines have a target. When aggression is present, orientation and
target line up. When it is absent, orientation still records where
the humor points while target is `null`.

### `target`

Who or what the humor is aimed at aggressively.

- Named character or group: `"the lawyer"`, `"academics"`,
  `"suburban husbands"`.
- Stereotype or ideological target: `"marriage"`, `"academic
  pretension"`, `"the establishment"`, `"romantic love"`.
- `null` — non-aggressive humor. Do NOT force a target. Many puns,
  garden paths, and absurdities have no target. Empty target is a
  valid, common outcome.

### `orientation`

Where the humor is pointed. **Never `null`** — every humorous line
has an orientation. Pick one:

- **`self`** — first-person / self-deprecating. The teller,
  narrator, or speaking character points the humor at themselves.
- **`hearer`** — second-person. The humor is pointed at the
  addressee (in fiction, another character being spoken to, or a
  direct address to the reader).
- **`other`** — third-party. A character, group, or absent party
  outside the current speaker-hearer pair.
- **`situation`** — the shared circumstance or frame the
  participants are inside. The humor points at the setup itself,
  not at a person. Example (Attardo 2020, p. 146): participants
  in an anechoic room jokingly compare themselves to eggs in an
  egg carton — no one is being mocked; the shared situation is
  the pivot. Distinct from the SI knowledge resource, which asks
  what world we are in; `orientation: situation` asks where the
  humor points.

Aggression + orientation → target. `orientation: other` +
`target: "the lawyer"` is the aggressive third-party case;
`orientation: other` + `target: null` is affectionate or neutral
third-party humor.

## NS — Narrative Strategy

The narrative form the line takes. Common values (extend as needed
and use the closest fit):

`joke`, `pun`, `riddle`, `q_and_a`, `adjacency_pair_request`,
`greeting`, `statement`, `title`, `quotation`, `visual`,
`understatement`, `metanarrative_comment`, `aside`, `epistolary`,
`speech`, `narration`, `dialogue`, `three_step_sequence`,
`compound`, `other`.

Two structural patterns worth flagging when present: the
**three-step sequence** (AAB — two parallel setups, then a
breaking third; Rozin et al. 2006 found this the most frequent
and highest-rated humor structure), and **compound** jokes with
multiple punch lines inside one segment (Hockett 1977; Norrick
2010). A jab line inside a longer structure retains its own SO
independent of the segment's terminal punch.

## LA — Language (wording-dependent humor detection)

We do NOT do full stylistic analysis. LA records whether the humor
depends on the specific wording — whether the line is a **verbal
joke** (would break under paraphrase) as opposed to a
**referential joke** (survives paraphrase).

Attardo (2020) treats LA as covering the full semiotic strategy of
the text (phonology, morphology, syntax, lexis, register, prosody,
punch-line placement). This pipeline restricts LA to the two most
common wording-dependent effects in short stories, recorded in
separate blocks: **wordplay** (puns and pun-like devices operating
on the linguistic unit — sound, word-form, meaning, structure) and
**register clash** (humor turning on a mismatch between the
stylistic level used and the situation, subject, or interlocutor).
Wordplay and register clash are independent mechanisms; a line can
in principle carry both, though usually only one applies.

**When LA is irrelevant.** LA is only fully irrelevant — both
`is_wordplay` and `is_register_effect` false, all sublabels null,
both notes `"irr"` — when the humor does not depend on the
specific wording at all. If a paraphrase in different words at a
neutral register preserves the humor intact, the humor is
referential and LA contributes nothing. Any other case leaves at
least one flag on.

**Global diagnostic.** Mentally paraphrase the line using
different wording that preserves meaning. If the humor survives →
not wordplay. If it breaks → wordplay. Then, separately, rewrite
the line in neutral register preserving meaning. If the humor
survives → not a register effect. If it collapses → it is.

### Wordplay block

- `is_wordplay`: `true` if the specific wording is doing the humor
  work via a pun or pun-like device on the linguistic unit;
  `false` otherwise.

- `wordplay_level`: if `is_wordplay: true`, the linguistic level
  at which the play operates. Pick one:
  - **`phonological`** — sound-level. *Does the humor depend on
    how the words sound?* Homophone puns, near-homophones,
    spoonerisms, and non-pun **sound patterning** including
    **alliteration**, assonance, consonance, and rhyme used for
    humor.
  - **`morphological`** — word-formation-level. *Does the humor
    depend on how the word is built or coined?* Portmanteaus
    (blends), malapropisms, playful affixation, coined words.
  - **`lexical`** — word-meaning-level. *Does the humor depend on
    a word or phrase carrying two meanings at once?* Polysemy
    puns, homonym puns, idiom literalization, figurative-literal
    collisions.
  - **`syntactic`** — structure-level. *Does the humor depend on
    how the sentence is put together?* Garden path sentences,
    attachment ambiguity, scope ambiguity, case ambiguity.
  - `null` when `is_wordplay: false`.

- `wordplay_subtype`: a short freeform label naming the specific
  device — e.g., `"homophone pun"`, `"portmanteau"`,
  `"malapropism"`, `"garden path"`, `"idiom literalization"`,
  `"attachment ambiguity"`, `"alliteration"`, `"assonance"`,
  `"rhyme"`. `null` when `is_wordplay: false`.

- `wordplay_note`: brief explanation of the wordplay if present;
  `"irr"` if `is_wordplay: false`.

### Register block

Register clash operates on the sociolinguistic layer above the
word — a mismatch between the register used and the situation,
subject, or interlocutor. It is not wordplay: the humor sits in
the stylistic choice, not in the linguistic unit itself.

- `is_register_effect`: `true` if the humor depends on a marked
  register choice — elevated diction on a squalid subject,
  technical jargon for a trivial event, sacred vocabulary for a
  profane act, formal prose for an intimate moment, sustained
  marked register whose oddity is itself the joke, obscenity or
  taboo vocabulary used for stylistic effect. `false` otherwise.
  Diagnostic: rewrite in neutral register preserving meaning. If
  the humor collapses → `true`.

- `register_effect_subtype`: a short freeform label naming the
  effect — e.g., `"mock-heroic register"`, `"bureaucratese on
  trivia"`, `"sacred vocabulary on profane act"`, `"clinical
  register on intimacy"`, `"obscenity in decorous frame"`. `null`
  when `is_register_effect: false`.

- `register_note`: brief explanation of the register effect if
  present; `"irr"` if `is_register_effect: false`.

For referential jokes — situational garden paths, absurdities,
ironies, and contradictions that don't depend on a specific word
or register choice — `is_wordplay: false`, `is_register_effect:
false`, all sublabels null, both notes `"irr"`.

## Uncertainty

Attardo annotates uncertain KRs with parenthetical `(?)`. Follow
suit: prefix or suffix uncertain values with `(?)`. Do not fabricate
certainty.

## `justification`

1–3 sentences focused on the SO. State why these two scripts, in what
sense they oppose (which type, which crucial characteristic differs),
and — if noteworthy — what makes this specifically a line rather than
incidental prose.

## Output

Return a single JSON object matching the schema. No prose, no code
fences.
