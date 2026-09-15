"""Проверка и нормализация входного изображения в JPEG Data URL."""

import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MIME_TYPE = "image/jpeg"


class VisionImageError(ValueError):
    """Изображение нельзя безопасно декодировать или нормализовать."""


def _check_dimensions(image) -> None:
    width, height = image.size
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise VisionImageError("слишком большое разрешение изображения")


def _open_image(raw: bytes):
    """Проверить файл через verify(), затем открыть его для декодирования."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as probe:
                _check_dimensions(probe)
                probe.verify()
            image = Image.open(BytesIO(raw))
            _check_dimensions(image)
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                image.close()
                raise VisionImageError("анимированные изображения не поддерживаются")
            image.load()
            return image
    except VisionImageError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise VisionImageError("изображение не удалось декодировать") from exc


def _to_rgb(image):
    image = ImageOps.exif_transpose(image)
    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def _encode(image, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def _compress_to_limit(image) -> bytes:
    current = image
    for _ in range(7):
        for quality in (88, 76, 64, 52, 40):
            encoded = _encode(current, quality)
            if len(encoded) <= MAX_IMAGE_BYTES:
                return encoded
        width, height = current.size
        if width <= 1 and height <= 1:
            break
        current = current.resize(
            (max(1, int(width * 0.7)), max(1, int(height * 0.7))),
            Image.Resampling.LANCZOS,
        )
    raise VisionImageError(
        f"нормализованное изображение слишком большое (лимит {MAX_IMAGE_BYTES} байт)"
    )


def normalize_image(raw: bytes) -> tuple[str, bytes]:
    """Проверить bytes и вернуть MIME-типа JPEG и сжатые JPEG-bytes."""
    if not isinstance(raw, (bytes, bytearray, memoryview)) or not raw:
        raise VisionImageError("пустые или некорректные байты изображения")
    raw = bytes(raw)
    if len(raw) > MAX_IMAGE_BYTES:
        raise VisionImageError(
            f"исходное изображение слишком большое (лимит {MAX_IMAGE_BYTES} байт)"
        )
    image = _open_image(raw)
    try:
        return MIME_TYPE, _compress_to_limit(_to_rgb(image))
    finally:
        image.close()


def to_data_url(raw: bytes) -> str:
    """Преобразовать изображение в компактный JPEG Data URL."""
    import base64

    mime, encoded = normalize_image(raw)
    return f"data:{mime};base64," + base64.b64encode(encoded).decode("ascii")


normalize_to_jpeg = normalize_image
image_to_data_url = to_data_url
make_data_url = to_data_url
