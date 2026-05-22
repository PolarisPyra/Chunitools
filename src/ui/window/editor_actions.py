from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu

from src.core.const import AirTraceColor, NoteType
from src.core.editor import add_note, make_note, snap_abs_pos
from src.notes import AirSlideStart, Note, Slide
from src.ui import theme
from src.ui.theme.notes import TRACE_COLORS, get_note_color

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow


AIR_ANCHORED_TYPES = {
    NoteType.AIR, NoteType.AUR, NoteType.AUL,
    NoteType.ADW, NoteType.ADR, NoteType.ADL,
    NoteType.AHD, NoteType.AHX,
    NoteType.ASD, NoteType.ASC,
}
GROUND_SLIDE_TYPES = {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}
AIR_SLIDE_TYPES = {NoteType.ASD, NoteType.ASC}


class NoteEditor:
    """Orchestrates note placement, context menus, and delegates to specialist helpers."""

    def __init__(self, window: MainWindow) -> None:
        self.w = window
        from src.ui.window.slide_editor import SlideEditor
        from src.ui.window.note_history import NoteHistory
        from src.ui.window.source_opener import SourceFileOpener
        self.slides = SlideEditor(window)
        self.history = NoteHistory(window)
        self.source = SourceFileOpener(window)

    @property
    def _chart(self):
        return self.w.current_chart

    @property
    def _read_only(self):
        return self.w._chart_read_only

    @property
    def _dirty(self):
        return self.w._chart_dirty

    @_dirty.setter
    def _dirty(self, v):
        self.w._chart_dirty = v

    # ── Place note (single click) ──

    def place_note_at(
        self, abs_pos: float, cell: int, width: int | None = None
    ) -> None:
        if self._chart is None:
            self.w.new_chart()
        if self._chart is None or self._read_only:
            return
        chart = self._chart
        res = chart.metadata.resolution
        measure, offset = snap_abs_pos(abs_pos, res, self.w.visualizer.subdivisions)
        nt = self.w._editor_note_type
        tick = measure * res + offset
        target_note, parent, cell, width = self._anchor_context(
            nt, tick, cell, self.w._editor_note_width if width is None else width,
        )
        note = make_note(nt, measure=measure, offset=offset, cell=cell, width=width,
                         duration=384, target_note=target_note, parent=parent)
        add_note(chart, note)
        self.history.push("add", [note])
        self._finish_placement(note, f"Placed {note.note_type.value} at {note.measure}:{note.offset}.")

    # ── Place note (drag) ──

    def place_note_drag(
        self, start_abs_pos: float, start_cell: int,
        end_abs_pos: float, end_cell: int,
    ) -> None:
        if self._chart is None:
            self.w.new_chart()
        if self._chart is None or self._read_only:
            return
        chart = self._chart
        res = chart.metadata.resolution
        sub = self.w.visualizer.subdivisions
        sm, so = snap_abs_pos(start_abs_pos, res, sub)
        em, eo = snap_abs_pos(end_abs_pos, res, sub)
        st = sm * res + so
        et = em * res + eo
        if et < st:
            st, et = et, st
            start_cell, end_cell = end_cell, start_cell
            sm, so = divmod(st, res)
        tick_step = max(1, round(res / max(1, sub)))
        duration = max(tick_step, et - st)
        target_note, parent, sc, w = self._anchor_context(
            self.w._editor_note_type, st, start_cell, self.w._editor_note_width,
        )
        ec = max(0, min(max(0, 16 - w), int(end_cell)))

        if self.w._editor_note_type in GROUND_SLIDE_TYPES:
            r = self.slides.append_ground(st, sc, w, sm, so, duration, ec)
            if r is not None:
                self.history.push("replace", [r.steps[0], r])
                self._finish_placement(r, f"Extended {r.note_type.value} at {sm}:{so}.")
                return

        if self.w._editor_note_type in AIR_SLIDE_TYPES:
            r = self.slides.append_air(st, sc, w, sm, so, duration, ec)
            if r is not None:
                self.history.push("replace", [r.steps[0], r])
                self._finish_placement(r, f"Extended {r.note_type.value} at {sm}:{so}.")
                return

        note = make_note(self.w._editor_note_type,
                         measure=sm, offset=so, cell=sc, width=w,
                         duration=duration, end_cell=ec, end_width=w,
                         target_note=target_note, parent=parent)
        add_note(chart, note)
        self.history.push("add", [note])
        self._finish_placement(note, f"Placed {note.note_type.value} from {note.measure}:{note.offset}.")

    def _finish_placement(self, note: Note, status: str) -> None:
        if self._chart is None:
            return
        pos = self.w.visualizer.current_pos
        self.w.playback_service.refresh_chart_after_edit()
        self._dirty = True
        self.w._display_chart(self._chart)
        self.w.visualizer.set_current_pos(pos)
        self.w.visualizer.selected_note = note
        self.w.visualizer.selected_notes = [note]
        self.w._on_note_selected(note)
        self.w._sync_file_actions()
        self.w.statusBar().showMessage(status, 2000)

    # ── Delete ──

    def delete_selected(self) -> None:
        if not self._chart or self._read_only:
            return
        from src.core.editor import remove_notes
        removed = remove_notes(self._chart, list(self.w.visualizer.selected_notes))
        if not removed:
            return
        self.w.playback_service.refresh_chart_after_edit()
        self._dirty = True
        self.w._display_chart(self._chart)
        self.w._sync_file_actions()
        self.w.statusBar().showMessage(f"Deleted {removed} note(s).", 2000)

    # ── Undo / Redo ──

    def undo(self) -> None:
        result = self.history.undo()
        if result:
            action, notes = result
            self._finish_history(
                {"undo_add": "Undid note placement.", "undo_replace": "Undid note edit."}[action],
                selected_note=notes[0] if notes else None,
            )

    def redo(self) -> None:
        result = self.history.redo()
        if result:
            action, notes = result
            self._finish_history(
                {"redo_add": "Redid note placement.", "redo_replace": "Redid note edit."}[action],
                selected_note=notes[0] if notes else None,
            )

    def _finish_history(self, message: str, *, selected_note: Note | None = None) -> None:
        if self._chart is None:
            return
        pos = self.w.visualizer.current_pos
        self.w.playback_service.refresh_chart_after_edit()
        self._dirty = True
        self.w._display_chart(self._chart)
        self.w.visualizer.set_current_pos(pos)
        if selected_note is None:
            self.w.visualizer.selected_note = None
            self.w.visualizer.selected_notes = []
            self.w._on_notes_selected([])
        else:
            self.w.visualizer.selected_note = selected_note
            self.w.visualizer.selected_notes = [selected_note]
            self.w._on_note_selected(selected_note)
        self.w._sync_file_actions()
        self.w.statusBar().showMessage(message, 2000)

    def _sync_history_actions(self) -> None:
        self.history._sync()

    def clear_history(self) -> None:
        self.history.clear()

    # ── Context menu ──

    def show_note_context_menu(self, note: Note, global_pos) -> None:
        menu = QMenu(self.w)
        act = menu.addAction("Open in Chart File")
        act.triggered.connect(lambda _=False: self.source.open(note))
        if note.note_type == NoteType.ALD:
            menu.addSeparator()
            self._add_trace_color_actions(menu, note)
        menu.exec(global_pos)

    def _add_trace_color_actions(self, menu: QMenu, note: Note) -> None:
        current = getattr(note, "color", "DEF")
        for c in AirTraceColor:
            code = c.value
            a = menu.addAction(self._trace_color_icon(code), code)
            a.setCheckable(True)
            a.setChecked(code == current)
            a.triggered.connect(lambda _=False, sel=code: self._change_trace_color(note, sel))

    def _trace_color_icon(self, color_code: str) -> QIcon:
        pix = QPixmap(18, 18)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(theme.qt(theme.BORDER_CONTROL_SOFT))
        p.setBrush(get_note_color(NoteType.ALD, color_code))
        p.drawRoundedRect(2, 2, 14, 14, 3, 3)
        p.end()
        return QIcon(pix)

    def _change_trace_color(self, note: Note, color_code: str) -> None:
        if self._chart is None or self._read_only:
            return
        if note.note_type != NoteType.ALD or color_code not in TRACE_COLORS:
            return
        if getattr(note, "color", None) == color_code:
            return
        replacement = replace(note, color=color_code)
        self.slides.replace_note(note, replacement)
        self.history.push("replace", [note, replacement])
        self._finish_history(f"Changed ALD color to {color_code}.", selected_note=replacement)

    # ── Anchor helpers ──

    def _anchor_context(self, note_type: NoteType, tick: int, cell: int, width: int) -> tuple[str, Note | None, int, int]:
        if self._chart is None or note_type not in AIR_ANCHORED_TYPES:
            return "DEF", None, cell, width
        anchor = self._editor_air_anchor(tick, cell, width)
        if anchor is None:
            return "DEF", None, cell, width
        return anchor

    def _editor_air_anchor(self, tick: int, cell: int, width: int) -> tuple[str, Note, int, int] | None:
        chart = self._chart
        if chart is None:
            return None
        tl = chart.timeline
        for cand in reversed(chart.notes):
            if cand.note_type == NoteType.ALD:
                continue
            points: list[tuple[str, Note, int, int, int]] = [
                (cand.note_type.value, cand, tl.note_tick(cand), int(cand.cell), int(cand.width)),
            ]
            if isinstance(cand, (Slide, AirSlideStart)):
                for step in cand.steps:
                    points.append((step.note_type.value, step, tl.note_end_tick(step), int(step.end_cell), int(step.end_width)))
            elif hasattr(cand, "duration"):
                end_cell = int(getattr(cand, "end_cell", cand.cell))
                end_width = int(getattr(cand, "end_width", cand.width))
                points.append((cand.note_type.value, cand, tl.note_end_tick(cand), end_cell, end_width))
            for tn, _, at, ac, aw in points:
                if at == tick and ac == cell and aw == width:
                    return tn, cand, ac, aw
        return None

    def sync_place_mode(self) -> None:
        if self.w.current_chart is None:
            self.w.visualizer.set_editor_place_mode(False)
            return
        self.w.visualizer.set_editor_place_mode(True)
