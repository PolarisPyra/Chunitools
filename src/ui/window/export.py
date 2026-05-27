from __future__ import annotations

import os
import re
import wave
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.core.config import USER_CONFIG_DIR
from src.core.read import load_chart_file
from src.ui.view.chart_renderer import ChartRenderer
from src.ui.view.export import export_to_image

if TYPE_CHECKING:
    from src.workspace.layout import MainWindow

CHART_EXTENSIONS = {".c2s"}


def _natural_key(value: str) -> list[int | str]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def _safe_filename(value: str) -> str:
    value = value.strip() or "chart"
    value = re.sub(r"[^\w\-().\[\] ]+", "_", value)
    value = re.sub(r"\s+", " ", value)
    return value[:180]


def _format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "ETA --:--"

    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"ETA {hours:d}:{minutes:02d}:{sec:02d}"

    return f"ETA {minutes:02d}:{sec:02d}"


def _set_export_progress_visible(window: MainWindow, visible: bool) -> None:
    for attr in (
        "status_eta_label",
        "status_progress",
        "status_cancel_button",
        "status_open_log_button",
    ):
        widget = getattr(window, attr, None)
        if widget:
            widget.setVisible(visible)

    if not visible:
        progress = getattr(window, "status_progress", None)
        eta = getattr(window, "status_eta_label", None)

        if progress:
            progress.setMaximum(1)
            progress.setValue(0)
            progress.setFormat("0/0")

        if eta:
            eta.setText("ETA --:--")


def _update_export_progress(
    window: MainWindow,
    current: int,
    total: int,
    started_at: float | None = None,
) -> None:
    progress = getattr(window, "status_progress", None)
    eta = getattr(window, "status_eta_label", None)

    total = max(1, total)
    current = max(0, min(current, total))

    if progress:
        progress.setMaximum(total)
        progress.setValue(current)

    if eta:
        if started_at is None or current <= 0:
            eta.setText("ETA --:--")
        else:
            elapsed = max(0.001, monotonic() - started_at)
            rate = current / elapsed
            remaining = (total - current) / rate if rate > 0 else None
            eta.setText(_format_eta(remaining))


def _get_chart_renderer(window: MainWindow) -> ChartRenderer:
    visualizer = window.visualizer

    for attr in (
        "chart_renderer",
        "_chart_renderer",
        "painter_engine",
        "painterEngine",
        "_chart_painter",
        "_painter",
    ):
        value = getattr(visualizer, attr, None)
        if isinstance(value, ChartRenderer):
            return value

    return ChartRenderer(
        projection=visualizer.projection,
        total_lanes=getattr(visualizer, "total_lanes", 16),
        visible_note_types=getattr(visualizer, "visible_note_types", {}),
        subdivisions=getattr(visualizer, "subdivisions", 4),
    )


def _discover_charts(window: MainWindow) -> list[str]:
    """Gather all available chart paths from the current window context."""
    paths: set[str] = set()

    # 1. From loaded songs list
    songs = getattr(window, "songs", []) or []
    for song in songs:
        if hasattr(song, "fumens"):
            for fumen in song.fumens:
                if hasattr(fumen, "file_path"):
                    paths.add(str(fumen.file_path))

    # 2. From data scanner root
    if not paths:
        scanner = getattr(window, "scanner", None)
        root = getattr(scanner, "data_root", None)
        if root and os.path.isdir(root):
            for p in Path(root).rglob("*.c2s"):
                paths.add(str(p))

    return sorted(paths, key=_natural_key)


# Redundant local definitions removed. Using src.ui.view.export.export_to_image.


def export_current_chart_image(window: MainWindow) -> None:
    chart = window.current_chart
    if chart is None:
        QMessageBox.warning(window, "Export failed", "No chart is currently loaded.")
        return

    title = chart.metadata.title
    difficulty = chart.metadata.difficulty or chart.metadata.level or ""

    if title:
        safe_title = _safe_filename(title)
        safe_diff = _safe_filename(str(difficulty))
        if safe_diff:
            default_name = f"{safe_title}_{safe_diff}.png"
        else:
            default_name = f"{safe_title}.png"
    else:
        current_file_path = getattr(window, "current_file_path", None)
        if current_file_path:
            default_name = Path(current_file_path).with_suffix(".png").name
        else:
            default_name = "chart.png"

    file_path, _ = QFileDialog.getSaveFileName(
        window,
        "Export Current Chart as Image",
        str(Path.home() / "Desktop" / default_name),
        "PNG Images (*.png)",
    )

    if not file_path:
        return

    if not file_path.lower().endswith(".png"):
        file_path += ".png"

    ok = export_to_image(
        chart=chart,
        painter_engine=_get_chart_renderer(window),
        file_path=file_path,
        jacket_path=chart.metadata.jacket_path,
    )

    if ok:
        folder = os.path.dirname(file_path)
        window._last_export_root = folder
        window._last_export_log = None
        window.statusBar().showMessage(f"Exported image: {file_path}", 5000)
    else:
        QMessageBox.warning(
            window, "Export failed", f"Could not write image:\n{file_path}"
        )


def export_all_charts(window: MainWindow) -> None:  # noqa: PLR0912, PLR0915
    chart_paths = _discover_charts(window)
    if not chart_paths:
        QMessageBox.warning(
            window, "Export all charts", "No .c2s chart files were found."
        )
        return

    export_root = QFileDialog.getExistingDirectory(
        window,
        "Select folder for exported chart images",
        str(Path.home() / "Desktop"),
    )
    if not export_root:
        return

    export_root_path = Path(export_root)
    export_root_path.mkdir(parents=True, exist_ok=True)

    window._export_cancel_requested = False
    window._last_export_root = str(export_root_path)

    _set_export_progress_visible(window, True)
    _update_export_progress(window, 0, len(chart_paths))

    painter_engine = _get_chart_renderer(window)

    ok_count = 0
    fail_count = 0
    log_lines: list[str] = []
    started_at = monotonic()

    try:
        for index, chart_path in enumerate(chart_paths, start=1):
            QApplication.processEvents()

            if getattr(window, "_export_cancel_requested", False):
                log_lines.append("CANCELLED")
                break

            src_path = Path(chart_path)

            try:
                chart = load_chart_file(str(src_path))

                title = chart.metadata.title or src_path.stem
                difficulty = chart.metadata.difficulty or chart.metadata.level or ""
                safe_title = _safe_filename(title)
                safe_diff = _safe_filename(str(difficulty))

                if safe_diff:
                    file_name = f"{index:04d}_{safe_title}_{safe_diff}.png"
                else:
                    file_name = f"{index:04d}_{safe_title}.png"

                out_path = export_root_path / file_name

                suffix = 2
                while out_path.exists():
                    if safe_diff:
                        file_name = f"{index:04d}_{safe_title}_{safe_diff}_{suffix}.png"
                    else:
                        file_name = f"{index:04d}_{safe_title}_{suffix}.png"
                    out_path = export_root_path / file_name
                    suffix += 1

                exported = export_to_image(
                    chart=chart,
                    painter_engine=painter_engine,
                    file_path=str(out_path),
                    jacket_path=chart.metadata.jacket_path,
                )

                if exported:
                    ok_count += 1
                    log_lines.append(f"OK\t{chart_path}\t{out_path}")
                    window.statusBar().showMessage(
                        f"Exported {ok_count}/{len(chart_paths)}: {src_path.name}",
                        0,
                    )
                else:
                    fail_count += 1
                    log_lines.append(f"FAIL\t{chart_path}\tCould not write image")

            except (OSError, RuntimeError, UnicodeDecodeError, ValueError) as exc:
                fail_count += 1
                log_lines.append(f"FAIL\t{chart_path}\t{type(exc).__name__}: {exc}")

            _update_export_progress(window, index, len(chart_paths), started_at)
            QApplication.processEvents()

    finally:
        _set_export_progress_visible(window, False)

    log_path = export_root_path / "export_log.tsv"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    window._last_export_log = str(log_path)

    cancelled = getattr(window, "_export_cancel_requested", False)
    if cancelled:
        window.statusBar().showMessage(
            f"Batch export cancelled: {ok_count} exported, {fail_count} failed.",
            8000,
        )
    else:
        window.statusBar().showMessage(
            f"Batch export complete: {ok_count} exported, {fail_count} failed.",
            8000,
        )

    QMessageBox.information(
        window,
        "Export all charts",
        (
            f"{'Export cancelled.' if cancelled else 'Export complete.'}\n\n"
            f"Exported: {ok_count}\n"
            f"Failed: {fail_count}\n"
            f"Folder:\n{export_root_path}"
        ),
    )


def cancel_export_all(window: MainWindow) -> None:
    window._export_cancel_requested = True
    window.statusBar().showMessage("Export cancellation requested.", 3000)


def open_last_export_folder(window: MainWindow) -> None:
    folder = getattr(window, "_last_export_root", None)

    if not folder or not os.path.isdir(folder):
        QMessageBox.information(
            window,
            "Open export folder",
            "No export folder is available yet.",
        )
        return

    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


def open_logs_folder(window: MainWindow) -> None:
    logs_dir = USER_CONFIG_DIR / "logs"
    if not logs_dir.exists():
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            QMessageBox.information(
                window,
                "Open logs folder",
                "Unable to create or access the logs folder.",
            )
            return

    QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir)))


def open_last_export_log(window: MainWindow) -> None:
    log_path = getattr(window, "_last_export_log", None)

    if not log_path or not os.path.exists(log_path):
        QMessageBox.information(
            window,
            "Open export log",
            "No export log is available yet.",
        )
        return

    QDesktopServices.openUrl(QUrl.fromLocalFile(log_path))


def export_current_audio(window: MainWindow) -> None:
    """Export the currently loaded chart's audio as a WAV file."""
    chart = window.current_chart
    if chart is None:
        QMessageBox.warning(window, "Export failed", "No chart is currently loaded.")
        return

    playback_service = getattr(window, "playback_service", None)
    if not playback_service:
        QMessageBox.warning(window, "Export failed", "Audio engine is not initialized.")
        return

    music_player = getattr(playback_service, "music_player", None)
    if not music_player:
        QMessageBox.warning(window, "Export failed", "Music player is not initialized.")
        return

    source_path = getattr(music_player, "_source_path", None)

    if not source_path:
        QMessageBox.warning(
            window, "Export failed", "No audio source available for this chart."
        )
        return

    title = (
        chart.metadata.title or Path(getattr(window, "current_file_path", "audio")).stem
    )
    safe_title = _safe_filename(title)
    default_name = f"{safe_title}.wav"

    desktop = Path.home() / "Desktop"
    file_path, _ = QFileDialog.getSaveFileName(
        window,
        "Export Current Audio as WAV",
        str(desktop / default_name),
        "WAV Audio (*.wav)",
    )

    if not file_path:
        return

    if not file_path.lower().endswith(".wav"):
        file_path += ".wav"

    try:
        music_player.export_wav(Path(file_path))
        window.statusBar().showMessage(f"Exported audio: {file_path}", 5000)
    except (OSError, RuntimeError, wave.Error) as exc:
        QMessageBox.warning(window, "Export failed", f"Could not export audio:\n{exc}")
