"""Pytania doprecyzowujące i lista zakupów (M5, D-015). Wszystko liczy kod, bez LLM.

Pytanie wskazuje produkt, którego brakuje przepisom tuż za progiem filtra (D-004): jeden brak za dużo
albo jeden produkt z lodówki za mało. Gdy użytkownik go ma (np. skan go nie zobaczył), te przepisy wchodzą.
"""

import json
import sqlite3
from collections import Counter

from smart_fridge_chef.recipes.schema import (
    FridgeItem,
    Question,
    Recipe,
    ShoppingItem,
    UserProfile,
)
from smart_fridge_chef.recipes.search import (
    MAX_MISSING,
    MIN_IN_FRIDGE,
    find_candidates,
    fridge_ids,
)

MAX_QUESTIONS = 3


def unlocking_counts(db: sqlite3.Connection, items: list[FridgeItem], profile: UserProfile) -> Counter[str]:
    """Dla każdego brakującego produktu: ile przepisów przeszłoby filtr, gdyby był w lodówce."""
    near = find_candidates(db, items, profile, max_missing=MAX_MISSING + 1, min_in_fridge=max(MIN_IN_FRIDGE - 1, 0))
    # Przepis, który dziś odpada, a z jednym produktem więcej przechodzi (ten sam filtr alergenów i wykluczeń).
    blocked = [
        c.recipe_id for c in near
        if not (c.n_missing <= MAX_MISSING and c.n_in_fridge >= MIN_IN_FRIDGE)
        and c.n_missing - 1 <= MAX_MISSING and c.n_in_fridge + 1 >= MIN_IN_FRIDGE
    ]
    rows = db.execute(
        "SELECT ri.ingredient_id FROM recipe_ingredients ri "
        "LEFT JOIN pantry_staples p ON p.ingredient_id = ri.ingredient_id "
        "WHERE p.ingredient_id IS NULL AND ri.recipe_id IN (SELECT value FROM json_each(?)) "
        "AND ri.ingredient_id NOT IN (SELECT value FROM json_each(?))",
        (json.dumps(blocked), json.dumps(fridge_ids(items))),
    )
    return Counter(row[0] for row in rows)


def find_questions(db: sqlite3.Connection, items: list[FridgeItem], profile: UserProfile) -> list[Question]:
    """Do 3 produktów, które odblokowują najwięcej przepisów. Pusta lista, gdy żaden nic nie zmienia."""
    best = sorted(unlocking_counts(db, items, profile).items(), key=lambda x: (-x[1], x[0]))[:MAX_QUESTIONS]
    names = dict(db.execute(
        "SELECT id, name_pl FROM ingredients WHERE id IN (SELECT value FROM json_each(?))",
        (json.dumps([ingredient_id for ingredient_id, _ in best]),),
    ))
    return [Question(ingredient_id=i, name_pl=names[i], unlocks=n) for i, n in best]


def shopping_list(recipes: list[Recipe]) -> list[ShoppingItem]:
    """Braki ze zwróconych przepisów, każdy raz, w kolejności przepisów."""
    items: dict[str, ShoppingItem] = {}
    for recipe in recipes:
        for ingredient in recipe.ingredients:
            if ingredient.status == "missing":
                item = items.setdefault(
                    ingredient.ingredient_id,
                    ShoppingItem(ingredient_id=ingredient.ingredient_id, name_pl=ingredient.name_pl, for_recipes=[]),
                )
                if recipe.title not in item.for_recipes:
                    item.for_recipes.append(recipe.title)
    return list(items.values())
