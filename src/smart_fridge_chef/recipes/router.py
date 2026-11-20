"""POST /recipes (D-009, D-012, D-013): kandydaci z SQL, wybór i tłumaczenie przez LLM, bez LLM ranking z SQL."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from smart_fridge_chef.recipes import llm
from smart_fridge_chef.recipes.chef import LLM, SELECTION_POOL, suggest
from smart_fridge_chef.recipes.schema import (
    Recipe,
    RecipeIngredient,
    RecipeRequest,
    RecipeResponse,
)
from smart_fridge_chef.recipes.search import Candidate, find_candidates, fridge_ids

DEFAULT_DB = Path(__file__).parents[3] / "data" / "recipes.sqlite"
RECIPES_DB: Path | None = None  # testy podmieniają; inaczej RECIPES_DB z .env albo DEFAULT_DB
# Klucz w .env dla dostawcy z RECIPE_MODEL; bez klucza endpoint działa jak w M2 (bez LLM)
API_KEYS = {"gemini-": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), llm.GROQ_PREFIX: ("GROQ_API_KEY",)}

router = APIRouter()


def database_path() -> Path:
    # Czytane przy zapytaniu, nie przy imporcie modułu: api.py woła load_dotenv() dopiero po importach.
    return RECIPES_DB or Path(os.getenv("RECIPES_DB") or DEFAULT_DB)


def get_llm() -> LLM | None:
    """LLM do wyboru i tłumaczenia albo None, gdy nie ma klucza. Testy podmieniają przez dependency_overrides."""
    model = llm.recipe_model()
    keys = next((names for prefix, names in API_KEYS.items() if model.startswith(prefix)), ())
    if not any(os.getenv(name) for name in keys):
        return None
    return lambda prompt, system_prompt, schema: llm.generate(prompt, system_prompt, schema, model)


def connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise HTTPException(503, "Recipe database not found; run `uv run import-recipes` first")
    # Tylko do odczytu: endpoint nigdy nie zmienia bazy.
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def describe(candidate: Candidate, missing_pl: list[str]) -> str:
    """Opis z szablonu: zostaje, gdy LLM nie działa albo jego opis nie przeszedł kontroli."""
    text = f"Masz {candidate.n_in_fridge} z {candidate.n_main} głównych składników."
    if missing_pl:
        text += f" Brakuje: {', '.join(missing_pl)}."
    return text


def build_recipe(db: sqlite3.Connection, candidate: Candidate, fridge: set[str]) -> Recipe:
    row = db.execute(
        "SELECT title, steps, ingredient_lines, servings, time_min, difficulty, kcal_per_serving, url "
        "FROM recipes WHERE id = ?",
        (candidate.recipe_id,),
    ).fetchone()
    title, steps, lines, servings, time_min, difficulty, kcal, url = row

    ingredients = []
    for ingredient_id, name_pl, is_pantry in db.execute(
        "SELECT ri.ingredient_id, i.name_pl, p.ingredient_id IS NOT NULL "
        "FROM recipe_ingredients ri JOIN ingredients i ON i.id = ri.ingredient_id "
        "LEFT JOIN pantry_staples p ON p.ingredient_id = ri.ingredient_id "
        "WHERE ri.recipe_id = ? ORDER BY ri.rowid",
        (candidate.recipe_id,),
    ):
        status = "pantry" if is_pantry else "in_fridge" if ingredient_id in fridge else "missing"
        ingredients.append(RecipeIngredient(ingredient_id=ingredient_id, name_pl=name_pl, status=status))

    missing_pl = [i.name_pl for i in ingredients if i.status == "missing"]
    return Recipe(
        id=candidate.recipe_id,
        source="database",
        title=title,
        description=describe(candidate, missing_pl),
        servings=servings,
        time_min=time_min,
        difficulty=difficulty,
        kcal_per_serving=kcal,
        ingredients=ingredients,
        ingredient_lines=json.loads(lines),
        steps=json.loads(steps),
        url=url,
    )


@router.post("/recipes")
def recipes(request: RecipeRequest, model: Annotated[LLM | None, Depends(get_llm)]) -> RecipeResponse:
    db = connect(database_path())
    try:
        candidates = find_candidates(db, request.items, request.profile)
        fridge = set(fridge_ids(request.items))
        pool = [build_recipe(db, c, fridge) for c in candidates[:SELECTION_POOL]]
        return RecipeResponse(
            recipes=suggest(db, pool, request.items, request.profile, model),
            candidates_considered=len(candidates),
        )
    finally:
        db.close()
