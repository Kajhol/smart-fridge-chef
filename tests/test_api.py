import json
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


@pytest.fixture(autouse=True)
def custom_file(tmp_path, monkeypatch):
    path = tmp_path / "custom_ingredients.json"
    monkeypatch.setattr(api, "CUSTOM_INGREDIENTS_FILE", path)
    return path


def test_ingredients_lists_whole_dictionary_without_aliases():
    response = client.get("/ingredients")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(api.INGREDIENTS)
    egg = next(item for item in body if item["id"] == "egg")
    assert egg == {"id": "egg", "name_pl": "jajko", "unit": "pcs", "custom": False}


def test_add_ingredient_saves_it_and_lists_it(custom_file):
    response = client.post("/ingredients", json={"name_pl": "Mandarynka", "unit": "pcs"})

    assert response.status_code == 200
    assert response.json() == {"id": "custom_mandarynka", "name_pl": "Mandarynka", "unit": "pcs", "custom": True}
    assert custom_file.exists()
    ids = [item["id"] for item in client.get("/ingredients").json()]
    assert "custom_mandarynka" in ids


def test_add_ingredient_twice_keeps_one_entry(custom_file):
    client.post("/ingredients", json={"name_pl": "Mandarynka", "unit": "pcs"})
    response = client.post("/ingredients", json={"name_pl": " mandarynka!", "unit": "g"})

    assert response.json()["id"] == "custom_mandarynka"
    assert len(api.load_custom_ingredients()) == 1


def test_add_ingredient_returns_existing_dictionary_entry(custom_file):
    response = client.post("/ingredients", json={"name_pl": "Jablko", "unit": "pcs"})

    assert response.json()["custom"] is False
    assert response.json()["name_pl"] == "jabłko"
    assert not custom_file.exists()


def test_add_ingredient_rejects_name_without_letters(custom_file):
    response = client.post("/ingredients", json={"name_pl": "!!!", "unit": "pcs"})

    assert response.status_code == 422
    assert not custom_file.exists()


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


@pytest.fixture
def scans_dir(tmp_path, monkeypatch):
    path = tmp_path / "scans"
    monkeypatch.setattr(api, "SCANS_DIR", path)
    return path


def save_scan_form(truth_items: str | None = None) -> dict:
    prediction = ScanResult(
        items=[
            DetectedItem(ingredient_id="egg", label="jajka", quantity=6, unit="pcs", confidence="high"),
            DetectedItem(ingredient_id="onion", label="cebula", quantity=1, unit="pcs", confidence="low"),
        ]
    )
    truth = [
        {"ingredient_id": "egg", "label": "jajka", "quantity": 10, "unit": "pcs", "visibility": "visible"},
        {"ingredient_id": "milk", "label": "mleko", "quantity": 1000, "unit": "ml", "visibility": "hidden"},
        {"ingredient_id": "custom_mandarynka", "label": "mandarynki", "quantity": 5, "unit": "pcs", "visibility": "visible"},
    ]
    return {
        "zones": ["door", "shelves_upper"],
        "prediction": prediction.model_dump_json(),
        "truth_items": truth_items if truth_items is not None else json.dumps(truth),
        "seconds": "4.2",
    }


def test_save_scan_writes_ground_truth_photos_and_metrics(scans_dir):
    response = client.post("/scans", files=upload("a.jpg", "b.jpg"), data=save_scan_form())

    assert response.status_code == 200
    body = response.json()
    assert body["scan_id"] == "scan_001"
    assert body["metrics"]["found"] == 1  # egg
    assert body["metrics"]["missed"] == ["milk"]
    assert body["metrics"]["hallucinations"] == ["onion"]

    folder = scans_dir / "scan_001"
    truth = api.GroundTruth.model_validate_json((folder / "ground_truth.json").read_text(encoding="utf-8"))
    assert truth.photos == {"door.jpg": "door", "shelves_upper.jpg": "shelves_upper"}
    assert (folder / "door.jpg").exists()
    assert truth.items[2].ingredient_id is None  # custom_mandarynka jest spoza słownika (D-003)
    assert len(list(folder.glob("pred_*_app_*.json"))) == 1
    metrics_file = next(folder.glob("metrics_*_app_*.json"))
    assert json.loads(metrics_file.read_text(encoding="utf-8"))["seconds"] == 4.2


def test_save_scan_takes_next_free_number(scans_dir):
    (scans_dir / "scan_001").mkdir(parents=True)
    (scans_dir / "scan_007").mkdir()

    response = client.post("/scans", files=upload("a.jpg", "b.jpg"), data=save_scan_form())

    assert response.json()["scan_id"] == "scan_008"


def test_save_scan_rejects_invalid_truth_items(scans_dir):
    response = client.post("/scans", files=upload("a.jpg", "b.jpg"), data=save_scan_form(truth_items='[{"label": "x"}]'))

    assert response.status_code == 422
    assert not scans_dir.exists()
