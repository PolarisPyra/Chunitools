from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu

from src.core.const import AirTraceColor, NoteType
from src.core.editor import add_note, make_note, remove_notes, snap_abs_pos
from src.notes import AirSlide, AirSlideStart, Note, Slide, SlideTo
from src.ui import theme
from src.ui.theme.notes import TRACE_COLORS, get_note_color

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow

LOGGER = logging.getLogger(__name__)
EDITOR_ENV_VAR = "CHUNITOOLS_EDITOR"

AIR_ANCHORED_EDITOR_TYPES = {
    NoteType.AIR,
    NoteType.AUR,
    NoteType.AUL,
    NoteType.ADW,
    NoteType.ADR,
    NoteType.ADL,
    NoteType.AHD,
    NoteType.AHX,
    NoteType.ASD,
    NoteType.ASC,
}
GROUND_SLIDE_EDITOR_TYPES = {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}
AIR_SLIDE_EDITOR_TYPES = {NoteType.ASD, NoteType.ASC}


class NoteEditor:
    """Manages note placement, editing, undo/redo, and slide operations."""

    def __init__(self, window: MainWindow) -> None:
        self.w = window

    # ── Quick-access helpers ──

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
        if self._chart is None:
            return
        if self._read_only:
            return
        chart = self._chart
        measure, offset = snap_abs_pos(
            abs_pos,
            chart.metadata.resolution,
            self.w.visualizer.subdivisions,
        )
        note_type = self.w._editor_note_type
        tick = measure * chart.metadata.resolution + offset
        target_note, parent, cell, width = self._placement_anchor_context(
            note_type, tick, cell, self.w._editor_note_width if width is None else width,
        )
        note = make_note(
            note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            duration=384,
            target_note=target_note,
            parent=parent,
        )
        add_note(chart, note)
        self._push_history("add", [note])
        current_pos = self.w.visualizer.current_pos
        self.w.playback_service.refresh_chart_after_edit()
        self._dirty = True
        self.w._display_chart(chart)
        self.w.visualizer.set_current_pos(current_pos)
        self.w.visualizer.selected_note = note
        self.w.visualizer.selected_notes = [note]
        self.w._on_note_selected(note)
        self.w._sync_file_actions()
        self.w.statusBar().showMessage(
            f"Placed {note.note_type.value} at {note.measure}:{note.offset}.", 2000,
        )

    # ── Place note (drag) ──

    def place_note_drag(
        self,
        start_abs_pos: float,
        start_cell: int,
        end_abs_pos: float,
        end_cell: int,
    ) -> None:
        if self._chart is None:
            self.w.new_chart()
        if self._chart is None:
            return
        if self._read_only:
            return

        chart = self._chart
        resolution = chart.metadata.resolution
        start_measure, start_offset = snap_abs_pos(
            start_abs_pos, resolution, self.w.visualizer.subdivisions,
        )
        end_measure, end_offset = snap_abs_pos(
            end_abs_pos, resolution, self.w.visualizer.subdivisions,
        )
        start_tick = start_measure * resolution + start_offset
        end_tick = end_measure * resolution + end_offset
        if end_tick < start_tick:
            start_tick, end_tick = end_tick, start_tick
            start_cell, end_cell = end_cell, start_cell
            start_measure, start_offset = divmod(start_tick, resolution)
        tick_step = max(1, round(resolution / max(1, self.w.visualizer.subdivisions)))
        duration = max(tick_step, end_tick - start_tick)
        target_note, parent, start_cell, width = self._placement_anchor_context(
            self.w._editor_note_type, start_tick, start_cell, self.w._editor_note_width,
        )
        max_cell = max(0, 16 - width)
        clamped_end_cell = max(0, min(max_cell, int(end_cell)))

        if self.w._editor_note_type in GROUND_SLIDE_EDITOR_TYPES:
            appended = self._append_ground_slide(
                start_tick, start_cell, width,
                start_measure, start_offset, duration, clamped_end_cell,
            )
            if appended is not None:
                self._finish_placement(
                    appended,
                    f"Extended {appended.note_type.value} at "
                    f"{start_measure}:{start_offset} for {duration} ticks.",
                )
                return

        if self.w._editor_note_type in AIR_SLIDE_EDITOR_TYPES:
            appended = self._append_air_slide(
                start_tick, start_cell, width,
                start_measure, start_offset, duration, clamped_end_cell,
            )
            if appended is not None:
                self._finish_placement(
                    appended,
                    f"Extended {appended.note_type.value} at "
                    f"{start_measure}:{start_offset} for {duration} ticks.",
                )
                return

        note = make_note(
            self.w._editor_note_type,
            measure=start_measure,
            offset=start_offset,
            cell=start_cell,
            width=width,
            duration=duration,
            end_cell=clamped_end_cell,
            end_width=width,
            target_note=target_note,
            parent=parent,
        )
        add_note(chart, note)
        self._push_history("add", [note])
        self._finish_placement(
            note,
            f"Placed {note.note_type.value} from {note.measure}:{note.offset} "
            f"for {duration} ticks.",
        )

    def _finish_placement(self, note: Note, status: str) -> None:
        if self._chart is None:
            return
        current_pos = self.w.visualizer.current_pos
        self.w.playback_service.refresh_chart_after_edit()
        self._dirty = True
        self.w._display_chart(self._chart)
        self.w.visualizer.set_current_pos(current_pos)
        self.w.visualizer.selected_note = note
        self.w.visualizer.selected_notes = [note]
        self.w._on_note_selected(note)
        self.w._sync_file_actions()
        self.w.statusBar().showMessage(status, 2000)

    # ── Ground slide segments ──

    def _append_ground_slide(
        self, start_tick: int, start_cell: int, width: int,
        start_measure: int, start_offset: int, duration: int, end_cell: int,
    ) -> Slide | None:
        if self._chart is None:
            return None
        tail = self._find_ground_slide_tail(start_tick, start_cell, width)
        if tail is None:
            return self._insert_ground_slide(
                start_tick, start_cell, width,
                start_measure, start_offset, duration, end_cell,
            )
        segment = make_note(
            self.w._editor_note_type,
            measure=start_measure, offset=start_offset,
            cell=start_cell, width=width,
            duration=duration, end_cell=end_cell, end_width=width,
        )
        if not isinstance(segment, Slide):
            return None
        original, _tail_step = tail
        replacement = replace(original, steps=(*original.steps, segment.steps[0]))
        self._replace_note(original, replacement)
        self._push_history("replace", [original, replacement])
        return replacement

    def _insert_ground_slide(
        self, start_tick: int, start_cell: int, width: int,
        start_measure: int, start_offset: int, duration: int, end_cell: int,
    ) -> Slide | None:
        if self._chart is None:
            return None
        containing = self._find_ground_slide_segment(start_tick, start_cell, width)
        if containing is None:
            return None
        original, split_step, split_index = containing
        timeline = self._chart.timeline
        seg_start = timeline.note_tick(split_step)
        seg_end = timeline.note_end_tick(split_step)
        inserted_end = start_tick + duration
        if inserted_end > seg_end:
            return None
        segment = make_note(
            self.w._editor_note_type,
            measure=start_measure, offset=start_offset,
            cell=start_cell, width=width,
            duration=duration, end_cell=end_cell, end_width=width,
        )
        if not isinstance(segment, Slide):
            return None
        inserted_step = segment.steps[0]
        steps: list[SlideTo] = list(original.steps[:split_index])
        steps.append(replace(split_step, duration=start_tick - seg_start, end_cell=start_cell, end_width=width))
        steps.append(inserted_step)
        if inserted_end < seg_end:
            rem_meas, rem_off = divmod(inserted_end, self._chart.metadata.resolution)
            steps.append(replace(split_step, measure=rem_meas, offset=rem_off, cell=end_cell, width=width, duration=seg_end - inserted_end))
        steps.extend(original.steps[split_index + 1:])
        replacement = replace(original, steps=tuple(steps))
        self._replace_note(original, replacement)
        self._push_history("replace", [original, replacement])
        return replacement

    def _find_ground_slide_tail(self, tick: int, cell: int, width: int) -> tuple[Slide, Note] | None:
        if self._chart is None:
            return None
        tl = self._chart.timeline
        for note in reversed(self._chart.notes):
            if not isinstance(note, Slide) or not note.steps:
                continue
            tail = note.steps[-1]
            if tl.note_end_tick(tail) == tick and tail.end_cell == cell and tail.end_width == width:
                return note, tail
        return None

    def _find_ground_slide_segment(self, tick: int, cell: int, width: int) -> tuple[Slide, SlideTo, int] | None:
        if self._chart is None:
            return None
        tl = self._chart.timeline
        candidates: list[tuple[int, Slide, SlideTo, int]] = []
        for note in reversed(self._chart.notes):
            if not isinstance(note, Slide):
                continue
            for idx, step in enumerate(note.steps):
                if not tl.note_tick(step) < tick < tl.note_end_tick(step):
                    continue
                span = tl.span_at(step, tick)
                if span is None:
                    continue
                if span == (cell, width):
                    return note, step, idx
                candidates.append((abs(span[0] - cell) + abs(span[1] - width), note, step, idx))
        if candidates:
            _, note, step, idx = min(candidates, key=lambda x: x[0])
            return note, step, idx
        return None

    # ── Air slide segments ──

    def _append_air_slide(
        self, start_tick: int, start_cell: int, width: int,
        start_measure: int, start_offset: int, duration: int, end_cell: int,
    ) -> AirSlideStart | None:
        if self._chart is None:
            return None
        tail = self._find_air_slide_tail(start_tick, start_cell, width)
        if tail is None:
            return self._insert_air_slide(
                start_tick, start_cell, width,
                start_measure, start_offset, duration, end_cell,
            )
        original, tail_step = tail
        segment = make_note(
            self.w._editor_note_type,
            measure=start_measure, offset=start_offset,
            cell=start_cell, width=width,
            duration=duration, end_cell=end_cell, end_width=width,
            target_note=tail_step.note_type.value, parent=tail_step,
        )
        if not isinstance(segment, AirSlideStart):
            return None
        replacement = replace(original, steps=(*original.steps, segment.steps[0]))
        self._replace_note(original, replacement)
        self._push_history("replace", [original, replacement])
        return replacement

    def _insert_air_slide(
        self, start_tick: int, start_cell: int, width: int,
        start_measure: int, start_offset: int, duration: int, end_cell: int,
    ) -> AirSlideStart | None:
        if self._chart is None:
            return None
        containing = self._find_air_slide_segment(start_tick, start_cell, width)
        if containing is None:
            return None
        original, split_step, split_index = containing
        timeline = self._chart.timeline
        seg_start = timeline.note_tick(split_step)
        seg_end = timeline.note_end_tick(split_step)
        inserted_end = start_tick + duration
        if inserted_end > seg_end:
            return None
        segment = make_note(
            self.w._editor_note_type,
            measure=start_measure, offset=start_offset,
            cell=start_cell, width=width,
            duration=duration, end_cell=end_cell, end_width=width,
            target_note=split_step.note_type.value, parent=split_step,
        )
        if not isinstance(segment, AirSlideStart):
            return None
        inserted_step = segment.steps[0]
        steps: list[AirSlide] = list(original.steps[:split_index])
        steps.append(replace(split_step, duration=start_tick - seg_start, end_cell=start_cell, end_width=width))
        steps.append(inserted_step)
        if inserted_end < seg_end:
            rem_meas, rem_off = divmod(inserted_end, self._chart.metadata.resolution)
            steps.append(replace(split_step, measure=rem_meas, offset=rem_off, cell=end_cell, width=width, duration=seg_end - inserted_end, target_note=inserted_step.note_type.value, parent=inserted_step))
        steps.extend(original.steps[split_index + 1:])
        replacement = replace(original, steps=tuple(steps))
        self._replace_note(original, replacement)
        self._push_history("replace", [original, replacement])
        return replacement

    def _find_air_slide_tail(self, tick: int, cell: int, width: int) -> tuple[AirSlideStart, Note] | None:
        if self._chart is None:
            return None
        tl = self._chart.timeline
        for note in reversed(self._chart.notes):
            if not isinstance(note, AirSlideStart) or not note.steps:
                continue
            tail = note.steps[-1]
            if tl.note_end_tick(tail) == tick and tail.end_cell == cell and tail.end_width == width:
                return note, tail
        return None

    def _find_air_slide_segment(self, tick: int, cell: int, width: int) -> tuple[AirSlideStart, AirSlide, int] | None:
        if self._chart is None:
            return None
        tl = self._chart.timeline
        candidates: list[tuple[int, AirSlideStart, AirSlide, int]] = []
        for note in reversed(self._chart.notes):
            if not isinstance(note, AirSlideStart):
                continue
            for idx, step in enumerate(note.steps):
                if not tl.note_tick(step) < tick < tl.note_end_tick(step):
                    continue
                span = tl.span_at(step, tick)
                if span is None:
                    continue
                if span == (cell, width):
                    return note, step, idx
                candidates.append((abs(span[0] - cell) + abs(span[1] - width), note, step, idx))
        if candidates:
            _, note, step, idx = min(candidates, key=lambda x: x[0])
            return note, step, idx
        return None

    # ── Note replacement ──

    def _replace_note(self, original: Note, replacement: Note) -> None:
        if self._chart is None:
            return
        for i, n in enumerate(self._chart.notes):
            if n is original:
                self._chart.notes[i] = replacement
                self._chart.invalidate_timeline()
                return

    def delete_selected(self) -> None:
        if not self._chart or self._read_only:
            return
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
        if self._chart is None or self._read_only or not self.w._undo_stack:
            return
        operation, notes = self.w._undo_stack.pop()
        if operation == "add":
            changed = remove_notes(self._chart, notes)
            if not changed:
                self._sync_history_actions()
                return
            self.w._redo_stack.append((operation, notes))
            self._finish_history("Undid note placement.")
        elif operation == "replace" and len(notes) == 2:
            original, replacement = notes
            self._replace_note(replacement, original)
            self.w._redo_stack.append((operation, notes))
            self._finish_history("Undid note edit.", selected_note=original)

    def redo(self) -> None:
        if self._chart is None or self._read_only or not self.w._redo_stack:
            return
        operation, notes = self.w._redo_stack.pop()
        if operation == "add":
            for n in notes:
                add_note(self._chart, n)
            self.w._undo_stack.append((operation, notes))
            self._finish_history("Redid note placement.", selected_note=notes[-1])
        elif operation == "replace" and len(notes) == 2:
            original, replacement = notes
            self._replace_note(original, replacement)
            self.w._undo_stack.append((operation, notes))
            self._finish_history("Redid note edit.", selected_note=replacement)

    def _push_history(self, operation: str, notes: list[Note]) -> None:
        self.w._undo_stack.append((operation, list(notes)))
        self.w._redo_stack.clear()
        self._sync_history_actions()

    def clear_history(self) -> None:
        self.w._undo_stack.clear()
        self.w._redo_stack.clear()
        self._sync_history_actions()

    def _sync_history_actions(self) -> None:
        can_edit = self._chart is not None and not self._read_only
        if hasattr(self.w, "undo_action"):
            self.w.undo_action.setEnabled(can_edit and bool(self.w._undo_stack))
        if hasattr(self.w, "redo_action"):
            self.w.redo_action.setEnabled(can_edit and bool(self.w._redo_stack))

    def _finish_history(
        self, message: str, *, selected_note: Note | None = None,
    ) -> None:
        if self._chart is None:
            return
        current_pos = self.w.visualizer.current_pos
        self.w.playback_service.refresh_chart_after_edit()
        self._dirty = True
        self.w._display_chart(self._chart)
        self.w.visualizer.set_current_pos(current_pos)
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

    # ── Context menus ──

    def show_note_context_menu(self, note: Note, global_pos) -> None:
        menu = QMenu(self.w)
        open_action = menu.addAction("Open in Chart File")
        open_action.triggered.connect(
            lambda checked=False: self.open_note_in_chart_file(note)
        )
        if note.note_type == NoteType.ALD:
            menu.addSeparator()
            self._add_air_trace_color_actions(menu, note)
        menu.exec(global_pos)

    def _show_air_trace_color_menu(self, note: Note, global_pos) -> None:
        menu = QMenu(self.w)
        menu.setTitle("Air Trace Color")
        self._add_air_trace_color_actions(menu, note)
        menu.exec(global_pos)

    def _add_air_trace_color_actions(self, menu: QMenu, note: Note) -> None:
        current = getattr(note, "color", "DEF")
        for c in AirTraceColor:
            code = c.value
            action = menu.addAction(self._air_trace_color_icon(code), code)
            action.setCheckable(True)
            action.setChecked(code == current)
            action.triggered.connect(
                lambda checked=False, sel=code: self._change_air_trace_color(note, sel)
            )

    def open_note_in_chart_file(self, note: Note) -> None:
        location = self._note_source_location(note)
        if location is None:
            self.w.statusBar().showMessage("No chart file is loaded for this note.", 3000)
            return

        path, line_number = location
        if line_number is None:
            self.w.statusBar().showMessage(
                "Could not find that note in the chart file. Save the chart and try again.",
                4000,
            )
            return

        if self._launch_source_location(path, line_number):
            self.w.statusBar().showMessage(
                f"Opened {path.name}:{line_number}.", 3000,
            )
        else:
            self.w.statusBar().showMessage(
                f"Could not open {path.name}:{line_number}.", 4000,
            )

    def _note_source_location(self, note: Note) -> tuple[Path, int | None] | None:
        file_path = getattr(self.w, "current_file_path", None)
        if not file_path:
            return None

        path = Path(file_path)
        source_note = self._source_note_for_lookup(note)
        target_line = self._source_line_for_note(source_note)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return path, None

        for line_number, raw_line in enumerate(lines, start=1):
            if raw_line.strip() == target_line:
                return path, line_number
        return path, None

    def _source_note_for_lookup(self, note: Note) -> Note:
        if isinstance(note, (Slide, AirSlideStart)) and note.steps:
            return note.steps[0]
        return note

    def _source_line_for_note(self, note: Note) -> str:
        if self._chart is not None:
            return self._chart.find_note_line(note)
        parts = [
            note.note_type.value,
            str(note.measure),
            str(note.offset),
            str(note.cell),
            str(note.width),
        ]
        if hasattr(note, "get_extra_parts"):
            parts.extend(str(part) for part in note.get_extra_parts())
        return "\t".join(parts)

    def _launch_source_location(self, path: Path, line_number: int) -> bool:
        configured_editor = os.environ.get(EDITOR_ENV_VAR)
        if configured_editor and self._launch_editor_command(
            configured_editor, path, line_number
        ):
            return True

        for command in (
            "code",
            "code-insiders",
            "codium",
            "cursor",
            "windsurf",
            "subl",
            "sublime_text",
            "kate",
            "kwrite",
            "gedit",
        ):
            if shutil.which(command) and self._launch_editor_command(
                command, path, line_number
            ):
                return True

        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _launch_editor_command(self, command: str, path: Path, line_number: int) -> bool:
        try:
            base_args = shlex.split(command)
        except ValueError:
            LOGGER.warning("Invalid %s command: %s", EDITOR_ENV_VAR, command)
            return False
        if not base_args:
            return False

        executable = Path(base_args[0]).name
        if executable in {"code", "code-insiders", "codium", "cursor", "windsurf"}:
            args = [*base_args, "-g", f"{path}:{line_number}"]
        elif executable in {"subl", "sublime_text"}:
            args = [*base_args, f"{path}:{line_number}"]
        elif executable in {"kate", "kwrite"}:
            args = [*base_args, "--line", str(line_number), str(path)]
        elif executable == "gedit":
            args = [*base_args, f"+{line_number}", str(path)]
        else:
            args = [*base_args, str(path)]

        try:
            subprocess.Popen(args)
        except OSError as exc:
            LOGGER.warning("Failed to launch editor command %s: %s", args, exc)
            return False
        return True

    def _air_trace_color_icon(self, color_code: str) -> QIcon:
        pix = QPixmap(18, 18)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(theme.qt(theme.BORDER_CONTROL_SOFT))
        p.setBrush(get_note_color(NoteType.ALD, color_code))
        p.drawRoundedRect(2, 2, 14, 14, 3, 3)
        p.end()
        return QIcon(pix)

    def _change_air_trace_color(self, note: Note, color_code: str) -> None:
        if self._chart is None or self._read_only:
            return
        if note.note_type != NoteType.ALD or color_code not in TRACE_COLORS:
            return
        if getattr(note, "color", None) == color_code:
            return
        replacement = replace(note, color=color_code)
        self._replace_note(note, replacement)
        self._push_history("replace", [note, replacement])
        self._finish_history(
            f"Changed ALD color to {color_code}.", selected_note=replacement,
        )

    # ── Anchor helpers ──

    def _placement_anchor_context(
        self, note_type: NoteType, tick: int, cell: int, width: int,
    ) -> tuple[str, Note | None, int, int]:
        if self._chart is None or note_type not in AIR_ANCHORED_EDITOR_TYPES:
            return "DEF", None, cell, width
        anchor = self._find_editor_air_anchor(tick, cell, width)
        if anchor is None:
            return "DEF", None, cell, width
        return anchor

    def _find_editor_air_anchor(
        self, tick: int, cell: int, width: int,
    ) -> tuple[str, Note, int, int] | None:
        if self._chart is None:
            return None
        tl = self._chart.timeline
        for cand in reversed(self._chart.notes):
            if cand.note_type == NoteType.ALD:
                continue
            points: list[tuple[str, Note, int, int, int]] = [
                (cand.note_type.value, cand, tl.note_tick(cand), int(cand.cell), int(cand.width)),
            ]
            if isinstance(cand, (Slide, AirSlideStart)):
                for step in cand.steps:
                    points.append((step.note_type.value, step, tl.note_end_tick(step), int(step.end_cell), int(step.end_width)))
            elif hasattr(cand, "duration"):
                points.append((cand.note_type.value, cand, tl.note_end_tick(cand), int(getattr(cand, "end_cell", cand.cell)), int(getattr(cand, "end_width", cand.width))))
            for tn, an, at, ac, aw in points:
                if at == tick and ac == cell and aw == width:
                    return tn, an, ac, aw
        return None

    def sync_place_mode(self) -> None:
        if self.w.current_chart is None:
            self.w.visualizer.set_editor_place_mode(False)
            return
        self.w.visualizer.set_editor_place_mode(True)
