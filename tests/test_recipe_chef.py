import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from test_recipe_search import (  # noqa: F401  (fixture z bazą 7 przepisów)
    RECIPES,
    db_path,
)

from smart_fridge_chef import api
from smart_fridge_chef.recipes import router
from smart_fridge_chef.recipes.chef import Guard, word_pattern
from smart_fridge_chef.recipes.schema import UserProfile

ITEMS = [
    {"ingredient_id": "egg", "label": "jajka", "quantity": 6, "unit": "pcs"},
    {"ingredient_id": "milk", "label": "mleko", "quantity": 1000, "unit": "ml"},
    {"ingredient_id": "butter", "label": "masło", "quantity": 200, "unit": "g"},
    {"ingredient_id": "custom_mandarynka", "label": "mandarynki", "quantity": 4, "unit": "pcs"},
]


class FakeLLM:
    """Odpowiedź według schematu; wyjątek w odpowiedzi jest rzucany. Zapisuje wywołania."""

    def __init__(self, **responses):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def __call__(self, prompt, system_prompt, schema):
        self.calls.append((schema.__name__, prompt))
        response = self.responses[schema.__name__]
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(prompt)
        return schema.model_validate(response)


def translation(prompt: str) -> dict:
    """Tłumacz testowy: „PL” przed każdym wpisem, liczby bez zmian."""
    recipe = json.loads(prompt)
    return {
        "title_pl": "PL " + recipe["title"],
        "steps_pl": ["PL " + s for s in recipe["steps"]],
        "ingredient_lines_pl": ["PL " + line for line in recipe["ingredient_lines"]],
    }


def post(db_path, monkeypatch, fake, profile=None, items=ITEMS):  # noqa: F811
    monkeypatch.setattr(router, "RECIPES_DB", db_path)
    api.app.dependency_overrides[router.get_llm] = lambda: fake
    try:
        response = TestClient(api.app).post("/recipes", json={"items": items, "profile": profile or {}})
    finally:
        api.app.dependency_overrides.pop(router.get_llm, None)
    assert response.status_code == 200
    return response.json()


def test_selection_is_validated_and_translated(db_path, monkeypatch):  # noqa: F811
    fake = FakeLLM(
        RecipeSelection={"picks": [
            {"recipe_id": "r_soup", "description": "Zupa z tego, co masz.",
             "substitutions": [{"missing_id": "carrot", "suggestion": "pietruszka"},
                               {"missing_id": "egg", "suggestion": "nie brakuje"}]},
            {"recipe_id": "r_invented", "description": "Nie ma takiego."},
            {"recipe_id": "r_soup", "description": "Drugi raz."},
        ]},
        TranslatedRecipe=translation,
    )
    data = post(db_path, monkeypatch, fake)

    ids = [r["id"] for r in data["recipes"]]
    # zmyślone i powtórzone ID odpada, brakujące miejsca dopełnia ranking z SQL
    # ranking bez alergenów: omelette (3), roast i cheese_omelette (1,5; roast ma wyższą ocenę)
    assert ids == ["r_soup", "r_omelette", "r_roast"]
    soup = data["recipes"][0]
    assert soup["description"] == "Zupa z tego, co masz."
    assert soup["substitutions"] == [{"missing_id": "carrot", "suggestion": "pietruszka"}]  # egg nie brakuje
    assert soup["title"] == "PL soup" and soup["steps"] == ["PL step 1"]
    assert soup["ingredient_lines"][0] == "PL 1 egg"
    assert data["recipes"][1]["description"].startswith("Masz ")  # opis z szablonu dla dopełnienia
    # prompt wyboru: kandydaci z ID i lodówka; mandarynki z aplikacji tylko w opisie lodówki
    prompt = fake.calls[0][1]
    assert "[r_cake]" in prompt and "mandarynki" in prompt
    assert [c[0] for c in fake.calls].count("TranslatedRecipe") == 3


def test_llm_never_returns_allergen(db_path, monkeypatch):  # noqa: F811
    # LLM próbuje podsunąć ciasto (gluten) i zamiennik z mlekiem przy alergii na gluten i mleko
    fake = FakeLLM(
        RecipeSelection={"picks": [
            {"recipe_id": "r_cake", "description": "Ciasto!"},
            {"recipe_id": "r_omelette", "description": "Omlet na maśle i mleku, podaj z serem."},
        ]},
        TranslatedRecipe=translation,
    )
    items = ITEMS + [{"ingredient_id": i, "label": i, "quantity": 1, "unit": "pcs"}
                     for i in ("flour", "sugar", "hard_cheese", "carrot")]
    for profile in ({"allergens": ["gluten"]}, {"allergens": ["eggs"]}, {"allergens": ["gluten", "celery"]}):
        data = post(db_path, monkeypatch, fake, profile, items)
        for recipe in data["recipes"]:
            assert not set(RECIPES[recipe["id"]][1]) & set(profile["allergens"])
    data = post(db_path, monkeypatch, fake, {"allergens": ["gluten"]}, items)
    assert "r_cake" not in [r["id"] for r in data["recipes"]]


def test_description_with_forbidden_ingredient_falls_back_to_template(db_path, monkeypatch):  # noqa: F811
    fake = FakeLLM(
        RecipeSelection={"picks": [{"recipe_id": "r_omelette", "description": "Świetny z mąką.",
                                    "substitutions": []}]},
        TranslatedRecipe=translation,
    )
    data = post(db_path, monkeypatch, fake, {"allergens": ["gluten"]})
    omelette = next(r for r in data["recipes"] if r["id"] == "r_omelette")
    assert omelette["description"].startswith("Masz ")


def test_llm_failure_degrades_to_sql_ranking(db_path, monkeypatch):  # noqa: F811
    fake = FakeLLM(RecipeSelection=RuntimeError("quota"), TranslatedRecipe=RuntimeError("quota"))
    data = post(db_path, monkeypatch, fake)
    assert [r["id"] for r in data["recipes"]] == ["r_omelette", "r_roast", "r_cheese_omelette"]
    assert data["recipes"][0]["title"] == "omelette"  # po angielsku, ale jest odpowiedź


def test_translation_keeps_numbers_and_counts(db_path, monkeypatch):  # noqa: F811
    def bad_translation(prompt):
        result = translation(prompt)
        result["ingredient_lines_pl"][0] = "2 jajka"  # było „1 egg”: zmieniona ilość
        result["steps_pl"].append("dodatkowy krok")
        return result

    fake = FakeLLM(RecipeSelection={"picks": []}, TranslatedRecipe=bad_translation)
    recipe = post(db_path, monkeypatch, fake)["recipes"][0]
    assert recipe["title"].startswith("PL ")
    assert recipe["ingredient_lines"][0] == "1 egg" and recipe["ingredient_lines"][1].startswith("PL ")
    assert recipe["steps"] == ["step 1"]


GENERATED = {
    "title_pl": "Mandarynki z cukrem",
    "description": "Szybki deser.",
    "ingredient_ids": ["sugar", "salt", "lemon"],
    "ingredient_lines_pl": ["2 łyżki cukru", "szczypta soli"],
    "steps_pl": ["Wymieszaj."],
    "time_min": 5,
    "difficulty": "easy",
}
NO_CANDIDATES = [
    {"ingredient_id": "sugar", "label": "cukier", "quantity": 500, "unit": "g"},
    {"ingredient_id": "lemon", "label": "cytryna", "quantity": 2, "unit": "pcs"},
]


def test_ai_recipe_when_no_candidates(db_path, monkeypatch):  # noqa: F811
    fake = FakeLLM(GeneratedRecipe=GENERATED)
    data = post(db_path, monkeypatch, fake, {"servings": 3}, NO_CANDIDATES)
    assert data["candidates_considered"] == 0
    [recipe] = data["recipes"]
    assert recipe["source"] == "ai_generated" and recipe["id"] is None and recipe["url"] is None
    assert recipe["servings"] == 3
    statuses = {i["ingredient_id"]: i["status"] for i in recipe["ingredients"]}
    assert statuses == {"sugar": "in_fridge", "salt": "pantry", "lemon": "in_fridge"}
    prompt = fake.calls[0][1]
    assert "sugar: cukier" in prompt and "salt: sól (przyprawa)" in prompt


@pytest.mark.parametrize("change", [
    {"ingredient_ids": ["sugar", "lemon", "flour"]},  # spoza lodówki
    {"ingredient_lines_pl": ["2 łyżki cukru", "1 jajko"]},  # zakazane przy alergii na jajka
    {"time_min": 90},  # dłużej niż max_time_min
])
def test_ai_recipe_is_rejected_when_unsafe(db_path, monkeypatch, change):  # noqa: F811
    fake = FakeLLM(GeneratedRecipe=GENERATED | change)
    data = post(db_path, monkeypatch, fake, {"allergens": ["eggs"], "max_time_min": 30}, NO_CANDIDATES)
    assert data["recipes"] == []


def test_ai_recipe_failure_returns_empty(db_path, monkeypatch):  # noqa: F811
    data = post(db_path, monkeypatch, FakeLLM(GeneratedRecipe=RuntimeError("timeout")), None, NO_CANDIDATES)
    assert data["recipes"] == [] and data["candidates_considered"] == 0 and data["shopping_list"] == []


def test_guard_catches_polish_forms(db_path):  # noqa: F811
    with sqlite3.connect(db_path) as db:
        guard = Guard(db, UserProfile(allergens=["eggs"], excluded_ingredients=["hard_cheese"]))
    assert "egg" in guard.banned and "hard_cheese" in guard.banned
    assert not guard.ok("Dodaj dwa jajka.") and not guard.ok("Posyp serem.") and not guard.ok("Beat the eggs")
    assert guard.ok("Serwuj na ciepło.")
    assert word_pattern([]) is None


def test_get_llm_without_key_is_none(monkeypatch):
    monkeypatch.setenv("RECIPE_MODEL", "gemini-3.1-flash-lite")
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert router.get_llm() is None
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert router.get_llm() is not None
    monkeypatch.setenv("RECIPE_MODEL", "groq/openai/gpt-oss-120b")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert router.get_llm() is None
