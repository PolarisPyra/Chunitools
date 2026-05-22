from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF

from src.ui.view.projection import ViewProjection
from src.ui.view.renderer.base import BaseRenderer


def test_note_head_shape_uses_beveled_functional_outline() -> None:
    renderer = BaseRenderer(ViewProjection())
    path = renderer._note_head_path(QRectF(0, 0, 64, 12))

    assert not path.contains(QPointF(0, 0))
    assert not path.contains(QPointF(64, 0))
    assert path.contains(QPointF(32, 6))
    assert path.contains(QPointF(0.5, 6))
