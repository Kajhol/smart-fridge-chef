from smart_fridge_chef.dictionary import load_ingredients
from smart_fridge_chef.vision.prompt import build_system_prompt


def test_prompt_contains_dictionary_line():
    prompt = build_system_prompt(load_ingredients())
    assert "egg | jajko | pcs" in prompt


def test_prompt_contains_every_ingredient_id():
    ingredients = load_ingredients()
    prompt = build_system_prompt(ingredients)
    for ingredient_id in ingredients:
        assert f"\n{ingredient_id} | " in prompt
