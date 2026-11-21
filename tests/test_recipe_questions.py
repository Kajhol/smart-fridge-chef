from fastapi.testclient import TestClient
from test_recipe_search import (  # noqa: F401  (baza 7 przepisów, endpoint bez LLM)
    db,
    db_path,
    fridge,
    no_llm,
)

from smart_fridge_chef import api
from smart_fridge_chef.recipes import router
from smart_fridge_chef.recipes.questions import find_questions
from smart_fridge_chef.recipes.schema import UserProfile
from smart_fridge_chef.recipes.search import find_candidates


def test_questions_point_to_products_that_unlock_recipes(db):  # noqa: F811
    # jajka i mleko: ciasto (3 braki) i zupa (1 produkt z lodówki) odpadają, masło odblokowuje oba
    questions = find_questions(db, fridge("egg", "milk"), UserProfile())
    assert [(q.ingredient_id, q.unlocks) for q in questions] == [("butter", 2), ("carrot", 1), ("flour", 1)]
    assert questions[0].name_pl


def test_unlocks_match_what_the_filter_really_gains(db):  # noqa: F811
    for profile in [UserProfile(), UserProfile(allergens=["gluten"]), UserProfile(allergens=["celery"])]:
        before = len(find_candidates(db, fridge("egg", "milk"), profile))
        for question in find_questions(db, fridge("egg", "milk"), profile):
            after = len(find_candidates(db, fridge("egg", "milk", question.ingredient_id), profile))
            assert after - before == question.unlocks


def test_questions_respect_allergens_and_exclusions(db):  # noqa: F811
    # z glutenem ciasto odpada, więc mąka i cukier nic nie odblokowują
    gluten = {q.ingredient_id for q in find_questions(db, fridge("egg", "milk"), UserProfile(allergens=["gluten"]))}
    assert gluten == {"butter", "carrot", "hard_cheese"}
    celery = find_questions(db, fridge("egg", "milk"), UserProfile(allergens=["celery"], excluded_ingredients=["butter"]))
    assert celery == []  # zupa ma seler, a każdy inny przepis ma wykluczone masło


def test_no_questions_when_nothing_is_close(db):  # noqa: F811
    assert find_questions(db, fridge("custom_mandarynka", None), UserProfile()) == []


def test_endpoint_returns_questions_and_shopping_list(db_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(router, "RECIPES_DB", db_path)
    items = [{"ingredient_id": i, "label": i, "quantity": 1, "unit": "pcs"} for i in ("egg", "milk", "butter")]
    response = TestClient(api.app).post("/recipes", json={"items": items, "profile": {"allergens": ["gluten"]}})
    data = response.json()
    assert [r["id"] for r in data["recipes"]] == ["r_omelette", "r_cheese_omelette", "r_soup"]
    assert data["shopping_list"] == [
        {"ingredient_id": "hard_cheese", "name_pl": data["shopping_list"][0]["name_pl"],
         "for_recipes": ["cheese_omelette", "soup"]},
        {"ingredient_id": "carrot", "name_pl": data["shopping_list"][1]["name_pl"], "for_recipes": ["soup"]},
    ]
    assert all(q["unlocks"] >= 1 for q in data["questions"])


def test_question_eval_counts_gain_and_dropped_items(db):  # noqa: F811
    from smart_fridge_chef.recipes.benchmark import question_rows, summarize_questions

    row = question_rows(db, "scan", fridge("egg", "milk", "butter"), "bez", UserProfile())
    assert row["candidates_if_yes"] >= row["candidates"]
    assert {d["ingredient_id"] for d in row["dropped"]} == {"egg", "milk", "butter"}
    # bez masła odpadają ciasto i zupa, a pytania wskazują masło
    butter = next(d for d in row["dropped"] if d["ingredient_id"] == "butter")
    assert butter["candidates_lost"] > 0 and butter["asked"]
    summary = summarize_questions([row])
    assert summary["requests"] == 1 and 0 <= summary["important_dropped_asked_share"] <= 1
