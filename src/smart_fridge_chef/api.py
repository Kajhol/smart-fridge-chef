"""Backend HTTP (D-005): aplikacja mobilna wysyła tu zdjęcia, a backend woła Vision LLM kluczem z .env."""

import os
from io import BytesIO
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ValidationError

from smart_fridge_chef.dictionary import load_ingredients
from smart_fridge_chef.vision.client import DEFAULT_MODEL, scan
from smart_fridge_chef.vision.schema import Photo, ScanResult, Unit, Zone

load_dotenv()

VISION_MODEL = os.getenv("VISION_MODEL", DEFAULT_MODEL)
MAX_PHOTOS = 8
MAX_PHOTO_BYTES = 15 * 1024 * 1024
INGREDIENTS = load_ingredients()

app = FastAPI(title="Smart Fridge Chef")


class IngredientOption(BaseModel):
    """Pozycja słownika do wyboru w aplikacji (ekran korekty), bez aliasów i alergenów."""

    id: str
    name_pl: str
    unit: Unit


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
    return [IngredientOption(id=item.id, name_pl=item.name_pl, unit=item.unit) for item in INGREDIENTS.values()]


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
