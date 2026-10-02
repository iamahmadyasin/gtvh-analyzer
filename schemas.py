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


class NarrativeStrategy(str, Enum):
    NARRATION = "narration"
    NARRATOR_ASIDE = "narrator_aside"
    FREE_INDIRECT_THOUGHT = "free_indirect_thought"
    SINGLE_UTTERANCE = "single_utterance"
    DIALOGUE_EXCHANGE = "dialogue_exchange"
    QUESTION_AND_ANSWER = "question_and_answer"
    EMBEDDED_TEXT = "embedded_text"
    LIST = "list"
    REPETITION_PATTERN = "repetition_pattern"
    OTHER = "other"


class TargetKind(str, Enum):
    PERSON = "person"
    GROUP = "group"
    INSTITUTION = "institution"
    IDEA = "idea"


class SocialClass(str, Enum):
    UPPER = "upper"
    MIDDLE = "middle"
    LOWER = "lower"
    MIXED = "mixed"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class SocialSphere(str, Enum):
    DOMESTIC = "domestic"
    ROMANCE_MARRIAGE = "romance_marriage"
    HIGH_SOCIETY = "high_society"
    RELIGION = "religion"
    POLITICS_GOVERNMENT = "politics_government"
    LAW_CRIME = "law_crime"
    COMMERCE_MONEY = "commerce_money"
    WORK_PROFESSION = "work_profession"
    ARTS_LETTERS = "arts_letters"
    SCIENCE_LEARNING = "science_learning"
    MEDICINE_HEALTH = "medicine_health"
    MILITARY = "military"
    SUPERNATURAL_BELIEF = "supernatural_belief"
    OTHER = "other"


class TextSpan(BaseModel):
    line_start: int
    line_end: int
    text: str

# Stage 1: Segmentation

class NarrativeSegment(BaseModel):
    segment_id: str
    label: str
    narrative_level: NarrativeLevel
    line_start: int
    line_end: int
    parent_segment_id: Optional[str]
    is_terminal: bool
    segmentation_cue: str
    description: str


class SegmentationResult(BaseModel):
    segments: list[NarrativeSegment]


# Stage 1b: Target inventory (one call per story)

class TargetEntry(BaseModel):
    target_id: str                      # "T-01"
    label: str                          # canonical name used everywhere else
    aliases: list[str]                  # other names the text uses for it
    kind: TargetKind
    social_class: SocialClass
    sphere: SocialSphere
    description: str


class TargetInventory(BaseModel):
    targets: list[TargetEntry]


# Stage 2: Detection

class DetectedLine(BaseModel):
    line_id: str
    span: TextSpan
    segment_id: str
    line_type: LineType
    disjunctor: Optional[str]
    disjunctor_span: Optional[TextSpan]
    setup: Optional[str]
    brief_reason: str
    confidence: Literal["high", "medium", "low"]


class DetectionResult(BaseModel):
    lines: list[DetectedLine]


# Stage 3: KR Annotation

class ScriptOpposition(BaseModel):
    script_1: str
    script_2: str
    essential_binary_category: BinaryCategory 
    opposition_type: OppositionType


class LanguageKR(BaseModel):
    is_wordplay: bool
    wordplay_level: Optional[WordplayLevel]
    wordplay_subtype: Optional[str]

    is_register_effect: bool
    register_effect_subtype: Optional[str]


class KRAnnotation(BaseModel):
    reasoning: str
    line_id: str
    classification: LineClassification
    narrative_level_of_classification: NarrativeLevel

    script_opposition: ScriptOpposition

    situation: str
    orientation: Orientation
    target_id: Optional[str]            # inventory entry, or null for a new / no target
    target: Optional[str]
    narrative_strategy: NarrativeStrategy
    narrative_strategy_note: Optional[str]
    language: LanguageKR

class AnnotatedLine(BaseModel):
    line_id: str
    span: TextSpan
    segment_id: str
    line_type: LineType
    disjunctor: Optional[str] = None
    disjunctor_span: Optional[TextSpan] = None
    # Carried over from Stage 2 so reviewers can filter weak detections.
    confidence: Optional[Literal["high", "medium", "low"]] = None
    setup: Optional[str] = None
    brief_reason: Optional[str] = None
    annotation: KRAnnotation
    # Set by normalize.py after annotation; reviewers can override them in
    # the workbook's Canonical Target / Canonical Situation columns.
    canonical_target: Optional[str] = None
    canonical_target_id: Optional[str] = None
    canonical_situation: Optional[str] = None


class Analysis(BaseModel):
    source_filename: str
    segments: list[NarrativeSegment]
    lines: list[AnnotatedLine]
    target_inventory: list[TargetEntry] = []
    normalization_method: Optional[str] = None


# Stage 4: Text-level analysis (textlevel.py, then one interpretive call)
#
# The metrics models are written by code, not by the model, so they may
# have defaults. They are the per-story record that a later corpus stage
# (stacks, baselines) reads, so keys are stable and every threshold used
# is stored with the results.

class SectionStat(BaseModel):
    index: int                          # 1-based
    word_start: int                     # inclusive
    word_end: int                       # exclusive
    n_lines: int
    line_ids: list[str]
    words_per_line: Optional[float]     # None when the section has no lines


class DistributionTest(BaseModel):
    null_hypothesis: Literal["random", "uniform"]
    statistic_name: str
    statistic: Optional[float]
    expected_under_null: Optional[float]
    p_value_greater: Optional[float]    # observed at least this large by chance
    p_value_less: Optional[float]       # observed at most this large by chance
    n_simulations: int
    conclusion: str


class Stretch(BaseModel):
    stretch_id: str                     # "W-1" (wave) or "R-1" (serious relief)
    kind: Literal["wave", "serious_relief"]
    first_section: int
    last_section: int
    word_start: int
    word_end: int
    n_lines: int
    words_per_line: Optional[float]


class Distribution(BaseModel):
    n_words: int
    n_lines: int
    n_sections: int
    words_per_line: Optional[float]
    sections: list[SectionStat]
    tests: list[DistributionTest]
    waves: list[Stretch]
    serious_reliefs: list[Stretch]


class StrandFeature(BaseModel):
    feature: str
    value: str


class Strand(BaseModel):
    strand_id: str                      # "S-001", by size within the story
    key: str                            # "feature=value[+feature=value]", stable across stories
    features: list[StrandFeature]
    line_ids: list[str]
    n_lines: int
    share: float                        # of all humorous lines in the story
    first_position: float               # fraction of text length
    last_position: float
    span_fraction: float
    centrality: Literal["central", "intermediate", "peripheral"]
    # Other keys with exactly the same lines (one strand, several descriptions)
    equivalent_keys: list[str] = []
    comb_ids: list[str] = []
    bridge_ids: list[str] = []


class Comb(BaseModel):
    comb_id: str
    strand_id: str
    line_ids: list[str]
    word_start: int
    word_end: int
    span_fraction: float
    words_per_line: Optional[float]


class Bridge(BaseModel):
    bridge_id: str
    strand_id: str
    from_line_id: str
    to_line_id: str
    gap_words: int
    gap_fraction: float


class JabPunchCount(BaseModel):
    group: str                          # segment id or narrative level
    label: str
    n_lines: int
    n_jab: int
    n_punch: int
    words: Optional[int] = None
    words_per_line: Optional[float] = None


class JabPunchSummary(BaseModel):
    n_jab: int
    n_punch: int
    by_segment: list[JabPunchCount]
    by_level: list[JabPunchCount]
    punch_line_ids: list[str]


class PlotIndicators(BaseModel):
    final_punch_line_ids: list[str]     # punch lines ending in the last stretch of text
    n_metanarrative_lines: int          # narrator asides or lines in framing levels
    metanarrative_share: float
    n_framing_segments: int             # level_+1 / level_+2 segments


class LineFeatures(BaseModel):
    line_id: str
    segment_id: str
    classification: str
    narrative_level: str
    word_start: int
    word_end: int
    position: float                     # midpoint, fraction of text length
    section: int
    features: dict[str, Optional[str]]  # strand feature -> value used


class TextLevelMetrics(BaseModel):
    schema_version: str
    story_id: str
    source_filename: str
    analysis_sha256: str
    story_sha256: str
    params: dict
    reviewer_overrides: int             # canonical values taken from the workbook
    lines: list[LineFeatures]
    distribution: Distribution
    strands: list[Strand]
    combs: list[Comb]
    bridges: list[Bridge]
    jab_punch: JabPunchSummary
    plot_indicators: PlotIndicators


# Stage 4b: interpretive call (LLM-facing: no defaults, closed enums)

class HumorousPlotType(str, Enum):
    SERIOUS_PLOT_WITH_JAB_LINES = "serious_plot_with_jab_lines"
    HUMOROUS_PLOT_WITH_PUNCH_LINE = "humorous_plot_with_punch_line"
    HUMOROUS_PLOT_WITH_METANARRATIVE_DISRUPTION = "humorous_plot_with_metanarrative_disruption"
    HUMOROUS_PLOT_WITH_HUMOROUS_CENTRAL_COMPLICATION = "humorous_plot_with_humorous_central_complication"


class EvidenceKind(str, Enum):
    STRAND = "strand"
    COMB = "comb"
    BRIDGE = "bridge"
    WAVE = "wave"
    SERIOUS_RELIEF = "serious_relief"
    DISTRIBUTION_TEST = "distribution_test"
    SEGMENT = "segment"
    JAB_PUNCH = "jab_punch"
    PLOT_INDICATOR = "plot_indicator"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ComplicationHumor(str, Enum):
    HUMOROUS = "humorous"
    NOT_HUMOROUS = "not_humorous"
    UNCLEAR = "unclear"


class EvidenceRef(BaseModel):
    kind: EvidenceKind
    ref_id: str                         # "S-003", "W-1", "NS-02", "random", ...
    figure: str                         # the count or statistic relied on


class PatternFinding(BaseModel):
    finding_id: str                     # "F-1"
    statement: str
    evidence: list[EvidenceRef]


class Reading(BaseModel):
    reading: str
    based_on: list[str]                 # finding_ids
    caveat: str


class CentralComplication(BaseModel):
    description: str
    segment_ids: list[str]
    humor_status: ComplicationHumor
    evidence: list[EvidenceRef]
    caveat: str


class PlotInterpretation(BaseModel):
    reasoning: str
    plot_type: HumorousPlotType
    plot_type_confidence: Confidence
    runner_up_plot_type: Optional[HumorousPlotType]
    plot_type_rationale: str
    plot_type_evidence: list[EvidenceRef]
    central_complication: CentralComplication
    pattern_findings: list[PatternFinding]
    readings: list[Reading]


class TextLevelReport(BaseModel):
    metrics: TextLevelMetrics
    interpretation: Optional[PlotInterpretation] = None
    interpretation_model: Optional[str] = None
    citation_warnings: list[str] = []
