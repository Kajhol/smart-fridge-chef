"""Backend HTTP (D-005): aplikacja mobilna wysyła tu zdjęcia, a backend woła Vision LLM kluczem z .env."""

import json
import os
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError

from smart_fridge_chef.dictionary import load_ingredients
from smart_fridge_chef.vision.client import DEFAULT_MODEL, scan
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
    if len(photos) != len(zones):
        raise HTTPException(422, f"Got {len(photos)} photos but {len(zones)} zones")
    if len(photos) > MAX_PHOTOS:
        raise HTTPException(422, f"At most {MAX_PHOTOS} photos per scan")

    scan_photos: list[Photo] = []
    for upload, zone in zip(photos, zones):
        data = upload.file.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, f"Photo {upload.filename} is larger than {MAX_PHOTO_BYTES // 1024 // 1024} MB")
        if not is_image(data):
            raise HTTPException(422, f"File {upload.filename} is not an image")
        scan_photos.append(Photo(zone=zone, data=data))

    try:
        return scan(scan_photos, model=VISION_MODEL)
    except ValidationError:
        raise HTTPException(502, "Vision model returned a response that does not match ScanResult")
