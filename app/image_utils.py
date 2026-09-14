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


_VARIANT_MAX_SIZE = {"original": None, "display": DISPLAY_MAX, "thumb": THUMB_MAX}


def _normalize(fileobj: BinaryIO) -> Image.Image:
    image = Image.open(fileobj)
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def _write_variants(image: Image.Image, filename: str, subdirs: tuple[str, ...]) -> None:
    for subdir in subdirs:
        variant = image.copy()
        max_size = _VARIANT_MAX_SIZE[subdir]
        if max_size is not None:
            variant.thumbnail(max_size, Image.Resampling.LANCZOS)
        path = _variant_path(subdir, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        variant.save(path, "JPEG", quality=JPEG_QUALITY, optimize=True)


def save_variants(
    fileobj: BinaryIO, subdirs: tuple[str, ...], filename: str | None = None
) -> tuple[str, int, int]:
    """Guarda las variantes pedidas (subconjunto de original/display/thumb) en
    JPEG. Si no se pasa `filename`, genera uno (uuid) nuevo; si se pasa,
    reescribe esas variantes para un Photo ya existente (p.ej. cuando el
    archivo cambió en la USB pero sigue siendo la misma foto registrada).
    Devuelve (filename, width, height).
    """
    filename = filename or uuid.uuid4().hex
    image = _normalize(fileobj)
    width, height = image.size
    _write_variants(image, filename, subdirs)
    return filename, width, height


def save_upload(fileobj: BinaryIO) -> tuple[str, int, int, int]:
    """Guarda un archivo subido como 3 variantes (original/display/thumb) en JPEG.

    Devuelve (filename, width, height, file_size_bytes) del original ya normalizado.
    """
    filename, width, height = save_variants(fileobj, ("original", "display", "thumb"))
    file_size_bytes = original_path(filename).stat().st_size
    return filename, width, height, file_size_bytes


def save_usb_preview(fileobj: BinaryIO) -> tuple[str, int, int]:
    """Registra una foto de USB todavía no copiada (has_original=False): genera
    solo display+thumb, nunca escribe 'original'. Devuelve (filename, width, height).
    """
    return save_variants(fileobj, ("display", "thumb"))


def promote_to_original(fileobj: BinaryIO, filename: str) -> tuple[int, int, int]:
    """'Copiar a la biblioteca': con los bytes reales del original, reescribe
    las 3 variantes reusando el filename ya asignado a un Photo existente.
    Devuelve (width, height, file_size_bytes).
    """
    image = _normalize(fileobj)
    width, height = image.size
    _write_variants(image, filename, ("original", "display", "thumb"))
    file_size_bytes = original_path(filename).stat().st_size
    return width, height, file_size_bytes


def delete_photo_files(filename: str) -> None:
    for path in (original_path(filename), display_path(filename), thumb_path(filename)):
        path.unlink(missing_ok=True)
