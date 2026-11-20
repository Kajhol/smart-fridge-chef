"""Backend HTTP (D-005): aplikacja mobilna wysyła tu zdjęcia, a backend woła Vision LLM kluczem z .env."""

import json
import os
import re
import unicodedata
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from smart_fridge_chef.dictionary import load_ingredients
from smart_fridge_chef.evaluation import GroundTruth, ScanMetrics, TruthItem, evaluate
from smart_fridge_chef.vision.client import DEFAULT_MODEL, scan
from smart_fridge_chef.vision.images import DEFAULT_MAX_SIDE
from smart_fridge_chef.vision.schema import Photo, ScanResult, Unit, Zone

load_dotenv()

VISION_MODEL = os.getenv("VISION_MODEL", DEFAULT_MODEL)
MAX_PHOTOS = 8
MAX_PHOTO_BYTES = 15 * 1024 * 1024
INGREDIENTS = load_ingredients()
# Produkty dodane z aplikacji. Osobno od ingredients.json z gita, żeby nie mieszać ich ze słownikiem
# zespołu: przepisy ich nie znają, dopóki ktoś nie dopisze aliasów i nie zaimportuje przepisów ponownie.
CUSTOM_INGREDIENTS_FILE = Path(
    os.getenv("CUSTOM_INGREDIENTS_FILE", Path(__file__).parents[2] / "data" / "custom_ingredients.json")
)
custom_ingredients_lock = Lock()
# Skany zapisane z aplikacji trafiają tam, gdzie scan_001: zdjęcia poza gitem, ground_truth.json w gicie (D-003).
SCANS_DIR = Path(os.getenv("SCANS_DIR", Path(__file__).parents[2] / "data" / "scans"))
scans_lock = Lock()

app = FastAPI(title="Smart Fridge Chef")


class IngredientOption(BaseModel):
    """Pozycja słownika do wyboru w aplikacji (ekran korekty), bez aliasów i alergenów."""

    id: str
    name_pl: str
    unit: Unit
    custom: bool = False


class NewIngredient(BaseModel):
    name_pl: str = Field(min_length=1, max_length=60)
    unit: Unit


class SavedScan(BaseModel):
    scan_id: str
    metrics: ScanMetrics


def slugify(name: str) -> str:
    """"Mandarynka!" i " mandarynka" dają to samo "mandarynka", więc nie powstanie duplikat."""
    text = name.lower().replace("ł", "l")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def dictionary_options() -> list[IngredientOption]:
    return [IngredientOption(id=item.id, name_pl=item.name_pl, unit=item.unit) for item in INGREDIENTS.values()]


def load_custom_ingredients() -> list[IngredientOption]:
    if not CUSTOM_INGREDIENTS_FILE.exists():
        return []
    raw = json.loads(CUSTOM_INGREDIENTS_FILE.read_text(encoding="utf-8"))
    return [IngredientOption.model_validate(item) for item in raw]


def is_image(data: bytes) -> bool:
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        return False
    return True


def read_photos(photos: list[UploadFile], zones: list[Zone]) -> list[Photo]:
    """Wspólne dla /scan i /scans: pary zdjęcie + strefa, limit liczby i rozmiaru, czy to na pewno obraz."""
    if len(photos) != len(zones):
        raise HTTPException(422, f"Got {len(photos)} photos but {len(zones)} zones")
    if len(photos) > MAX_PHOTOS:
        raise HTTPException(422, f"At most {MAX_PHOTOS} photos per scan")

    result: list[Photo] = []
    for upload, zone in zip(photos, zones):
        data = upload.file.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, f"Photo {upload.filename} is larger than {MAX_PHOTO_BYTES // 1024 // 1024} MB")
        if not is_image(data):
            raise HTTPException(422, f"File {upload.filename} is not an image")
        result.append(Photo(zone=zone, data=data))
    return result


def next_scan_id(scans_dir: Path) -> str:
    numbers = [
        int(path.name.removeprefix("scan_"))
        for path in scans_dir.glob("scan_*")
        if path.is_dir() and path.name.removeprefix("scan_").isdigit()
    ]
    return f"scan_{max(numbers, default=0) + 1:03d}"


def photo_filename(photo: Photo, used: set[str]) -> str:
    with Image.open(BytesIO(photo.data)) as image:
        suffix = ".png" if image.format == "PNG" else ".jpg"
    name, number = f"{photo.zone}{suffix}", 2
    while name in used:  # dwa zdjęcia tej samej strefy (np. extra): extra.jpg, extra_2.jpg
        name, number = f"{photo.zone}_{number}{suffix}", number + 1
    used.add(name)
    return name


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": VISION_MODEL}


@app.get("/ingredients")
def ingredients() -> list[IngredientOption]:
    return dictionary_options() + load_custom_ingredients()


@app.post("/ingredients")
def add_ingredient(new: NewIngredient) -> IngredientOption:
    slug = slugify(new.name_pl)
    if not slug:
        raise HTTPException(422, "Name must contain at least one letter or digit")

    # Dwa telefony naraz nie mogą nadpisać sobie nawzajem pliku (odczyt, dopisanie, zapis).
    with custom_ingredients_lock:
        custom = load_custom_ingredients()
        for option in dictionary_options() + custom:
            if slugify(option.name_pl) == slug:
                return option

        option = IngredientOption(id=f"custom_{slug}", name_pl=new.name_pl.strip(), unit=new.unit, custom=True)
        CUSTOM_INGREDIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [item.model_dump() for item in [*custom, option]]
        CUSTOM_INGREDIENTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return option


@app.post("/scan")
def scan_fridge(
    photos: Annotated[list[UploadFile], File(description="Zdjęcia lodówki, w tej samej kolejności co zones")],
    zones: Annotated[list[Zone], Form(description="Strefa każdego zdjęcia (D-001)")],
) -> ScanResult:
    scan_photos = read_photos(photos, zones)
    try:
        return scan(scan_photos, model=VISION_MODEL)
    except ValidationError:
        raise HTTPException(502, "Vision model returned a response that does not match ScanResult")


@app.post("/scans")
def save_scan(
    photos: Annotated[list[UploadFile], File(description="Te same zdjęcia, które poszły do /scan")],
    zones: Annotated[list[Zone], Form(description="Strefa każdego zdjęcia (D-001)")],
    prediction: Annotated[str, Form(description="JSON: odpowiedź /scan bez poprawek (ScanResult)")],
    truth_items: Annotated[str, Form(description="JSON: lista po korekcie z polem visibility (TruthItem)")],
    seconds: Annotated[float | None, Form(description="Czas /scan zmierzony w aplikacji")] = None,
) -> SavedScan:
    """Zapisuje skan do ewaluacji (D-003) i od razu liczy metryki modelu, który go rozpoznał."""
    scan_photos = read_photos(photos, zones)
    try:
        predicted = ScanResult.model_validate_json(prediction)
        items = TypeAdapter(list[TruthItem]).validate_json(truth_items)
    except ValidationError as error:
        raise HTTPException(422, f"Invalid prediction or truth_items: {error.error_count()} errors")
    if not items:
        raise HTTPException(422, "truth_items must not be empty")

    # Produkty dodane z aplikacji (custom_..., D-011) model zna tylko ze słownika, więc w ręcznej liście
    # to pozycje spoza słownika (null), jak każą reguły D-003. Inaczej liczyłyby się jako pominięte.
    items = [
        item.model_copy(update={"ingredient_id": None}) if (item.ingredient_id or "").startswith("custom_") else item
        for item in items
    ]

    # Blokada: dwa zapisy naraz nie mogą dostać tego samego numeru skanu.
    with scans_lock:
        scan_id = next_scan_id(SCANS_DIR)
        folder = SCANS_DIR / scan_id
        folder.mkdir(parents=True)

    used: set[str] = set()
    photo_zones: dict[str, Zone] = {}
    for photo in scan_photos:
        name = photo_filename(photo, used)
        (folder / name).write_bytes(photo.data)
        photo_zones[name] = photo.zone

    truth = GroundTruth(scan_id=scan_id, date=date.today(), photos=photo_zones, items=items)
    (folder / "ground_truth.json").write_text(truth.model_dump_json(indent=2), encoding="utf-8")

    run_name = f"{VISION_MODEL}_{DEFAULT_MAX_SIDE}px_app_{datetime.now():%Y%m%d-%H%M%S}"
    (folder / f"pred_{run_name}.json").write_text(predicted.model_dump_json(indent=2), encoding="utf-8")
    metrics = evaluate(truth, predicted)
    report = {"model": VISION_MODEL, "max_side": DEFAULT_MAX_SIDE, "source": "app", "seconds": seconds}
    report |= metrics.model_dump()
    (folder / f"metrics_{run_name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    return SavedScan(scan_id=scan_id, metrics=metrics)
