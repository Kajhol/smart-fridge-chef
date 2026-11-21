"""Porównanie modeli na tej samej ewaluacji (M5.5): `uv run eval-clash`.

Każdy model przechodzi ten sam zestaw skan × profil co `eval-recipes`, z tym samym budżetem czasu na zapytanie.
Modele w chmurze (Gemini, Groq) idą zawsze. Lokalne (`ollama/...`) tylko wtedy, gdy jest karta NVIDIA
(`nvidia-smi`) i działa Ollama z pobranym modelem: na samym CPU czasy nie są porównywalne, więc trzeba
to wymusić `--allow-cpu`. Wynik to same liczby (bez tekstów z Food.com), można go wysłać dalej.
"""

import argparse
import json
import platform
import shutil
import sqlite3
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from smart_fridge_chef.recipes import llm
from smart_fridge_chef.recipes.benchmark import (
    OUT_DIR,
    PROFILES,
    ROOT,
    SCANS_DIR,
    Calls,
    load_scan,
    run,
    secrets,
    shareable_rows,
    summarize,
)
from smart_fridge_chef.recipes.router import database_path

DEFAULT_MODELS = ["gemini-3.1-flash-lite", "groq/openai/gpt-oss-120b"]
# USD za 1 mln tokenów (wejście, wyjście). Inne modele: --price MODEL IN OUT. Lokalne kosztują 0.
PRICES = {"gemini-3.1-flash-lite": (0.25, 1.50)}
# W WSL nvidia-smi leży poza PATH
NVIDIA_SMI = ("nvidia-smi", "/usr/lib/wsl/lib/nvidia-smi")


def detect_gpu(runner=subprocess.run) -> dict | None:
    """Pierwsza karta NVIDIA z `nvidia-smi` (nazwa i VRAM w MB) albo None, gdy karty albo sterownika nie ma."""
    for command in NVIDIA_SMI:
        path = shutil.which(command) or (command if Path(command).exists() else None)
        if path is None:
            continue
        try:
            out = runner([path, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        line = out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else ""
        if "," in line:
            name, memory = (part.strip() for part in line.split(",", 1))
            return {"name": name, "vram_mb": int(float(memory)) if memory.replace(".", "").isdigit() else None}
    return None


def ollama_models(base_url: str | None = None) -> set[str] | None:
    """Modele pobrane do Ollamy (np. `qwen2.5:7b`) albo None, gdy Ollama nie odpowiada."""
    url = (base_url or llm.ollama_base_url()).rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return {m["id"] for m in json.load(response).get("data", [])}
    except (OSError, ValueError):
        return None


def local_skip_reason(model: str, gpu: dict | None, available: set[str] | None, allow_cpu: bool) -> str | None:
    """Dlaczego lokalnego modelu nie puszczamy; None = można puszczać."""
    if not llm.local(model):
        return f"{model} nie jest modelem lokalnym (oczekiwano ollama/<model>)"
    if gpu is None and not allow_cpu:
        return "brak karty NVIDIA (nvidia-smi); na CPU czasy są nieporównywalne, wymuś --allow-cpu"
    if available is None:
        return f"Ollama nie odpowiada pod {llm.ollama_base_url()}; uruchom `ollama serve`"
    name = model.split("/", 1)[1]
    if name not in available and f"{name}:latest" not in available:
        return f"modelu nie ma w Ollamie; pobierz: `ollama pull {name}`"
    return None


class Ping(BaseModel):
    ok: bool


def warm_up(model: str) -> None:
    """Pierwsze wywołanie ładuje model do VRAM; nie chcemy, żeby wliczało się do czasów."""
    try:
        llm.generate('Return {"ok": true}.', "Answer with JSON only.", Ping, model)
    except Exception as error:  # noqa: BLE001  (rozgrzewka: błąd i tak wyjdzie w ewaluacji)
        print(f"Rozgrzewka {model} nie wyszła: {type(error).__name__}")


COLUMNS = [
    ("Model", lambda m, s: m),
    ("Zapytania", lambda m, s: s["requests"]),
    ("Naruszenia", lambda m, s: s["violations"]),
    ("Podejrzane", lambda m, s: s["recipes_with_suspects"]),
    ("Z błędem LLM", lambda m, s: s["requests_with_llm_errors"]),
    ("Timeouty", lambda m, s: s["llm_timeouts"]),
    ("Mediana [s]", lambda m, s: s["seconds_median"]),
    ("p90 [s]", lambda m, s: s["seconds_p90"]),
    ("USD/zapytanie", lambda m, s: "–" if s["usd_per_request"] is None else s["usd_per_request"]),
    ("Nieprzetłumaczone", lambda m, s: f"{s['untranslated_share']:.1%}"),
    ("Przepisy AI", lambda m, s: s["ai_generated"]),
]


def table(summaries: dict[str, dict]) -> str:
    """Tabela markdown do `docs/wyniki.md`."""
    lines = ["| " + " | ".join(name for name, _ in COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for model, summary in summaries.items():
        lines.append("| " + " | ".join(str(get(model, summary)) for _, get in COLUMNS) + " |")
    return "\n".join(lines)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="LLM clash: te same skany i profile dla kilku modeli (M5.5).")
    parser.add_argument("scans", nargs="*", type=Path, help="ground_truth.json albo folder skanu; domyślnie wszystkie")
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS, help="modele w chmurze")
    parser.add_argument("--local", nargs="*", default=[], help="modele Ollamy, np. ollama/qwen2.5:7b (tylko z GPU)")
    parser.add_argument("--allow-cpu", action="store_true", help="puść lokalne modele także bez karty NVIDIA")
    parser.add_argument("--profiles", nargs="*", default=list(PROFILES), choices=list(PROFILES))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--budget", type=float, default=None,
                        help="sekundy na jedno zapytanie dla wszystkich modeli (domyślnie jak w /recipes)")
    parser.add_argument("--price", nargs=3, action="append", default=[], metavar=("MODEL", "IN", "OUT"),
                        help="cennik modelu w USD za 1 mln tokenów; można podać kilka razy")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    prices = PRICES | {model: (float(i), float(o)) for model, i, o in args.price}
    gpu = detect_gpu() if args.local else None
    available = ollama_models() if args.local else None
    skipped = {m: reason for m in args.local if (reason := local_skip_reason(m, gpu, available, args.allow_cpu))}
    for model, reason in skipped.items():
        print(f"POMIJAM {model}: {reason}")
    models = list(args.models) + [m for m in args.local if m not in skipped]
    if not models:
        raise SystemExit("Nie ma żadnego modelu do puszczenia.")

    paths = [p / "ground_truth.json" if p.is_dir() else p for p in args.scans] or sorted(
        SCANS_DIR.glob("*/ground_truth.json")
    )
    db_path = args.db or database_path()
    if not db_path.exists():
        raise SystemExit(f"Brak bazy przepisów: {db_path}. Najpierw `uv run import-recipes` (README) albo podaj --db.")
    scans = [load_scan(p) for p in paths]
    profiles = {p: PROFILES[p] for p in args.profiles}
    db = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    summaries, rows = {}, {}
    for model in models:
        print(f"== {model}: {len(scans)} skanów × {len(profiles)} profili × {args.repeats}")
        if llm.local(model):
            warm_up(model)
        result = run(db, scans, profiles, Calls(model, budget_s=args.budget), None, args.repeats)
        price = (0.0, 0.0) if llm.local(model) else prices.get(model)
        summaries[model] = summarize(result, price)
        rows[model] = shareable_rows(result["rows"])
    db.close()

    hardware = {"platform": platform.platform(), "gpu": gpu}
    report = table(summaries)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M")
    text = json.dumps({"hardware": hardware, "scans": len(scans), "profiles": list(profiles),
                       "repeats": args.repeats, "summaries": summaries, "skipped": skipped, "rows": rows},
                      ensure_ascii=False, indent=1)
    if any(value in text for value in secrets(ROOT / ".env")):
        raise SystemExit("STOP: w wyniku jest klucz API, nic nie zapisano.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"clash_{stamp}.json"
    out.write_text(text, encoding="utf-8")
    (OUT_DIR / f"clash_{stamp}.md").write_text(report + "\n", encoding="utf-8")
    print(report)
    if gpu:
        print(f"GPU: {gpu['name']} ({gpu['vram_mb']} MB)")
    print(f"Wyniki (same liczby, można wysłać): {out}")
    bad = [m for m, s in summaries.items() if s["violations"]]
    if bad:
        raise SystemExit(f"BRAMKA NIE PRZESZŁA dla: {', '.join(bad)}")
