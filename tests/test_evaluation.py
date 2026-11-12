import pytest
from pydantic import ValidationError

from smart_fridge_chef.evaluation import GroundTruth, TruthItem, evaluate, f1_score, ratio
from smart_fridge_chef.vision.schema import DetectedItem, ScanResult


def truth_item(ingredient_id, visibility="visible", quantity=1, unit="pcs"):
    return TruthItem(ingredient_id=ingredient_id, label="x", quantity=quantity, unit=unit, visibility=visibility)


def predicted_item(ingredient_id, quantity=1, unit="pcs"):
    return DetectedItem(ingredient_id=ingredient_id, label="x", quantity=quantity, unit=unit, confidence="high")


def run(truth_items, predicted_items):
    truth = GroundTruth(scan_id="test", date="2026-11-12", photos={"a.jpg": "door"}, items=truth_items)
    return evaluate(truth, ScanResult(items=predicted_items))


def test_perfect_prediction():
    metrics = run([truth_item("egg"), truth_item("milk")], [predicted_item("egg"), predicted_item("milk")])
    assert metrics.recall == 1
    assert metrics.precision == 1
    assert metrics.f1 == 1
    assert metrics.missed == metrics.hallucinations == metrics.duplicates == []


def test_hallucination_lowers_precision_only():
    metrics = run([truth_item("egg")], [predicted_item("egg"), predicted_item("onion")])
    assert metrics.recall == 1
    assert metrics.precision == 0.5
    assert metrics.hallucinations == ["onion"]
    assert metrics.duplicates == []


def test_extra_entry_of_existing_product_is_duplicate_not_hallucination():
    metrics = run([truth_item("lettuce")], [predicted_item("lettuce"), predicted_item("lettuce")])
    assert metrics.duplicates == ["lettuce"]
    assert metrics.hallucinations == []
    assert metrics.precision == 0.5


def test_one_of_two_same_products_found_counts_visible_one_as_found():
    truth = [truth_item("mayonnaise", visibility="partial"), truth_item("mayonnaise", visibility="visible")]
    metrics = run(truth, [predicted_item("mayonnaise")])
    assert metrics.found == 1
    assert metrics.missed == ["mayonnaise"]
    assert metrics.recall_by_visibility == {"visible": 1, "partial": 0, "hidden": None}


def test_hidden_items_excluded_from_recall_seen():
    truth = [truth_item("egg"), truth_item("garlic", visibility="hidden")]
    metrics = run(truth, [predicted_item("egg")])
    assert metrics.recall == 0.5
    assert metrics.recall_seen == 1


def test_items_outside_dictionary_are_counted_separately():
    metrics = run([truth_item("egg"), truth_item(None)], [predicted_item("egg"), predicted_item(None)])
    assert metrics.expected == 1
    assert metrics.predicted == 1
    assert metrics.precision == 1
    assert metrics.unknown_expected == 1
    assert metrics.unknown_predicted == 1


def test_quantity_error_is_relative_and_skips_unit_mismatch():
    truth = [truth_item("milk", quantity=1000, unit="ml"), truth_item("lettuce", quantity=500, unit="g")]
    predicted = [predicted_item("milk", quantity=500, unit="ml"), predicted_item("lettuce", quantity=1, unit="pcs")]
    metrics = run(truth, predicted)
    assert metrics.quantity_error == 0.5
    assert metrics.unit_mismatches == ["lettuce"]


def test_quantity_error_skipped_when_counts_differ():
    truth = [truth_item("mayonnaise", quantity=400, unit="g"), truth_item("mayonnaise", quantity=700, unit="g")]
    metrics = run(truth, [predicted_item("mayonnaise", quantity=400, unit="g")])
    assert metrics.quantity_error is None


def test_water_is_ignored():
    metrics = run([truth_item("egg")], [predicted_item("egg"), predicted_item("water", quantity=1000, unit="ml")])
    assert metrics.predicted == 1
    assert metrics.hallucinations == []
    assert metrics.precision == 1


def test_empty_prediction():
    metrics = run([truth_item("egg")], [])
    assert metrics.recall == 0
    assert metrics.precision is None
    assert metrics.f1 is None


def test_ratio_and_f1_edge_cases():
    assert ratio(1, 0) is None
    assert f1_score(0.0, 1.0) == 0.0
    assert f1_score(None, 1.0) is None


def test_ground_truth_rejects_typo_in_visibility():
    with pytest.raises(ValidationError):
        truth_item("egg", visibility="visable")
