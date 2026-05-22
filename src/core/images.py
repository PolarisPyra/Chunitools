"""Image helpers for editor-managed CHUNITHM jacket assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

__all__ = [
    "JACKET_IMAGE_SIZE",
    "SUPPORTED_JACKET_SOURCE_SUFFIXES",
    "convert_jacket_image_to_dds",
]

JACKET_IMAGE_SIZE = (512, 512)
SUPPORTED_JACKET_SOURCE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def convert_jacket_image_to_dds(
    source_path: str | Path,
    output_dir: str | Path,
    music_id: str = "",
) -> Path:
    """Convert a PNG/JPEG jacket source to a 512x512 DDS file."""
    source = Path(source_path).expanduser()
    if source.suffix.lower() not in SUPPORTED_JACKET_SOURCE_SUFFIXES:
        raise ValueError("expected a PNG or JPEG source image")

    destination_dir = Path(output_dir).expanduser()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / _jacket_dds_filename(source, music_id)

    try:
        with Image.open(source) as image:
            dds_image = ImageOps.fit(
                image.convert("RGBA"),
                JACKET_IMAGE_SIZE,
                method=Image.Resampling.LANCZOS,
            )
            dds_image.save(destination, format="DDS")
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"could not convert image to DDS: {exc}") from exc

    return destination


def _jacket_dds_filename(source: Path, music_id: str) -> str:
    normalized_id = music_id.strip()
    if normalized_id:
        return f"CHU_UI_Jacket_{normalized_id}.dds"
    return f"{source.stem}.dds"
