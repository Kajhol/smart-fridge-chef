import json
import sqlite3
import sys
from types import SimpleNamespace

import httpx
from test_recipe_benchmark import ITEMS, fake, translation
from test_recipe_search import db_path  # noqa: F401  (fixture z bazą 7 przepisów)

from smart_fridge_chef.recipes import clash, llm
from smart_fridge_chef.recipes.benchmark import PROFILES, run, summarize

GPU = {"name": "NVIDIA GeForce RTX 4070", "vram_mb": 12282}


def test_gpu_is_read_from_nvidia_smi(monkeypatch):
    monkeypatch.setattr(clash.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)
    out = SimpleNamespace(returncode=0, stdout="NVIDIA GeForce RTX 4070, 12282\n")
    assert clash.detect_gpu(lambda *a, **kw: out) == GPU


def test_no_gpu_without_nvidia_smi(monkeypatch):
    monkeypatch.setattr(clash.shutil, "which", lambda name: None)
    monkeypatch.setattr(clash, "NVIDIA_SMI", ("nvidia-smi", "/nie/ma/nvidia-smi"))
    assert clash.detect_gpu() is None


def test_local_models_need_gpu_ollama_and_a_pulled_model():
    model = "ollama/qwen2.5:7b"
    assert "NVIDIA" in clash.local_skip_reason(model, None, {"qwen2.5:7b"}, allow_cpu=False)
    assert clash.local_skip_reason(model, None, {"qwen2.5:7b"}, allow_cpu=True) is None
    assert "ollama serve" in clash.local_skip_reason(model, GPU, None, allow_cpu=False)
    assert "ollama pull qwen2.5:7b" in clash.local_skip_reason(model, GPU, {"llama3.1:8b"}, allow_cpu=False)
    assert clash.local_skip_reason(model, GPU, {"qwen2.5:7b"}, allow_cpu=False) is None
    assert clash.local_skip_reason("groq/x", GPU, set(), allow_cpu=False) is not None


def test_timeouts_are_counted_and_the_request_still_answers(db_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(llm, "RETRY_DELAY_S", 0)
    calls = fake(RecipeSelection=httpx.ReadTimeout("slow"), TranslatedRecipe=translation)
    with sqlite3.connect(db_path) as db:
        result = run(db, [("scan_test", ITEMS)], {"bez_ograniczen": PROFILES["bez_ograniczen"]}, calls)
    summary = summarize(result)
    assert summary["llm_timeouts"] == 1  # jedno wywołanie, ponawiane w środku generate()
    assert summary["recipes"] > 0  # ranking z SQL, gdy wybór LLM nie przyszedł


def test_clash_writes_one_table_for_all_models(db_path, tmp_path, monkeypatch):  # noqa: F811
    scan = tmp_path / "ground_truth.json"
    scan.write_text(json.dumps({"scan_id": "s1", "items": [i.model_dump() for i in ITEMS]}), encoding="utf-8")
    monkeypatch.setattr(clash, "OUT_DIR", tmp_path / "eval")
    monkeypatch.setattr(clash, "ROOT", tmp_path)
    monkeypatch.setattr(clash, "Calls", lambda model, budget_s=None: fake(
        RecipeSelection={"picks": [{"recipe_id": "r_omelette", "description": "Omlet."}]},
        TranslatedRecipe=translation,
    ))
    monkeypatch.setattr(sys, "argv", ["eval-clash", str(scan), "--db", str(db_path), "--profiles", "jajka_mleko",
                                      "--models", "gemini-a", "groq/b", "--local", "ollama/qwen2.5:7b"])
    monkeypatch.setattr(clash, "detect_gpu", lambda: None)
    monkeypatch.setattr(clash, "ollama_models", lambda: None)
    clash.main()

    out = json.loads(next((tmp_path / "eval").glob("clash_*.json")).read_text(encoding="utf-8"))
    assert list(out["summaries"]) == ["gemini-a", "groq/b"]
    assert "NVIDIA" in out["skipped"]["ollama/qwen2.5:7b"]
    assert "title" not in json.dumps(out["rows"])
    table = next((tmp_path / "eval").glob("clash_*.md")).read_text(encoding="utf-8")
    assert table.count("\n") == 4 and "| groq/b | 1 | 0 |" in table
