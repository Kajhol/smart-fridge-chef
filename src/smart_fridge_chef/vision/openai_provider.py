"""Wywołanie OpenAI: zdjęcia + prompt -> ScanResult z surowymi ID od modelu."""

import base64

from openai import OpenAI

from smart_fridge_chef.vision.images import prepare_image
from smart_fridge_chef.vision.schema import Photo, ScanResult


def build_input(photos: list[Photo], max_side: int) -> list[dict]:
    content: list[dict] = []
    for number, photo in enumerate(photos, start=1):
        encoded = base64.b64encode(prepare_image(photo.data, max_side)).decode("ascii")
        content.append({"type": "input_text", "text": f"Photo {number}, zone: {photo.zone}"})
        content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}", "detail": "high"})
    return [{"role": "user", "content": content}]


def call(
    photos: list[Photo],
    system_prompt: str,
    model: str,
    max_side: int,
    client: OpenAI | None = None,
) -> ScanResult:
    client = client or OpenAI()
    response = client.responses.parse(
        model=model,
        instructions=system_prompt,
        input=build_input(photos, max_side),
        text_format=ScanResult,
    )
    return ScanResult.model_validate_json(response.output_text)
