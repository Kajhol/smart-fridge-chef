"""Skan lodówki: wybór dostawcy Vision LLM po nazwie modelu i normalizacja ID do słownika."""

from typing import Any

from smart_fridge_chef.dictionary import Ingredient, load_ingredients
from smart_fridge_chef.vision import gemini_provider, openai_provider
from smart_fridge_chef.vision.images import DEFAULT_MAX_SIDE
from smart_fridge_chef.vision.prompt import build_system_prompt
from smart_fridge_chef.vision.schema import Photo, ScanResult

DEFAULT_MODEL = "gemini-3.1-flash-lite"


def resolve_id(raw_id: str | None, ingredients: dict[str, Ingredient], alias_to_id: dict[str, str]) -> str | None:
    if raw_id is None or raw_id in ingredients:
        return raw_id
    return alias_to_id.get(raw_id.strip().lower().replace("_", " "))


def normalize_ids(result: ScanResult, ingredients: dict[str, Ingredient]) -> ScanResult:
    alias_to_id = {alias: ingredient.id for ingredient in ingredients.values() for alias in ingredient.aliases}
    items = [
        item.model_copy(update={"ingredient_id": resolve_id(item.ingredient_id, ingredients, alias_to_id)})
        for item in result.items
    ]
    return ScanResult(items=items)


def scan(
    photos: list[Photo],
    model: str = DEFAULT_MODEL,
    max_side: int = DEFAULT_MAX_SIDE,
    client: Any = None,
) -> ScanResult:
    ingredients = load_ingredients()
    raw = scan_raw(photos, ingredients, model=model, max_side=max_side, client=client)
    return normalize_ids(raw, ingredients)


def scan_raw(
    photos: list[Photo],
    ingredients: dict[str, Ingredient],
    model: str = DEFAULT_MODEL,
    max_side: int = DEFAULT_MAX_SIDE,
    client: Any = None,
) -> ScanResult:
    if not photos:
        raise ValueError("A scan needs at least one photo")

    system_prompt = build_system_prompt(ingredients)
    if model.startswith("gemini-"):
        return gemini_provider.call(photos, system_prompt, model, max_side, client)
    if model.startswith("gpt-"):
        return openai_provider.call(photos, system_prompt, model, max_side, client)
    raise ValueError(f"Unknown provider for model: {model}")
