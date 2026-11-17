from typing import get_args

import pytest
from pydantic import ValidationError

from smart_fridge_chef.dictionary import load_ingredients
from smart_fridge_chef.recipes.schema import (
    Allergen,
    Recipe,
    RecipeIngredient,
    RecipeRequest,
    RecipeResponse,
    RecipeSelection,
)
from smart_fridge_chef.vision.schema import DetectedItem, ScanResult


def test_accepts_scan_result_unchanged():
    scan = ScanResult(items=[DetectedItem(ingredient_id="egg", label="jajka", quantity=6, unit="pcs", confidence="high")])
    request = RecipeRequest.model_validate_json(scan.model_dump_json())
    assert request.items[0].ingredient_id == "egg"


def test_accepts_item_added_by_hand_without_confidence():
    raw = '{"items": [{"ingredient_id": "butter", "label": "masło", "quantity": 200, "unit": "g"}]}'
    request = RecipeRequest.model_validate_json(raw)
    assert request.items[0].unit == "g"


def test_profile_defaults():
    raw = '{"items": [{"ingredient_id": "egg", "label": "jajka", "quantity": 6, "unit": "pcs"}]}'
    profile = RecipeRequest.model_validate_json(raw).profile
    assert profile.allergens == []
    assert profile.servings == 2
    assert profile.max_difficulty == "hard"


def test_rejects_empty_fridge():
    with pytest.raises(ValidationError):
        RecipeRequest.model_validate_json('{"items": []}')


def test_rejects_unknown_allergen():
    raw = '{"items": [{"ingredient_id": "egg", "label": "jajka", "quantity": 6, "unit": "pcs"}], "profile": {"allergens": ["lactose"]}}'
    with pytest.raises(ValidationError):
        RecipeRequest.model_validate_json(raw)


def test_allergens_match_dictionary():
    used = {allergen for ingredient in load_ingredients().values() for allergen in ingredient.allergens}
    assert used == set(get_args(Allergen))


def test_llm_selection_limited_to_three():
    pick = {"recipe_id": "r1", "description": "opis"}
    with pytest.raises(ValidationError):
        RecipeSelection.model_validate({"picks": [pick] * 4})


def test_response_limited_to_three_recipes():
    assert RecipeResponse.model_json_schema()["properties"]["recipes"]["maxItems"] == 3


def test_recipe_without_servings_keeps_exact_lines():
    recipe = Recipe(
        id="fc_1001", source="database", title="Jajecznica", description="Masz jajka.", servings=None,
        time_min=10, difficulty="easy", kcal_per_serving=210.5,
        ingredients=[RecipeIngredient(ingredient_id="egg", name_pl="jajko", status="in_fridge")],
        ingredient_lines=["4 duże jajka"], steps=["Roztrzep jajka."], url=None,
    )
    assert recipe.servings is None
    assert recipe.ingredient_lines == ["4 duże jajka"]
