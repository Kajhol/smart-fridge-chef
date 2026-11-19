from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from smart_fridge_chef import api
from smart_fridge_chef.vision.schema import DetectedItem, ScanResult

client = TestClient(api.app)


def make_jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (100, 100)).save(buffer, format="JPEG")
    return buffer.getvalue()


def upload(*names: str) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("photos", (name, make_jpeg(), "image/jpeg")) for name in names]


@pytest.fixture
def fake_scan(monkeypatch):
    calls = []

    def fake(photos, model):
        calls.append((photos, model))
        item = DetectedItem(ingredient_id="egg", label="jajka", quantity=6, unit="pcs", confidence="high")
        return ScanResult(items=[item])

    monkeypatch.setattr(api, "scan", fake)
    return calls


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ingredients_lists_whole_dictionary_without_aliases():
    response = client.get("/ingredients")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(api.INGREDIENTS)
    egg = next(item for item in body if item["id"] == "egg")
    assert egg == {"id": "egg", "name_pl": "jajko", "unit": "pcs"}


def test_scan_returns_scan_result_and_passes_zones(fake_scan):
    response = client.post("/scan", files=upload("a.jpg", "b.jpg"), data={"zones": ["door", "extra"]})

    assert response.status_code == 200
    assert response.json()["items"][0]["ingredient_id"] == "egg"
    photos, model = fake_scan[0]
    assert [photo.zone for photo in photos] == ["door", "extra"]
    assert model == api.VISION_MODEL


def test_scan_rejects_photo_zone_count_mismatch(fake_scan):
    response = client.post("/scan", files=upload("a.jpg", "b.jpg"), data={"zones": ["door"]})
    assert response.status_code == 422
    assert fake_scan == []


def test_scan_rejects_unknown_zone(fake_scan):
    response = client.post("/scan", files=upload("a.jpg"), data={"zones": ["garage"]})
    assert response.status_code == 422
    assert fake_scan == []


def test_scan_rejects_too_many_photos(fake_scan):
    names = [f"{i}.jpg" for i in range(api.MAX_PHOTOS + 1)]
    response = client.post("/scan", files=upload(*names), data={"zones": ["extra"] * len(names)})
    assert response.status_code == 422
    assert fake_scan == []


def test_scan_rejects_non_image_file(fake_scan):
    response = client.post(
        "/scan", files=[("photos", ("notes.txt", b"not an image", "text/plain"))], data={"zones": ["door"]}
    )
    assert response.status_code == 422
    assert fake_scan == []


def test_scan_reports_bad_model_response_as_502(monkeypatch):
    def broken(photos, model):
        ScanResult.model_validate_json('{"items": [{"quantity": 0}]}')

    monkeypatch.setattr(api, "scan", broken)
    response = client.post("/scan", files=upload("a.jpg"), data={"zones": ["door"]})
    assert response.status_code == 502
