"""Audyt alergenów w bazie przepisów: szuka w tekście składników słów, które sugerują alergen spoza recipe_allergens.

Słowa kluczowe dają fałszywe alarmy (np. „peanut butter” przy mleku), więc wynik czyta człowiek.
"""

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from smart_fridge_chef.recipes.importer import DEFAULT_DB

KEYWORDS = {
    "gluten": r"\b(flour|wheat|bread|breadcrumbs?|pasta|noodles?|spaghetti|macaroni|barley|rye|oats?|couscous|bulgur|"
    r"semolina|crackers?|cookies?|tortillas?|pita|croutons|beer|soy sauce|worcestershire|malt)\b",
    "milk": r"\b(milk|cream|cheese|butter|yogurt|ghee|whey|buttermilk|parmesan|mozzarella|cheddar|ricotta|chocolate)\b",
    "eggs": r"\b(eggs?|mayonnaise|mayo|meringue)\b",
    "nuts": r"\b(almonds?|walnuts?|pecans?|hazelnuts?|cashews?|pistachios?|macadamia|nuts?|marzipan)\b",
    "peanuts": r"\bpeanuts?\b",
    "soy": r"\b(soy|soya|tofu|miso|edamame|tempeh|teriyaki)\b",
    "sesame": r"\b(sesame|tahini)\b",
    "mustard": r"\b(mustard|dijon)\b",
    "celery": r"\b(celery|celeriac)\b",
    "fish": r"\b(fish|anchov(y|ies)|salmon|tuna|cod|tilapia|sardines?|worcestershire)\b",
    "crustaceans": r"\b(shrimps?|prawns?|crabs?|lobsters?|crayfish)\b",
    "sulphites": r"\b(wine|sherry|vinegar|dried apricots?|raisins)\b",
}


def audit(db_path: Path) -> dict[str, Counter[str]]:
    """Dla każdego alergenu: linie składników, które go sugerują w przepisach, gdzie recipe_allergens go nie ma."""
    db = sqlite3.connect(db_path)
    allergens: dict[str, set[str]] = defaultdict(set)
    for recipe_id, allergen in db.execute("SELECT recipe_id, allergen FROM recipe_allergens"):
        allergens[recipe_id].add(allergen)

    suspects: dict[str, Counter[str]] = defaultdict(Counter)
    for recipe_id, raw, lines in db.execute("SELECT id, raw_ingredients, ingredient_lines FROM recipes"):
        for text in json.loads(raw) + json.loads(lines):
            for allergen, pattern in KEYWORDS.items():
                if allergen not in allergens[recipe_id] and re.search(pattern, text.lower()):
                    suspects[allergen][text.lower()] += 1
    db.close()
    return suspects


def main() -> None:
    parser = argparse.ArgumentParser(description="Audyt alergenów w bazie przepisów.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    for allergen, texts in sorted(audit(args.db).items(), key=lambda x: -x[1].total()):
        print(f"\n{allergen}: {texts.total()} podejrzanych linii")
        for text, count in texts.most_common(args.top):
            print(f"  {count:>5}  {text}")
