"""Wywołanie Vision LLM (Gemini): zdjęcia jednego skanu -> ScanResult."""

from dataclasses import dataclass
from typing import Literal

from google import genai
from google.genai import types

from smart_fridge_chef.dictionary import Ingredient, load_ingredients
from smart_fridge_chef.vision.images import DEFAULT_MAX_SIDE, prepare_image
from smart_fridge_chef.vision.prompt import build_system_prompt
from smart_fridge_chef.vision.schema import ScanResult

Zone = Literal["door", "shelves_upper", "shelves_lower", "extra"]

DEFAULT_MODEL = "gemini-3.1-flash-lite"


@dataclass
class Photo:
    zone: Zone
    data: bytes


def build_contents(photos: list[Photo], max_side: int) -> list[str | types.Part]:
    contents: list[str | types.Part] = []
    for number, photo in enumerate(photos, start=1):
        contents.append(f"Photo {number}, zone: {photo.zone}")
        contents.append(types.Part.from_bytes(data=prepare_image(photo.data, max_side), mime_type="image/jpeg"))
    return contents


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
    client: genai.Client | None = None,
) -> ScanResult:
    if not photos:
        raise ValueError("A scan needs at least one photo")

    ingredients = load_ingredients()
    client = client or genai.Client()
    response = client.models.generate_content(
        model=model,
        contents=build_contents(photos, max_side),
        config=types.GenerateContentConfig(
            system_instruction=build_system_prompt(ingredients),
            response_mime_type="application/json",
            response_json_schema=ScanResult.model_json_schema(),
        ),
    )
    result = ScanResult.model_validate_json(response.text)
    return normalize_ids(result, ingredients)
