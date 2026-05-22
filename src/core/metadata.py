"""Fast metadata extraction from .c2s files without full parsing."""

from __future__ import annotations

import re
from pathlib import Path

from src.core.const import Command
from src.core.library_scanner import DataScanner
from src.core.library_models import MetadataPreview

__all__ = ["DataScanner", "fast_get_metadata", "load_chart_file", "parse_c2s"]


def parse_c2s(content: str):
    """Compatibility wrapper for the full .c2s parser."""
    from src.core.read import parse_c2s as parse

    return parse(content)


def load_chart_file(path: str | Path):
    """Compatibility wrapper for chart loading."""
    from src.core.read import load_chart_file as load

    return load(path)


def _process_metadata_line(
    line: str,
    meta: MetadataPreview,
    patterns: tuple[re.Pattern, ...],
) -> int:
    """Extract metadata from a single line using provided patterns."""
    bpm_pattern, creator_pattern, version_pattern = patterns
    bpm_match = bpm_pattern.match(line)
    if bpm_match:
        meta["bpm_def"] = bpm_match.group(1).split()
        return 1

    creator_match = creator_pattern.match(line)
    if creator_match:
        meta["creator"] = creator_match.group(1).strip()
        return 1

    version_match = version_pattern.match(line)
    if version_match:
        meta["version"] = version_match.group(1).strip().split()[0]
        return 1

    return 0


def _try_extract_metadata(
    file_path: str, encoding_name: str, meta: MetadataPreview
) -> bool:
    """Attempt to extract metadata from a file using a specific encoding."""
    patterns = (
        re.compile(rf"^{Command.BPM_DEF.value}\s+(.*)$"),
        re.compile(rf"^{Command.CREATOR.value}\s+(.*)$"),
        re.compile(rf"^{Command.VERSION.value}\s+(.*)$"),
    )
    found_count = 0
    try:
        with open(file_path, encoding=encoding_name) as file_handle:
            for _ in range(100): # Scan only the first 100 lines for speed
                line = file_handle.readline()
                if not line:
                    break
                found_count += _process_metadata_line(line.strip(), meta, patterns)
                if found_count >= 3:
                    return True
        return found_count > 0
    except (UnicodeDecodeError, UnicodeError, OSError):
        return False


def fast_get_metadata(file_path: str | Path) -> MetadataPreview:
    """
    Quickly extract BPM_DEF, CREATOR and VERSION without full chart parsing.
    
    This is useful for showing previews in the song picker or library scanner
    where parsing thousands of full charts would be too slow.
    """
    meta: MetadataPreview = {"bpm_def": None, "creator": None, "version": None}
    encodings = ["utf-8", "cp932", "shift_jis"]
    
    file_path_str = str(file_path)

    for encoding_name in encodings:
        if _try_extract_metadata(file_path_str, encoding_name, meta):
            break

    return meta
