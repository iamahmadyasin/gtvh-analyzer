"""
Pydantic schemas implements the annotation schema.

LLM-facing models avoid default values because OpenAI structured
outputs require all fields to be present in `required`. Optional
fields use `Optional[X]`.
"""

from typing import Literal, Optional
from enum import Enum
from pydantic import BaseModel


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


class WordplayLevel(str, Enum):
    PHONOLOGICAL = "phonological"
    MORPHOLOGICAL = "morphological"
    LEXICAL = "lexical"
    SYNTACTIC = "syntactic"


class Orientation(str, Enum):
    SELF = "self"
    HEARER = "hearer"
    OTHER = "other"
    SITUATION = "situation"


class TextSpan(BaseModel):
    line_start: int
    line_end: int
    text: str

# Stage 1: Segmentation

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
    segments: list[NarrativeSegment]


# Stage 2: Detection

class DetectedLine(BaseModel):
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
    lines: list[DetectedLine]


# Stage 3: KR Annotation

class ScriptOpposition(BaseModel):
    script_1: str                         # concrete level, UPPERCASE
    script_2: str                         # concrete level, UPPERCASE
    essential_binary_category: BinaryCategory  # intermediate level
    opposition_type: OppositionType            # abstract level


class LanguageKR(BaseModel):
    is_wordplay: bool
    wordplay_level: Optional[WordplayLevel]
    wordplay_subtype: Optional[str]

    is_register_effect: bool
    register_effect_subtype: Optional[str]


class KRAnnotation(BaseModel):
    line_id: str
    classification: LineClassification
    narrative_level_of_classification: NarrativeLevel

    script_opposition: ScriptOpposition

    situation: str
    target: Optional[str]
    orientation: Orientation
    narrative_strategy: str
    language: LanguageKR


# Assembled outputs

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
