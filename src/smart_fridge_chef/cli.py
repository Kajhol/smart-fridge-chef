"""Skan z linii poleceń: zdjęcia z folderu -> Vision LLM -> wynik w JSON, a jeśli jest ręczna lista, to też metryki."""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import get_args

from dotenv import load_dotenv

from smart_fridge_chef.dictionary import load_ingredients
from smart_fridge_chef.evaluation import ScanMetrics, evaluate, load_ground_truth
from smart_fridge_chef.vision.client import DEFAULT_MODEL, normalize_ids, scan_raw
from smart_fridge_chef.vision.schema import Photo, ScanResult, Zone
from smart_fridge_chef.vision.images import DEFAULT_MAX_SIDE

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png"}
GROUND_TRUTH_FILE = "ground_truth.json"


def zone_from_filename(path: Path) -> Zone | None:
    for zone in get_args(Zone):
        if path.stem.startswith(zone):
            return zone
    return None


def collect_photos(folder: Path, zones: dict[str, Zone] | None) -> list[Photo]:
    photos: list[Photo] = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in PHOTO_SUFFIXES:
            continue
        zone = zones.get(path.name) if zones is not None else zone_from_filename(path)
        if zone is None:
            print(f"Pomijam {path.name}: nie wiem, jaka to strefa")
            continue
        photos.append(Photo(zone=zone, data=path.read_bytes()))
    return photos


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def print_id_changes(raw: ScanResult, result: ScanResult) -> None:
    changes = [
        f"  {before.ingredient_id} -> {after.ingredient_id}  ({after.label})"
        for before, after in zip(raw.items, result.items)
        if before.ingredient_id != after.ingredient_id
    ]
    if changes:
        print("\nPoprawione ID (surowe od modelu -> po normalizacji):")
        print("\n".join(changes))


def print_metrics(metrics: ScanMetrics) -> None:
    by_visibility = ", ".join(f"{name} {percent(value)}" for name, value in metrics.recall_by_visibility.items())
    f1 = "-" if metrics.f1 is None else f"{metrics.f1:.2f}"
    print(f"\nRecall {percent(metrics.recall)} ({by_visibility})")
    print(f"Precision {percent(metrics.precision)} | F1 {f1} | znalezione {metrics.found} z {metrics.expected}")
    print(f"Pominięte:           {', '.join(metrics.missed) or '-'}")
    print(f"Halucynacje:         {', '.join(metrics.hallucinations) or '-'}")
    print(f"Duplikaty:           {', '.join(metrics.duplicates) or '-'}")
    print(f"Niezgodne jednostki: {', '.join(metrics.unit_mismatches) or '-'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Skanuje zdjęcia lodówki z jednego folderu.")
    parser.add_argument("folder", type=Path, help="folder skanu, np. data/scans/scan_001")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-side", type=int, default=DEFAULT_MAX_SIDE)
    args = parser.parse_args()

    load_dotenv()
    truth_path = args.folder / GROUND_TRUTH_FILE
    truth = load_ground_truth(truth_path) if truth_path.exists() else None
    photos = collect_photos(args.folder, truth.photos if truth else None)

    ingredients = load_ingredients()
    start = time.perf_counter()
    raw = scan_raw(photos, ingredients, model=args.model, max_side=args.max_side)
    seconds = time.perf_counter() - start
    result = normalize_ids(raw, ingredients)

    print(f"{args.model} | {args.max_side} px | {len(photos)} zdjęć | {seconds:.1f} s | {len(result.items)} pozycji\n")
    for item in result.items:
        print(f"  {str(item.ingredient_id):<20} {item.quantity:>7g} {item.unit:<4} {item.confidence:<7} {item.label}")

    print_id_changes(raw, result)

    run_name = f"{args.model}_{args.max_side}px_{datetime.now():%Y%m%d-%H%M%S}"
    (args.folder / f"raw_{run_name}.json").write_text(raw.model_dump_json(indent=2), encoding="utf-8")
    (args.folder / f"pred_{run_name}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    if truth is None:
        print(f"\nBrak {GROUND_TRUTH_FILE}, więc bez metryk.")
        return

    metrics = evaluate(truth, result)
    report = {"model": args.model, "max_side": args.max_side, "seconds": round(seconds, 1), **metrics.model_dump()}
    (args.folder / f"metrics_{run_name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_metrics(metrics)
