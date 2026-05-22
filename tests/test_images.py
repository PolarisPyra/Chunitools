from __future__ import annotations

import pytest
from PIL import Image

from src.core.images import JACKET_IMAGE_SIZE, convert_jacket_image_to_dds


def test_convert_jacket_image_to_dds_writes_named_desktop_style_asset(tmp_path) -> None:
    source = tmp_path / "source.png"
    output_dir = tmp_path / "Desktop"
    Image.new("RGB", (32, 48), "red").save(source)

    output_path = convert_jacket_image_to_dds(source, output_dir, "1234")

    assert output_path == output_dir / "CHU_UI_Jacket_1234.dds"
    with Image.open(output_path) as converted:
        assert converted.size == JACKET_IMAGE_SIZE


def test_convert_jacket_image_to_dds_rejects_non_png_or_jpeg(tmp_path) -> None:
    source = tmp_path / "source.gif"
    source.write_bytes(b"not a supported jacket source")

    with pytest.raises(ValueError, match="PNG or JPEG"):
        convert_jacket_image_to_dds(source, tmp_path)
