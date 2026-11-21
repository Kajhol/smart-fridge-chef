import json
import sqlite3
from types import SimpleNamespace

from test_recipe_search import (  # noqa: F401  (fixture z bazą 7 przepisów)
    RECIPES,
    db_path,
)

from smart_fridge_chef.recipes import benchmark
from smart_fridge_chef.recipes.benchmark import (
    PROFILES,
    Calls,
    rating_sheet,
    run,
    summarize,
)
from smart_fridge_chef.recipes.schema import FridgeItem

ITEMS = [FridgeItem(ingredient_id=i, label=i, quantity=1, unit="pcs")
         for i in ("egg", "milk", "butter", "hard_cheese", "flour", "sugar", "carrot")]


class FakeModels:
    """Klient Gemini na niby: odpowiedź według schematu z configu, z tokenami."""

    def __init__(self, answers):
        self.answers = answers

    def generate_content(self, model, contents, config):
        schema = config.response_json_schema["title"]
        answer = self.answers[schema]
        if isinstance(answer, Exception):
            raise answer
        text = json.dumps(answer(contents) if callable(answer) else answer)
        meta = SimpleNamespace(prompt_token_count=1000, candidates_token_count=200, thoughts_token_count=None)
        return SimpleNamespace(text=text, usage_metadata=meta)


def translation(prompt):
    recipe = json.loads(prompt)
    return {"title_pl": "PL " + recipe["title"], "steps_pl": ["PL " + s for s in recipe["steps"]],
            "ingredient_lines_pl": ["PL " + line for line in recipe["ingredient_lines"]]}


def fake(**answers):
    return Calls("gemini-test", SimpleNamespace(models=FakeModels(answers)))


def test_gate_and_costs(db_path):  # noqa: F811
    # LLM próbuje wcisnąć ciasto (gluten) i omlet każdemu; kod i tak nie przepuszcza alergenów
    main = fake(RecipeSelection={"picks": [{"recipe_id": "r_cake", "description": "Ciasto."},
                                           {"recipe_id": "r_omelette", "description": "Omlet."}]},
                TranslatedRecipe=translation)
    with sqlite3.connect(db_path) as db:
        result = run(db, [("scan_test", ITEMS)], PROFILES, main)
    summary = summarize(result, prices=(0.1, 0.4))

    assert summary["requests"] == len(PROFILES)
    assert summary["violations"] == 0
    for row in result["rows"]:
        for recipe in row["recipes"]:
            assert not set(RECIPES[recipe["id"]][1]) & set(PROFILES[row["profile"]].allergens)
    bez = next(r for r in result["rows"] if r["profile"] == "bez_ograniczen")
    assert bez["calls"] == 4 and bez["input_tokens"] == 4000 and bez["output_tokens"] == 800
    assert summary["usd_per_request"] is not None and summary["untranslated_share"] < 0.5


def test_llm_errors_are_counted_and_baseline_compared(db_path):  # noqa: F811
    main = fake(RecipeSelection=RuntimeError("quota"), TranslatedRecipe=translation)
    baseline = fake(TranslatedRecipe=RuntimeError("down"))
    with sqlite3.connect(db_path) as db:
        result = run(db, [("scan_test", ITEMS)], {"bez_ograniczen": PROFILES["bez_ograniczen"]}, main, baseline)
    summary = summarize(result)

    assert summary["requests_with_llm_errors"] == 1 and summary["usd_per_request"] is None
    assert len(result["translations"]) == 3
    assert summary["baseline_untranslated_share"] == 1.0  # baseline padł: wszystko po angielsku
    sheet = rating_sheet(result["translations"], "gemini-test", "groq/test")
    assert sheet.count("ocena: [ ]") == 6 and "## Klucz" in sheet


def test_ai_recipe_violation_is_caught(db_path):  # noqa: F811
    from smart_fridge_chef.recipes.chef import Guard
    from smart_fridge_chef.recipes.schema import Recipe, RecipeIngredient, UserProfile

    profile = UserProfile(allergens=["eggs"])
    recipe = Recipe(id=None, source="ai_generated", title="Jajecznica", description="", servings=2, time_min=5,
                    difficulty="easy", kcal_per_serving=None, url=None, ingredient_lines=["3 jajka"], steps=["Smaż."],
                    ingredients=[RecipeIngredient(ingredient_id="egg", name_pl="jajko", status="in_fridge")])
    with sqlite3.connect(db_path) as db:
        found = benchmark.violations(db, recipe, profile, Guard(db, profile))
    assert any("alergeny" in f for f in found) and any("AI" in f for f in found)


def test_load_scan_skips_zero_quantity(tmp_path):
    path = tmp_path / "ground_truth.json"
    path.write_text(json.dumps({"scan_id": "s1", "items": [
        {"ingredient_id": "egg", "label": "jajka", "quantity": 6, "unit": "pcs", "visibility": "visible"},
        {"ingredient_id": None, "label": "pusty słoik", "quantity": 0, "unit": "pcs"},
    ]}), encoding="utf-8")
    scan_id, items = benchmark.load_scan(path)
    assert scan_id == "s1" and [i.label for i in items] == ["jajka"]


def test_api_keys_are_redacted_from_errors(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret_123456")
    calls = fake(RecipeSelection=RuntimeError("bad key gsk_secret_123456"))
    try:
        calls("p", "s", __import__("smart_fridge_chef.recipes.schema", fromlist=["x"]).RecipeSelection)
    except RuntimeError:
        pass
    assert "gsk_secret" not in calls.errors[0] and "<GROQ_API_KEY>" in calls.errors[0]


def test_shareable_has_numbers_but_no_recipe_text(db_path, tmp_path, monkeypatch):  # noqa: F811
    main = fake(RecipeSelection={"picks": []}, TranslatedRecipe=translation)
    with sqlite3.connect(db_path) as db:
        result = run(db, [("scan_test", ITEMS)], {"bez_ograniczen": PROFILES["bez_ograniczen"]}, main)
    result |= {"model": "gemini-test", "baseline": None, "summary": summarize(result)}
    source = tmp_path / "recipes_test.json"
    source.write_text(json.dumps(result), encoding="utf-8")

    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["eval-recipes-share", str(source), "--out", str(tmp_path / "share.json")])
    benchmark.share_main()
    shared = json.loads((tmp_path / "share.json").read_text(encoding="utf-8"))
    assert shared["summary"]["requests"] == 1 and shared["rows"][0]["recipes"][0]["id"] in RECIPES
    assert "PL " not in json.dumps(shared) and "title" not in json.dumps(shared["rows"])


def test_share_refuses_when_a_key_leaks(tmp_path, monkeypatch):
    import pytest

    (tmp_path / ".env").write_text("GEMINI_API_KEY=AIza_secret_value_123\n", encoding="utf-8")
    source = tmp_path / "recipes_x.json"
    source.write_text(json.dumps({"model": "m", "baseline": None, "summary": {"note": "AIza_secret_value_123"},
                                  "rows": []}), encoding="utf-8")
    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["eval-recipes-share", str(source), "--out", str(tmp_path / "share.json")])
    with pytest.raises(SystemExit, match="STOP"):
        benchmark.share_main()
    assert not (tmp_path / "share.json").exists()
