"""Ewaluacja rozpoznawania (D-003): wynik Vision LLM porównany z ręczną listą jednego skanu."""

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from smart_fridge_chef.vision.schema import DetectedItem, ScanResult, Unit, Zone

Visibility = Literal["visible", "partial", "hidden"]
VISIBILITY_ORDER: dict[Visibility, int] = {"visible": 0, "partial": 1, "hidden": 2}
IGNORED_IDS = frozenset({"water"})


class TruthItem(BaseModel):
    ingredient_id: str | None
    label: str
    quantity: float = Field(gt=0)
    unit: Unit
    visibility: Visibility


class GroundTruth(BaseModel):
    scan_id: str
    date: date
    photos: dict[str, Zone]
    items: list[TruthItem]


class ScanMetrics(BaseModel):
    scan_id: str
    expected: int
    predicted: int
    found: int
    recall: float | None
    recall_seen: float | None
    recall_by_visibility: dict[Visibility, float | None]
    precision: float | None
    f1: float | None
    missed: list[str]
    hallucinations: list[str]
    duplicates: list[str]
    quantity_error: float | None
    unit_mismatches: list[str]
    unknown_expected: int
    unknown_predicted: int


def load_ground_truth(path: Path) -> GroundTruth:
    return GroundTruth.model_validate_json(path.read_text(encoding="utf-8"))


def ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def f1_score(precision: float | None, recall: float | None) -> float | None:
    if not precision or not recall:
        return None if precision is None or recall is None else 0.0
    return 2 * precision * recall / (precision + recall)


def match(expected: list[TruthItem], predicted_counts: Counter[str]) -> tuple[list[TruthItem], list[TruthItem]]:
    by_id: dict[str, list[TruthItem]] = defaultdict(list)
    for item in expected:
        by_id[item.ingredient_id].append(item)

    matched: list[TruthItem] = []
    missed: list[TruthItem] = []
    for ingredient_id, items in by_id.items():
        items.sort(key=lambda item: VISIBILITY_ORDER[item.visibility])
        found = predicted_counts[ingredient_id]
        matched += items[:found]
        missed += items[found:]
    return matched, missed


def quantity_errors(
    expected: list[TruthItem], predicted: list[DetectedItem]
) -> tuple[list[float], list[str]]:
    errors: list[float] = []
    unit_mismatches: list[str] = []
    expected_ids = {item.ingredient_id for item in expected}
    for ingredient_id in sorted(expected_ids):
        truth = [item for item in expected if item.ingredient_id == ingredient_id]
        guess = [item for item in predicted if item.ingredient_id == ingredient_id]
        if len(truth) != len(guess):
            continue
        if {item.unit for item in guess} != {item.unit for item in truth}:
            unit_mismatches.append(ingredient_id)
            continue
        true_total = sum(item.quantity for item in truth)
        guess_total = sum(item.quantity for item in guess)
        errors.append(abs(guess_total - true_total) / true_total)
    return errors, unit_mismatches


def evaluate(truth: GroundTruth, prediction: ScanResult) -> ScanMetrics:
    expected = [item for item in truth.items if item.ingredient_id is not None and item.ingredient_id not in IGNORED_IDS]
    predicted = [
        item for item in prediction.items if item.ingredient_id is not None and item.ingredient_id not in IGNORED_IDS
    ]
    expected_counts = Counter(item.ingredient_id for item in expected)
    predicted_counts = Counter(item.ingredient_id for item in predicted)

    matched, missed = match(expected, predicted_counts)

    hallucinations: list[str] = []
    duplicates: list[str] = []
    for ingredient_id, count in predicted_counts.items():
        if ingredient_id not in expected_counts:
            hallucinations += [ingredient_id] * count
        elif count > expected_counts[ingredient_id]:
            duplicates += [ingredient_id] * (count - expected_counts[ingredient_id])

    seen = [item for item in expected if item.visibility != "hidden"]
    matched_seen = [item for item in matched if item.visibility != "hidden"]
    recall_by_visibility = {
        visibility: ratio(
            sum(item.visibility == visibility for item in matched),
            sum(item.visibility == visibility for item in expected),
        )
        for visibility in VISIBILITY_ORDER
    }

    recall = ratio(len(matched), len(expected))
    precision = ratio(len(matched), len(predicted))
    errors, unit_mismatches = quantity_errors(expected, predicted)

    return ScanMetrics(
        scan_id=truth.scan_id,
        expected=len(expected),
        predicted=len(predicted),
        found=len(matched),
        recall=recall,
        recall_seen=ratio(len(matched_seen), len(seen)),
        recall_by_visibility=recall_by_visibility,
        precision=precision,
        f1=f1_score(precision, recall),
        missed=sorted(item.ingredient_id for item in missed),
        hallucinations=sorted(hallucinations),
        duplicates=sorted(duplicates),
        quantity_error=sum(errors) / len(errors) if errors else None,
        unit_mismatches=unit_mismatches,
        unknown_expected=sum(item.ingredient_id is None for item in truth.items),
        unknown_predicted=sum(item.ingredient_id is None for item in prediction.items),
    )
