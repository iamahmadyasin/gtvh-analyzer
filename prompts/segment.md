# Stage 1 — Narrative Segmentation

You are analyzing a humorous short story under the General Theory of
Verbal Humor (GTVH; Attardo 2001, 2020). This is Stage 1 of a
multi-stage pipeline. Your only task here is to partition the story
into narrative segments. Do NOT identify humor, classify lines, or
annotate anything else — later stages handle that.

Reason **heuristically**, as an experienced text analyst would. This is
not symbolic parsing.

## Why segmentation matters

Punch lines are defined by occurring at the END of a narrative unit.
Jab lines occur anywhere else. Classification depends on knowing where
narratives begin and end. Segmentation is therefore a prerequisite.

## What counts as a segment

A segment is a bounded stretch of narrative with its own beginning and
end. Each segment has a `narrative_level`:

- **level_0** — the main storyline. Default when nothing else applies.
- **level_-1** — a narrative embedded within level_0 and told BY a
  character or narrator inside it: a speech, a letter, a quoted story,
  a song, a recalled event, a digression, an epistolary insert, a
  reported conversation.
- **level_-2** — embedded within a level_-1 narrative (a character in
  a letter quotes someone else, etc.).
- **level_+1** — a framing narrative that CONTAINS the main storyline:
  prologues, dedications, editorial forewords, first-person framing.
- **level_+2** — an implied metanarrator distancing themselves from
  the level_+1 narrator. Rare; look for cases where the narrator says
  things the reader is clearly meant to disagree with.

## Segmentation cues (in order of reliability)

1. **Explicit metatextual authorial markers.** Chapter headings,
   section breaks (`***`, blank lines with a divider), "End of Act I",
   epistolary headers ("Dear —,"), quoted-song delimiters, italicized
   inserts.
2. **Changes in setting.** Shift in location or clear time jump.
3. **Entries and exits of major characters.** A scene ending as its
   principal actor leaves; a new scene beginning as one enters.
4. **Shifts in narrative level.** A character begins to tell a story,
   quote a letter, sing a song, deliver a speech, or the narrator steps
   outside the storyline for commentary.

Do NOT use presence or absence of humor as a segmentation cue.

## Segment sizing

Prefer segments that correspond to actual narrative units, not
arbitrary paragraph groupings. Most short stories produce 3–12
segments. Avoid producing 30+ tiny segments unless the story genuinely
warrants it (picaresque, episodic).

## Input format

The story is provided with each line numbered:

```
Line 1: ...
Line 2: ...
```

Use these line numbers directly for `line_start` and `line_end`.

## Output

Return a JSON object with a `segments` array. Each element has:

- `segment_id`: sequential — `"NS-01"`, `"NS-02"`, ...
- `label`: short human-readable name (e.g., `"Opening at the newsroom"`,
  `"Anna's letter"`, `"Chapter 1"`).
- `narrative_level`: one of `level_0`, `level_-1`, `level_-2`,
  `level_+1`, `level_+2`.
- `line_start`, `line_end`: inclusive global line numbers.
- `parent_segment_id`: the containing segment's ID, or `null` for
  level_0 and level_+n.
- `is_terminal`: `true` if this segment ends at the same line as its
  parent (its end IS the parent's end); else `false`.
- `segmentation_cue`: which cue justified this boundary
  (e.g., `"chapter break"`, `"character exit"`, `"speech begins"`).
- `description`: one-line summary of what happens in this segment.

Return ONLY the JSON object. No prose, no code fences, no commentary.
