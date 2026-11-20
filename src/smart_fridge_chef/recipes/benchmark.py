"""Ewaluacja części przepisowej (M4, O-012): bezpieczeństwo alergenów, czas, koszt, jakość tłumaczenia.

`uv run eval-recipes` puszcza tę samą logikę co `POST /recipes` (`router.recommend`) dla każdej pary
skan × profil i zapisuje wyniki do `data/eval/` (poza gitem: są tam teksty przepisów z Food.com, D-010).
Do `docs/wyniki.md` przepisujemy tylko liczby z podsumowania.
"""

import argparse
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from smart_fridge_chef.recipes import llm
from smart_fridge_chef.recipes.audit import KEYWORDS
from smart_fridge_chef.recipes.chef import Guard, translate
from smart_fridge_chef.recipes.router import database_path, recommend
from smart_fridge_chef.recipes.schema import (
    FridgeItem,
    Recipe,
    RecipeRequest,
    UserProfile,
)

ROOT = Path(__file__).parents[3]
SCANS_DIR = ROOT / "data" / "scans"
OUT_DIR = ROOT / "data" / "eval"

MEAT_AND_FISH = [
    "bacon", "ham", "ground_beef", "chicken_breast", "chicken", "shrimp", "chicken_broth", "beef_broth",
    "worcestershire_sauce",  # zawiera anchois
]

# O-012: profile testowe. Klucz to nazwa w raporcie.
PROFILES = {
    "bez_ograniczen": UserProfile(),
    "jajka_mleko": UserProfile(allergens=["eggs", "milk"]),
    "gluten_orzechy": UserProfile(allergens=["gluten", "nuts", "peanuts"]),
    "wege": UserProfile(allergens=["fish", "crustaceans"], excluded_ingredients=MEAT_AND_FISH),
    "szybko_seler_gorczyca": UserProfile(
        allergens=["celery", "mustard", "sesame", "soy"], max_difficulty="easy", max_time_min=30
    ),
}


@dataclass
class Calls:
    """Opakowanie LLM do ewaluacji: liczy wywołania, błędy i tokeny."""

    model: str
    client: Any = None
    usage: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    calls: int = 0

    def __call__(self, prompt: str, system_prompt: str, schema: type) -> Any:
        self.calls += 1
        try:
            return llm.generate(prompt, system_prompt, schema, self.model, self.client, self.usage)
        except Exception as error:
            self.errors.append(f"{schema.__name__}: {type(error).__name__}: {error}"[:300])
            raise

    def take(self) -> dict:
        """Stan od ostatniego `take` i wyzerowanie liczników."""
        state = {
            "calls": self.calls,
            "errors": self.errors,
            "input_tokens": sum(u["input_tokens"] for u in self.usage),
            "output_tokens": sum(u["output_tokens"] for u in self.usage),
        }
        self.usage, self.errors, self.calls = [], [], 0
        return state


# --- Bezpieczeństwo ----------------------------------------------------------


def violations(db: sqlite3.Connection, recipe: Recipe, profile: UserProfile, guard: Guard) -> list[str]:
    """Twarda bramka: alergen albo wykluczony składnik w zwróconym przepisie. Musi być pusta."""
    found = []
    ids = [i.ingredient_id for i in recipe.ingredients]
    excluded = set(ids) & set(profile.excluded_ingredients)
    if excluded:
        found.append(f"wykluczone: {sorted(excluded)}")
    if recipe.source == "database":
        rows = db.execute("SELECT allergen FROM recipe_allergens WHERE recipe_id = ?", (recipe.id,))
        allergens = {row[0] for row in rows}
    else:
        rows = db.execute(
            "SELECT allergens FROM ingredients WHERE id IN (SELECT value FROM json_each(?))", (json.dumps(ids),)
        )
        allergens = {a for row in rows for a in json.loads(row[0])}
        texts = [recipe.title, recipe.description, *recipe.ingredient_lines, *recipe.steps]
        if not guard.ok(*texts):
            found.append("tekst przepisu AI wspomina zakazany składnik")
    hit = allergens & set(profile.allergens)
    if hit:
        found.append(f"alergeny: {sorted(hit)}")
    for substitution in recipe.substitutions:
        if not guard.ok(substitution.suggestion):
            found.append(f"zamiennik: {substitution.suggestion}")
    return found


def suspects(db: sqlite3.Connection, recipe: Recipe, profile: UserProfile) -> list[str]:
    """Miękki sygnał do przejrzenia przez człowieka: oryginalne linie z Food.com ze słowem sugerującym alergen.

    Niezależne od mapowania na słownik, ale z fałszywymi alarmami (np. „peanut butter” przy mleku), jak w audycie.
    """
    if recipe.source != "database":
        return []
    raw, lines = db.execute("SELECT raw_ingredients, ingredient_lines FROM recipes WHERE id = ?", (recipe.id,)).fetchone()
    texts = [t.lower() for t in json.loads(raw) + json.loads(lines)]
    return sorted({
        f"{allergen}: {text}"
        for allergen in profile.allergens
        for text in texts
        if re.search(KEYWORDS[allergen], text)
    })


# --- Tłumaczenie -------------------------------------------------------------


def original(db: sqlite3.Connection, recipe: Recipe) -> Recipe:
    title, steps, lines = db.execute(
        "SELECT title, steps, ingredient_lines FROM recipes WHERE id = ?", (recipe.id,)
    ).fetchone()
    return recipe.model_copy(update={"title": title, "steps": json.loads(steps), "ingredient_lines": json.loads(lines)})


def untranslated(source: Recipe, translated: Recipe) -> int:
    """Ile wpisów zostało po angielsku (tłumaczenie odrzucone przez kontrolę liczb albo liczby wpisów)."""
    pairs = list(zip(source.steps, translated.steps)) + list(zip(source.ingredient_lines, translated.ingredient_lines))
    return sum(a == b for a, b in pairs) + (source.title == translated.title)


def entries(recipe: Recipe) -> int:
    return len(recipe.steps) + len(recipe.ingredient_lines) + 1


# --- Przebieg ----------------------------------------------------------------


def load_scan(path: Path) -> tuple[str, list[FridgeItem]]:
    """Skan po ekranie korekty: ground_truth.json (D-003) albo dowolny JSON z polem `items`."""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [
        FridgeItem(**{key: item[key] for key in ("ingredient_id", "label", "quantity", "unit")})
        for item in data["items"]
        if item.get("quantity", 0) > 0
    ]
    return data.get("scan_id", path.parent.name), items


def run(
    db: sqlite3.Connection,
    scans: list[tuple[str, list[FridgeItem]]],
    profiles: dict[str, UserProfile],
    main: Calls,
    baseline: Calls | None = None,
    repeats: int = 1,
) -> dict:
    rows, translations = [], []
    seen: set[str] = set()
    for scan_id, items in scans:
        for name, profile in profiles.items():
            guard = Guard(db, profile)
            for attempt in range(repeats):
                main.take()
                start = time.perf_counter()
                response = recommend(db, RecipeRequest(items=items, profile=profile), main)
                seconds = time.perf_counter() - start
                usage = main.take()
                recipes = []
                for recipe in response.recipes:
                    entry = {
                        "id": recipe.id,
                        "source": recipe.source,
                        "title": recipe.title,
                        "violations": violations(db, recipe, profile, guard),
                        "suspects": suspects(db, recipe, profile),
                    }
                    if recipe.source == "database":
                        source = original(db, recipe)
                        entry["untranslated"] = untranslated(source, recipe)
                        entry["entries"] = entries(source)
                        if baseline is not None and recipe.id not in seen:
                            seen.add(recipe.id)
                            translations.append(compare(source, recipe, baseline))
                    recipes.append(entry)
                rows.append({
                    "scan": scan_id, "profile": name, "attempt": attempt + 1, "seconds": round(seconds, 2),
                    "candidates": response.candidates_considered, "recipes": recipes, **usage,
                })
    return {"rows": rows, "translations": translations}


def compare(source: Recipe, translated: Recipe, baseline: Calls) -> dict:
    baseline.take()
    start = time.perf_counter()
    other = translate(source, baseline)
    seconds = time.perf_counter() - start
    usage = baseline.take()
    return {
        "id": source.id,
        "original": {"title": source.title, "ingredient_lines": source.ingredient_lines, "steps": source.steps},
        "main": {"title": translated.title, "ingredient_lines": translated.ingredient_lines, "steps": translated.steps},
        "baseline": {"title": other.title, "ingredient_lines": other.ingredient_lines, "steps": other.steps},
        "baseline_untranslated": untranslated(source, other),
        "baseline_seconds": round(seconds, 2),
        "baseline_errors": usage["errors"],
        "entries": entries(source),
    }


# --- Podsumowanie ------------------------------------------------------------


def cost(input_tokens: int, output_tokens: int, prices: tuple[float, float] | None) -> float | None:
    """Koszt w USD przy cenach za 1 mln tokenów (wejście, wyjście). Ceny podaje się z cennika dostawcy."""
    if prices is None:
        return None
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))] if ordered else 0.0


def summarize(result: dict, prices: tuple[float, float] | None = None) -> dict:
    rows = result["rows"]
    recipes = [r for row in rows for r in row["recipes"]]
    seconds = [row["seconds"] for row in rows]
    database = [r for r in recipes if r["source"] == "database"]
    n = max(len(rows), 1)
    input_tokens = sum(row["input_tokens"] for row in rows)
    output_tokens = sum(row["output_tokens"] for row in rows)
    per_request = cost(input_tokens / n, output_tokens / n, prices)
    summary = {
        "requests": len(rows),
        "recipes": len(recipes),
        "ai_generated": sum(r["source"] == "ai_generated" for r in recipes),
        "empty_responses": sum(not row["recipes"] for row in rows),
        "violations": sum(len(r["violations"]) for r in recipes),
        "recipes_with_suspects": sum(bool(r["suspects"]) for r in recipes),
        "seconds_median": round(percentile(seconds, 0.5), 2),
        "seconds_p90": round(percentile(seconds, 0.9), 2),
        "llm_calls_per_request": round(sum(row["calls"] for row in rows) / n, 1),
        "requests_with_llm_errors": sum(bool(row["errors"]) for row in rows),
        "input_tokens_per_request": round(input_tokens / n),
        "output_tokens_per_request": round(output_tokens / n),
        "usd_per_request": None if per_request is None else round(per_request, 5),
        "untranslated_share": round(
            sum(r["untranslated"] for r in database) / max(sum(r["entries"] for r in database), 1), 3
        ),
    }
    if result["translations"]:
        t = result["translations"]
        summary["baseline_untranslated_share"] = round(
            sum(x["baseline_untranslated"] for x in t) / max(sum(x["entries"] for x in t), 1), 3
        )
        summary["baseline_seconds_median"] = round(percentile([x["baseline_seconds"] for x in t], 0.5), 2)
    return summary


def per_profile(result: dict) -> list[str]:
    """Tabela markdown: profil, kandydaci, przepisy, naruszenia, czas (do wklejenia w wyniki.md)."""
    lines = ["| Skan | Profil | Kandydaci | Przepisy (AI) | Naruszenia | Podejrzane | Czas [s] |", "|---|---|---|---|---|---|---|"]
    for row in result["rows"]:
        recipes = row["recipes"]
        ai = sum(r["source"] == "ai_generated" for r in recipes)
        lines.append(
            f"| {row['scan']} | {row['profile']} | {row['candidates']} | {len(recipes)} ({ai}) | "
            f"{sum(len(r['violations']) for r in recipes)} | {sum(bool(r['suspects']) for r in recipes)} | "
            f"{row['seconds']} |"
        )
    return lines


def rating_sheet(translations: list[dict], main_model: str, baseline_model: str) -> str:
    """Arkusz do ślepej oceny 1–5 przez zespół: wersja A i B bez nazw modeli, klucz na końcu."""
    parts = [
        "# Ocena tłumaczeń przepisów (M4)\n",
        (
            "Oceń każdą wersję od 1 (niezrozumiałe, błędy w ilościach) do 5 (naturalny polski, ilości bez zmian). "
            "Kolejność A/B jest losowana dla każdego przepisu, modele są w kluczu na końcu. Wpisz ocenę w `[ ]`.\n"
        ),
    ]
    key = []
    for number, t in enumerate(translations, 1):
        flip = hash(t["id"]) % 2 == 1  # stały dla przebiegu, różny między przepisami
        a, b = (t["baseline"], t["main"]) if flip else (t["main"], t["baseline"])
        key.append(f"{number}. {t['id']}: A = {baseline_model if flip else main_model}, "
                   f"B = {main_model if flip else baseline_model}")
        parts.append(f"## {number}. {t['original']['title']}\n")
        for label, version in (("A", a), ("B", b)):
            parts.append(f"### Wersja {label}: {version['title']}  ocena: [ ]\n")
            parts.extend(f"- {line}" for line in version["ingredient_lines"])
            parts.append("")
            parts.extend(f"{i}. {step}" for i, step in enumerate(version["steps"], 1))
            parts.append("")
    parts.append("## Klucz\n")
    parts.extend(key)
    return "\n".join(parts) + "\n"


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Ewaluacja POST /recipes na skanach i profilach testowych (M4).")
    parser.add_argument("scans", nargs="*", type=Path, help="ground_truth.json albo folder skanu; domyślnie wszystkie")
    parser.add_argument("--db", type=Path, default=None, help="baza przepisów; domyślnie RECIPES_DB albo data/")
    parser.add_argument("--model", default=llm.recipe_model())
    parser.add_argument("--baseline", default=None, help="drugi model do porównania tłumaczeń, np. groq/openai/gpt-oss-120b")
    parser.add_argument("--profiles", nargs="*", default=list(PROFILES), choices=list(PROFILES))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--price", type=float, nargs=2, metavar=("IN", "OUT"), help="USD za 1 mln tokenów")
    args = parser.parse_args()

    paths = [p / "ground_truth.json" if p.is_dir() else p for p in args.scans] or sorted(
        SCANS_DIR.glob("*/ground_truth.json")
    )
    db = sqlite3.connect(f"{(args.db or database_path()).resolve().as_uri()}?mode=ro", uri=True)
    main_calls = Calls(args.model)
    baseline = Calls(args.baseline) if args.baseline else None
    result = run(db, [load_scan(p) for p in paths], {p: PROFILES[p] for p in args.profiles}, main_calls, baseline,
                 args.repeats)
    db.close()

    summary = summarize(result, tuple(args.price) if args.price else None)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"recipes_{args.model.replace('/', '_')}_{stamp}.json"
    out.write_text(json.dumps({"model": args.model, "baseline": args.baseline, "summary": summary, **result},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(per_profile(result)))
    print(json.dumps(summary, indent=1))
    print(f"Wyniki: {out}")
    if baseline is not None:
        sheet = OUT_DIR / f"translations_{stamp}.md"
        sheet.write_text(rating_sheet(result["translations"], args.model, args.baseline), encoding="utf-8")
        print(f"Arkusz do oceny tłumaczeń: {sheet}")
    if summary["violations"]:
        raise SystemExit(f"BRAMKA NIE PRZESZŁA: {summary['violations']} naruszeń alergenów/wykluczeń")
