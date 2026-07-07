"""
GTVH Humor Analysis — Pydantic schemas.

Implements the annotation schema for the SSTH (Raskin 1985) and GTVH
(Attardo & Raskin 1991; Attardo 2001, 2020) — Script Opposition (SO),
Situation (SI), Target (TA), Narrative Strategy (NS), Language (LA).
Logical Mechanism (LM) is intentionally excluded.

LLM-facing models avoid default values because OpenAI structured
outputs require all fields to be present in `required`. Optional
fields use `Optional[X]` (nullable).
"""

from typing import Literal, Optional
from enum import Enum
from pydantic import BaseModel


# ---------- Enums ----------

class NarrativeLevel(str, Enum):
    LEVEL_0 = "level_0"
    LEVEL_MINUS_1 = "level_-1"
    LEVEL_MINUS_2 = "level_-2"
    LEVEL_PLUS_1 = "level_+1"
    LEVEL_PLUS_2 = "level_+2"


class LineClassification(str, Enum):
    JAB = "jab"
    PUNCH = "punch"


class LineType(str, Enum):
    DISCRETE = "discrete"
    REGISTER_CLASH = "register_clash"
    IRONY = "irony"


class TriggerType(str, Enum):
    AMBIGUITY_REGULAR = "ambiguity_regular"
    AMBIGUITY_FIGURATIVE = "ambiguity_figurative"
    AMBIGUITY_SYNTACTIC = "ambiguity_syntactic"
    AMBIGUITY_SITUATIONAL = "ambiguity_situational"
    AMBIGUITY_QUASI = "ambiguity_quasi"
    CONTRADICTION_REGULAR = "contradiction_regular"
    CONTRADICTION_DICHOTOMIZING = "contradiction_dichotomizing"
    CONTRADICTION_SENTENTIAL = "contradiction_sentential"
    NOT_APPLICABLE = "not_applicable"


class OppositionType(str, Enum):
    ACTUAL_VS_NONACTUAL = "actual_vs_nonactual"
    NORMAL_VS_ABNORMAL = "normal_vs_abnormal"
    POSSIBLE_VS_IMPOSSIBLE = "possible_vs_impossible"


class BinaryCategory(str, Enum):
    GOOD_BAD = "good_bad"
    LIFE_DEATH = "life_death"
    OBSCENE_NONOBSCENE = "obscene_nonobscene"
    MONEY_NOMONEY = "money_nomoney"
    HIGH_LOW_STATURE = "high_low_stature"
    NONE = "none"


class OverlapDegree(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    TRULY_PARTIAL = "truly_partial"


class WordplayLevel(str, Enum):
    PHONOLOGICAL = "phonological"
    MORPHOLOGICAL = "morphological"
    LEXICAL = "lexical"
    SYNTACTIC = "syntactic"


class Orientation(str, Enum):
    """TA sub-field: where the humor points (never null)."""
    SELF = "self"
    HEARER = "hearer"
    OTHER = "other"
    SITUATION = "situation"


# ---------- Text location ----------

class TextSpan(BaseModel):
    line_start: int
    line_end: int
    text: str  # exact quoted text


# ---------- Stage 1: Segmentation ----------

class NarrativeSegment(BaseModel):
    segment_id: str                       # "NS-01"
    label: str
    narrative_level: NarrativeLevel
    line_start: int                       # inclusive
    line_end: int                         # inclusive
    parent_segment_id: Optional[str]      # None for level_0 / level_+n
    is_terminal: bool                     # ends at its parent's end?
    segmentation_cue: str
    description: str


class SegmentationResult(BaseModel):
    """Wrapper for OpenAI structured output."""
    segments: list[NarrativeSegment]


# ---------- Stage 2: Detection ----------

class DetectedLine(BaseModel):
    """Candidate humorous line, pre-annotation."""
    line_id: str                          # will be re-numbered globally
    span: TextSpan
    segment_id: str
    line_type: LineType
    disjunctor: Optional[str]             # null for register_clash / irony
    disjunctor_span: Optional[TextSpan]
    setup: Optional[str]                  # brief Script 1 description
    brief_reason: str
    confidence: Literal["high", "medium", "low"]


class DetectionResult(BaseModel):
    """Wrapper for OpenAI structured output."""
    lines: list[DetectedLine]


# ---------- Stage 3: KR Annotation ----------

class ScriptOpposition(BaseModel):
    script_1: str                         # UPPERCASE
    script_2: str
    real_situation: str
    unreal_situation: str
    shadow_opposition: Optional[str]
    opposition_type: OppositionType
    essential_binary_category: BinaryCategory
    overlap_degree: OverlapDegree


class LanguageKR(BaseModel):
    # Wordplay block — pun-like devices on the linguistic unit
    is_wordplay: bool
    wordplay_level: Optional[WordplayLevel]
    wordplay_subtype: Optional[str]       # freeform, e.g., "homophone pun"
    wordplay_note: str                    # brief note or "irr"

    # Register block — stylistic mismatch above the word
    is_register_effect: bool
    register_effect_subtype: Optional[str]  # freeform, e.g., "mock-heroic register"
    register_note: str                      # brief note or "irr"


class KRAnnotation(BaseModel):
    line_id: str
    classification: LineClassification
    narrative_level_of_classification: NarrativeLevel

    # SO — Raskin core
    script_opposition: ScriptOpposition
    trigger_type: TriggerType

    # Other KRs — kept light
    situation: str                        # SI: e.g., "newsroom", "cotext", "irr"
    target: Optional[str]                 # TA: None = non-aggressive
    orientation: Orientation              # TA sub-field: where humor points (never None)
    narrative_strategy: str               # NS
    language: LanguageKR                  # LA

    justification: str                    # 1-3 sentences


# ---------- Assembled outputs (internal, defaults OK) ----------

class AnnotatedLine(BaseModel):
    line_id: str
    span: TextSpan
    segment_id: str
    line_type: LineType
    disjunctor: Optional[str] = None
    disjunctor_span: Optional[TextSpan] = None
    annotation: KRAnnotation


class Analysis(BaseModel):
    source_filename: str
    segments: list[NarrativeSegment]
    lines: list[AnnotatedLine]
