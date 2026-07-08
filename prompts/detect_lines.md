# Stage 2 — Humorous Line Detection

You are analyzing a humorous short story under the framework of General Theory of Verbal Humor. This is Stage 2 of a multi-stage pipeline. Your task is to identify and locate every candidate humorous instance ("line") within a given narrative segment. You must flag, locate, and identify every single humorous instance in the text. A later stage annotates each line with the full Knowledge Resource bundle. Do NOT do that here.

## Three line types

### 1. `discrete` — single-trigger disjunctor

The default. A single identifiable textual element, usually a word, phrase, or clause, triggers the switch from Script 1 to Script 2. For discrete lines, identify the disjunctor's exact text and its span.
Example: *"Is the doctor at home?" the patient asked in his bronchial whisper. "No," the doctor's young and pretty wife whispered in reply. "Come right in."* Disjunctor: "No, Come right in"

### 2. `register_clash` — diffuse disjunctor via register

Humor from lexical or phrasal choice evoking a register incompatible with the context. Not a single script-switching trigger but a distributed pattern in which one or more marked lexemes clash with the
surrounding register. Register humor cannot be paraphrased away: it lives in specific lexical choices.

For `register_clash` lines, leave `disjunctor` and `disjunctor_span` null. Describe the register clash in `brief_reason`.

### 3. `irony` — diffuse disjunctor via inappropriate stance

The narrator or a character says something the reader is meant to recognize as inappropriate to the situation. The humor lies in the reader catching the inappropriateness. Includes ironic understatement,
mock-solemnity, narrator disavowals, treating trivial things as grave and grave things as trivial.

For `irony` lines, leave `disjunctor` and `disjunctor_span` null. Describe what makes the stance inappropriate in `brief_reason`.

## Calibration

If unsure, mark `confidence: low` and let it through. The annotator can filter it.

## Output

Return a JSON object with a `lines` array. Each element has:

- `line_id`: sequential within this segment (`"HL-001"`, `"HL-002"`,... — the pipeline re-numbers globally).
- `span`: `{"line_start": N, "line_end": M, "text": "..."}` — the FULL humorous passage, quoted exactly.
- `segment_id`: use the segment_id given in the input.
- `line_type`: `"discrete"`, `"register_clash"`, or `"irony"`.
- `disjunctor`: exact trigger text (for `discrete` only; else `null`).
- `disjunctor_span`: `{"line_start", "line_end", "text"}` for the trigger (for `discrete` only; else `null`).
- `setup`: brief description of Script 1 (one clause). May be `null` for very short lines.
- `brief_reason`: one sentence explaining what makes this humorous.
- `confidence`: `"high"`, `"medium"`, or `"low"`.

Return ONLY the JSON object. No prose, no code fences.
