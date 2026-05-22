"""Core models for the CHUNITHM chart domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.engine.timeline import ChartTimeline
    from src.notes import Note


@dataclass(slots=True)
class ChartMetadata:
    """
    Header metadata parsed from a .c2s file.
    """

    version: str = ""
    """The C2S specification version (e.g., '1.08.00', '1.13.00')."""

    music_id: str = ""
    """The internal music ID associated with the chart."""

    title: str = ""
    """The display title of the track."""

    artist: str = ""
    """The display artist of the track."""

    sequence_id: str = ""
    """Unique sequence identifier for the difficulty."""

    difficulty: str = ""
    """Human-readable difficulty name (BASIC, EXPERT, etc.)."""

    level: str = ""
    """Display level (e.g., '14', '15+')."""

    creator: str = ""
    """The chart author's display name."""

    bpm_def: list[str] = field(default_factory=list)
    """Initial BPM definition from the BPM_DEF tag."""

    met_def: tuple[int, int] = (4, 4)
    """Default time signature (beats per measure, beat unit)."""

    resolution: int = 384
    """Ticks per measure (standardized to 384 for modern charts)."""

    clk_def: int = 384
    """Click definition resolution."""

    progjudge_bpm: float = 240.0
    """Internal arcade judge timing reference (default 240.0)."""

    progjudge_aer: float = 0.999
    """Judge aerial coefficient."""

    tutorial: bool = False
    """Flag indicating if this is a tutorial sequence."""

    we_name: str = ""
    """WORLD'S END specific title/variant."""

    we_level: int = 0
    """WORLD'S END star rating."""

    difficulty_id: int = 0
    """Numeric difficulty index (0-5)."""

    jacket_path: str = ""
    """Absolute path to the song's jacket art (.dds)."""

    audio_path: str = ""
    """Optional custom chart music path for editor-created charts."""



class TimeSignatureEntry(TypedDict):
    """A single time signature change event."""

    measure: int
    numerator: int
    denominator: int


class BpmEntry(TypedDict):

    """A single BPM change event parsed from the chart header."""

    measure: int
    offset: int
    bpm: float


@dataclass(slots=True)
class SofLanArea:
    """SLA — soflan playfield area with lane position and duration."""

    measure: int
    tick: int
    cell: int
    width: int
    duration: int
    area_id: int


@dataclass(slots=True)
class SofLanPattern:
    """SLP — soflan pattern definition tied to a soflan area."""

    measure: int
    tick: int
    duration: int
    speed: float
    pattern_id: int


@dataclass(slots=True)
class ScrollSpeed:
    """SFL / SFE — scroll speed multiplier over a duration."""

    measure: int
    tick: int
    duration: int
    multiplier: float


@dataclass(slots=True)
class Stop:
    """STP — stop/halt notes for a duration."""

    measure: int
    tick: int
    duration: int


@dataclass(slots=True)
class Deceleration:
    """DCM — deceleration rate over a duration."""

    measure: int
    tick: int
    duration: int
    rate: float


@dataclass(slots=True)
class Click:
    """CLK — metronome click at a position."""

    measure: int
    tick: int


@dataclass(slots=True)
class Chart:
    """A fully parsed Chunithm chart."""

    metadata: ChartMetadata = field(default_factory=ChartMetadata)
    editor: dict[str, str] = field(default_factory=dict)
    notes: list[Note] = field(default_factory=list)
    bpms: list[BpmEntry] = field(default_factory=list)
    signatures: list[TimeSignatureEntry] = field(default_factory=list)
    soflan_areas: list[SofLanArea] = field(default_factory=list)
    soflan_patterns: list[SofLanPattern] = field(default_factory=list)
    scroll_speeds: list[ScrollSpeed] = field(default_factory=list)
    stops: list[Stop] = field(default_factory=list)
    decelerations: list[Deceleration] = field(default_factory=list)
    clicks: list[Click] = field(default_factory=list)
    _warnings: list[str] = field(default_factory=list)

    _timeline: ChartTimeline | None = None

    @property
    def timeline(self) -> ChartTimeline:
        """Get the spatial-temporal timeline for this chart."""
        if self._timeline is None:
            from src.engine.timeline import ChartTimeline

            self._timeline = ChartTimeline(self)
        return self._timeline

    @property
    def warnings(self) -> list[str]:
        """Get validation warnings."""
        return self._warnings

    @warnings.setter
    def warnings(self, value: list[str]) -> None:
        self._warnings = value

    def invalidate_timeline(self) -> None:
        """Clear cached timeline after chart mutations."""
        self._timeline = None

    def find_note_line(self, note: Note) -> str:
        """Best-effort reconstruction of the source line for *note*."""
        return note.serialize()
