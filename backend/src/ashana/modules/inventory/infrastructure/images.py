import io

from PIL import Image, ImageOps, UnidentifiedImageError

from ashana.modules.inventory.domain.models import invalid

MAX_UPLOAD = 8 * 1024 * 1024
MAX_SIDE = 800
# Decompression-bomb guard: refuse images with more pixels than a 40 MP photo.
Image.MAX_IMAGE_PIXELS = 40_000_000


def normalize_photo(data: bytes) -> bytes:
    """Re-encode an uploaded photo to WebP: drops EXIF/GPS and anything that is not pixels."""
    if not data or len(data) > MAX_UPLOAD:
        raise invalid("image", "Фото до 8 МБ в формате JPEG, PNG или WebP")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ("JPEG", "PNG", "WEBP"):
                raise invalid("image", "Поддерживаются JPEG, PNG и WebP")
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            image.save(out, "WEBP", quality=82, method=4)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise invalid("image", "Не удалось прочитать фото. Выберите другой файл") from None
    return out.getvalue()
