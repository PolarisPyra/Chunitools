from __future__ import annotations

import re
from html import escape
from typing import TYPE_CHECKING

from src.core.const import NoteType, RenderRole
from src.notes.schema import NOTE_SCHEMAS

if TYPE_CHECKING:
    from src.core.models import Chart
from src.notes import AirSlideStart, Note, Slide

_AIR_DIRECTION_BEHAVIOR = {
    NoteType.AIR: "AIR UP",
    NoteType.AUR: "AIR UP-RIGHT",
    NoteType.AUL: "AIR UP-LEFT",
    NoteType.ADW: "AIR DOWN",
    NoteType.ADR: "AIR DOWN-RIGHT",
    NoteType.ADL: "AIR DOWN-LEFT",
}

_NOTE_COLORS: dict[NoteType, str] = {
    NoteType.TAP: "#ff4040",
    NoteType.CHR: "#ffcc00",
    NoteType.FLK: "#d0d0d0",
    NoteType.MNE: "#af52de",
    NoteType.HLD: "#ff9000",
    NoteType.HXD: "#ff9000",
    NoteType.SLD: "#0090ff",
    NoteType.SLC: "#0090ff",
    NoteType.SXD: "#0090ff",
    NoteType.SXC: "#0090ff",
    NoteType.AIR: "#33ff55",
    NoteType.AUR: "#33ff55",
    NoteType.AUL: "#33ff55",
    NoteType.ADW: "#ff33cc",
    NoteType.ADR: "#ff33cc",
    NoteType.ADL: "#ff33cc",
    NoteType.AHD: "#33ff55",
    NoteType.AHX: "#d13bff",
    NoteType.ALD: "#33ff55",
    NoteType.ASD: "#34c759",
    NoteType.ASC: "#34c759",
    NoteType.ASO: "#45c4ff",
    NoteType.HHD: "#fff4a3",
    NoteType.HHX: "#fff4a3",
}


def _note_tag(note_type: NoteType) -> str:
    color = _NOTE_COLORS.get(note_type, "#ffffff")
    return f'<span style="color:{color};font-weight:bold;">{escape(note_type.value)}</span>'


def _detail_line(label: str, value: str, *, rich_value: bool = False) -> str:
    rendered_value = value if rich_value else escape(value)
    return f'<span style="color:#ffffff;">{escape(label)}</span> ' \
           f'<span style="color:#cccccc;">{rendered_value}</span><br>'


def format_render_behavior(note: Note, chart: Chart | None = None) -> str:  # noqa: PLR0912
    """Format the calculated render behavior of *note* as HTML."""
    note_type = note.note_type
    timeline = chart.timeline if chart else None

    role = timeline.note_render_role(note) if timeline else None
    abs_pos = timeline.note_abs_pos(note) if timeline else 0.0
    anchor = timeline.note_anchor(note) if timeline else None

    behavior_map = {
        NoteType.TAP: "TAP",
        NoteType.CHR: "EX TAP",
        NoteType.FLK: "FLICK",
        NoteType.MNE: "MINE",
        NoteType.HLD: "HOLD",
        NoteType.HXD: "EX HOLD",
        NoteType.AHD: "AIR HOLD",
        NoteType.AHX: "AIR HOLD ACTION",
    }

    if note_type in behavior_map:
        behavior = behavior_map[note_type]
    elif note_type == NoteType.SLC:
        behavior = "SLIDE" if role == RenderRole.HEAD else "SLIDE CONTROL POINT"
    elif note_type == NoteType.SXC:
        behavior = "SLIDE (EX)" if role == RenderRole.HEAD else "SLIDE CONTROL POINT (EX)"
    elif note_type == NoteType.SLD:
        behavior = "SLIDE"
    elif note_type == NoteType.SXD:
        behavior = "SLIDE (EX)"
    elif note_type in {NoteType.ASD, NoteType.ASC}:
        behavior = "AIR SLIDE" if note_type == NoteType.ASD else "AIR SLIDE CONTROL"
    elif note_type == NoteType.ALD:
        color = getattr(note, "color", "")
        if color == "NON":
            behavior = "AIR ACTION / AIR CRUSH"
        elif color == "DEF":
            behavior = "AIR TRACE"
        else:
            behavior = "AIR TRACE / EFFECT"
    elif note_type in _AIR_DIRECTION_BEHAVIOR:
        behavior = _AIR_DIRECTION_BEHAVIOR[note_type]
    else:
        behavior = f"UNKNOWN ({note_type})"

    duration = getattr(note, "duration", 0) if hasattr(note, "duration") else 0

    html = '<div style="font-family:monospace;font-size:12px;line-height:1.7;">'
    html += _detail_line("TYPE", _note_tag(note_type), rich_value=True)
    html += _detail_line("POS", f"{note.measure}:{note.offset}  (abs={abs_pos:.3f})")
    html += _detail_line("LANE", f"{note.cell}  (width={note.width})")
    html += _detail_line("BEH", behavior)

    if role and note_type not in {NoteType.SLC, NoteType.SXC, NoteType.SLD, NoteType.SXD}:
        html += _detail_line("ROLE", role.name)

    if duration > 0:
        html += _detail_line("DUR", f"{duration} ticks")

    if anchor:
        html += _detail_line(
            "ANC",
            f'{_note_tag(anchor.note_type)}  at {anchor.measure}:{anchor.offset}',
            rich_value=True,
        )

    html += "</div>"
    return html


def _flatten_notes(raw: list[Note]) -> list[Note]:
    out: list[Note] = []
    for n in raw:
        if isinstance(n, (Slide, AirSlideStart)):
            out.extend(n.steps)
        else:
            out.append(n)
    return out


def format_notes_summary(notes: list[Note], chart: Chart | None = None, grouped: bool = True) -> str:
    """Format a summary for multiple selected notes as HTML."""
    if not notes:
        return '<span style="color:#888;">No notes selected.</span>'

    flat = _flatten_notes(notes)

    html = '<div style="font-family:monospace;font-size:12px;line-height:1.6;">'
    html += f'<span style="color:#ffffff;font-size:13px;font-weight:bold;">' \
            f'SELECTED NOTES: {len(flat)}</span>'

    if chart:
        chart_total = sum(
            len(n.steps) if isinstance(n, (Slide, AirSlideStart)) else 1
            for n in chart.notes
        )
        html += f'  <span style="color:#888;">/ {chart_total} total</span>'

    html += '<br><br>'

    if chart:
        if grouped:
            html += _format_grouped(flat, chart)
        else:
            html += _format_chronological(flat, chart)
    else:
        counts: dict[NoteType, int] = {}
        for n in notes:
            counts[n.note_type] = counts.get(n.note_type, 0) + 1
        sorted_types = sorted(counts.items(), key=lambda x: (-x[1], x[0].value))
        for ntype, count in sorted_types:
            html += f'{_note_tag(ntype)}: <span style="color:#ccc;">{count}</span><br>'

    html += "</div>"
    return html


def _format_grouped(notes: list[Note], chart: Chart) -> str:
    html = ""
    notes_by_type: dict[NoteType, list[Note]] = {}
    for note in notes:
        notes_by_type.setdefault(note.note_type, []).append(note)

    for ntype, type_notes in notes_by_type.items():
        header_parts = _get_header_parts(ntype)
        col_widths = [3, 4, 3, 3] + [max(len(h), 5) for h in header_parts[4:]]

        html += f'<span style="color:{_NOTE_COLORS.get(ntype, "#ffffff")};' \
                f'font-weight:bold;">[{escape(ntype.value)}]</span><br>'

        html += _render_table_header(header_parts, col_widths)
        html += _render_table_separator(col_widths)

        for note in type_notes:
            raw = chart.find_note_line(note)
            parts = raw.split()
            row_html = "&nbsp;".join(
                f'{"&nbsp;" * (w - len(p))}{escape(p)}'
                for p, w in zip(parts[1:], col_widths, strict=False)
            )
            html += row_html + "<br>"
        html += "<br>"

    return html


def _format_chronological(notes: list[Note], chart: Chart) -> str:
    sorted_notes = sorted(notes, key=lambda n: (n.measure, n.offset, n.cell, n.width))
    # Unified base columns: TYPE MS OFF CEL WID
    header_parts = ["TYPE", "MS", "OFF", "CEL", "WID"]
    base_count = 5
    col_widths = [5, 3, 4, 3, 3]
    html = _render_table_header(header_parts, col_widths)
    html += _render_table_separator(col_widths)
    for note in sorted_notes:
        raw = chart.find_note_line(note)
        parts = raw.split()
        cells = [escape(parts[0])]
        for p, w in zip(parts[1:base_count], col_widths[1:], strict=False):
            cells.append(f'{"&nbsp;" * (w - len(p))}{escape(p)}')
        if len(parts) > base_count:
            extra = " ".join(parts[base_count:])
            cells.append(f"  <span style='color:#666;'>{escape(extra)}</span>")
        color = _NOTE_COLORS.get(note.note_type, "#ffffff")
        html += f'<span style="color:{color};">' + "&nbsp;".join(cells) + "</span><br>"
    html += "<br>"
    return html


def _render_table_header(header_parts: list[str], col_widths: list[int]) -> str:
    html = '<span style="color:#aaa;">'
    parts_html = "&nbsp;".join(
        f'{"&nbsp;" * (w - len(h))}{escape(h)}'
        for h, w in zip(header_parts, col_widths, strict=False)
    )
    html += parts_html + "</span><br>"
    return html


def _render_table_separator(col_widths: list[int]) -> str:
    dash = "─" * (sum(col_widths) + len(col_widths) - 1)
    return f'<span style="color:#555;">{dash}</span><br>'


def _get_header_parts(ntype: NoteType) -> list[str]:  # noqa: PLR0911
    """Return descriptive header parts for the given note type."""
    base = ["MS", "OFF", "CEL", "WID"]

    labels = {
        "animation": "ANI",
        "color": "CLR",
        "crush_interval": "TICK",
        "direction": "DIR",
        "duration": "DUR",
        "end_cell": "ECL",
        "end_width": "EWD",
        "heaven_id": "HID",
        "starting_depth": "DEP",
        "starting_height": "HGT",
        "target_depth": "EDEP",
        "target_height": "EHGT",
        "target_id": "TYPE",
        "target_note": "TRG",
    }
    schema = NOTE_SCHEMAS.get(ntype)
    if schema is not None:
        return base + [
            f"[{labels.get(field.name, field.name.upper())}]"
            if not field.required
            else labels.get(field.name, field.name.upper())
            for field in schema.fields
        ]

    if ntype in (NoteType.TAP, NoteType.MNE):
        return base
    if ntype == NoteType.FLK:
        return base + ["UNK"]
    if ntype == NoteType.CHR:
        return base + ["ANI"]
    if ntype in (NoteType.HLD, NoteType.HXD):
        return base + ["DUR", "[ANI]"]
    if ntype in (NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC):
        return base + ["DUR", "ECL", "EWD", "TYPE", "[ANI]"]
    if ntype == NoteType.AIR:
        return base + ["TRG"]
    if ntype in (NoteType.AUR, NoteType.AUL, NoteType.ADW, NoteType.ADR, NoteType.ADL):
        return base + ["TRG", "CLR"]
    if ntype == NoteType.AHD:
        return base + ["TRG", "DUR"]
    if ntype == NoteType.AHX:
        return base + ["TRG", "DUR", "CLR"]
    if ntype == NoteType.ALD:
        return base + ["TICK", "HGT", "DUR", "ECL", "EWD", "EHGT", "CLR"]
    if ntype in (NoteType.ASD, NoteType.ASC):
        return base + ["TRG", "HGT", "DUR", "ECL", "EWD", "EHGT", "CLR"]

    return base


def resolve_warning_note(chart: Chart, warning: str) -> Note | None:
    match = re.search(r"at (\d+):(\d+)", warning)
    if not match:
        return None
    measure = int(match.group(1))
    offset = int(match.group(2))
    for note in chart.notes:
        if note.measure == measure and note.offset == offset:
            return note
    return None
