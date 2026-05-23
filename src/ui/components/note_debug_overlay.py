"""Debug overlay that displays note type labels above notes on the timeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from src.core.const import AIR_ARROW_NOTES, NoteType
from src.ui import theme
from src.ui.theme.notes import get_note_color

if TYPE_CHECKING:
    from src.engine.timeline import ChartTimeline
    from src.notes import Note
    from src.ui.components.viewport import ChartViewport
    from src.ui.view.projection import ViewProjection


AIR_ACTION_DEBUG_ANCHOR_TYPES = frozenset(
    {NoteType.ASD, NoteType.ASC, NoteType.AHD}
)
AIR_ARROW_DEBUG_LABEL_OFFSET = 44.0
DEFAULT_DEBUG_LABEL_OFFSET = 18.0


class NoteDebugOverlay(QWidget):
    """Overlay widget that renders note type labels above each note head."""

    note_hovered = Signal(object)

    def __init__(self, parent: ChartViewport | None = None) -> None:
        super().__init__(parent)
        self._viewport = parent
        self._active = False
        self._hovered_note: Note | None = None
        self._hover_rects: list[tuple[QRectF, Note]] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setStyleSheet(f"background: {theme.TRANSPARENT}; border: none;")
        self.hide()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self.setVisible(active)
        self.update()

    def is_active(self) -> bool:
        return self._active

    def set_viewport(self, viewport: ChartViewport) -> None:
        self._viewport = viewport

    def _get_visible_notes(self) -> list[Note]:
        if not self._viewport or not self._viewport.chart:
            return []
        viewport = self._viewport
        chart = viewport.chart
        assert chart is not None
        timeline = chart.timeline
        projection = viewport.projection
        view_height = viewport.height()
        judgment_offset = viewport.judgment_offset
        render_pos = viewport.current_pos

        top_abs_pos = projection.pos_at(-(view_height - judgment_offset), render_pos)
        bottom_abs_pos = projection.pos_at(judgment_offset, render_pos)
        lo = min(top_abs_pos, bottom_abs_pos)
        hi = max(top_abs_pos, bottom_abs_pos)

        notes: list[Note] = []
        assert chart is not None
        for note in chart.notes:
            abs_pos = timeline.note_abs_pos(note)
            if lo - 1 <= abs_pos <= hi + 1:
                notes.append(note)
        return notes

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802, PLR0915
        if not self._active or not self._viewport or not self._viewport.chart:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        viewport = self._viewport
        chart = viewport.chart
        assert chart is not None
        timeline = chart.timeline
        projection = viewport.projection
        render_pos = viewport.current_pos
        chart_width = projection.x(viewport.total_lanes)
        offset_x = (viewport.width() - chart_width) / 2.0
        baseline_y = viewport.height() - viewport.judgment_offset

        self._hover_rects.clear()

        font = QFont(theme.FONT_MONO, 9, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        notes = self._get_visible_notes()
        for note in notes:
            nt_val = note.note_type.value
            if not viewport.visible_note_types.get(nt_val, True):
                composite_types = {
                    NoteType.HLD, NoteType.HXD, NoteType.SLD, NoteType.SXD,
                    NoteType.SLC, NoteType.SXC, NoteType.ASD, NoteType.ASC,
                    NoteType.ASX, NoteType.AHD, NoteType.AHX, NoteType.ALD,
                }
                if note.note_type not in composite_types:
                    continue

            abs_pos, cell, width = self._label_anchor(note, timeline)
            note_y = projection.y(abs_pos, render_pos) + baseline_y
            note_x = projection.x(cell) + offset_x
            note_w = projection.w(width)

            label = nt_val
            color = get_note_color(note.note_type)

            if getattr(note, "duration", 0) > 0:
                label = f"{nt_val}"

            text_width = metrics.horizontalAdvance(label)
            text_height = metrics.height()

            label_x = note_x + (note_w - text_width) / 2
            label_y = note_y - self._label_y_offset(note)

            is_hovered = note is self._hovered_note
            alpha = 220 if is_hovered else 160
            bg_color = theme.with_alpha(color, 40 if is_hovered else 25)
            border_color = theme.with_alpha(color, alpha)

            padding = 3
            rect = QRectF(
                label_x - padding,
                label_y - text_height + padding,
                text_width + padding * 2,
                text_height + padding * 2,
            )

            path = QPainterPath()
            path.addRoundedRect(rect, 3, 3)
            painter.fillPath(path, bg_color)
            painter.setPen(QPen(border_color, 1))
            painter.drawPath(path)

            painter.setPen(theme.qt(theme.TEXT_EDITOR) if is_hovered else color)
            painter.drawText(
                rect.toRect(),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

            self._hover_rects.append((rect, note))

        if self._hovered_note:
            self._draw_hover_tooltip(
                painter, self._hovered_note, viewport, timeline,
                projection, render_pos, offset_x, baseline_y,
            )

        painter.end()

    def _draw_hover_tooltip(  # noqa: PLR0913
        self,
        painter: QPainter,
        note: Note,
        viewport: ChartViewport,
        timeline: ChartTimeline,
        projection: ViewProjection,
        render_pos: float,
        offset_x: float,
        baseline_y: float,
    ) -> None:
        abs_pos, cell, width = self._label_anchor(note, timeline)
        note_y = projection.y(abs_pos, render_pos) + baseline_y
        note_x = projection.x(cell) + offset_x
        note_w = projection.w(width)

        lines = self._build_tooltip_lines(note, timeline)
        font = QFont(theme.FONT_MONO, 10, QFont.Weight.Normal)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        line_height = metrics.height()
        max_width = max(metrics.horizontalAdvance(line) for line in lines)
        padding = 8
        tooltip_w = max_width + padding * 2
        tooltip_h = line_height * len(lines) + padding * 2

        tooltip_x = note_x + note_w / 2 - tooltip_w / 2
        tooltip_y = note_y - 40 - tooltip_h

        if tooltip_y < 5:
            tooltip_y = note_y + 25

        tooltip_x = max(5, min(viewport.width() - tooltip_w - 5, tooltip_x))

        panel = QPainterPath()
        panel.addRoundedRect(QRectF(tooltip_x, tooltip_y, tooltip_w, tooltip_h), 5, 5)
        painter.fillPath(panel, theme.qt(theme.OVERLAY_PANEL_FILL))
        painter.setPen(QPen(theme.qt(theme.OVERLAY_PANEL_BORDER), 1))
        painter.drawPath(panel)

        painter.setPen(theme.qt(theme.ACCENT))
        painter.drawText(
            int(tooltip_x + padding),
            int(tooltip_y + padding + line_height - metrics.descent()),
            lines[0],
        )
        painter.setPen(theme.qt(theme.TEXT_EDITOR))
        for i, line in enumerate(lines[1:], 1):
            painter.drawText(
                int(tooltip_x + padding),
                int(tooltip_y + padding + line_height * (i + 1) - metrics.descent()),
                line,
            )

    def _build_tooltip_lines(self, note: Note, timeline: ChartTimeline) -> list[str]:
        lines: list[str] = []
        abs_pos = timeline.note_abs_pos(note)
        lines.append(f"{note.note_type.value}")

        measure = note.measure
        resolution = getattr(timeline, "resolution", 192)
        tick_in_measure = note.offset
        lines.append(f"Measure: {measure}  Tick: {tick_in_measure}/{resolution}")

        lines.append(f"Cell: {note.cell}  Width: {note.width}")
        lines.append(f"Abs Pos: {abs_pos:.4f}")

        note_duration = getattr(note, "duration", 0)
        if note_duration:
            abs_end = timeline.note_abs_end_pos(note)
            lines.append(f"Duration: {note_duration} ticks")
            lines.append(f"End Pos: {abs_end:.4f}")

        note_animation = getattr(note, "animation", None)
        if note_animation:
            lines.append(f"Animation: {note_animation}")

        note_direction = getattr(note, "direction", None)
        if note_direction:
            lines.append(f"Direction: {note_direction}")

        note_color = getattr(note, "color", None)
        if note_color:
            lines.append(f"Color: {note_color}")

        note_steps = getattr(note, "steps", None)
        if note_steps is not None:
            lines.append(f"Steps: {len(note_steps)}")

        return lines

    def _label_anchor(self, note: Note, timeline: ChartTimeline) -> tuple[float, float, float]:
        if note.note_type in AIR_ACTION_DEBUG_ANCHOR_TYPES:
            return (
                timeline.note_abs_end_pos(note),
                float(getattr(note, "end_cell", note.cell)),
                float(getattr(note, "end_width", note.width)),
            )
        return (
            timeline.note_abs_pos(note),
            float(note.cell),
            float(note.width),
        )

    def _label_y_offset(self, note: Note) -> float:
        if note.note_type in AIR_ARROW_NOTES:
            return AIR_ARROW_DEBUG_LABEL_OFFSET
        return DEFAULT_DEBUG_LABEL_OFFSET

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._active:
            return

        pos = event.position()
        found: Note | None = None
        for rect, note in self._hover_rects:
            if rect.contains(pos):
                found = note
                break

        if found is not self._hovered_note:
            self._hovered_note = found
            self.update()
            if found is not None:
                self.note_hovered.emit(found)
            else:
                self.note_hovered.emit(None)

    def leaveEvent(self, event: QEvent | None) -> None:  # noqa: N802
        if self._hovered_note is not None:
            self._hovered_note = None
            self.update()
