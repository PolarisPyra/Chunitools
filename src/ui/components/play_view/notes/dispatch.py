from __future__ import annotations

# ruff: noqa: PLR0912, PLR0913, PLR0915
from typing import TYPE_CHECKING

from PySide6.QtGui import QColor, QPainter

from src.core.const import NoteType
from src.ui.components.play_view.geometry import (
    ACTIVE_DEPTH_MAX,
    ACTIVE_DEPTH_MIN,
    DRAW_DEPTH_MAX,
    DRAW_DEPTH_MIN,
    _air_path_screen_span,
    _air_path_world_y,
    _has_sustain,
    _note_screen_span,
    _sustain_draw_depths,
)
from src.ui.theme.notes import TRACE_COLORS, get_note_color

if TYPE_CHECKING:
    from src.notes import Note

AIR_WRAPPED_GROUND_TYPES = {
    NoteType.TAP,
    NoteType.CHR,
    NoteType.FLK,
    NoteType.MNE,
    NoteType.HLD,
    NoteType.HXD,
    NoteType.SLD,
    NoteType.SLC,
    NoteType.SXD,
    NoteType.SXC,
}
AIR_WRAPPED_EX_HEAD_TYPES = {NoteType.CHR, NoteType.HXD, NoteType.SXD, NoteType.SXC}


class PlayViewNoteDispatchMixin:
    def _get_note_color(self, note: Note) -> QColor:
        if note.note_type == NoteType.ALD:
            color_code = getattr(note, "color", "DEF")
            return QColor(TRACE_COLORS.get(color_code, "#b4b4c8"))

        return get_note_color(note.note_type)

    def _draw_notes(self, painter: QPainter, judge_time: float) -> None:  # noqa: PLR0912
        w, h = self.width(), self.height()
        vanish_x = w / 2.0
        vanish_y = h * 0.10
        judge_y = h * 0.90

        if not self.chart:
            return
        visible_notes = []
        tl = self.chart.timeline
        for note in self._notes:
            if not self.visible_note_types.get(note.note_type.value, True):
                continue
            note_time = self._note_times.get(id(note), 0.0)
            end_time = self._note_end_times.get(id(note), note_time)
            depth = self._compute_note_depth(note, tl.note_tick(note), note_time, judge_time)
            end_depth = self._compute_note_depth(note, tl.note_end_tick(note), end_time, judge_time)

            if _has_sustain(note):
                if _sustain_draw_depths(depth, end_depth) is None:
                    continue
            else:
                if depth > ACTIVE_DEPTH_MAX:
                    continue
                if depth < ACTIVE_DEPTH_MIN:
                    continue

            visible_notes.append((note, depth, end_depth))

        visible_notes.sort(key=lambda x: x[1], reverse=True)

        self._deferred_air_arrows.clear()
        self._defer_air_arrows = True
        try:
            for note, depth, end_depth in visible_notes:
                if _has_sustain(note):
                    if _sustain_draw_depths(depth, end_depth) is None:
                        continue
                else:
                    if depth >= DRAW_DEPTH_MAX:
                        continue
                    if depth <= DRAW_DEPTH_MIN:
                        continue

                scale, screen_y, t = self._world_z_to_screen(depth, vanish_y, judge_y)
                lane_x, note_w = _note_screen_span(note.cell, note.width, vanish_x, scale)
                if note_w < 2:
                    continue

                alpha = max(30, int(255 * (1.0 - abs(t) * 0.5)))

                self._draw_note(
                    painter,
                    note,
                    lane_x,
                    screen_y,
                    note_w,
                    scale,
                    alpha,
                    judge_time,
                    depth,
                    end_depth,
                    vanish_x,
                    vanish_y,
                    judge_y,
                )
        finally:
            self._defer_air_arrows = False

        for payload in self._deferred_air_arrows:
            self._draw_air_arrow_for_note(painter, *payload)
        self._deferred_air_arrows.clear()

    def _draw_note(  # noqa: PLR0912
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        judge_time: float,
        depth: float,
        end_depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        nt = note.note_type
        color = self._get_note_color(note)
        color.setAlpha(alpha)

        has_duration = hasattr(note, "duration") and getattr(note, "duration", 0) > 0
        is_air_arrow = nt in {
            NoteType.AIR,
            NoteType.AUR,
            NoteType.AUL,
            NoteType.ADW,
            NoteType.ADR,
            NoteType.ADL,
        }

        air_y = self._air_path_screen_y(note, depth)
        if air_y is not None:
            y = air_y

        if is_air_arrow:
            x, w = self._air_arrow_screen_span_at_anchor(note, vanish_x, scale)
        elif nt in {
            NoteType.AHD,
            NoteType.AHX,
            NoteType.ALD,
            NoteType.ASD,
            NoteType.ASC,
        }:
            x, w = _air_path_screen_span(note.cell, note.width, vanish_x, scale)

        if nt == NoteType.TAP:
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, depth)
        elif nt == NoteType.CHR:
            self._draw_extap_quad(painter, x, y, w, scale, color, alpha, note, depth)
        elif nt == NoteType.FLK:
            self._draw_flick(painter, x, y, w, scale, color, alpha, note, depth)
        elif nt == NoteType.MNE:
            self._draw_mine(painter, x, y, w, scale, color, alpha)
        elif nt == NoteType.AHD:
            self._draw_air_hold_segment(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
                is_start=True,
            )
        elif nt == NoteType.AHX:
            sustain_color = get_note_color(NoteType.AHD)
            sustain_color.setAlpha(alpha)
            self._draw_air_hold_segment(
                painter,
                note,
                x,
                y,
                w,
                scale,
                sustain_color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
                is_start=True,
            )
        elif nt in {NoteType.HLD, NoteType.HXD}:
            if has_duration:
                self._draw_hold(
                    painter,
                    note,
                    x,
                    y,
                    w,
                    scale,
                    color,
                    alpha,
                    judge_time,
                    depth,
                    end_depth,
                    vanish_x,
                    vanish_y,
                    judge_y,
                )
            else:
                self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, depth)
        elif nt in {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}:
            self._draw_slide(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        elif is_air_arrow:
            self._draw_or_defer_air_arrow(
                painter,
                note,
                x,
                y,
                w,
                scale,
                alpha,
                nt,
                depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        elif nt in {NoteType.ASD, NoteType.ASC}:
            self._draw_air_slide(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        elif nt == NoteType.ALD:
            self._draw_air_trace(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        else:
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, depth)
    def _get_world_y(self, note: Note) -> float:
        wy = _air_path_world_y(note)
        return wy if wy is not None else 0.0
