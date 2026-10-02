from __future__ import annotations

import argparse
import sys
from pathlib import Path

from typing import Optional

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink

from review_workbook import (
    CANONICAL_COLUMNS,
    GENERATED_SHEET,
    REVIEWER_COLUMNS,
    matching,
    read_review,
)
from schemas import Analysis, TextLevelReport
from textlevel import load_analysis

ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
TEXT_LEVEL_DIR = OUTPUT_DIR / "text_level"

FONT_NAME = "Arial"
HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(name=FONT_NAME, bold=True, color="FFFFFF")
HUMOR_ROW_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
HYPERLINK_FONT = Font(name=FONT_NAME, color="0563C1", underline="single")
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")
EDITABLE = CANONICAL_COLUMNS  # pre-filled; reviewers correct them in place
EDITABLE_HEADER_FILL = PatternFill(start_color="C55A11", end_color="C55A11", fill_type="solid")
NOTE_FONT = Font(name=FONT_NAME, italic=True, color="595959")
TITLE_FONT = Font(name=FONT_NAME, bold=True, size=12)


def _style_header(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = ws.cell(row=row + 1, column=1).coordinate


def _autofit(ws, widths: dict[int, int]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def build_report(
    analysis: Analysis,
    story_text: str,
    out_path: Path,
    text_level: Optional[TextLevelReport] = None,
) -> int:
    """Write the workbook; returns how many reviewer canonical edits from
    the previous version of the workbook were kept."""
    review = read_review(out_path)
    n_lines = len(story_text.splitlines())

    # Map each global line number -> containing segment label
    def segment_for_line(line_no: int) -> str:
        # Innermost segment, so lines of an embedded letter or speech show
        # that segment rather than the story it sits in
        containing = [s for s in analysis.segments
                      if s.line_start <= line_no <= s.line_end]
        if not containing:
            return ""
        return min(containing, key=lambda s: s.line_end - s.line_start).label

    line_to_annotation_ids: dict[int, list[str]] = {i: [] for i in range(1, n_lines + 1)}
    for al in analysis.lines:
        for ln in range(al.span.line_start, al.span.line_end + 1):
            if ln in line_to_annotation_ids:
                line_to_annotation_ids[ln].append(al.line_id)

    annotation_row = {al.line_id: i + 2 for i, al in enumerate(analysis.lines)}

    wb = Workbook()

    story_ws = wb.active
    story_ws.title = "Story"
    story_headers = ["Line #", "Segment", "Text", "Annotation(s)"]
    for c, h in enumerate(story_headers, start=1):
        story_ws.cell(row=1, column=c, value=h)
    _style_header(story_ws, 1, len(story_headers))

    for i, raw_line in enumerate(story_text.splitlines(), start=1):
        row = i + 1
        story_ws.cell(row=row, column=1, value=i).alignment = TOP
        story_ws.cell(row=row, column=2, value=segment_for_line(i)).alignment = TOP
        text_cell = story_ws.cell(row=row, column=3, value=raw_line)
        text_cell.alignment = WRAP

        ids = line_to_annotation_ids.get(i, [])
        ann_cell = story_ws.cell(row=row, column=4)
        if ids:
            ann_cell.value = ", ".join(ids)
            # Jump to the first annotation touching this line
            first_row = annotation_row[ids[0]]
            ann_cell.hyperlink = Hyperlink(ref=ann_cell.coordinate, location=f"Annotations!A{first_row}")
            ann_cell.font = HYPERLINK_FONT
            for c in range(1, len(story_headers) + 1):
                story_ws.cell(row=row, column=c).fill = HUMOR_ROW_FILL

    _autofit(story_ws, {1: 8, 2: 24, 3: 90, 4: 18})
    story_ws.auto_filter.ref = f"A1:D{n_lines + 1}"

    # Annotations sheet
    ann_ws = wb.create_sheet("Annotations")
    # (header, width); editable columns are listed in EDITABLE below
    ann_columns = [
        ("Line ID", 10), ("Context ▶", 14), ("Classification", 12),
        ("Narrative Level", 14), ("Segment", 22), ("Line Type", 14),
        ("Detection Confidence", 12), ("Span", 10), ("Humorous Text", 45),
        ("Disjunctor", 20), ("Detection Reason", 40),
        ("Script 1", 22), ("Script 2", 22), ("Binary Category", 18),
        ("Opposition Type", 20), ("Situation", 22), ("Canonical Situation", 22),
        ("Target", 20), ("Canonical Target", 20), ("Target Attributes", 26),
        ("Orientation", 12), ("Narrative Strategy", 18),
        ("Wordplay?", 10), ("Wordplay Level", 14), ("Wordplay Subtype", 18),
        ("Register Effect?", 14), ("Register Subtype", 18), ("Model Reasoning", 60),
        ("Reviewer Verdict", 16), ("Reviewer Notes", 30),
    ]
    ann_headers = [h for h, _ in ann_columns]
    col = {h: i + 1 for i, h in enumerate(ann_headers)}
    wrap_cols = {col[h] for h in ("Humorous Text", "Detection Reason",
                                  "Model Reasoning", "Reviewer Notes")}
    for c, h in enumerate(ann_headers, start=1):
        ann_ws.cell(row=1, column=c, value=h)
    _style_header(ann_ws, 1, len(ann_headers))
    for h in EDITABLE:
        ann_ws.cell(row=1, column=col[h]).fill = EDITABLE_HEADER_FILL

    seg_label = {s.segment_id: s.label for s in analysis.segments}
    inventory = {e.target_id: e for e in analysis.target_inventory}
    generated_rows = []
    kept_edits = 0

    for i, al in enumerate(analysis.lines):
        row = i + 2
        a = al.annotation
        so = a.script_opposition
        lang = a.language
        entry = inventory.get(al.canonical_target_id or "")
        values = {
            "Line ID": al.line_id,
            "Classification": a.classification.value,
            "Narrative Level": a.narrative_level_of_classification.value,
            "Segment": seg_label.get(al.segment_id, al.segment_id),
            "Line Type": al.line_type.value,
            "Detection Confidence": al.confidence or "",
            "Span": f"{al.span.line_start}\u2013{al.span.line_end}",
            "Humorous Text": al.span.text,
            "Disjunctor": al.disjunctor or "",
            "Detection Reason": al.brief_reason or "",
            "Script 1": so.script_1,
            "Script 2": so.script_2,
            "Binary Category": so.essential_binary_category.value,
            "Opposition Type": so.opposition_type.value,
            "Situation": a.situation,
            "Canonical Situation": al.canonical_situation or "",
            "Target": a.target or "",
            "Canonical Target": al.canonical_target or "",
            "Target Attributes": (
                f"{entry.kind.value}, {entry.social_class.value}, {entry.sphere.value}"
                if entry else ""),
            "Orientation": a.orientation.value,
            "Narrative Strategy": (
                f"other: {a.narrative_strategy_note}"
                if a.narrative_strategy.value == "other" and a.narrative_strategy_note
                else a.narrative_strategy.value),
            "Wordplay?": "Yes" if lang.is_wordplay else "No",
            "Wordplay Level": lang.wordplay_level.value if lang.wordplay_level else "",
            "Wordplay Subtype": lang.wordplay_subtype or "",
            "Register Effect?": "Yes" if lang.is_register_effect else "No",
            "Register Subtype": lang.register_effect_subtype or "",
            "Model Reasoning": a.reasoning,
            "Reviewer Verdict": "",
            "Reviewer Notes": "",
        }
        generated_rows.append((al.line_id, al.span.text, values["Canonical Target"],
                               values["Canonical Situation"]))

        # Keep what a reviewer typed into the previous version of this workbook.
        previous = matching(review, al.line_id, al.span.text)
        if previous is not None:
            for h in REVIEWER_COLUMNS:
                if previous.values.get(h) not in (None, ""):
                    values[h] = previous.values[h]
            for h, v in previous.edited_canonical().items():
                values[h] = v or ""
                kept_edits += 1

        for h, v in values.items():
            cell = ann_ws.cell(row=row, column=col[h], value=v)
            cell.alignment = WRAP if col[h] in wrap_cols else TOP

        ctx_cell = ann_ws.cell(row=row, column=col["Context ▶"], value="\u25b6 view in story")
        ctx_cell.hyperlink = Hyperlink(ref=ctx_cell.coordinate, location=f"Story!A{al.span.line_start + 1}")
        ctx_cell.font = HYPERLINK_FONT

    _autofit(ann_ws, {i + 1: w for i, (_, w) in enumerate(ann_columns)})
    ann_ws.auto_filter.ref = f"A1:{get_column_letter(len(ann_headers))}{len(analysis.lines) + 1}"

    verdict_col = get_column_letter(col["Reviewer Verdict"])
    dv = DataValidation(type="list", formula1='"Agree,Disagree,Partial,Unsure"', allow_blank=True)
    ann_ws.add_data_validation(dv)
    dv.add(f"{verdict_col}2:{verdict_col}{len(analysis.lines) + 1}")

    gen_ws = wb.create_sheet(GENERATED_SHEET)
    gen_ws.append(["Line ID", "Humorous Text", *CANONICAL_COLUMNS])
    for record in generated_rows:
        gen_ws.append(list(record))
    gen_ws.sheet_state = "hidden"

    seg_ws = wb.create_sheet("Segments")
    seg_headers = ["Segment ID", "Label", "Narrative Level", "Line Range",
                   "Parent", "Terminal?", "Cue", "Description"]
    for c, h in enumerate(seg_headers, start=1):
        seg_ws.cell(row=1, column=c, value=h)
    _style_header(seg_ws, 1, len(seg_headers))
    for i, seg in enumerate(analysis.segments):
        row = i + 2
        values = [
            seg.segment_id, seg.label, seg.narrative_level.value,
            f"{seg.line_start}\u2013{seg.line_end}",
            seg.parent_segment_id or "", "Yes" if seg.is_terminal else "No",
            seg.segmentation_cue, seg.description,
        ]
        for c, v in enumerate(values, start=1):
            seg_ws.cell(row=row, column=c, value=v).alignment = TOP
    _autofit(seg_ws, {1: 10, 2: 26, 3: 16, 4: 12, 5: 12, 6: 10, 7: 22, 8: 40})

    if text_level is not None:
        _strands_sheet(wb, text_level)
        _distribution_sheet(wb, text_level)
        if text_level.interpretation is not None:
            _plot_sheet(wb, text_level)

    wb.move_sheet(GENERATED_SHEET, offset=len(wb.sheetnames))

    # Apply the base font everywhere
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.font is None or cell.font.name != FONT_NAME:
                    existing = cell.font
                    cell.font = Font(
                        name=FONT_NAME,
                        bold=existing.bold, color=existing.color,
                        underline=existing.underline,
                    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return kept_edits


def _title(ws, row: int, text: str, note: str = "") -> int:
    ws.cell(row=row, column=1, value=text).font = TITLE_FONT
    if note:
        ws.cell(row=row + 1, column=1, value=note).font = NOTE_FONT
        return row + 3
    return row + 2


def _table(ws, top: int, headers: list[str], rows: list[list], wrap: tuple = ()) -> int:
    for c, h in enumerate(headers, start=1):
        ws.cell(row=top, column=c, value=h)
    _style_header_row(ws, top, len(headers))
    for r, values in enumerate(rows, start=top + 1):
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment = WRAP if headers[c - 1] in wrap else TOP
    return top + len(rows) + 2


def _style_header_row(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _strands_sheet(wb, report: TextLevelReport) -> None:
    m, p = report.metrics, report.metrics.params
    ws = wb.create_sheet("Strands")
    key_of = {s.strand_id: s.key for s in m.strands}
    row = _title(
        ws, 1, f"Strands: {len(m.strands)} (lines sharing a KR value or a pair of values)",
        f"Kept with at least {p['min_strand_lines']} lines. Central: span >= "
        f"{p['central_min_span']} of the text; peripheral: span <= "
        f"{p['peripheral_max_span']}. Comb: >= {p['comb_min_lines']} lines, each within "
        f"{p['comb_max_gap']} of the text of the next. Bridge: consecutive lines >= "
        f"{p['bridge_min_gap']} of the text apart.")
    row = _table(ws, row, [
        "Strand ID", "Key", "Lines", "Share", "Centrality", "First", "Last",
        "Span", "Combs", "Bridges", "Line IDs", "Equivalent Keys"],
        [[s.strand_id, s.key, s.n_lines, s.share, s.centrality, s.first_position,
          s.last_position, s.span_fraction, ", ".join(s.comb_ids),
          ", ".join(s.bridge_ids), ", ".join(s.line_ids), "; ".join(s.equivalent_keys)]
         for s in m.strands],
        wrap=("Key", "Line IDs", "Equivalent Keys"))
    ws.cell(row=row, column=1, value="Combs").font = TITLE_FONT
    row = _table(ws, row + 1, [
        "Comb ID", "Strand", "Strand Key", "Lines", "Words", "Words per Line", "Line IDs"],
        [[c.comb_id, c.strand_id, key_of.get(c.strand_id, ""), len(c.line_ids),
          f"{c.word_start}\u2013{c.word_end}", c.words_per_line, ", ".join(c.line_ids)]
         for c in m.combs], wrap=("Strand Key",))
    ws.cell(row=row, column=1, value="Bridges").font = TITLE_FONT
    _table(ws, row + 1, [
        "Bridge ID", "Strand", "Strand Key", "From Line", "To Line", "Gap (words)",
        "Gap (fraction)"],
        [[b.bridge_id, b.strand_id, key_of.get(b.strand_id, ""), b.from_line_id,
          b.to_line_id, b.gap_words, b.gap_fraction] for b in m.bridges],
        wrap=("Strand Key",))
    _autofit(ws, {1: 11, 2: 46, 3: 10, 4: 12, 5: 13, 6: 9, 7: 9, 8: 9, 9: 14, 10: 14, 11: 40, 12: 46})
    ws.freeze_panes = "A4"


def _distribution_sheet(wb, report: TextLevelReport) -> None:
    m = report.metrics
    d = m.distribution
    ws = wb.create_sheet("Distribution")
    row = _title(
        ws, 1, "Distribution of humorous lines",
        f"{d.n_words} words, {d.n_lines} humorous lines, one line every "
        f"{d.words_per_line} words on average; text cut into {d.n_sections} sections "
        f"of equal word count.")

    row = _table(ws, row, [
        "Null Hypothesis", "Statistic", "Value", "Expected if Null", "p (greater)",
        "p (less)", "Simulations", "Conclusion"],
        [[t.null_hypothesis, t.statistic_name, t.statistic, t.expected_under_null,
          t.p_value_greater, t.p_value_less, t.n_simulations, t.conclusion]
         for t in d.tests], wrap=("Conclusion",))

    in_stretch = {}
    for st in [*d.waves, *d.serious_reliefs]:
        for i in range(st.first_section, st.last_section + 1):
            in_stretch[i] = st.stretch_id
    header_row = row
    row = _table(ws, row, ["Section", "Words", "Lines", "Words per Line", "Wave / Relief"],
                 [[s.index, f"{s.word_start}\u2013{s.word_end}", s.n_lines,
                   s.words_per_line, in_stretch.get(s.index, "")] for s in d.sections])

    chart = BarChart()
    chart.type = "col"
    chart.title = "Humorous lines per section"
    chart.x_axis.title = "Section (equal word count)"
    chart.y_axis.title = "Lines"
    chart.legend = None
    chart.add_data(Reference(ws, min_col=3, min_row=header_row,
                             max_row=header_row + len(d.sections)), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=header_row + 1,
                                   max_row=header_row + len(d.sections)))
    chart.width, chart.height = 22, 9
    ws.add_chart(chart, f"G{header_row}")

    row = _table(ws, row, [
        "Stretch ID", "Kind", "Sections", "Words", "Lines", "Words per Line"],
        [[st.stretch_id, st.kind, f"{st.first_section}\u2013{st.last_section}",
          f"{st.word_start}\u2013{st.word_end}", st.n_lines, st.words_per_line]
         for st in [*d.waves, *d.serious_reliefs]])

    jp = m.jab_punch
    ws.cell(row=row, column=1,
            value=f"Jab and punch lines: {jp.n_jab} jab, {jp.n_punch} punch").font = TITLE_FONT
    row = _table(ws, row + 1, ["Segment", "Label", "Lines", "Jab", "Punch", "Words",
                               "Words per Line"],
                 [[c.group, c.label, c.n_lines, c.n_jab, c.n_punch, c.words, c.words_per_line]
                  for c in jp.by_segment], wrap=("Label",))
    row = _table(ws, row, ["Narrative Level", "Lines", "Jab", "Punch"],
                 [[c.group, c.n_lines, c.n_jab, c.n_punch] for c in jp.by_level])
    pi = m.plot_indicators
    _table(ws, row, ["Plot Indicator", "Value"], [
        ["Final punch lines", ", ".join(pi.final_punch_line_ids) or "none"],
        ["Metanarrative lines", f"{pi.n_metanarrative_lines} ({pi.metanarrative_share:.0%})"],
        ["Framing segments", pi.n_framing_segments],
    ])
    _autofit(ws, {1: 16, 2: 30, 3: 10, 4: 15, 5: 13, 6: 12, 7: 12, 8: 60})


def _evidence(refs) -> str:
    return "; ".join(f"{e.kind.value} {e.ref_id}: {e.figure}" for e in refs)


def _plot_sheet(wb, report: TextLevelReport) -> None:
    it = report.interpretation
    ws = wb.create_sheet("Plot")
    row = _title(
        ws, 1, "Text-level interpretation",
        f"One interpretive call ({report.interpretation_model}) on the aggregates only. "
        "The theory detects patterns; readings are interpretations layered on them, "
        "not findings of the theory.")
    cc = it.central_complication
    row = _table(ws, row, ["Item", "Value", "Evidence"], [
        ["Plot type", it.plot_type.value, _evidence(it.plot_type_evidence)],
        ["Confidence", it.plot_type_confidence.value, ""],
        ["Runner-up", it.runner_up_plot_type.value if it.runner_up_plot_type else "", ""],
        ["Rationale", it.plot_type_rationale, ""],
        ["Central complication", cc.description, _evidence(cc.evidence)],
        ["Complication segments", ", ".join(cc.segment_ids), ""],
        ["Complication humorous?", cc.humor_status.value, ""],
        ["Complication caveat", cc.caveat, ""],
    ], wrap=("Value", "Evidence"))
    row = _table(ws, row, ["Finding", "Pattern", "Evidence"],
                 [[f.finding_id, f.statement, _evidence(f.evidence)]
                  for f in it.pattern_findings], wrap=("Pattern", "Evidence"))
    row = _table(ws, row, ["Based On", "Reading", "Caveat"],
                 [[", ".join(r.based_on), r.reading, r.caveat] for r in it.readings],
                 wrap=("Reading", "Caveat"))
    if report.citation_warnings:
        _table(ws, row, ["Citation Warnings"], [[w] for w in report.citation_warnings],
               wrap=("Citation Warnings",))
    _autofit(ws, {1: 24, 2: 70, 3: 60})


def _run_one(json_path: Path, story_path: Path | None, out_path: Path | None,
             text_level_path: Path | None = None) -> None:
    analysis, _ = load_analysis(json_path)

    if story_path is None:
        story_path = INPUT_DIR / analysis.source_filename
    if not story_path.exists():
        print(f"  \u2717 story text not found: {story_path}", file=sys.stderr)
        print(f"    (expected from source_filename={analysis.source_filename!r} "
              f"in {json_path.name})", file=sys.stderr)
        return

    if out_path is None:
        out_path = json_path.with_suffix(".xlsx")
    text_level_path = text_level_path or (TEXT_LEVEL_DIR / f"{json_path.stem}.json")
    text_level = None
    if text_level_path.exists():
        text_level = TextLevelReport.model_validate_json(
            text_level_path.read_text(encoding="utf-8"))

    story_text = story_path.read_text(encoding="utf-8")
    try:
        kept = build_report(analysis, story_text, out_path, text_level)
    except PermissionError:
        print(f"  \u2717 can't write {out_path}: close it in Excel and re-run",
              file=sys.stderr)
        return
    extras = " with Strands/Distribution" if text_level else ""
    extras += "/Plot" if text_level and text_level.interpretation else ""
    print(f"  wrote {out_path}{extras}"
          + (f" (kept {kept} reviewer canonical edits)" if kept else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a reviewable Excel report.")
    parser.add_argument("--json", type=Path, help="Single analysis JSON (default: all in output/).")
    parser.add_argument("--story", type=Path, help="Override path to the original story .txt.")
    parser.add_argument("--out", type=Path, help="Output .xlsx path (default: alongside the JSON).")
    parser.add_argument("--text-level", type=Path,
                        help="Text-level results to add as Strands/Distribution/Plot sheets "
                             "(default: output/text_level/<story>.json, if present).")
    args = parser.parse_args()

    if args.json:
        print(f"\u2192 Building report for {args.json.name}")
        _run_one(args.json, args.story, args.out, args.text_level)
        return

    files = sorted(OUTPUT_DIR.glob("*.json"))
    if not files:
        print(f"No .json files in {OUTPUT_DIR}. Run the pipeline first.")
        return
    for jp in files:
        print(f"\u2192 Building report for {jp.name}")
        _run_one(jp, None, None)


if __name__ == "__main__":
    main()
