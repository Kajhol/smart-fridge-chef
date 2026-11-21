"""Import przepisów z Food.com (D-010) do SQLite.

Kroki, czas i kcal są z RAW_recipes.csv (Kaggle), ilości i porcje z parsed_recipes.csv (Karo8870, HF).
Składniki mapujemy na słownik raz, przy imporcie (D-004).
"""

import argparse
import ast
import csv
import json
import re
import sqlite3
from collections import defaultdict
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from smart_fridge_chef.dictionary import Ingredient, load_ingredients

DEFAULT_DB = Path("data/recipes.sqlite")
SOURCE = "food.com"
URL_TEMPLATE = "https://www.food.com/recipe/{id}"

# Przyprawy podstawowe (O-010): użytkownik zawsze je ma, nie liczą się do braków.
PANTRY_STAPLES = ("salt", "black_pepper", "water", "vegetable_oil", "olive_oil")

# Pozycje z Food.com, które pomijamy przy mapowaniu: nie są produktem albo są przyprawą spoza słownika.
# Przepis z taką pozycją nie odpada. Lista rozszerzana na podstawie raportu z importu.
SKIPPED_RAW = frozenset({
    "juice of", "zest of", "ice", "ice cubes", "crushed ice",
    "boiling water", "cold water", "warm water", "hot water", "ice water",
    "white pepper", "ground pepper", "pepper", "garlic salt", "seasoning salt", "celery salt",
    "ground cloves", "clove", "cloves", "ground coriander", "italian seasoning", "turmeric",
    "allspice", "ground allspice", "celery seed", "cajun seasoning", "cream of tartar",
    "dried basil", "dried parsley", "salt and black pepper", "fresh ground black pepper",
    "salt and pepper", "salt & pepper",
})

# Pominięte pozycje, które niosą alergen: przepis zostaje, ale alergen trafia do recipe_allergens.
SKIPPED_ALLERGENS = {"celery salt": ("celery",), "celery seed": ("celery",)}

# Słowa sugerujące alergen w tekście składnika. Używa ich audyt, ewaluacja i import (zamienniki niżej).
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

# Linia z zamiennikiem („vanilla or almond extract”, „(or soy milk)”, „can sub walnuts”). Mapowanie bierze
# pierwszy składnik, a użytkownik może sięgnąć po drugi, więc alergeny z całej takiej linii dopisujemy do przepisu.
ALTERNATIVE = re.compile(r"\bor\b|\(|\bsub(stitute)?\b|\binstead\b")
# Fragmenty, które pasują do KEYWORDS, a alergenu nie niosą (fałszywe alarmy z audytu). Ocet spirytusowy
# i jabłkowy traktujemy jak słownik (bez siarczynów); ocet winny łapie słowo „wine”.
NOT_ALLERGENS = re.compile(r"cream of tartar|coconut (milk|cream)|crab ?apples?|butternut|vinegar")
# „Peanut butter” to nie masło (bez mleka), ale orzeszki zostają: zamieniamy na samo „peanut”, nie wycinamy.
PEANUT_BUTTER = re.compile(r"peanut butter")


def alternative_allergens(lines: list[str]) -> set[str]:
    """Alergeny z linii składników, w których jest zamiennik. Ostrożnie: lepiej odrzucić przepis niż przepuścić alergen."""
    found = set()
    for line in lines:
        text = line.lower()
        if ALTERNATIVE.search(text):
            text = PEANUT_BUTTER.sub("peanut", text)
            text = NOT_ALLERGENS.sub(" ", text)
            found |= {allergen for allergen, pattern in KEYWORDS.items() if re.search(pattern, text)}
    return found


# Ocena przepisu to średnia ważona (bayesowska): przy kilku ocenach ciągnie do średniej całej bazy,
# żeby przepis z jedną piątką nie wygrywał z przepisem z setką ocen 4,8.
RATING_PRIOR_WEIGHT = 5

# Porcje spoza tego zakresu w Karo8870 to śmieci (np. 32767), traktujemy jak brak.
SERVINGS_RANGE = (1, 24)

MODIFIERS = re.compile(
    r"^(fresh|freshly|dried|dry|ground|chopped|minced|large|small|medium|whole|raw|frozen|canned|"
    r"unsalted|salted|lean|boneless|skinless|extra virgin|extra-virgin|light|low-fat|fat-free|cold|warm|hot|"
    r"ripe|shredded|grated|sliced|diced|crushed|plain|pure|organic|reduced-fat|lowfat|nonfat|fine|coarse|"
    r"kosher|sea|granulated|fresh ground|freshly ground) "
)

SCHEMA = """
CREATE TABLE ingredients (
    id TEXT PRIMARY KEY, name_pl TEXT NOT NULL, name_en TEXT NOT NULL,
    unit TEXT NOT NULL, allergens TEXT NOT NULL
);
CREATE TABLE recipes (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT, steps TEXT NOT NULL,
    raw_ingredients TEXT NOT NULL, time_min INTEGER, difficulty TEXT NOT NULL,
    kcal_per_serving REAL, rating REAL, source TEXT NOT NULL, url TEXT,
    servings INTEGER, ingredient_lines TEXT NOT NULL, n_ratings INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE recipe_ingredients (
    recipe_id TEXT NOT NULL REFERENCES recipes(id),
    ingredient_id TEXT NOT NULL REFERENCES ingredients(id),
    raw_text TEXT NOT NULL,
    PRIMARY KEY (recipe_id, ingredient_id)
);
CREATE TABLE pantry_staples (ingredient_id TEXT PRIMARY KEY REFERENCES ingredients(id));
CREATE TABLE recipe_allergens (
    recipe_id TEXT NOT NULL REFERENCES recipes(id),
    allergen TEXT NOT NULL,
    PRIMARY KEY (recipe_id, allergen)
);
CREATE INDEX recipe_ingredients_by_ingredient ON recipe_ingredients(ingredient_id);
"""

SKIP = "skip"


@dataclass
class ImportReport:
    read: int = 0
    imported: int = 0
    dropped_unmapped: int = 0
    dropped_invalid: int = 0
    dropped_no_match: int = 0
    dropped_no_quantities: int = 0
    with_servings: int = 0
    with_ratings: int = 0
    unmapped: Counter[str] = field(default_factory=Counter)

    def to_dict(self, top: int = 50) -> dict:
        return {
            "read": self.read,
            "imported": self.imported,
            "dropped_unmapped": self.dropped_unmapped,
            "dropped_invalid": self.dropped_invalid,
            "dropped_no_match": self.dropped_no_match,
            "dropped_no_quantities": self.dropped_no_quantities,
            "with_servings": self.with_servings,
            "with_ratings": self.with_ratings,
            "top_unmapped": self.unmapped.most_common(top),
        }


def build_alias_index(ingredients: dict[str, Ingredient]) -> dict[str, str]:
    index: dict[str, str] = {}
    for ingredient in ingredients.values():
        for name in [*ingredient.aliases, ingredient.name_en, ingredient.id.replace("_", " ")]:
            index.setdefault(name.lower(), ingredient.id)
    return index


def map_ingredient(raw: str, alias_index: dict[str, str]) -> str | None:
    """ID ze słownika, SKIP dla pozycji pomijanych albo None, gdy nie da się zmapować."""
    text = raw.strip().strip('"').lower()
    if text in alias_index:
        return alias_index[text]
    if text in SKIPPED_RAW:
        return SKIP

    for _ in range(3):
        shorter = MODIFIERS.sub("", text)
        if shorter == text:
            break
        text = shorter
        if text in alias_index:
            return alias_index[text]
        if text in SKIPPED_RAW:
            return SKIP

    for singular in (text[:-2] if text.endswith("es") else None, text[:-1] if text.endswith("s") else None):
        if singular and singular in alias_index:
            return alias_index[singular]
    return None


def skipped_allergens(raw: str) -> set[str]:
    text = raw.strip().strip('"').lower()
    return {a for name, allergens in SKIPPED_ALLERGENS.items() if name in text for a in allergens}


def difficulty(minutes: int, n_ingredients: int, n_steps: int, tags: list[str]) -> str:
    if minutes > 90 or n_steps > 15 or n_ingredients > 12:
        return "hard"
    if "easy" in tags or "beginner-cook" in tags or (minutes <= 30 and n_ingredients <= 7 and n_steps <= 8):
        return "easy"
    return "medium"


def join_key(name: str, kcal: float) -> tuple[str, float]:
    """Klucz łączenia RAW_recipes z Karo8870: nazwa bez znaków innych niż [a-z0-9] i kcal z dokładnością 0,1."""
    return re.sub(r"[^a-z0-9]+", "", name.lower()), round(kcal, 1)


def unescape(text: str) -> str:
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)


def format_line(item: dict) -> str:
    """Linia składnika do wyświetlenia, np. "1 can (5 1/2 ounce) baby corn, drained"."""
    parts = [item.get("quantity", ""), item.get("unit", "")]
    if item.get("unitQuantity"):
        parts.append(f"({item['unitQuantity']} {item.get('unitUnit', '')})".replace(" )", ")"))
    parts.append(item.get("name", ""))
    line = " ".join(" ".join(p.split()) for p in parts if p and p.strip())
    if item.get("description", "").strip():
        line += ", " + " ".join(item["description"].split())
    return unescape(line)


def has_quantities(items: list[dict], alias_index: dict[str, str]) -> bool:
    """Każda linia ma ilość, poza solą, pieprzem i innymi pozycjami, które i tak nie liczą się do braków."""
    for item in items:
        if item.get("quantity", "").strip():
            continue
        mapped = map_ingredient(unescape(item.get("name", "")), alias_index)
        if mapped != SKIP and mapped not in PANTRY_STAPLES:
            return False
    return True


def parse_servings(value: str) -> int | None:
    try:
        servings = float(value)
    except ValueError:
        return None
    low, high = SERVINGS_RANGE
    return int(servings) if low <= servings <= high and servings.is_integer() else None


def load_quantities(path: Path, keys: set[tuple[str, float]]) -> dict[tuple[str, float], list[dict]]:
    """Wiersze z Karo8870 pasujące do kluczy przepisów z RAW (trzymamy w pamięci tylko te)."""
    matches: dict[tuple[str, float], list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            try:
                key = join_key(row["name"], float(row["calories"]))
            except ValueError:
                continue
            if key in keys:
                matches[key].append({"ingredients": row["ingredients"], "servings": row["servings"]})
    return matches


def load_ratings(path: Path, recipe_ids: set[str]) -> dict[str, tuple[float, int]]:
    """Średnia bayesowska i liczba ocen z RAW_interactions.csv. Ocena 0 to recenzja bez gwiazdek, pomijamy ją."""
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    with path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            recipe_id = f"fc_{row['recipe_id']}"
            try:
                rating = float(row["rating"])
            except ValueError:
                continue
            if recipe_id in recipe_ids and 1 <= rating <= 5:
                sums[recipe_id][0] += rating
                sums[recipe_id][1] += 1
    if not sums:
        return {}
    mean = sum(total for total, _ in sums.values()) / sum(count for _, count in sums.values())
    return {
        recipe_id: (
            round((total + RATING_PRIOR_WEIGHT * mean) / (count + RATING_PRIOR_WEIGHT), 3),
            int(count),
        )
        for recipe_id, (total, count) in sums.items()
    }


def parse_list(value: str) -> list:
    parsed = ast.literal_eval(value) if value else []
    return parsed if isinstance(parsed, list) else []


def create_db(path: Path, ingredients: dict[str, Ingredient]) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.executemany(
        "INSERT INTO ingredients VALUES (?, ?, ?, ?, ?)",
        [(i.id, i.name_pl, i.name_en, i.unit, json.dumps(i.allergens)) for i in ingredients.values()],
    )
    db.executemany("INSERT INTO pantry_staples VALUES (?)", [(i,) for i in PANTRY_STAPLES if i in ingredients])
    return db


def import_recipes(
    csv_path: Path,
    quantities_path: Path,
    db_path: Path,
    limit: int | None = None,
    interactions_path: Path | None = None,
) -> ImportReport:
    ingredients = load_ingredients()
    alias_index = build_alias_index(ingredients)
    report = ImportReport()
    # Nie sys.maxsize: na Windowsie C long ma 32 bity i field_size_limit rzuca OverflowError.
    csv.field_size_limit(2**31 - 1)

    # 1. RAW_recipes: przepisy, których wszystkie składniki są w słowniku.
    candidates = []
    with csv_path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            report.read += 1
            try:
                minutes = int(row["minutes"])
                raw_ingredients = [str(x) for x in parse_list(row["ingredients"])]
                steps = [str(x) for x in parse_list(row["steps"])]
                tags = [str(x) for x in parse_list(row.get("tags", ""))]
                nutrition = parse_list(row.get("nutrition", ""))
                kcal = float(nutrition[0])
            except (ValueError, SyntaxError, IndexError):
                report.dropped_invalid += 1
                continue
            if not row["name"].strip() or not raw_ingredients or not steps or not 0 <= minutes <= 24 * 60:
                report.dropped_invalid += 1
                continue

            mapped: dict[str, str] = {}
            unmapped = []
            allergens: set[str] = set()
            for raw in raw_ingredients:
                ingredient_id = map_ingredient(raw, alias_index)
                if ingredient_id is None:
                    unmapped.append(raw.strip().lower())
                elif ingredient_id == SKIP:
                    allergens |= skipped_allergens(raw)
                else:
                    mapped.setdefault(ingredient_id, raw)
                    allergens.update(ingredients[ingredient_id].allergens)
            if unmapped or not mapped:
                report.dropped_unmapped += 1
                report.unmapped.update(unmapped)
                continue
            candidates.append((row, minutes, raw_ingredients, steps, tags, kcal, mapped, allergens))

    # 2. Karo8870: ilości i porcje, łączone po nazwie i kcal. Niejednoznaczne trafienie odrzucamy.
    quantities = load_quantities(quantities_path, {join_key(c[0]["name"], c[5]) for c in candidates})

    db = create_db(db_path, ingredients)
    for row, minutes, raw_ingredients, steps, tags, kcal, mapped, allergens in candidates:
        matches = quantities.get(join_key(row["name"], kcal), [])
        if len(matches) != 1:
            report.dropped_no_match += 1
            continue
        items = json.loads(matches[0]["ingredients"])
        if not items or not has_quantities(items, alias_index):
            report.dropped_no_quantities += 1
            continue
        servings = parse_servings(matches[0]["servings"])
        report.with_servings += servings is not None

        recipe_id = f"fc_{row['id']}"
        lines = [format_line(item) for item in items]
        allergens = allergens | alternative_allergens(lines)
        db.execute(
            "INSERT OR IGNORE INTO recipes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                recipe_id,
                row["name"].strip(),
                (row.get("description") or "").strip() or None,
                json.dumps(steps, ensure_ascii=False),
                json.dumps(raw_ingredients, ensure_ascii=False),
                minutes or None,
                difficulty(minutes, len(raw_ingredients), len(steps), tags),
                kcal,
                None,
                SOURCE,
                URL_TEMPLATE.format(id=row["id"]),
                servings,
                json.dumps(lines, ensure_ascii=False),
            ),
        )
        db.executemany(
            "INSERT OR IGNORE INTO recipe_ingredients VALUES (?, ?, ?)",
            [(recipe_id, ingredient_id, raw) for ingredient_id, raw in mapped.items()],
        )
        db.executemany(
            "INSERT OR IGNORE INTO recipe_allergens VALUES (?, ?)", [(recipe_id, a) for a in sorted(allergens)],
        )
        report.imported += 1
        if limit and report.imported >= limit:
            break

    # 3. Oceny z RAW_interactions (opcjonalnie): do rankingu w wyszukiwaniu.
    if interactions_path:
        recipe_ids = {row[0] for row in db.execute("SELECT id FROM recipes")}
        ratings = load_ratings(interactions_path, recipe_ids)
        db.executemany(
            "UPDATE recipes SET rating = ?, n_ratings = ? WHERE id = ?",
            [(rating, count, recipe_id) for recipe_id, (rating, count) in ratings.items()],
        )
        report.with_ratings = len(ratings)

    db.commit()
    db.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Importuje przepisy z Food.com (RAW_recipes + Karo8870) do SQLite.")
    parser.add_argument("csv", type=Path, help="ścieżka do RAW_recipes.csv, np. data/raw/RAW_recipes.csv")
    parser.add_argument("quantities", type=Path, help="ścieżka do parsed_recipes.csv (Karo8870), np. data/raw/parsed_recipes.csv")
    parser.add_argument(
        "--interactions", type=Path, default=None,
        help="ścieżka do RAW_interactions.csv (oceny do rankingu), np. data/raw/RAW_interactions.csv",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int, default=None, help="maksymalna liczba zaimportowanych przepisów")
    args = parser.parse_args()

    report = import_recipes(args.csv, args.quantities, args.db, args.limit, args.interactions)
    report_path = args.db.with_suffix(".report.json")
    report_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Przeczytane: {report.read} | zaimportowane: {report.imported} ({report.imported / max(report.read, 1):.1%})")
    print(
        f"Odrzucone: {report.dropped_unmapped} (składnik spoza słownika), {report.dropped_invalid} (złe dane), "
        f"{report.dropped_no_match} (brak jednoznacznej pary w Karo8870), {report.dropped_no_quantities} (brak ilości)"
    )
    print(f"Z liczbą porcji: {report.with_servings} | z ocenami: {report.with_ratings}")
    print("Najczęstsze składniki spoza słownika:")
    for raw, count in report.unmapped.most_common(15):
        print(f"  {count:>6}  {raw}")
    print(f"\nBaza: {args.db} | raport: {report_path}")
