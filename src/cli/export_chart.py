
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.core.read import load_chart_file
from src.engine.timeline import ChartTimeline
from src.ui.view.chart_renderer import ChartRenderer
from src.ui.view.projection import ViewProjection
from src.ui.window.export import export_to_image, _safe_filename

USAGE = "Usage: python src/cli/export_chart.py <chart_path> [output_path]"


def _default_output_path(chart_path: str, title: str, difficulty: str) -> str:
    output_title = title or Path(chart_path).stem
    safe_title = _safe_filename(output_title)
    safe_difficulty = _safe_filename(difficulty) if difficulty else ""
    if safe_difficulty:
        return f"{safe_title}_{safe_difficulty}.png"
    return f"{safe_title}.png"


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write(f"{USAGE}\n")
        return 1

    chart_path = sys.argv[1]
    app = QApplication.instance() or QApplication(sys.argv)
    
    try:
        chart = load_chart_file(chart_path)
        timeline = ChartTimeline(chart)
        proj = ViewProjection(timeline_engine=timeline)
        painter = ChartRenderer(proj)
        
        title = chart.metadata.title
        difficulty = chart.metadata.difficulty or chart.metadata.level or ""
        
        if len(sys.argv) > 2:
            out_path = sys.argv[2]
        else:
            out_path = _default_output_path(chart_path, title, str(difficulty))

        sys.stderr.write(f"Exporting {chart_path} to {out_path}...\n")
        ok = export_to_image(chart, painter, out_path)
        if ok:
            sys.stderr.write(f"Successfully exported to {out_path}\n")
            return 0

        sys.stderr.write(f"Failed to export to {out_path}\n")
        return 1
            
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
