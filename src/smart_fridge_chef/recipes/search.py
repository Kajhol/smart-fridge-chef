"""Wyszukiwanie kandydatów (D-004): filtr i ranking w SQL, bez LLM. LLM w M3 wybiera spośród wyników."""

import json
import sqlite3
from dataclasses import dataclass

from smart_fridge_chef.recipes.schema import FridgeItem, UserProfile

MAX_MISSING = 2  # ile składników (poza przyprawami) może brakować, D-004
MIN_MAIN_INGREDIENTS = 3  # przepisy z 1–2 składnikami (jajko na twardo, „microwave cleaner”) to nie danie
MIN_IN_FRIDGE = 2  # przepis ma korzystać z lodówki, a nie tylko z przypraw
DIFFICULTY_RANK = {"easy": 1, "medium": 2, "hard": 3}
# Ranking: każdy produkt z lodówki +1, każdy brak -1,5. Przepis na 5 produktów z lodówki i 1 brak (3,5)
# wygrywa z 3 produktami bez braków (3), ale 2 braki przy 5 produktach (2) już przegrywają.
MISSING_PENALTY = 1.5

QUERY = """
WITH fridge(ingredient_id) AS (SELECT value FROM json_each(:fridge)),
stats AS (
    SELECT
        ri.recipe_id,
        SUM(p.ingredient_id IS NULL AND f.ingredient_id IS NOT NULL) AS n_in_fridge,
        SUM(p.ingredient_id IS NULL AND f.ingredient_id IS NULL) AS n_missing,
        SUM(p.ingredient_id IS NULL) AS n_main
    FROM recipe_ingredients ri
    LEFT JOIN pantry_staples p ON p.ingredient_id = ri.ingredient_id
    LEFT JOIN fridge f ON f.ingredient_id = ri.ingredient_id
    GROUP BY ri.recipe_id
)
SELECT r.id, s.n_in_fridge, s.n_missing, s.n_main
FROM recipes r JOIN stats s ON s.recipe_id = r.id
WHERE s.n_missing <= :max_missing
  AND s.n_in_fridge >= :min_in_fridge
  AND s.n_main >= :min_main
  AND (CASE r.difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END) <= :max_difficulty
  AND (:max_time IS NULL OR r.time_min IS NULL OR r.time_min <= :max_time)
  AND NOT EXISTS (
      SELECT 1 FROM recipe_allergens ra
      WHERE ra.recipe_id = r.id AND ra.allergen IN (SELECT value FROM json_each(:allergens))
  )
  AND NOT EXISTS (
      SELECT 1 FROM recipe_ingredients ri
      WHERE ri.recipe_id = r.id AND ri.ingredient_id IN (SELECT value FROM json_each(:excluded))
  )
ORDER BY s.n_in_fridge - :missing_penalty * s.n_missing DESC, s.n_missing ASC,
         COALESCE(r.rating, 0) DESC, r.n_ratings DESC, r.id
"""


@dataclass
class Candidate:
    recipe_id: str
    n_in_fridge: int
    n_missing: int
    n_main: int


def fridge_ids(items: list[FridgeItem]) -> list[str]:
    """ID z lodówki. Pozycje bez ID i dodane z aplikacji (custom_…, D-011) nie pasują do żadnego przepisu."""
    return sorted({item.ingredient_id for item in items if item.ingredient_id})


def find_candidates(
    db: sqlite3.Connection,
    items: list[FridgeItem],
    profile: UserProfile,
    max_missing: int = MAX_MISSING,
    min_in_fridge: int = MIN_IN_FRIDGE,
) -> list[Candidate]:
    """Wszystkie przepisy, które przechodzą filtr, od najlepszego. Pusta lista to normalny wynik, nie błąd.

    Luźniejsze progi (`max_missing`, `min_in_fridge`) bierze tylko szukanie pytań doprecyzowujących (D-015).
    """
    rows = db.execute(
        QUERY,
        {
            "fridge": json.dumps(fridge_ids(items)),
            "allergens": json.dumps(profile.allergens),
            "excluded": json.dumps(profile.excluded_ingredients),
            "max_missing": max_missing,
            "min_in_fridge": min_in_fridge,
            "min_main": MIN_MAIN_INGREDIENTS,
            "max_difficulty": DIFFICULTY_RANK[profile.max_difficulty],
            "max_time": profile.max_time_min,
            "missing_penalty": MISSING_PENALTY,
        },
    ).fetchall()
    return [Candidate(*row) for row in rows]
