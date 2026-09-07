import uuid
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps

from app.config import settings

THUMB_MAX = (400, 400)
DISPLAY_MAX = (2560, 1440)
JPEG_QUALITY = 85


def _variant_path(subdir: str, filename: str) -> Path:
    return settings.photos_dir / subdir / f"{filename}.jpg"


def original_path(filename: str) -> Path:
    return _variant_path("original", filename)


def display_path(filename: str) -> Path:
    return _variant_path("display", filename)


def thumb_path(filename: str) -> Path:
    return _variant_path("thumb", filename)


def save_upload(fileobj: BinaryIO) -> tuple[str, int, int, int]:
    """Guarda un archivo subido como 3 variantes (original/display/thumb) en JPEG.

    Devuelve (filename, width, height, file_size_bytes) del original ya normalizado.
    """
    filename = uuid.uuid4().hex

    image = Image.open(fileobj)
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size

    for subdir, max_size in (
        ("original", None),
        ("display", DISPLAY_MAX),
        ("thumb", THUMB_MAX),
    ):
        variant = image.copy()
        if max_size is not None:
            variant.thumbnail(max_size, Image.Resampling.LANCZOS)
        path = _variant_path(subdir, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        variant.save(path, "JPEG", quality=JPEG_QUALITY, optimize=True)

    file_size_bytes = original_path(filename).stat().st_size
    return filename, width, height, file_size_bytes


def delete_photo_files(filename: str) -> None:
    for path in (original_path(filename), display_path(filename), thumb_path(filename)):
        path.unlink(missing_ok=True)
