"""Format odpowiedzi Vision LLM: produkty rozpoznane na zdjęciach jednego skanu."""

from typing import Literal

from pydantic import BaseModel, Field

Unit = Literal["pcs", "g", "ml"]
Confidence = Literal["low", "medium", "high"]


class DetectedItem(BaseModel):
    ingredient_id: str | None = Field(
        description="Ingredient ID from the dictionary, or null if the product is not in the dictionary.",
    )
    label: str = Field(
        description="Short description of the product as seen in the photo, in Polish, e.g. 'kefir Bakoma 400 g'.",
    )
    quantity: float = Field(gt=0, description="Amount expressed in the unit given in the unit field.")
    unit: Unit
    confidence: Confidence


class ScanResult(BaseModel):
    items: list[DetectedItem]