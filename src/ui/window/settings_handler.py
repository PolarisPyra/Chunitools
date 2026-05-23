from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from src.core.config import DEFAULT_SCROLL_SPEED, settings
from src.ui.components.viewport import DEFAULT_VIEW_LANE_WIDTH

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow


class SettingsHandler:
    """Manages settings sync, panel toggles, volume/grid/speed controls."""

    def __init__(self, window: MainWindow) -> None:
        self.w = window

    # ── Apply all settings ──

    def apply(self) -> None:
        self.w._show_warning_panel = settings.show_warnings
        self.w._show_note_inspector = settings.show_inspector and not self.w._show_editor_panel

        is_timeline = hasattr(self.w, "_view_stack") and self.w._view_stack.currentIndex() == 0
        if hasattr(self.w, "radar"):
            self.w.radar.setVisible(is_timeline and settings.show_radar)
        if hasattr(self.w, "fps_overlay"):
            self.w.fps_overlay.setVisible(settings.show_fps)
            self.w.fps_overlay.set_active(settings.show_fps)
        self.w.visualizer.set_note_debug_overlay_active(settings.show_note_debug_overlay)
        if hasattr(self.w, "open_folder_btn"):
            self.w.open_folder_btn.setVisible(settings.show_export_button)

        self.w.visualizer.set_visible_note_types(settings.visible_note_types)
        if hasattr(self.w, "play_view"):
            self.w.play_view.set_visible_note_types(settings.visible_note_types)
        self.w.visualizer.set_subdivisions(settings.subdivisions)
        self.w.timeline_widget.set_subdivisions(settings.subdivisions)
        self.w.visualizer.set_scroll_speed(settings.scroll_speed)
        self.w.play_view.set_scroll_speed(settings.scroll_speed)
        self.w.playback_service.set_hitsound_volume(settings.hitsound_volume)
        self.w.playback_service.set_music_volume(settings.music_volume)

        self.sync_inspector_visibility()
        self.sync_menu_states()
        self.w._sync_file_actions()

    # ── Menu state sync ──

    def sync_menu_states(self) -> None:
        if hasattr(self.w, "toggle_inspector_action"):
            self.w.toggle_inspector_action.setChecked(self.w._show_note_inspector)
        if hasattr(self.w, "toggle_editor_action"):
            self.w.toggle_editor_action.setChecked(self.w._show_editor_panel)
        if hasattr(self.w, "toggle_note_debug_action"):
            self.w.toggle_note_debug_action.setChecked(settings.show_note_debug_overlay)

    # ── Panel visibility ──

    def sync_inspector_visibility(self) -> None:
        self.w.warning_section.setVisible(self.w._show_warning_panel)
        self.w.note_section.setVisible(self.w._show_note_inspector)
        if self.w.metadata_editor:
            self.w.metadata_editor.setVisible(self.w._show_editor_panel)
        should_show = self.w._show_warning_panel or self.w._show_note_inspector or self.w._show_editor_panel
        self.w.inspector_panel.setVisible(should_show)
        QTimer.singleShot(0, self.w.overlay_manager.reposition)

    # ── Panel toggles ──

    def toggle_warnings(self, checked: bool) -> None:
        self.w._show_warning_panel = checked
        settings.show_warnings = checked
        settings.save()
        self.sync_inspector_visibility()

    def toggle_inspector(self, checked: bool) -> None:
        self.w._show_note_inspector = checked
        settings.show_inspector = checked
        settings.save()
        self.w.note_section.setVisible(checked)
        if hasattr(self.w, "toggle_inspector_action"):
            self.w.toggle_inspector_action.setChecked(checked)
        self.sync_inspector_visibility()

    def toggle_editor_panel(self, checked: bool) -> None:
        self.w._show_editor_panel = checked
        if checked and self.w._show_note_inspector:
            self.w._show_note_inspector = False
            if hasattr(self.w, "toggle_inspector_action"):
                self.w.toggle_inspector_action.setChecked(False)
            self.w.note_section.hide()
        if hasattr(self.w, "toggle_editor_action"):
            self.w.toggle_editor_action.setChecked(checked)
        self.sync_inspector_visibility()

    def reset_zoom(self) -> None:
        self.w.visualizer.set_scroll_speed(DEFAULT_SCROLL_SPEED)
        self.w.play_view.set_scroll_speed(DEFAULT_SCROLL_SPEED)
        settings.scroll_speed = DEFAULT_SCROLL_SPEED
        settings.save()
        self.w.visualizer.projection.lane_width = DEFAULT_VIEW_LANE_WIDTH
        self.w.visualizer.zoom_changed.emit()
        self.sync_menu_states()
        self.w.visualizer.update()

    def toggle_radar(self, checked: bool) -> None:
        self.w.radar.setVisible(checked)
        settings.show_radar = checked
        settings.save()

    def toggle_fps(self, checked: bool) -> None:
        self.w.fps_overlay.setVisible(checked)
        self.w.fps_overlay.set_active(checked)
        settings.show_fps = checked
        settings.save()

    def toggle_note_debug_overlay(self, checked: bool) -> None:
        self.w.visualizer.set_note_debug_overlay_active(checked)
        if hasattr(self.w, "play_view_3d") and self.w.play_view_3d:
            self.w.play_view_3d.set_note_debug_overlay_active(checked)
        settings.show_note_debug_overlay = checked
        settings.save()
        if hasattr(self.w, "toggle_note_debug_action"):
            self.w.toggle_note_debug_action.setChecked(checked)

    def toggle_export_button(self, checked: bool) -> None:
        if hasattr(self.w, "open_folder_btn"):
            self.w.open_folder_btn.setVisible(checked)
        if hasattr(self.w, "open_logs_btn"):
            self.w.open_logs_btn.setVisible(checked)
        settings.show_export_button = checked
        settings.save()

    # ── Volume ──

    def on_hitsound_volume(self, value: int) -> None:
        volume = max(0.0, min(1.0, value / 100.0))
        settings.hitsound_volume = volume
        settings.save()
        self.w.playback_service.set_hitsound_volume(volume)

    def on_music_volume(self, value: int) -> None:
        volume = max(0.0, min(1.0, value / 100.0))
        settings.music_volume = volume
        settings.save()
        self.w.playback_service.set_music_volume(volume)

    # ── Note visibility ──

    def toggle_note_visibility(self, note_type_value: str, checked: bool) -> None:
        settings.visible_note_types[note_type_value] = checked
        settings.save()
        self.w.visualizer.set_visible_note_types(settings.visible_note_types)
        if hasattr(self.w, "play_view"):
            self.w.play_view.set_visible_note_types(settings.visible_note_types)

    # ── Grid ──

    def on_grid_subdivision(self, val: int) -> None:
        if not val:
            return
        settings.subdivisions = val
        settings.save()
        self.w.visualizer.set_subdivisions(val)
        self.w.timeline_widget.set_subdivisions(val)
        self.sync_menu_states()
        self.w.statusBar().showMessage(f"Grid: 1/{val}", 2000)

    # ── Scroll speed ──

    def on_scroll_speed(self, val: float) -> None:
        if not val:
            return
        settings.scroll_speed = float(val)
        settings.save()
        self.w.visualizer.set_scroll_speed(float(val))
        self.w.play_view.set_scroll_speed(float(val))
        self.sync_menu_states()
        self.w.statusBar().showMessage(f"Scroll Speed: {float(val):.2f}", 2000)
