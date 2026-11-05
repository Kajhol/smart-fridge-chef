"""Słownik składników: wspólne ID dla lodówki i przepisów."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from smart_fridge_chef.vision.schema import Unit


class Ingredient(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name_pl: str
    name_en: str
    unit: Unit
    allergens: list[str] = []
    aliases: list[str] = []


DATA_FILE = Path(__file__).parent / "data" / "ingredients.json"


def load_ingredients(path: Path = DATA_FILE) -> dict[str, Ingredient]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    ingredients = [Ingredient.model_validate(item) for item in raw]

    by_id: dict[str, Ingredient] = {}
    alias_owner: dict[str, str] = {}
    for ingredient in ingredients:
        if ingredient.id in by_id:
            raise ValueError(f"Duplicate ingredient id: {ingredient.id}")
        by_id[ingredient.id] = ingredient

        for alias in ingredient.aliases:
            if alias in alias_owner:
                raise ValueError(f"Alias '{alias}' used by {alias_owner[alias]} and {ingredient.id}")
            alias_owner[alias] = ingredient.id
    return by_id
