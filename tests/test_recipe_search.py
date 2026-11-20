import json

import pytest
from fastapi.testclient import TestClient

from smart_fridge_chef import api
from smart_fridge_chef.dictionary import load_ingredients
from smart_fridge_chef.recipes import router
from smart_fridge_chef.recipes.importer import create_db
from smart_fridge_chef.recipes.schema import FridgeItem, UserProfile
from smart_fridge_chef.recipes.search import find_candidates

# id: (składniki, alergeny, trudność, czas, ocena)
RECIPES = {
    "r_omelette": (["egg", "milk", "butter", "salt"], ["eggs", "milk"], "easy", 10, 4.5),
    "r_cheese_omelette": (["egg", "milk", "butter", "hard_cheese"], ["eggs", "milk"], "easy", 15, 4.0),
    "r_cake": (["egg", "flour", "sugar", "butter", "milk"], ["eggs", "gluten", "milk"], "medium", 60, 4.8),
    "r_soup": (["egg", "butter", "hard_cheese", "carrot"], ["eggs", "milk", "celery"], "easy", 20, 4.9),
    "r_boiled_egg": (["egg", "salt", "water"], ["eggs"], "easy", 10, 5.0),
    "r_roast": (["egg", "milk", "butter", "flour"], ["eggs", "milk", "gluten"], "hard", 120, 4.1),
    "r_far": (["egg", "flour", "sugar", "carrot", "hard_cheese"], ["eggs", "gluten", "milk"], "easy", 10, 5.0),
}


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "recipes.sqlite"
    db = create_db(path, load_ingredients())
    for recipe_id, (ingredients, allergens, difficulty, time_min, rating) in RECIPES.items():
        db.execute(
            "INSERT INTO recipes VALUES (?, ?, NULL, ?, ?, ?, ?, 200, ?, 'food.com', NULL, 2, ?, 10)",
            (recipe_id, recipe_id.removeprefix("r_"), json.dumps(["step 1"]), json.dumps(ingredients),
             time_min, difficulty, rating, json.dumps([f"1 {i}" for i in ingredients])),
        )
        db.executemany("INSERT INTO recipe_ingredients VALUES (?, ?, ?)", [(recipe_id, i, i) for i in ingredients])
        db.executemany("INSERT INTO recipe_allergens VALUES (?, ?)", [(recipe_id, a) for a in allergens])
    db.commit()
    db.close()
    return path


@pytest.fixture
def db(db_path):
    import sqlite3

    connection = sqlite3.connect(db_path)
    yield connection
    connection.close()


def fridge(*ids: str | None) -> list[FridgeItem]:
    return [FridgeItem(ingredient_id=i, label=str(i), quantity=1, unit="pcs") for i in ids]


def ids(candidates) -> list[str]:
    return [c.recipe_id for c in candidates]


def test_filters_and_ranking(db):
    found = ids(find_candidates(db, fridge("egg", "milk", "butter", "hard_cheese"), UserProfile()))
    # far: tylko 2 z 5 w lodówce i 3 braki; boiled_egg: 1 główny składnik
    assert "r_far" not in found and "r_boiled_egg" not in found
    # wynik: w lodówce - 1,5 * braki; sól to przyprawa; przy remisie (soup, roast: 1,5) wyższa ocena
    assert found == ["r_cheese_omelette", "r_omelette", "r_soup", "r_roast", "r_cake"]


def test_allergens_are_never_returned(db):
    items = fridge("egg", "milk", "butter", "hard_cheese", "flour", "sugar", "carrot")
    for allergen in ["eggs", "milk", "gluten", "celery"]:
        for candidate in find_candidates(db, items, UserProfile(allergens=[allergen])):
            assert allergen not in RECIPES[candidate.recipe_id][1]
    assert "r_soup" not in ids(find_candidates(db, items, UserProfile(allergens=["celery"])))


def test_excluded_difficulty_and_time(db):
    items = fridge("egg", "milk", "butter", "flour")
    assert "r_roast" in ids(find_candidates(db, items, UserProfile()))
    assert "r_roast" not in ids(find_candidates(db, items, UserProfile(max_difficulty="medium")))
    assert "r_roast" not in ids(find_candidates(db, items, UserProfile(max_time_min=60)))
    assert not set(ids(find_candidates(db, items, UserProfile(excluded_ingredients=["butter"])))) & {"r_roast", "r_omelette"}


def test_custom_and_unknown_items_are_ignored(db):
    found = ids(find_candidates(db, fridge("egg", "milk", "butter", None, "custom_mandarynka"), UserProfile()))
    assert "r_omelette" in found


def test_endpoint(db_path, monkeypatch):
    monkeypatch.setattr(router, "RECIPES_DB", db_path)
    client = TestClient(api.app)
    body = {
        "items": [
            {"ingredient_id": "egg", "label": "jajka", "quantity": 6, "unit": "pcs", "confidence": "high"},
            {"ingredient_id": "milk", "label": "mleko", "quantity": 1000, "unit": "ml"},
            {"ingredient_id": "butter", "label": "masło", "quantity": 200, "unit": "g"},
            {"ingredient_id": "custom_mandarynka", "label": "mandarynki", "quantity": 4, "unit": "pcs"},
        ],
        "profile": {"allergens": ["gluten"]},
    }
    response = client.post("/recipes", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["candidates_considered"] == len(data["recipes"]) == 3  # omelette, cheese_omelette, soup
    omelette = next(r for r in data["recipes"] if r["id"] == "r_omelette")
    statuses = {i["ingredient_id"]: i["status"] for i in omelette["ingredients"]}
    assert statuses == {"egg": "in_fridge", "milk": "in_fridge", "butter": "in_fridge", "salt": "pantry"}
    cheese = next(r for r in data["recipes"] if r["id"] == "r_cheese_omelette")
    assert "Brakuje" in cheese["description"]


def test_endpoint_without_database(tmp_path, monkeypatch):
    monkeypatch.setattr(router, "RECIPES_DB", tmp_path / "missing.sqlite")
    response = TestClient(api.app).post(
        "/recipes", json={"items": [{"ingredient_id": "egg", "label": "jajka", "quantity": 6, "unit": "pcs"}]}
    )
    assert response.status_code == 503
