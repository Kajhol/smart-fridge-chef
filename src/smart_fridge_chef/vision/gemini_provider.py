"""Wywołanie Gemini: zdjęcia + prompt -> ScanResult z surowymi ID od modelu."""

from google import genai
from google.genai import types

from smart_fridge_chef.vision.images import prepare_image
from smart_fridge_chef.vision.schema import Photo, ScanResult


def build_contents(photos: list[Photo], max_side: int) -> list[str | types.Part]:
    contents: list[str | types.Part] = []
    for number, photo in enumerate(photos, start=1):
        contents.append(f"Photo {number}, zone: {photo.zone}")
        contents.append(types.Part.from_bytes(data=prepare_image(photo.data, max_side), mime_type="image/jpeg"))
    return contents


def call(
    photos: list[Photo],
    system_prompt: str,
    model: str,
    max_side: int,
    client: genai.Client | None = None,
) -> ScanResult:
    client = client or genai.Client()
    response = client.models.generate_content(
        model=model,
        contents=build_contents(photos, max_side),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_json_schema=ScanResult.model_json_schema(),
        ),
    )
    return ScanResult.model_validate_json(response.text)
