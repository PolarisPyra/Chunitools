"""Service helpers for indexing chart metadata across the data directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.read import discover_chart_files, load_chart_file


@dataclass(slots=True)
class ChartIndexEntry:
    path: Path
    music_id: str
    title: str
    difficulty: str
    notes: int
    warnings: int


@dataclass(slots=True)
class ChartIndex:
    entries: list[ChartIndexEntry]
    failures: list[tuple[Path, str]]


def build_index(
    data_dir: str | Path,
    *,
    parse_metadata: bool = True,
    suffixes: tuple[str, ...] = (".c2s",),
) -> ChartIndex:
    """Build a chart index from candidates in `data_dir`."""
    entries: list[ChartIndexEntry] = []
    failures: list[tuple[Path, str]] = []
    for path in discover_chart_files(data_dir, suffixes=suffixes):
        if not parse_metadata:
            entries.append(
                ChartIndexEntry(
                    path=path,
                    music_id="",
                    title=path.stem,
                    difficulty="",
                    notes=0,
                    warnings=0,
                )
            )
            continue
        try:
            chart = load_chart_file(path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            failures.append((path, str(exc)))
            continue
        entries.append(
            ChartIndexEntry(
                path=path,
                music_id=getattr(chart.metadata, "music_id", ""),
                title=getattr(chart.metadata, "title", "") or path.stem,
                difficulty=getattr(chart.metadata, "difficulty", ""),
                notes=len(chart.notes),
                warnings=len(chart.warnings),
            )
        )
    return ChartIndex(entries=entries, failures=failures)
