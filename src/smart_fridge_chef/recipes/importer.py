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
    servings INTEGER, ingredient_lines TEXT NOT NULL
);
CREATE TABLE recipe_ingredients (
    recipe_id TEXT NOT NULL REFERENCES recipes(id),
    ingredient_id TEXT NOT NULL REFERENCES ingredients(id),
    raw_text TEXT NOT NULL,
    PRIMARY KEY (recipe_id, ingredient_id)
);
CREATE TABLE pantry_staples (ingredient_id TEXT PRIMARY KEY REFERENCES ingredients(id));
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
    csv_path: Path, quantities_path: Path, db_path: Path, limit: int | None = None,
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
            for raw in raw_ingredients:
                ingredient_id = map_ingredient(raw, alias_index)
                if ingredient_id is None:
                    unmapped.append(raw.strip().lower())
                elif ingredient_id != SKIP:
                    mapped.setdefault(ingredient_id, raw)
            if unmapped or not mapped:
                report.dropped_unmapped += 1
                report.unmapped.update(unmapped)
                continue
            candidates.append((row, minutes, raw_ingredients, steps, tags, kcal, mapped))

    # 2. Karo8870: ilości i porcje, łączone po nazwie i kcal. Niejednoznaczne trafienie odrzucamy.
    quantities = load_quantities(quantities_path, {join_key(c[0]["name"], c[5]) for c in candidates})

    db = create_db(db_path, ingredients)
    for row, minutes, raw_ingredients, steps, tags, kcal, mapped in candidates:
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
        db.execute(
            "INSERT OR IGNORE INTO recipes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                json.dumps([format_line(item) for item in items], ensure_ascii=False),
            ),
        )
        db.executemany(
            "INSERT OR IGNORE INTO recipe_ingredients VALUES (?, ?, ?)",
            [(recipe_id, ingredient_id, raw) for ingredient_id, raw in mapped.items()],
        )
        report.imported += 1
        if limit and report.imported >= limit:
            break

    db.commit()
    db.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Importuje przepisy z Food.com (RAW_recipes + Karo8870) do SQLite.")
    parser.add_argument("csv", type=Path, help="ścieżka do RAW_recipes.csv, np. data/raw/RAW_recipes.csv")
    parser.add_argument("quantities", type=Path, help="ścieżka do parsed_recipes.csv (Karo8870), np. data/raw/parsed_recipes.csv")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int, default=None, help="maksymalna liczba zaimportowanych przepisów")
    args = parser.parse_args()

    report = import_recipes(args.csv, args.quantities, args.db, args.limit)
    report_path = args.db.with_suffix(".report.json")
    report_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Przeczytane: {report.read} | zaimportowane: {report.imported} ({report.imported / max(report.read, 1):.1%})")
    print(
        f"Odrzucone: {report.dropped_unmapped} (składnik spoza słownika), {report.dropped_invalid} (złe dane), "
        f"{report.dropped_no_match} (brak jednoznacznej pary w Karo8870), {report.dropped_no_quantities} (brak ilości)"
    )
    print(f"Z liczbą porcji: {report.with_servings}")
    print("Najczęstsze składniki spoza słownika:")
    for raw, count in report.unmapped.most_common(15):
        print(f"  {count:>6}  {raw}")
    print(f"\nBaza: {args.db} | raport: {report_path}")
