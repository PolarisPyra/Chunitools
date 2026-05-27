from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeySequence, QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton

from src.core import config
from src.core.config import settings
from src.core.const import NoteType
from src.core.write import serialize_c2s
from src.notes import Air, AirHold, AirHoldStart, AirSlideStart, CrashSlide, Hold, Slide
from src.ui.components.viewport import DEFAULT_VIEW_LANE_WIDTH, ChartViewport
from src.ui.view.projection import ViewProjection
from src.ui.view.renderer.base import CHED_BAR_LINE, CHED_BEAT_LINE, BaseRenderer
from src.ui.view.timeline_widget import TimelineWidget
from src.workspace.layout import MainWindow


@pytest.fixture(autouse=True)
def isolate_user_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", tmp_path / "config.yaml")
    monkeypatch.setattr(config, "LEGACY_USER_CONFIG_PATH", tmp_path / "config.json")


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _left_click(viewport, point: QPointF) -> None:
    viewport.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    viewport.mouseReleaseEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


def test_editor_starts_with_wider_timeline_view(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")

    window = MainWindow()
    try:
        assert window.visualizer.lane_width == DEFAULT_VIEW_LANE_WIDTH
        assert window.visualizer.lane_width > 16.0
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_editor_defaults_to_place_mode_and_uses_top_note_picker(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)

    def fail_if_prompted(*args, **kwargs):
        raise AssertionError("startup should not prompt for data root in this test")

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", fail_if_prompted)
    window = MainWindow()
    try:
        assert window.visualizer.editor_place_mode
        assert hasattr(window, "editor_toolbar")
        assert hasattr(window, "editor_controls_toolbar")
        assert window.editor_toolbar.isHidden()
        assert not hasattr(window, "note_type_combo")
        assert not hasattr(window, "note_btn")
        assert hasattr(window, "width_btn")
        assert not hasattr(window, "note_width_spin")
        assert not hasattr(window, "note_duration_spin")
        assert not hasattr(window, "met_num_spin")
        assert not hasattr(window, "delete_notes_button")
        assert not hasattr(window, "import_audio_button")
        window.set_editor_note_type(NoteType.FLK)
        assert window._editor_note_type == NoteType.FLK
        assert window._note_tool_buttons[NoteType.FLK.value].isChecked()
        assert {note_type.value for note_type in NoteType} <= set(window._note_tool_buttons)
        for note_type in {
            NoteType.AIR,
            NoteType.AUL,
            NoteType.AUR,
            NoteType.ADW,
            NoteType.ADL,
            NoteType.ADR,
        }:
            assert note_type.value in window._note_tool_buttons
            assert not window._note_tool_buttons[note_type.value].icon().isNull()
        window._note_tool_buttons[NoteType.SXC.value].trigger()
        assert window._editor_note_type == NoteType.SXC
        assert window.visualizer.editor_place_note_type == NoteType.SXC
        window._on_note_width_changed(6)
        assert window._editor_note_width == 6
        assert window.width_btn.text() == "6"
        window.new_chart()
        assert not window.editor_toolbar.isHidden()
        assert not window.editor_controls_toolbar.isHidden()
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_viewport_visibility_updates_existing_renderer_delegate() -> None:
    _app()
    viewport = ChartViewport()

    class CacheProbe:
        def __init__(self) -> None:
            self.cleared = False

        def clear(self) -> None:
            self.cleared = True

    class DelegateProbe:
        def __init__(self) -> None:
            self.visible_note_types = {}
            self.cache = CacheProbe()

    delegate = DelegateProbe()
    viewport.painter_engine._delegate = delegate
    visible = {NoteType.AIR.value: False}

    viewport.set_visible_note_types(visible)

    assert viewport.painter_engine.visible_note_types is visible
    assert delegate.visible_note_types is visible
    assert delegate.cache.cleared


def test_data_folder_chart_loads_read_only(monkeypatch, tmp_path) -> None:
    _app()
    data_root = tmp_path / "data"
    chart_path = data_root / "A000" / "music" / "music000001" / "0001_03.c2s"
    chart_path.parent.mkdir(parents=True)
    chart_path.write_text(
        "\n".join(
            [
                "MUSIC\t1",
                "BPM_DEF\t120.000\t120.000\t120.000\t120.000",
                "RESOLUTION\t384",
            ]
        ),
        encoding="utf-8",
    )
    old_data_root = settings.data_root
    settings.data_root = str(data_root)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.load_chart_file(str(chart_path))

        assert window._chart_read_only
        assert not window.visualizer.editor_place_mode
        assert not window.editor_toolbar.isHidden()
        assert not window.editor_controls_toolbar.isHidden()
        assert not window.speed_btn.isHidden()
        assert not window.grid_btn.isHidden()
        assert window.editor_toolbar.maximumWidth() == window._editor_toolbar_width
        assert not window.width_btn.isHidden()
        width_label = window.editor_toolbar.findChild(QLabel, "WidthDropdownLabel")
        assert width_label is not None
        assert width_label.width() >= width_label.sizeHint().width()
        width_x = window.width_btn.mapTo(window.editor_toolbar, QPoint(0, 0)).x()
        assert width_x < window.speed_btn.x() < window.grid_btn.x()
        assert window.grid_btn.geometry().right() <= window.editor_toolbar.width()
        assert window.editor_toolbar.width() - window.grid_btn.geometry().right() <= 24
        top_padding = window.editor_controls_toolbar.y()
        bottom_padding = (
            window.editor_toolbar.height()
            - window.editor_controls_toolbar.y()
            - window.editor_controls_toolbar.height()
        )
        assert top_padding == bottom_padding
        menu_action_center = window.menuBar().actionGeometry(window.menuBar().actions()[0]).center().y()
        toolbar_center = window.editor_controls_toolbar.mapTo(
            window.menuBar(),
            window.editor_controls_toolbar.rect().center(),
        ).y()
        assert toolbar_center == menu_action_center
        assert not window.save_chart_action.isEnabled()
        assert all(not field.isEnabled() for field in window.metadata_fields.values())
        before_count = len(window.current_chart.notes)
        window._place_note_at(1.0, 0)
        assert len(window.current_chart.notes) == before_count
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_custom_chart_loads_editable(monkeypatch, tmp_path) -> None:
    _app()
    data_root = tmp_path / "data"
    data_root.mkdir()
    chart_path = tmp_path / "custom.c2s"
    chart_path.write_text(
        "\n".join(
            [
                "MUSIC\t1",
                "BPM_DEF\t120.000\t120.000\t120.000\t120.000",
                "RESOLUTION\t384",
            ]
        ),
        encoding="utf-8",
    )
    old_data_root = settings.data_root
    settings.data_root = str(data_root)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.load_chart_file(str(chart_path))

        assert not window._chart_read_only
        assert window.visualizer.editor_place_mode
        assert not window.editor_toolbar.isHidden()
        assert window.save_chart_action.isEnabled()
        assert all(field.isEnabled() for field in window.metadata_fields.values())
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_left_click_places_and_right_click_starts_selection(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_show_inspector = settings.show_inspector
    settings.data_root = str(tmp_path)
    settings.show_inspector = False
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        viewport = window.visualizer
        viewport.resize(800, 600)
        point = QPointF(400, 500)
        left_press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        viewport.mousePressEvent(left_press)
        viewport.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                point,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        assert len(window.current_chart.notes) == 1
        placed_note = window.current_chart.notes[0]
        placed_pos = (
            placed_note.measure
            + placed_note.offset / window.current_chart.metadata.resolution
        )
        assert window.playback.audible_trigger_count_at(placed_pos) == 1
        assert not window.note_section.isVisible()

        right_press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            point,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        viewport.mousePressEvent(right_press)

        assert viewport._selection_drag_origin is not None
        assert len(window.current_chart.notes) == 1
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.show_inspector = old_show_inspector


def test_right_click_note_selects_first_then_requests_context_menu() -> None:
    _app()
    viewport = ChartViewport()
    note = CrashSlide(
        note_type=NoteType.ALD,
        measure=0,
        offset=0,
        cell=4,
        width=2,
        crush_interval=0,
        starting_height=1.0,
        duration=96,
        end_cell=4,
        end_width=2,
        target_height=1.0,
        color="DEF",
    )
    emitted: list[object] = []
    selected: list[object] = []
    viewport._pick_note = lambda _x, _y: note
    viewport.note_selected.connect(selected.append)
    viewport.note_context_requested.connect(lambda selected, _pos: emitted.append(selected))

    right_press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    right_release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(10, 10),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    viewport.mousePressEvent(right_press)
    viewport.mouseReleaseEvent(right_release)
    assert viewport.selected_note is note
    assert selected == [note]
    assert emitted == []

    viewport.mousePressEvent(right_press)
    assert emitted == []
    viewport.mouseReleaseEvent(right_release)
    assert viewport.selected_note is note
    assert emitted == [note]


def test_right_drag_on_selected_note_batch_selects_without_context_menu() -> None:
    _app()
    viewport = ChartViewport()
    note = CrashSlide(
        note_type=NoteType.ALD,
        measure=0,
        offset=0,
        cell=4,
        width=2,
        crush_interval=0,
        starting_height=1.0,
        duration=96,
        end_cell=4,
        end_width=2,
        target_height=1.0,
        color="DEF",
    )
    emitted: list[object] = []
    applied: list[bool] = []
    viewport._pick_note = lambda _x, _y: note
    viewport._apply_selection_rect = lambda: applied.append(True)
    viewport.selected_note = note
    viewport.selected_notes = [note]
    viewport.note_context_requested.connect(lambda selected, _pos: emitted.append(selected))

    viewport.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    viewport.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(24, 24),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    viewport.mouseReleaseEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(24, 24),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )

    assert applied == [True]
    assert emitted == []


def test_open_note_in_chart_file_launches_source_line(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path / "data")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    chart_path = tmp_path / "custom.c2s"
    chart_path.write_text(
        "# comment before the note\n"
        "TAP\t2\t96\t4\t4\n",
        encoding="utf-8",
    )
    window = MainWindow()
    try:
        window.load_chart_file(str(chart_path))
        note = window.current_chart.notes[0]
        launched: list[tuple[object, int]] = []
        monkeypatch.setattr(
            window.note_editor,
            "_launch_source_location",
            lambda path, line_number: launched.append((path, line_number)) or True,
        )

        window.note_editor.open_note_in_chart_file(note)

        assert launched == [(chart_path, 2)]
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_air_slide_context_source_location_uses_first_chart_segment(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path / "data")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    chart_path = tmp_path / "custom.c2s"
    chart_path.write_text(
        "ASD\t0\t0\t4\t2\tTAP\t1.0\t96\t6\t2\t1.0\tDEF\n"
        "ASC\t0\t96\t6\t2\tASD\t1.0\t96\t8\t2\t1.0\tDEF\n",
        encoding="utf-8",
    )
    window = MainWindow()
    try:
        window.load_chart_file(str(chart_path))
        note = next(note for note in window.current_chart.notes if isinstance(note, AirSlideStart))

        assert window.note_editor._note_source_location(note) == (chart_path, 1)
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_dragging_tap_width_sets_note_size(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window.set_editor_note_type(NoteType.TAP)
        viewport = window.visualizer
        viewport.resize(800, 600)

        chart_left = (viewport.width() - viewport.projection.x(viewport.total_lanes)) / 2
        y = 500
        start = QPointF(chart_left + viewport.projection.x(4) + 2, y)
        end = QPointF(chart_left + viewport.projection.x(7) + 2, y)
        expected_target = viewport._placement_target(start)
        assert expected_target == (0.0, 4)

        viewport.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                start,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        note = window.current_chart.notes[-1]
        assert note.note_type == NoteType.TAP
        assert note.cell == 4
        assert note.width == 4

        left_start = QPointF(chart_left + viewport.projection.x(10) + 2, y)
        left_end = QPointF(chart_left + viewport.projection.x(8) + 2, y)
        viewport.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                left_start,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove,
                left_end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                left_end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        note = window.current_chart.notes[-1]
        assert note.cell == 8
        assert note.width == 3
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_undo_redo_note_placement_actions_use_common_shortcuts(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()

        window._place_note_at(1.0, 4)
        placed_note = window.current_chart.notes[0]

        assert window.undo_action.isEnabled()
        assert not window.redo_action.isEnabled()
        assert {
            shortcut.toString(QKeySequence.SequenceFormat.PortableText)
            for shortcut in window.undo_action.shortcuts()
        } == {"Ctrl+Z"}
        assert {
            shortcut.toString(QKeySequence.SequenceFormat.PortableText)
            for shortcut in window.redo_action.shortcuts()
        } == {"Ctrl+Y", "Ctrl+Shift+Z"}

        window.undo_action.trigger()
        assert window.current_chart.notes == []
        assert not window.undo_action.isEnabled()
        assert window.redo_action.isEnabled()

        window.redo_action.trigger()
        assert window.current_chart.notes == [placed_note]
        assert window.undo_action.isEnabled()
        assert not window.redo_action.isEnabled()
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_grid_selection_updates_toolbar_viewport_and_timeline(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window._on_grid_subdivision_changed(32)

        assert settings.subdivisions == 32
        assert window.grid_btn.text() == "1/32"
        assert window.visualizer.subdivisions == 32
        assert window.visualizer.painter_engine.subdivisions == 32
        assert window.timeline_widget._subdivisions == 32
        assert window._grid_actions[32].isChecked()
        labels = {
            label.objectName(): label.text()
            for label in window.menuBar().findChildren(QLabel)
            if label.objectName() in {"SpeedDropdownLabel", "DivisionDropdownLabel"}
        }
        assert labels == {
            "SpeedDropdownLabel": "SPEED",
            "DivisionDropdownLabel": "DIVISION",
        }
    finally:
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_grid_selection_updates_existing_renderer_delegate(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        delegate = BaseRenderer(window.visualizer.projection, subdivisions=4)
        window.visualizer.painter_engine._delegate = delegate

        window._on_grid_subdivision_changed(32)

        assert window.visualizer.painter_engine.subdivisions == 32
        assert delegate.subdivisions == 32
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_timeline_tracks_active_subdivision_span() -> None:
    _app()
    timeline = TimelineWidget()
    timeline.resize(800, 36)
    timeline.set_subdivisions(16)
    timeline.set_playhead_measure(2.125)

    span = timeline._active_subdivision_span(max_measure=8, width=800)

    assert span is not None
    start_x, end_x = span
    assert start_x == 212
    assert end_x == 219


def test_timeline_subdivision_ticks_are_clamped_to_display_extent() -> None:
    _app()
    timeline = TimelineWidget()
    timeline.set_subdivisions(4)

    ticks = timeline._subdivision_tick_positions(max_measure=2.0, width=100)

    assert ticks == [
        (13, 0, 1),
        (25, 0, 2),
        (38, 0, 3),
        (63, 1, 1),
        (75, 1, 2),
        (88, 1, 3),
    ]


def test_editor_grid_uses_ched_line_colors() -> None:
    assert CHED_BAR_LINE.getRgb()[:3] == (160, 160, 160)
    assert CHED_BEAT_LINE.getRgb()[:3] == (80, 80, 80)


def test_editor_grid_labels_measures_like_ched() -> None:
    renderer = BaseRenderer(
        ViewProjection(base_scroll_scale=100.0),
        subdivisions=4,
    )

    class LabelCapturePainter:
        def __init__(self) -> None:
            self.labels: list[str] = []
            self.label_rects = []

        def setPen(self, _pen) -> None:
            pass

        def drawLines(self, _lines: list[QPointF]) -> None:
            pass

        def save(self) -> None:
            pass

        def restore(self) -> None:
            pass

        def drawText(self, rect, _flags, text: str) -> None:
            self.labels.append(text)
            self.label_rects.append(rect)

    painter = LabelCapturePainter()

    renderer.draw_measure_lines(
        painter,
        start_measure=0,
        end_measure=2,
        current_position=0.0,
        viewport_width=100,
    )

    assert painter.labels == ["001", "002", "003"]
    assert painter.label_rects
    assert all(rect.right() <= 0 for rect in painter.label_rects)


def test_measure_grid_subdivisions_stop_at_terminal_measure() -> None:
    renderer = BaseRenderer(
        ViewProjection(base_scroll_scale=100.0),
        subdivisions=4,
    )

    class LineCapturePainter:
        def __init__(self) -> None:
            self.line_batches: list[list[QPointF]] = []

        def setPen(self, _pen) -> None:
            pass

        def drawLines(self, lines: list[QPointF]) -> None:
            self.line_batches.append(list(lines))

    painter = LineCapturePainter()

    renderer.draw_measure_lines(
        painter,
        start_measure=0,
        end_measure=2,
        current_position=0.0,
        viewport_width=100,
        show_labels=False,
    )

    subdivision_lines = painter.line_batches[0]
    subdivision_y_positions = [
        subdivision_lines[index].y()
        for index in range(0, len(subdivision_lines), 2)
    ]
    assert subdivision_y_positions == [-25.0, -50.0, -75.0, -125.0, -150.0, -175.0]


def test_timeline_scrubber_uses_song_total_measure_override() -> None:
    _app()
    timeline = TimelineWidget()
    timeline.resize(800, 36)
    timeline.set_total_measures(128)

    seen: list[float] = []
    timeline.seek_requested.connect(seen.append)
    timeline.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(600, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )

    assert seen == [96.0]
    assert timeline._display_measure_count() == 128


def test_window_timeline_extent_uses_song_duration(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window.playback.set_playback_duration(100.0)
        window._sync_timeline_extent(window.current_chart)

        assert window.timeline_widget._display_measure_count() == 50.0
        assert window.visualizer._max_scroll_measure == 53.0
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_dragging_hold_places_duration_from_drag(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window.set_editor_note_type(NoteType.HLD)
        viewport = window.visualizer
        viewport.resize(800, 600)

        start = QPointF(400, 500)
        end = QPointF(400, 200)
        viewport.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                start,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        assert len(window.current_chart.notes) == 0

        viewport.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        assert len(window.current_chart.notes) == 1
        note = window.current_chart.notes[0]
        assert isinstance(note, Hold)
        assert note.note_type == NoteType.HLD
        assert note.duration == 96
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_slide_places_end_lane_and_duration(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window.set_editor_note_type(NoteType.SLD)
        window._on_note_width_changed(2)
        viewport = window.visualizer
        viewport.resize(800, 600)

        start = QPointF(400, 500)
        end = QPointF(480, 200)
        expected_start = viewport._placement_target(start)
        expected_end = viewport._placement_target(end)
        assert expected_start is not None
        assert expected_end is not None

        viewport.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                start,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        note = window.current_chart.notes[0]
        assert isinstance(note, Slide)
        assert note.note_type == NoteType.SLD
        assert note.duration == 96
        assert note.cell == expected_start[1]
        assert note.end_cell == expected_end[1]
        assert note.end_width == 2
        assert len(note.steps) == 1
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_slide_backwards_normalizes_time_order(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window.set_editor_note_type(NoteType.SLD)
        viewport = window.visualizer
        viewport.resize(800, 600)

        later = QPointF(480, 200)
        earlier = QPointF(400, 500)
        expected_start = viewport._placement_target(earlier)
        expected_end = viewport._placement_target(later)
        assert expected_start is not None
        assert expected_end is not None

        viewport.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                later,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove,
                earlier,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                earlier,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        note = window.current_chart.notes[0]
        assert isinstance(note, Slide)
        assert note.duration == 96
        assert note.cell == expected_start[1]
        assert note.end_cell == expected_end[1]
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_slide_from_exact_tail_extends_existing_chain(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.SLD)
        window._place_note_drag(0.0, 4, 0.25, 6)
        window.set_editor_note_type(NoteType.SLC)
        window._place_note_drag(0.25, 6, 0.5, 8)

        slides = [note for note in window.current_chart.notes if isinstance(note, Slide)]
        assert len(slides) == 1
        assert [step.note_type for step in slides[0].steps] == [NoteType.SLD, NoteType.SLC]
        assert slides[0].steps[1].cell == slides[0].steps[0].end_cell
        assert "SLC\t0\t96\t6\t2\t96\t8\t2" in serialize_c2s(window.current_chart)
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_slide_control_from_mid_segment_splits_existing_chain(
    monkeypatch, tmp_path
) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.SLD)
        window._place_note_drag(0.0, 4, 0.5, 8)
        window.set_editor_note_type(NoteType.SLC)
        window._place_note_drag(0.25, 6, 0.5, 8)

        slides = [note for note in window.current_chart.notes if isinstance(note, Slide)]
        assert len(slides) == 1
        assert [step.note_type for step in slides[0].steps] == [NoteType.SLD, NoteType.SLC]
        assert [(step.duration, step.end_cell) for step in slides[0].steps] == [
            (96, 6),
            (96, 8),
        ]
        c2s = serialize_c2s(window.current_chart)
        assert "SLD\t0\t0\t4\t2\t96\t6\t2" in c2s
        assert "SLC\t0\t96\t6\t2\t96\t8\t2" in c2s
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_slide_control_from_mid_segment_can_reshape_off_current_path(
    monkeypatch, tmp_path
) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.SLD)
        window._place_note_drag(0.0, 4, 0.5, 8)
        window.set_editor_note_type(NoteType.SLC)
        window._place_note_drag(0.25, 10, 0.5, 8)

        slides = [note for note in window.current_chart.notes if isinstance(note, Slide)]
        assert len(slides) == 1
        assert [(step.note_type, step.duration, step.end_cell) for step in slides[0].steps] == [
            (NoteType.SLD, 96, 10),
            (NoteType.SLC, 96, 8),
        ]
        assert "SLC\t0\t96\t10\t2\t96\t8\t2" in serialize_c2s(window.current_chart)
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_air_arrow_click_attaches_to_overlapped_note(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        viewport = window.visualizer
        viewport.resize(800, 600)
        point = QPointF(400, 500)

        _left_click(viewport, point)
        anchor = window.current_chart.notes[0]

        window.set_editor_note_type(NoteType.ADR)
        _left_click(viewport, point)

        air = next(note for note in window.current_chart.notes if isinstance(note, Air))
        assert isinstance(air, Air)
        assert air.note_type == NoteType.ADR
        assert air.target_note == NoteType.TAP.value
        assert air.parent is anchor
        assert window.current_chart.timeline.note_anchor(air) is anchor
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_air_hold_does_not_attach_to_middle_of_long_note(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(4)

        window.set_editor_note_type(NoteType.HLD)
        window._place_note_drag(0.0, 4, 1.0, 4)
        window.set_editor_note_type(NoteType.AHD)
        window._place_note_drag(0.5, 4, 0.75, 4)

        air_hold = next(
            note for note in window.current_chart.notes if isinstance(note, AirHoldStart)
        )
        assert air_hold.parent is None
        assert air_hold.target_note == "DEF"
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_air_hold_attaches_and_sets_duration(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        viewport = window.visualizer
        viewport.resize(800, 600)
        start = QPointF(400, 500)
        end = QPointF(400, 200)

        _left_click(viewport, start)
        anchor = window.current_chart.notes[0]

        window.set_editor_note_type(NoteType.AHD)
        viewport.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                start,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        note = next(note for note in window.current_chart.notes if isinstance(note, AirHoldStart))
        assert isinstance(note, AirHoldStart)
        assert note.target_note == NoteType.TAP.value
        assert note.parent is anchor
        assert note.duration == 96
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_air_action_from_air_hold_tail_targets_air_hold(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.TAP)
        window._place_note_at(0.0, 4)
        window.set_editor_note_type(NoteType.AHD)
        window._place_note_drag(0.0, 4, 0.25, 4)
        window.set_editor_note_type(NoteType.AHX)
        window._place_note_drag(0.25, 4, 0.5, 4)

        air_hold = next(
            note for note in window.current_chart.notes if isinstance(note, AirHoldStart)
        )
        action = next(note for note in window.current_chart.notes if isinstance(note, AirHold))
        assert action.parent is air_hold
        assert action.target_note == NoteType.AHD.value
        assert "AHX\t0\t96\t4\t2\tAHD\t96" in serialize_c2s(window.current_chart)
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_air_slide_creates_joined_air_slide(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        viewport = window.visualizer
        viewport.resize(800, 600)
        start = QPointF(400, 500)
        end = QPointF(480, 200)

        _left_click(viewport, start)
        anchor = window.current_chart.notes[0]

        window.set_editor_note_type(NoteType.ASD)
        viewport.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                start,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseMoveEvent(
            QMouseEvent(
                QEvent.Type.MouseMove,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        viewport.mouseReleaseEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                end,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )

        note = next(note for note in window.current_chart.notes if isinstance(note, AirSlideStart))
        assert isinstance(note, AirSlideStart)
        assert note.target_note == NoteType.TAP.value
        assert note.parent is anchor
        assert note.duration == 96
        assert len(note.steps) == 1
        assert note.end_cell != note.cell
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_air_slide_from_exact_tail_extends_existing_chain(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.TAP)
        window._place_note_at(0.0, 4)
        window.set_editor_note_type(NoteType.ASD)
        window._place_note_drag(0.0, 4, 0.25, 6)
        window.set_editor_note_type(NoteType.ASC)
        window._place_note_drag(0.25, 6, 0.5, 8)

        air_slides = [
            note for note in window.current_chart.notes if isinstance(note, AirSlideStart)
        ]
        assert len(air_slides) == 1
        assert [step.note_type for step in air_slides[0].steps] == [
            NoteType.ASD,
            NoteType.ASC,
        ]
        assert air_slides[0].steps[0].target_note == NoteType.TAP.value
        assert air_slides[0].steps[1].target_note == NoteType.ASD.value
        assert "ASC\t0\t96\t6\t2\tASD\t1.0\t96\t8\t2\t1.0\tDEF" in serialize_c2s(
            window.current_chart
        )
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_air_slide_control_from_mid_segment_splits_existing_chain(
    monkeypatch, tmp_path
) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.TAP)
        window._place_note_at(0.0, 4)
        window.set_editor_note_type(NoteType.ASD)
        window._place_note_drag(0.0, 4, 0.5, 8)
        window.set_editor_note_type(NoteType.ASC)
        window._place_note_drag(0.25, 6, 0.5, 8)

        air_slides = [
            note for note in window.current_chart.notes if isinstance(note, AirSlideStart)
        ]
        assert len(air_slides) == 1
        assert [step.note_type for step in air_slides[0].steps] == [
            NoteType.ASD,
            NoteType.ASC,
        ]
        assert [(step.duration, step.end_cell) for step in air_slides[0].steps] == [
            (96, 6),
            (96, 8),
        ]
        assert air_slides[0].steps[0].target_note == NoteType.TAP.value
        assert air_slides[0].steps[1].target_note == NoteType.ASD.value
        c2s = serialize_c2s(window.current_chart)
        assert "ASD\t0\t0\t4\t2\tTAP\t1.0\t96\t6\t2\t1.0\tDEF" in c2s
        assert "ASC\t0\t96\t6\t2\tASD\t1.0\t96\t8\t2\t1.0\tDEF" in c2s
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_air_slide_control_from_mid_segment_can_reshape_off_current_path(
    monkeypatch, tmp_path
) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.TAP)
        window._place_note_at(0.0, 4)
        window.set_editor_note_type(NoteType.ASD)
        window._place_note_drag(0.0, 4, 0.5, 8)
        window.set_editor_note_type(NoteType.ASC)
        window._place_note_drag(0.25, 10, 0.5, 8)

        air_slides = [
            note for note in window.current_chart.notes if isinstance(note, AirSlideStart)
        ]
        assert len(air_slides) == 1
        assert [
            (step.note_type, step.duration, step.end_cell, step.target_note)
            for step in air_slides[0].steps
        ] == [
            (NoteType.ASD, 96, 10, NoteType.TAP.value),
            (NoteType.ASC, 96, 8, NoteType.ASD.value),
        ]
        assert "ASC\t0\t96\t10\t2\tASD\t1.0\t96\t8\t2\t1.0\tDEF" in serialize_c2s(
            window.current_chart
        )
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_dragging_air_trace_does_not_attach_to_ground_note(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.TAP)
        window._place_note_at(0.0, 4)
        window.set_editor_note_type(NoteType.ALD)
        window._place_note_drag(0.0, 4, 0.25, 6)

        air_trace = next(note for note in window.current_chart.notes if isinstance(note, CrashSlide))
        assert air_trace.parent is None
        assert not hasattr(air_trace, "target_note")
        assert "ALD\t0\t0\t4\t2\t0\t1.0\t96\t6\t2\t1.0\tNON" in serialize_c2s(
            window.current_chart
        )
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_air_trace_does_not_accept_air_note_attachment(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)

        window.set_editor_note_type(NoteType.ALD)
        window._place_note_drag(0.0, 4, 0.25, 6)
        window.set_editor_note_type(NoteType.AIR)
        window._place_note_at(0.0, 4)

        air = next(note for note in window.current_chart.notes if isinstance(note, Air))
        assert air.parent is None
        assert air.target_note == "DEF"
        assert "AIR\t0\t0\t4\t2\tDEF" in serialize_c2s(window.current_chart)
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_air_trace_color_can_be_changed_from_editor_context(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    old_subdivisions = settings.subdivisions
    settings.data_root = str(tmp_path)
    settings.subdivisions = 4
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        window._on_note_width_changed(2)
        window.set_editor_note_type(NoteType.ALD)
        window._place_note_drag(0.0, 4, 0.25, 6)
        note = next(note for note in window.current_chart.notes if isinstance(note, CrashSlide))

        window._change_air_trace_color(note, "VLT")

        changed = next(note for note in window.current_chart.notes if isinstance(note, CrashSlide))
        assert changed.color == "VLT"
        assert "ALD\t0\t0\t4\t2\t0\t1.0\t96\t6\t2\t1.0\tVLT" in serialize_c2s(
            window.current_chart
        )
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root
        settings.subdivisions = old_subdivisions


def test_editor_mode_disables_legacy_audio_export(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()

        assert not hasattr(window, "export_chart_action")
        assert not hasattr(window, "convert_image_to_dds_action")
        assert not window.export_audio_action.isEnabled()
        assert hasattr(window, "create_option_folder_button")
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_left_click_can_place_above_playbar_without_resetting_view(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        window.new_chart()
        viewport = window.visualizer
        viewport.resize(800, 600)
        viewport.set_current_pos(4.0)

        point = QPointF(400, 300)
        _left_click(viewport, point)

        note = window.current_chart.notes[0]
        assert note.measure + note.offset / window.current_chart.metadata.resolution > 4.0
        assert viewport.current_pos == 4.0
    finally:
        window._chart_dirty = False
        window.close()
        settings.data_root = old_data_root


def test_editor_path_fields_have_browse_buttons(monkeypatch, tmp_path) -> None:
    _app()
    old_data_root = settings.data_root
    settings.data_root = str(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        buttons = window.editor_section.findChildren(QPushButton)
        browse_buttons = [
            button
            for button in buttons
            if button.text() == "..."
        ]
        assert len(browse_buttons) == 3
        margins = window.editor_section.layout().contentsMargins()
        assert margins.left() > 0
        assert margins.right() > 0
        assert margins.top() > 0
        assert "hca_key" in window.metadata_fields
        button_index = window.editor_section.layout().indexOf(window.create_option_folder_button)
        assert window.editor_section.layout().itemAt(button_index).alignment() & (
            Qt.AlignmentFlag.AlignHCenter
        )
    finally:
        window.close()
        settings.data_root = old_data_root


def test_editor_mode_hides_note_inspector_by_default_even_if_setting_was_on(
    monkeypatch,
    tmp_path,
) -> None:
    _app()
    old_data_root = settings.data_root
    old_show_inspector = settings.show_inspector
    settings.data_root = str(tmp_path)
    settings.show_inspector = True
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        assert window._show_editor_panel
        assert not window.editor_section.isHidden()
        assert window.note_section.isHidden()
        assert not window.toggle_inspector_action.isChecked()

        window._toggle_note_inspector(True)
        assert not window.note_section.isHidden()

        window._toggle_editor_panel(True)
        assert window._show_editor_panel
        assert window.note_section.isHidden()
    finally:
        window.close()
        settings.data_root = old_data_root
        settings.show_inspector = old_show_inspector


def test_note_debug_overlay_restores_and_persists_menu_state(
    monkeypatch,
    tmp_path,
) -> None:
    _app()
    old_data_root = settings.data_root
    old_show_note_debug_overlay = settings.show_note_debug_overlay
    settings.data_root = str(tmp_path)
    settings.show_note_debug_overlay = True
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "")
    window = MainWindow()
    try:
        assert window.toggle_note_debug_action.isChecked()
        assert window.visualizer.note_debug_overlay.is_active()

        window._toggle_note_debug_overlay(False)

        assert not settings.show_note_debug_overlay
        assert not window.toggle_note_debug_action.isChecked()
        assert not window.visualizer.note_debug_overlay.is_active()
    finally:
        window.close()
        settings.data_root = old_data_root
        settings.show_note_debug_overlay = old_show_note_debug_overlay
