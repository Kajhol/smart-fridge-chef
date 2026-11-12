import base64
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from smart_fridge_chef.vision.client import scan
from smart_fridge_chef.vision.openai_provider import build_input
from smart_fridge_chef.vision.schema import Photo, ScanResult


def make_jpeg(width: int = 4000, height: int = 3000) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


def test_build_input_labels_each_photo_and_embeds_jpeg():
    photos = [Photo(zone="door", data=make_jpeg()), Photo(zone="extra", data=make_jpeg())]
    content = build_input(photos, max_side=1000)[0]["content"]

    assert content[0] == {"type": "input_text", "text": "Photo 1, zone: door"}
    assert content[2]["text"] == "Photo 2, zone: extra"
    image = content[1]
    assert image["type"] == "input_image"
    assert image["detail"] == "high"
    prefix = "data:image/jpeg;base64,"
    assert image["image_url"].startswith(prefix)
    decoded = base64.b64decode(image["image_url"].removeprefix(prefix))
    assert Image.open(BytesIO(decoded)).size == (1000, 750)


def test_scan_routes_gpt_models_to_openai():
    output = '{"items": [{"ingredient_id": "eggs", "label": "jajka", "quantity": 6, "unit": "pcs", "confidence": "high"}]}'
    client = SimpleNamespace(responses=FakeResponses(output))

    result = scan([Photo(zone="door", data=make_jpeg())], model="gpt-test", client=client)

    assert result.items[0].ingredient_id == "egg"
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["text_format"] is ScanResult
    assert "egg | jajko | pcs" in call["instructions"]
