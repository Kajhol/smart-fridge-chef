from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from smart_fridge_chef.dictionary import Ingredient
from smart_fridge_chef.vision.client import normalize_ids, resolve_id, scan, scan_raw
from smart_fridge_chef.vision.gemini_provider import build_contents
from smart_fridge_chef.vision.schema import Photo
from smart_fridge_chef.vision.schema import DetectedItem, ScanResult

INGREDIENTS = {
    "egg": Ingredient(id="egg", name_pl="jajko", name_en="egg", unit="pcs", aliases=["eggs", "egg yolks"]),
    "milk": Ingredient(id="milk", name_pl="mleko", name_en="milk", unit="ml", aliases=["whole milk"]),
}
ALIAS_TO_ID = {"eggs": "egg", "egg yolks": "egg", "whole milk": "milk"}


def make_jpeg(width: int = 4000, height: int = 3000) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format="JPEG")
    return buffer.getvalue()


def make_item(ingredient_id: str | None, label: str = "coś") -> DetectedItem:
    return DetectedItem(ingredient_id=ingredient_id, label=label, quantity=1, unit="pcs", confidence="high")


class FakeModels:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.response_text)


def make_fake_client(response_text: str) -> SimpleNamespace:
    return SimpleNamespace(models=FakeModels(response_text))


@pytest.mark.parametrize(
    ("raw_id", "expected"),
    [
        ("egg", "egg"),
        (None, None),
        ("eggs", "egg"),
        ("Egg_Yolks", "egg"),
        (" whole_milk ", "milk"),
        ("jogurt", None),
    ],
)
def test_resolve_id(raw_id, expected):
    assert resolve_id(raw_id, INGREDIENTS, ALIAS_TO_ID) == expected


def test_normalize_ids_keeps_other_fields():
    result = normalize_ids(ScanResult(items=[make_item("eggs", label="jajka L")]), INGREDIENTS)
    item = result.items[0]
    assert item.ingredient_id == "egg"
    assert item.label == "jajka L"
    assert item.quantity == 1


def test_build_contents_labels_each_photo_with_zone():
    photos = [Photo(zone="door", data=make_jpeg()), Photo(zone="shelves_upper", data=make_jpeg())]
    contents = build_contents(photos, max_side=1000)

    assert contents[0] == "Photo 1, zone: door"
    assert contents[2] == "Photo 2, zone: shelves_upper"
    image_part = contents[1]
    assert image_part.inline_data.mime_type == "image/jpeg"
    assert Image.open(BytesIO(image_part.inline_data.data)).size == (1000, 750)


def test_scan_returns_normalized_result():
    response = '{"items": [{"ingredient_id": "eggs", "label": "jajka", "quantity": 6, "unit": "pcs", "confidence": "high"}]}'
    client = make_fake_client(response)

    result = scan([Photo(zone="door", data=make_jpeg())], model="gemini-test", client=client)

    assert result.items[0].ingredient_id == "egg"
    call = client.models.calls[0]
    assert call["model"] == "gemini-test"
    assert "egg | jajko | pcs" in call["config"].system_instruction
    assert call["config"].response_mime_type == "application/json"


def test_scan_raw_keeps_model_ids_unchanged():
    response = '{"items": [{"ingredient_id": "eggs", "label": "jajka", "quantity": 6, "unit": "pcs", "confidence": "high"}]}'
    raw = scan_raw([Photo(zone="door", data=make_jpeg())], INGREDIENTS, client=make_fake_client(response))
    assert raw.items[0].ingredient_id == "eggs"


def test_scan_rejects_response_breaking_schema():
    response = '{"items": [{"ingredient_id": "milk", "label": "mleko", "quantity": 0, "unit": "ml", "confidence": "high"}]}'
    with pytest.raises(ValueError):
        scan([Photo(zone="door", data=make_jpeg())], client=make_fake_client(response))


def test_scan_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        scan([Photo(zone="door", data=make_jpeg())], model="llama-3", client=make_fake_client("{}"))


def test_scan_without_photos_does_not_call_model():
    client = make_fake_client("{}")
    with pytest.raises(ValueError):
        scan([], client=client)
    assert client.models.calls == []
