"""LLM w POST /recipes (D-013): wybór 3 z kandydatów, tłumaczenie, przepis od AI przy 0 kandydatach.

LLM wybiera, opisuje i tłumaczy; kod sprawdza każdą odpowiedź (ID wśród kandydatów, alergeny, liczby w liniach).
Gdy LLM zawiedzie, odpowiedź jest taka jak w M2: ranking z SQL, tekst po angielsku, opis z szablonu.
"""

import json
import logging
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel

from smart_fridge_chef.recipes.schema import (
    FridgeItem,
    GeneratedRecipe,
    Recipe,
    RecipeIngredient,
    RecipeSelection,
    TranslatedRecipe,
    UserProfile,
)

log = logging.getLogger(__name__)

# (prompt, system_prompt, schema) -> odpowiedź zwalidowana schematem; w aplikacji to llm.generate
LLM = Callable[[str, str, type[BaseModel]], Any]

SELECTION_POOL = 20  # tylu kandydatów z czoła rankingu widzi LLM
TOP_N = 3

SELECT_SYSTEM = """You help a Polish user decide what to cook from their fridge.
You get candidate recipes that already passed a filter: they are safe for the user's allergies and diet.
Pick up to 3 recipes. Prefer recipes that use more of the fridge and miss fewer ingredients,
and pick different kinds of dishes (not three omelettes). Use only recipe IDs from the list.
For each pick write 1-2 sentences in Polish addressed to the user (\"ty\") saying why it fits their fridge.
Suggest a substitution only for an ingredient marked as missing in that recipe, and only with something
the user can safely eat. Never mention or suggest any ingredient from the forbidden list."""

TRANSLATE_SYSTEM = """You translate recipes from English into natural, simple Polish for a home cook.
Translate every step and every ingredient line, keeping the same number of entries and the same order.
Keep all numbers and fractions exactly as written. Translate units into Polish words without converting them.
Do not add, remove or change ingredients."""

GENERATE_SYSTEM = """You write one simple home recipe in Polish when no recipe from the database fits.
Use only ingredients from the allowed list (by ID); you do not have to use all of them.
Use at least two ingredients that are not pantry staples. Give realistic amounts and short steps.
Never use any ingredient from the forbidden list, even as an optional extra or garnish."""


# --- Zakazane słowa (alergeny i wykluczenia) ------------------------------


def forbidden_ids(db: sqlite3.Connection, profile: UserProfile) -> set[str]:
    """Składniki słownika z alergenem z profilu albo wykluczone przez użytkownika."""
    banned = set(profile.excluded_ingredients)
    if profile.allergens:
        banned |= {
            ingredient_id
            for ingredient_id, allergens in db.execute("SELECT id, allergens FROM ingredients")
            if set(json.loads(allergens)) & set(profile.allergens)
        }
    return banned


def word_pattern(names: list[str]) -> re.Pattern | None:
    """Wzorzec na nazwy z odmianą: „jajko” łapie „jajka”, „jajkiem”; „ser” łapie „sera”, ale nie „serwuj”."""
    stems = set()
    for name in names:
        for word in re.findall(r"[^\W\d_]+", name.lower()):
            if len(word) >= 3:
                stems.add(word[:-1] if len(word) > 3 and word[-1] in "aeiouyąęó" else word)
    if not stems:
        return None
    # krótki rdzeń dostaje krótszą końcówkę, żeby „ser” nie łapał „serwuj”
    variants = (rf"{re.escape(s)}\w{{0,{3 if len(s) > 3 else 2}}}" for s in sorted(stems, key=len, reverse=True))
    return re.compile(rf"\b(?:{'|'.join(variants)})\b", re.IGNORECASE)


class Guard:
    """Sprawdza tekst od LLM: czy nie wspomina składnika z alergenem albo wykluczonego (po polsku i angielsku)."""

    def __init__(self, db: sqlite3.Connection, profile: UserProfile):
        self.banned = forbidden_ids(db, profile)
        rows = db.execute(
            "SELECT name_pl, name_en FROM ingredients WHERE id IN (SELECT value FROM json_each(?))",
            (json.dumps(sorted(self.banned)),),
        ).fetchall()
        self.names = [name for row in rows for name in row]
        self.pattern = word_pattern(self.names)

    def ok(self, *texts: str) -> bool:
        return self.pattern is None or not any(self.pattern.search(text) for text in texts)


# --- Wybór -----------------------------------------------------------------


def fridge_text(items: list[FridgeItem]) -> str:
    return ", ".join(f"{item.label} ({item.quantity:g} {item.unit})" for item in items)


def candidate_line(recipe: Recipe) -> str:
    def names(status: str) -> str:
        return ", ".join(i.name_pl for i in recipe.ingredients if i.status == status) or "-"

    time = f"{recipe.time_min} min" if recipe.time_min else "czas nieznany"
    return (f"[{recipe.id}] {recipe.title} | {time}, {recipe.difficulty} | "
            f"z lodówki: {names('in_fridge')} | brakuje: {names('missing')}")


def selection_prompt(pool: list[Recipe], items: list[FridgeItem], guard: Guard) -> str:
    forbidden = ", ".join(sorted(set(guard.names))) or "-"
    candidates = "\n".join(candidate_line(recipe) for recipe in pool)
    return (f"Lodówka: {fridge_text(items)}\n"
            f"Zakazane składniki: {forbidden}\n\n"
            f"Kandydaci (od najlepiej dopasowanego):\n{candidates}")


def select(pool: list[Recipe], items: list[FridgeItem], guard: Guard, llm: LLM) -> list[Recipe]:
    """Wybór LLM po walidacji, uzupełniony z rankingu do 3. Błąd LLM leci wyżej (obsługuje go `suggest`)."""
    by_id = {recipe.id: recipe for recipe in pool}
    selection = llm(selection_prompt(pool, items, guard), SELECT_SYSTEM, RecipeSelection)

    chosen: list[Recipe] = []
    for pick in selection.picks:
        recipe = by_id.get(pick.recipe_id)
        if recipe is None or recipe.id in {c.id for c in chosen}:
            log.warning("LLM picked unknown or repeated recipe %s", pick.recipe_id)
            continue
        missing = {i.ingredient_id for i in recipe.ingredients if i.status == "missing"}
        substitutions = [
            s for s in pick.substitutions
            if s.missing_id in missing and guard.ok(s.suggestion)
        ]
        description = pick.description if guard.ok(pick.description) else recipe.description
        chosen.append(recipe.model_copy(update={"description": description, "substitutions": substitutions}))
        if len(chosen) == TOP_N:
            break

    for recipe in pool:  # LLM wybrał mniej niż 3 albo odpadły złe ID: dopełniamy rankingiem z SQL
        if len(chosen) == TOP_N:
            break
        if recipe.id not in {c.id for c in chosen}:
            chosen.append(recipe)
    return chosen


# --- Tłumaczenie -------------------------------------------------------------


def numbers(text: str) -> Counter:
    return Counter(re.findall(r"\d+", text))


def translation_prompt(recipe: Recipe) -> str:
    return json.dumps(
        {"title": recipe.title, "ingredient_lines": recipe.ingredient_lines, "steps": recipe.steps},
        ensure_ascii=False,
        indent=1,
    )


def translate(recipe: Recipe, llm: LLM) -> Recipe:
    """Tytuł, kroki i linie po polsku. Liczba wpisów musi się zgadzać, a w liniach składników liczby.

    Linię, w której zmieniła się liczba, zostawiamy po angielsku: ilość jest ważniejsza niż język (D-010).
    """
    try:
        translated = llm(translation_prompt(recipe), TRANSLATE_SYSTEM, TranslatedRecipe)
    except Exception:
        log.exception("Translation failed for %s", recipe.id)
        return recipe

    update: dict[str, Any] = {"title": translated.title_pl}
    if len(translated.steps_pl) == len(recipe.steps):
        update["steps"] = translated.steps_pl
    else:
        log.warning("Translation of %s changed the number of steps", recipe.id)
    if len(translated.ingredient_lines_pl) == len(recipe.ingredient_lines):
        update["ingredient_lines"] = [
            pl if numbers(pl) == numbers(en) else en
            for en, pl in zip(recipe.ingredient_lines, translated.ingredient_lines_pl, strict=True)
        ]
    else:
        log.warning("Translation of %s changed the number of ingredient lines", recipe.id)
    return recipe.model_copy(update=update)


# --- Przepis od AI -----------------------------------------------------------


def generate(
    db: sqlite3.Connection, items: list[FridgeItem], profile: UserProfile, guard: Guard, llm: LLM
) -> Recipe | None:
    """Przepis od AI z produktów z lodówki i przypraw. Odrzucony, gdy użyje składnika spoza listy albo zakazanego."""
    fridge = {item.ingredient_id for item in items if item.ingredient_id}
    pantry = {row[0] for row in db.execute("SELECT ingredient_id FROM pantry_staples")}
    rows = db.execute(
        "SELECT id, name_pl FROM ingredients WHERE id IN (SELECT value FROM json_each(?)) ORDER BY id",
        (json.dumps(sorted((fridge | pantry) - guard.banned)),),
    ).fetchall()
    allowed = dict(rows)
    if len(set(allowed) - pantry) < 2:
        return None

    listing = "\n".join(f"{i}: {name}{' (przyprawa)' if i in pantry else ''}" for i, name in allowed.items())
    limits = f"maksymalna trudność: {profile.max_difficulty}"
    if profile.max_time_min:
        limits += f", maksymalny czas: {profile.max_time_min} min"
    prompt = (f"Lodówka: {fridge_text(items)}\nDozwolone składniki (ID: nazwa):\n{listing}\n"
              f"Zakazane składniki: {', '.join(sorted(set(guard.names))) or '-'}\n"
              f"Porcje: {profile.servings}; {limits}")
    try:
        recipe = llm(prompt, GENERATE_SYSTEM, GeneratedRecipe)
    except Exception:
        log.exception("AI recipe generation failed")
        return None

    used = list(dict.fromkeys(recipe.ingredient_ids))
    texts = [recipe.title_pl, recipe.description, *recipe.ingredient_lines_pl, *recipe.steps_pl]
    rank = {"easy": 1, "medium": 2, "hard": 3}
    if (
        not set(used) <= set(allowed)
        or not guard.ok(*texts)
        or rank[recipe.difficulty] > rank[profile.max_difficulty]
        or (profile.max_time_min is not None and recipe.time_min > profile.max_time_min)
    ):
        log.warning("AI recipe rejected: ingredients %s", used)
        return None

    return Recipe(
        id=None,
        source="ai_generated",
        title=recipe.title_pl,
        description=recipe.description,
        servings=profile.servings,
        time_min=recipe.time_min,
        difficulty=recipe.difficulty,
        kcal_per_serving=None,
        ingredients=[
            RecipeIngredient(ingredient_id=i, name_pl=allowed[i], status="pantry" if i in pantry else "in_fridge")
            for i in used
        ],
        ingredient_lines=recipe.ingredient_lines_pl,
        steps=recipe.steps_pl,
        url=None,
    )


# --- Całość ------------------------------------------------------------------


def suggest(
    db: sqlite3.Connection,
    pool: list[Recipe],
    items: list[FridgeItem],
    profile: UserProfile,
    llm: LLM | None,
) -> list[Recipe]:
    """3 przepisy dla użytkownika. `pool` to czoło rankingu SQL już złożone w `Recipe` (szablon opisu, po angielsku)."""
    if llm is None:
        return pool[:TOP_N]
    guard = Guard(db, profile)
    if not pool:
        generated = generate(db, items, profile, guard, llm)
        return [generated] if generated else []
    try:
        chosen = select(pool, items, guard, llm)
    except Exception:
        log.exception("Recipe selection failed, using SQL ranking")
        chosen = pool[:TOP_N]
    with ThreadPoolExecutor(max_workers=TOP_N) as executor:
        return list(executor.map(lambda recipe: translate(recipe, llm), chosen))
