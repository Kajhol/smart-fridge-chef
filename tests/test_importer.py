import json
import re
import sqlite3
from pathlib import Path

import pytest

from smart_fridge_chef.dictionary import load_ingredients
from smart_fridge_chef.recipes.importer import (
    SKIP,
    SKIPPED_ALLERGENS,
    SKIPPED_RAW,
    build_alias_index,
    difficulty,
    format_line,
    import_recipes,
    join_key,
    map_ingredient,
    parse_servings,
    skipped_allergens,
)

SAMPLE = Path(__file__).parent / "data" / "raw_recipes_sample.csv"
KARO_SAMPLE = Path(__file__).parent / "data" / "karo_parsed_sample.csv"
INTERACTIONS_SAMPLE = Path(__file__).parent / "data" / "raw_interactions_sample.csv"


@pytest.fixture(scope="module")
def alias_index():
    return build_alias_index(load_ingredients())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("eggs", "egg"),
        ("large eggs", "egg"),
        ("fresh chives", "chives"),
        ("unsalted butter", "butter"),
        ("cucumbers", "cucumber"),
        ('"confectioners sugar"', "powdered_sugar"),
        ("white pepper", SKIP),
        ("juice of", SKIP),
        ("truffle oil", None),
    ],
)
def test_map_ingredient(alias_index, raw, expected):
    assert map_ingredient(raw, alias_index) == expected


def test_difficulty():
    assert difficulty(10, 4, 3, []) == "easy"
    assert difficulty(45, 9, 10, []) == "medium"
    assert difficulty(45, 9, 10, ["easy"]) == "easy"
    assert difficulty(120, 5, 5, ["easy"]) == "hard"


def test_join_key_ignores_case_and_punctuation():
    assert join_key("aunt jane s honey  waffles", 653.04) == join_key("Aunt Jane's Honey Waffles!", 653.0)


def test_format_line():
    assert format_line({"quantity": "1/4", "unit": "cup", "name": "olive oil"}) == "1/4 cup olive oil"
    assert format_line({"quantity": "3", "name": "large eggs"}) == "3 large eggs"
    item = {"quantity": "1", "unitQuantity": "5 1/2", "unitUnit": "ounce", "unit": "can", "name": "baby corn", "description": "drained"}
    assert format_line(item) == "1 can (5 1/2 ounce) baby corn, drained"
    assert format_line({"name": "salt \\u0026 pepper"}) == "salt & pepper"


def test_skipped_allergens():
    assert skipped_allergens("celery seed") == {"celery"}
    assert skipped_allergens("ground cloves") == set()


def test_parse_servings():
    assert parse_servings("4.0") == 4
    assert parse_servings("") is None
    assert parse_servings("32767.0") is None
    assert parse_servings("2.5") is None


def test_import_sample(tmp_path):
    db_path = tmp_path / "recipes.sqlite"
    report = import_recipes(SAMPLE, KARO_SAMPLE, db_path)

    assert (report.read, report.imported, report.dropped_unmapped, report.dropped_invalid) == (7, 2, 1, 1)
    assert (report.dropped_no_quantities, report.dropped_no_match, report.with_servings) == (1, 2, 1)
    assert report.unmapped["spaghetti"] == 1

    db = sqlite3.connect(db_path)
    recipe = db.execute(
        "SELECT title, difficulty, kcal_per_serving, url, servings FROM recipes WHERE id = 'fc_1001'"
    ).fetchone()
    assert recipe == ("scrambled eggs with chives", "easy", 210.5, "https://www.food.com/recipe/1001", 2)

    lines = json.loads(db.execute("SELECT ingredient_lines FROM recipes WHERE id = 'fc_1001'").fetchone()[0])
    assert lines[0] == "4 large eggs"
    assert lines[-1] == "salt & pepper, to taste"

    ingredients = {row[0] for row in db.execute("SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id = 'fc_1001'")}
    assert ingredients == {"egg", "milk", "butter", "chives", "salt"}

    steps, servings = db.execute("SELECT steps, servings FROM recipes WHERE id = 'fc_1003'").fetchone()
    assert json.loads(steps) == ["whisk eggs", "fry with cheese"]
    assert servings is None
    assert db.execute("SELECT COUNT(*) FROM pantry_staples").fetchone()[0] >= 3

    allergens = {r[0]: set() for r in db.execute("SELECT id FROM recipes")}
    for recipe_id, allergen in db.execute("SELECT recipe_id, allergen FROM recipe_allergens"):
        allergens[recipe_id].add(allergen)
    assert allergens["fc_1001"] == {"eggs", "milk"}
    assert allergens["fc_1003"] == {"eggs", "milk", "celery"}  # celery salt jest pomijana, ale alergen zostaje


def test_skipped_items_with_allergen_keep_it():
    """Pozycja pomijana przy mapowaniu nie może zgubić alergenu (audyt M2)."""
    keywords = re.compile(r"celery|mustard|sesame|soy|peanut|nut|almond|fish|anchov|shrimp|wheat|flour|milk|cream|cheese|egg")
    risky = {raw for raw in SKIPPED_RAW if keywords.search(raw)} - {"cream of tartar", "nutmeg"}
    assert risky <= set(SKIPPED_ALLERGENS)


def test_audit_finds_no_leaks_in_sample(tmp_path):
    from smart_fridge_chef.recipes.audit import audit

    db_path = tmp_path / "recipes.sqlite"
    import_recipes(SAMPLE, KARO_SAMPLE, db_path)
    assert audit(db_path) == {}


def test_import_ratings(tmp_path):
    db_path = tmp_path / "recipes.sqlite"
    report = import_recipes(SAMPLE, KARO_SAMPLE, db_path, interactions_path=INTERACTIONS_SAMPLE)
    assert report.with_ratings == 2

    db = sqlite3.connect(db_path)
    ratings = dict(db.execute("SELECT id, n_ratings FROM recipes").fetchall())
    assert ratings == {"fc_1001": 2, "fc_1003": 1}  # ocena 0 i przepis spoza bazy pominięte
    # średnia wszystkich ocen to 14/3; przy wadze 5 jedna piątka nie bije dwóch ocen 4,5
    (rating_1001,), (rating_1003,) = db.execute("SELECT rating FROM recipes ORDER BY id").fetchall()
    assert rating_1003 < 5 and rating_1001 < 5


def test_alternatives_in_ingredient_lines_add_allergens():
    """Zamiennik w linii („or almond extract”) może trafić do garnka, więc jego alergen trafia do przepisu."""
    from smart_fridge_chef.recipes.importer import alternative_allergens

    assert alternative_allergens(["2 teaspoons vanilla or 2 teaspoons almond extract"]) == {"nuts"}
    assert alternative_allergens(["1 1/2 cups milk (or soy milk)"]) == {"milk", "soy"}
    assert alternative_allergens(["1 tablespoon cider vinegar or 1 tablespoon malt vinegar"]) == {"gluten"}
    assert alternative_allergens(["1 lb filet of beef or 24 raw shrimp, peeled"]) == {"crustaceans"}
    assert "fish" in alternative_allergens(["1 dash tabasco sauce or 1 dash worcestershire sauce"])


def test_alternative_check_skips_plain_lines_and_false_alarms():
    from smart_fridge_chef.recipes.importer import alternative_allergens

    assert alternative_allergens(["1 cup peanut butter"]) == set()  # bez zamiennika ufamy mapowaniu
    assert alternative_allergens(["1 (14 ounce) can coconut milk"]) == set()
    assert alternative_allergens(["6 lbs crab apples (or tart apples)"]) == set()
    assert alternative_allergens(["1/4 teaspoon cream of tartar (optional)"]) == set()
    assert alternative_allergens(["2 tablespoons lemon juice or 2 tablespoons white vinegar"]) == set()
    assert alternative_allergens(["2 tablespoons cider vinegar or 2 tablespoons red wine vinegar"]) == {"sulphites"}
