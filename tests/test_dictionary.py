import json

import pytest
from pydantic import ValidationError

from smart_fridge_chef.dictionary import load_ingredients


def write_dictionary(tmp_path, entries):
    path = tmp_path / "ingredients.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_real_dictionary_loads():
    ingredients = load_ingredients()
    assert "egg" in ingredients


def test_rejects_duplicate_id(tmp_path):
    entry = {"id": "egg", "name_pl": "jajko", "name_en": "egg", "unit": "pcs"}
    path = write_dictionary(tmp_path, [entry, entry])
    with pytest.raises(ValueError, match="Duplicate ingredient id"):
        load_ingredients(path)


def test_rejects_invalid_id(tmp_path):
    entry = {"id": "Mleko 3,2%", "name_pl": "mleko", "name_en": "milk", "unit": "ml"}
    path = write_dictionary(tmp_path, [entry])
    with pytest.raises(ValidationError):
        load_ingredients(path)


def test_rejects_alias_used_twice(tmp_path):
    entries = [
        {"id": "heavy_cream", "name_pl": "śmietanka", "name_en": "heavy cream", "unit": "ml", "aliases": ["cream"]},
        {"id": "sour_cream", "name_pl": "śmietana", "name_en": "sour cream", "unit": "g", "aliases": ["cream"]},
    ]
    path = write_dictionary(tmp_path, entries)
    with pytest.raises(ValueError, match="Alias 'cream'"):
        load_ingredients(path)
