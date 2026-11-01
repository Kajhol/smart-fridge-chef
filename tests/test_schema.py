import pytest
from pydantic import ValidationError

from smart_fridge_chef.vision.schema import ScanResult


def test_parses_valid_response():
    raw = '{"items": [{"ingredient_id": "egg", "label": "jajka", "quantity": 6, "unit": "pcs", "confidence": "high"}]}'
    result = ScanResult.model_validate_json(raw)
    assert result.items[0].quantity == 6


def test_accepts_item_outside_dictionary():
    raw = '{"items": [{"ingredient_id": null, "label": "sos sojowy", "quantity": 150, "unit": "ml", "confidence": "medium"}]}'
    result = ScanResult.model_validate_json(raw)
    assert result.items[0].ingredient_id is None


def test_rejects_zero_quantity():
    raw = '{"items": [{"ingredient_id": "milk", "label": "mleko", "quantity": 0, "unit": "ml", "confidence": "high"}]}'
    with pytest.raises(ValidationError):
        ScanResult.model_validate_json(raw)
