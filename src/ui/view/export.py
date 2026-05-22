import os
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QImageWriter, QPainter, QLinearGradient, QPen, QFont

from src.core.models import Chart
from src.notes import Note
from src.ui.view.chart_renderer import ChartRenderer
from src.ui import theme


def render_segment(
    painter: QPainter,
    chart: Chart,
    painter_engine: ChartRenderer,
    x_left: int,
    segment_height: int,
    start_measure: int,
    chunk: int = 4,
) -> None:
    projection = painter_engine.projection
    chart_width = projection.x(painter_engine.total_lanes)
    end_measure = start_measure + chunk
    fake_cur_pos = float(start_measure)

    painter.save()
    painter.translate(x_left, segment_height)

    # In export mode, the segment height is chunk * measure_height
    # We want top of view to be start_measure + chunk
    top_abs_pos = float(end_measure)
    bottom_abs_pos = float(start_measure)
    
    # Clipping rect to prevent notes from bleeding out of the segment area
    # Relative to the translated state (anchor at bottom)
    clip_rect = QRectF(0, -float(chunk * projection.measure_height) - 40, chart_width, float(chunk * projection.measure_height) + 80)
    painter.setClipRect(clip_rect)

    painter_engine.draw_lane_lines(painter, fake_cur_pos, top_abs_pos, bottom_abs_pos)
    painter_engine.draw_measure_lines(
        painter, start_measure, end_measure, fake_cur_pos, chart_width, show_labels=False
    )

    # Collect visible notes for this segment
    visible: list[Note] = []
    # Simple filtering by measure since we are rendering segments
    for note in chart.notes:
        if note.measure <= end_measure and chart.timeline.note_abs_end_pos(note) >= start_measure:
            visible.append(note)
            
    painter_engine.draw_notes(painter, visible, fake_cur_pos)
    painter.restore()


def _draw_gutter(
    painter: QPainter,
    x: int,
    width: int,
    img_height: int,
    measure_height: float,
    measures_per_column: int,
    start_m: int,
    draw_labels: bool = True,
) -> None:
    """Helper to draw a stylized metallic gutter at a specific X position."""
    # Vertical metallic gradient for the gutter
    grad = QLinearGradient(x, 0, x + width, 0)
    grad.setColorAt(0.0, theme.qt(theme.PITCH_BLACK))
    grad.setColorAt(0.1, theme.qt(theme.DEEP_SLATE))
    grad.setColorAt(0.5, theme.qt(theme.CHARCOAL_GREY))
    grad.setColorAt(0.9, theme.qt(theme.DEEP_SLATE))
    grad.setColorAt(1.0, theme.qt(theme.PITCH_BLACK))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawRect(x, 20, width, img_height - 40)

    # Gutter edge highlights
    painter.setPen(QPen(theme.qt(theme.BORDER_CONTROL), 1))
    painter.drawLine(x + 1, 20, x + 1, img_height - 20)
    painter.drawLine(x + width - 1, 20, x + width - 1, img_height - 20)

    # Measure separation ticks and numbers
    painter.setPen(QPen(theme.qt(theme.BORDER_CONTROL_SOFT), 1))
    
    if draw_labels:
        font = painter.font()
        font.setPointSizeF(28.0)
        font.setBold(True)
        painter.setFont(font)

    for m in range(measures_per_column + 1):
        y = int(img_height - 40 - m * measure_height)
        if 20 <= y <= img_height - 20:
            # Draw tick
            painter.setPen(QPen(theme.qt(theme.BORDER_CONTROL_SOFT), 1))
            painter.drawLine(x + 5, y, x + width - 5, y)
            
            if draw_labels:
                # Draw Measure Number (Centered in gutter)
                measure_idx = start_m + m
                painter.setPen(theme.qt(theme.TEXT_MEASURE))
                label_rect = QRectF(float(x), float(y - 25), float(width), 50.0)
                painter.drawText(
                    label_rect, 
                    Qt.AlignmentFlag.AlignCenter, 
                    str(measure_idx)
                )


def _load_dds_to_image(path: str) -> QImage:
    """Load a DDS file using PIL and convert it to QImage."""
    if not os.path.exists(path):
        return QImage()

    try:
        with Image.open(path) as source:
            # We want high quality for export, so no aggressive thumbnailing like in the picker
            image = source.convert("RGBA")
            data = image.tobytes("raw", "RGBA")
            return QImage(
                data, image.size[0], image.size[1], QImage.Format.Format_RGBA8888
            ).copy()  # .copy() to ensure we own the buffer
    except (OSError, ValueError):
        return QImage()


def export_to_image(
    chart: Chart,
    painter_engine: ChartRenderer,
    file_path: str,
    measures_per_column: int = 4,
    png_quality: int | None = None,
    antialias: bool = True,
    jacket_path: str | None = None,
) -> bool:
    # Use current projection settings for export density
    projection = painter_engine.projection
    
    try:
        # Calculate true chart length considering note durations and metadata events
        last_note_end = max((chart.timeline.note_abs_end_pos(n) for n in chart.notes), default=0.0)
        last_bpm_m = max((b["measure"] for b in chart.bpms), default=0)
        last_sig_m = max((s["measure"] for s in chart.signatures), default=0)
        
        total_measures = int(max(last_note_end, float(last_bpm_m), float(last_sig_m))) + 1
        num_columns = (total_measures + measures_per_column - 1) // measures_per_column

        lane_area_width = projection.x(painter_engine.total_lanes)
        # Symmetrical column layout: [Padding 25] [Gutter 75] [Gap 10] [Lanes W] [Gap 10] [Gutter 75] [Padding 25]
        column_width = lane_area_width + 220

        # Header logic: 800px jacket + padding
        header_height = 840 if (jacket_path or chart.metadata.title) else 0
        
        img_width = int(num_columns * column_width + 50)
        img_height = int(measures_per_column * projection.measure_height + 120 + header_height)

        image = QImage(img_width, img_height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(theme.qt(theme.PITCH_BLACK))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)

        # --- Draw Header ---
        if header_height > 0:
            painter.save()
            header_margin = 40
            current_x = float(header_margin)
            
            # 1. Jacket Art
            if jacket_path:
                jacket_img = _load_dds_to_image(jacket_path)
                if not jacket_img.isNull():
                    target_rect = QRectF(float(header_margin), 20.0, 800.0, 800.0)
                    painter.drawImage(target_rect, jacket_img)
                    current_x += 840.0
            
            # 2. Song Info
            title_font = QFont(theme.FONT_UI, 180, QFont.Weight.Bold)
            painter.setFont(title_font)
            painter.setPen(theme.qt(theme.TEXT_PRIMARY))
            title_y = 260.0
            painter.drawText(int(current_x), int(title_y), chart.metadata.title or "Untitled")
            
            creator_font = QFont(theme.FONT_UI, 90)
            painter.setFont(creator_font)
            painter.setPen(theme.qt(theme.TEXT_SOFT))
            painter.drawText(int(current_x), int(title_y + 200), f"Charter: {chart.metadata.creator or 'Unknown'}")
            
            # 3. Difficulty & Level
            painter.setPen(theme.qt(theme.TEXT_SOFT))
            diff_text = f"{chart.metadata.difficulty or 'Unknown'} {chart.metadata.level or ''}".strip()
            painter.drawText(int(current_x), int(title_y + 340), diff_text)
            
            # Bottom border for header
            painter.setPen(QPen(theme.qt(theme.BORDER_CONTROL_SOFT), 2))
            painter.drawLine(header_margin, header_height - 10, img_width - header_margin, header_height - 10)
            painter.restore()

        for col in range(num_columns):
            start_m = col * measures_per_column
            # x_left is the start of the lane area
            x_left = col * column_width + 110
            
            painter.save()
            painter.translate(0, header_height)

            # --- Draw Left Gutter ---
            _draw_gutter(painter, x_left - 85, 75, img_height - header_height, projection.measure_height, measures_per_column, start_m, draw_labels=True)
            
            # --- Draw Right Gutter ---
            _draw_gutter(painter, x_left + lane_area_width + 10, 75, img_height - header_height, projection.measure_height, measures_per_column, start_m, draw_labels=False)
            
            # Lane area borders
            painter.setPen(QPen(theme.qt(theme.BORDER_CONTROL), 2))
            painter.drawLine(x_left, 20, x_left, img_height - header_height - 20)
            painter.drawLine(x_left + lane_area_width, 20, x_left + lane_area_width, img_height - header_height - 20)
            
            render_segment(
                painter, 
                chart, 
                painter_engine, 
                int(x_left), 
                int(img_height - header_height - 40), 
                start_m, 
                measures_per_column
            )
            painter.restore()

        painter.end()
    finally:
        pass

    if png_quality is None:
        return image.save(file_path)

    writer = QImageWriter(file_path, b"png")
    writer.setQuality(png_quality)
    return writer.write(image)
