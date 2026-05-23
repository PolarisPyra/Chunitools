from __future__ import annotations

from dataclasses import dataclass, field

from src.notes.base import Note


@dataclass(frozen=True, kw_only=True, slots=True)
class SlideTo(Note):
    """A single segment/step within a slide chain."""

    duration: int
    end_cell: int
    end_width: int
    target_id: str | None = None
    animation: str | None = None
    is_visible: bool = True

    def get_extra_parts(self) -> list[str]:
        parts = [str(self.duration), str(self.end_cell), str(self.end_width)]
        parts.append(self.target_id if self.target_id is not None else "")
        if self.animation is not None:
            parts.append(self.animation)
        return parts


@dataclass(frozen=True, kw_only=True, slots=True)
class Slide(Note):
    """Hierarchical slide note containing multiple steps, matching Ched's structure."""

    steps: tuple[SlideTo, ...] = field(default_factory=tuple)

    @property
    def duration(self) -> int:
        """Get the total duration from the start of the slide to the end of the last step."""
        return sum(s.duration for s in self.steps)

    @property
    def end_cell(self) -> int:
        return self.steps[-1].end_cell if self.steps else self.cell

    @property
    def end_width(self) -> int:
        return self.steps[-1].end_width if self.steps else self.width

    def get_extra_parts(self) -> list[str]:
        return []
