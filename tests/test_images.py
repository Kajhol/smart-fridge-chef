from io import BytesIO

from PIL import Image

from smart_fridge_chef.vision.images import prepare_image

EXIF_ORIENTATION = 0x0112
ROTATE_90_CW = 6


def make_image(width: int, height: int, mode: str = "RGB", fmt: str = "JPEG", orientation: int | None = None) -> bytes:
    image = Image.new(mode, (width, height))
    buffer = BytesIO()
    if orientation is None:
        image.save(buffer, format=fmt)
    else:
        exif = image.getexif()
        exif[EXIF_ORIENTATION] = orientation
        image.save(buffer, format=fmt, exif=exif)
    return buffer.getvalue()


def open_result(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


def test_downscales_long_side_and_keeps_proportions():
    result = open_result(prepare_image(make_image(4000, 3000)))
    assert result.size == (1500, 1125)


def test_respects_custom_max_side():
    result = open_result(prepare_image(make_image(4000, 3000), max_side=1000))
    assert result.size == (1000, 750)


def test_does_not_upscale_small_image():
    result = open_result(prepare_image(make_image(800, 600)))
    assert result.size == (800, 600)


def test_applies_exif_rotation_and_drops_tag():
    result = open_result(prepare_image(make_image(400, 200, orientation=ROTATE_90_CW)))
    assert result.size == (200, 400)
    assert EXIF_ORIENTATION not in result.getexif()


def test_converts_transparent_png_to_jpeg():
    result = open_result(prepare_image(make_image(300, 300, mode="RGBA", fmt="PNG")))
    assert result.format == "JPEG"
    assert result.mode == "RGB"
