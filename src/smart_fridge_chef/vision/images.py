"""Przygotowanie zdjęcia przed wysłaniem do Vision LLM: obrót wg EXIF, zmniejszenie, JPEG."""

from io import BytesIO

from PIL import Image, ImageOps

DEFAULT_MAX_SIDE = 1500
JPEG_QUALITY = 85


def prepare_image(data: bytes, max_side: int = DEFAULT_MAX_SIDE) -> bytes:
    with Image.open(BytesIO(data)) as original:
        image = ImageOps.exif_transpose(original)
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()
