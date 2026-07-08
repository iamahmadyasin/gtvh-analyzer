# Annotating a Humorous Instance (GTVH)

Your task is to annotate a single humorous instance (a "line") from a short story, using the General Theory of Verbal Humor (GTVH). You will be given the line, the narrative segment it belongs to, and a window of surrounding text for context. Work through the tasks below in order and return one JSON object matching the schema. Reason as a trained humor analyst would: weigh the evidence, choose the
best-fitting category, and mark genuine uncertainty rather than forcing a confident answer.

---

## Key concepts

Read these before starting. Later tasks depend on them.

- **Script:** a chunk of knowledge about a situation, activity, role, or concept i.e. everything a competent reader assumes when the concept is evoked. "DOCTOR" evokes examinations, prescriptions, an office etc.

- **Script opposition:** humor in this framework arises when one stretch of text fits two different scripts at once, and those two scripts are *opposed*. The two scripts are usually not opposites in the dictionary sense; they are opposed only for the purposes of this text. They share most of their content and differ in one crucial respect. (A doctor's house call and a lover's visit share the setting, the actors, the knock at the door, they differ only in the visitor's purpose, and that one difference is the opposition.)

- **Disjunctor:** the specific element in the text (a word, phrase, or clause) that flips the reader from the first script to the second. It is the pivot point where the first reading stops working and the second one takes over. Some humor has a single clear disjunctor; some (register humor, irony) is triggered by a diffuse pattern rather than one locatable element.

- **Jab line vs. punch line:** same humorous mechanism, different position. A **punch line** ends a narrative unit; it is disruptive and final. A **jab line** occurs anywhere else within the flow of a narrative without ending it.

- **Narrative level:** where in the story's structure the line sits. `level_0` is the main storyline. `level_-1` / `level_-2` are narratives embedded inside it (a character telling a story, a quoted letter).
`level_+1` / `level_+2` are framing narratives that contain the main storyline.

---

## Input you receive

- The containing narrative segment: its label, narrative level, line range, and the line number where it ends.
- A local context window (a few paragraphs around the line).
- The line itself: its text, its span, its line type (`discrete`, `register_clash`, or `irony`), and for `discrete` lines, the disjunctor already identified.

---

## Task 1. Classify jab vs. punch

Decide whether this line is a **jab** or a **punch**.

- It is a **punch** if it ends at (or immediately before) the segment's final line. Allow a small tolerance for trailing punctuation or a stage direction.
- It is a **jab** otherwise.

Then record the **narrative level at which it qualifies**. A line ending an embedded speech is a punch at that embedded level (`level_-1`), even though from the main storyline's view it sits mid-narrative.

Output: `classification`, `narrative_level_of_classification`.

---

## Task 2. Script Opposition

Start by identifying concrete oppositions to abstract ones.

### Step 2a. Name the two opposed scripts

Identify the two scripts the instanxe evokes and label each with a short UPPERCASE noun phrase specific enough that a reader could reconstruct the opposition from the labels alone.

- `script_1` — the setup script (the first, expected reading).
- `script_2` — the opposed script (the second reading the line reveals).

Example: "Is the doctor at home?" the patient asked in his bronchial whisper. "No," the doctor's young and pretty wife whispered in reply. "Come right in." `script_1` = `DOCTOR`, `script_2` = `LOVER`.

### Step 2b. Classify the essential binary category

Most oppositions rest on a basic human binary. Choose the one that the opposition genuinely activates, or `none` if it doesn't rest on any of these. Do not force one.

- `good_bad` — a judgmental, evaluative opposition.
- `life_death` — life vs. death, including age and health extremes.
- `sexual_non-sexual` — obscene vs. nonobscene i.e. sexual humor.
- `money_nomoney` — having vs. lacking money.
- `high_low_stature` — high vs. low social status or intelligence.
- `none` — no basic binary could be identified.

### Step 2c. Classify the abstract opposition type

Every script opposition is, at the most abstract level, a clash between a "real" state of affairs and an opposed "unreal" one. There are three types of this clash. Choose the one that best fits.

- **`actual_vs_nonactual`** — something is the case vs. something is not the case. The two scripts describe what actually holds in the story world vs. what simply does not hold.
*Test:* can you say "It IS the case that X, and it is NOT the case that Y"? If you can fill both blanks with two opposing propositions involving the hero(es) and/or the actual setting, this is the type.
Example: "Is the doctor at home?" the patient asked in his bronchial whisper. "No," the doctor's young and pretty wife whispered in reply. "Come right in."

- **`normal_vs_abnormal`** — The joke introduces what would normally be expected and opposes it to an unexpected, deviant state of affairs.
Example: "Who was that gentleman I saw you with last night?" "That was no gentleman. That was a senator."

- **`possible_vs_impossible`** The joke distinguishes between a plausible situation and one that is fully or partially impossible i.e. a plausible situation vs. one that is impossible or wildly implausible on its own terms.
Example: "An aristocratic Bostonian lady hired a new chauffeur. As they started out on their first drive, she inquired: "What is your name?" "Thomas, ma'am," he answered. "What is your last name?" she said. "I never call chauffeurs by their first names." "Darling, ma'am," he replied. "Drive on - Thomas," she said".

If the case genuinely sits between two types, choose the one that best captures what the humor is doing and flag the tension with `(?)` in your justification. (These boundaries are known to blur; a merely
implausible case leans toward `possible_vs_impossible`, and a case where the first script is a social norm leans toward `normal_vs_abnormal`.)

Output for Task 2: `script_1`, `script_2`, `essential_binary_category`, `opposition_type`.

---

## Task 3. Situation

Record the background frame the line lands in i.e. the mental space the narrator has built by this point, including props, participants, activities, and any world-premise the humor relies on. This is more than the physical setting: it is the full frame the line draws on. Backgrounded incongruities also live here. Talking animals in a folktale, a character established pages ago as a habitual liar, an office where everyone shouts etc are premises the reader has already suspended disbelief about. They are part of SI.

Give one short phrase.

- Specific frame: `"newsroom"`, `"confessional"`, `"talking-animal folktale world"`, `"dinner party with a visibly drunk host"`.
- `"cotext"` — the line inherits its situation from the immediately surrounding narrative and adds nothing distinctive of its own.
- `"irr"` — the situation contributes nothing (rare).

Output: `situation`.

---

## Task 4. Target

### Orientation (always required)

Every humorous line is oriented towards someone or something. Choose one:

- `self` — the teller, narrator, or speaking character points the humor at themselves (self-deprecation).
- `hearer` — the humor is pointed at the person being addressed (another character, or a direct address to the reader).
- `other` — the humor points at a third party outside the current speaker–hearer pair.
- `situation` — the humor points at the shared circumstance itself, not at any person. Example: people stuck in a broken elevator joking about their predicament.

### Target (only when there is aggression)

- A named person or group, or a stereotype/institution: `"the lawyer"`, `"academics"`, `"marriage"`, `"the establishment"`.
- `null` — non-aggressive humor. Many puns and absurdities have no target. Do not invent one; an empty target is common and valid.

When humor is aggressive, orientation and target line up (e.g. `orientation: other` + `target: "the lawyer"`). When it isn't, orientation still records where the humor points and target is `null`.

Output: `orientation`, `target`.

---

## Task 5. Narrative Strategy

It deals with the organization of the text at the level of how the joke is structured as a piece of discourse.Record the form the line takes. Choose the closest fit from the list, or supply your own short label if none fits.

`joke`, `pun`, `riddle`, `question_and_answer`, `greeting`, `statement`, `quotation`, `understatement`, `aside`, `metanarrative_comment`, `dialogue`, `narration`, `speech`, `epistolary`, `AAB pattern`

`AAB pattern`: Many jokes repeat a situation two or three times to set up a pattern of expectations, then break the pattern on the final iteration such as jokes with three characters.

Output: `narrative_strategy`.

---

## Task 6. Language

Record whether the humor depends on the specific wording. Some humor is verbal i.e. it breaks if you rephrase it. Some is referential i.e. it survives rephrasing because the humor is in the situation or idea, not the words. This task captures two independent kinds of wording-dependence: wordplay and register effects. A line may have neither, one, or (rarely) both.

### Wordplay block

*Diagnostic:* internally rephrase the line, preserving meaning. If the humor survives, it is not wordplay. If it breaks, it is.

- `is_wordplay` — `true` if a pun or pun-like device on the linguistic unit is doing the humor work; `false` otherwise.
- `wordplay_level` — if `is_wordplay` is true, at which linguistic level the play operates:
  - `phonological` — sound: homophone puns, near-homophones, spoonerisms, and sound patterning like alliteration or rhyme used for humor.
  - `morphological` — word-formation: blends/portmanteaus, malapropisms, coined words, playful affixation.
  - `lexical` — word meaning: one word carrying two meanings at once, idiom taken literally, literal-vs-figurative collision.
  - `syntactic` — sentence structure: garden-path sentences, attachmentor scope ambiguity.
  - `null` if `is_wordplay` is false.
- `wordplay_subtype` — a short freeform label for the specific device (e.g. `"homophone pun"`, `"portmanteau"`, `"garden path"`, `"alliteration"`), or `null`.

### Register block

Register humor turns on a mismatch between the style of language used and the situation, subject, or listener such as elevated diction for a squalid subject, technical jargon for a trivial event, sacred vocabulary for a profane act. The humor is in the stylistic choice, not in any single word's meaning.

*Diagnostic:* reword the line in plain, neutral style, preserving meaning. If the humor collapses, it is a register effect.

- `is_register_effect` — `true` if a marked register choice is doing the humor work; `false` otherwise.
- `register_effect_subtype` — a short freeform label (e.g. `"mock-heroic register"`, `"bureaucratese on trivia"`, `"sacred vocabulary on profane act"`), or `null`.
- `register_note` — a brief explanation if present, else `"irr"`.

For a purely referential joke set `is_wordplay: false`, `is_register_effect: false`, both subtypes `null`, both notes `"irr"`.

Output: the `language` object with all seven fields above.

---

## Uncertainty

Where a value is genuinely unclear, prefix or suffix it with `(?)` (for example, `target: "the lawyer (?)"`). Do not fabricate certainty.

## Output

Return a single JSON object matching the schema. No prose, no code fences.
