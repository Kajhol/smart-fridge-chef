"""Formaty przepisów (D-004, D-009): wejście POST /recipes, odpowiedź i odpowiedź LLM tekstowego."""

from typing import Literal

from pydantic import BaseModel, Field

from smart_fridge_chef.vision.schema import Unit

Allergen = Literal[
    "celery", "crustaceans", "eggs", "fish", "gluten", "milk",
    "mustard", "nuts", "peanuts", "sesame", "soy", "sulphites",
]
Difficulty = Literal["easy", "medium", "hard"]
IngredientStatus = Literal["in_fridge", "missing", "pantry"]
RecipeSource = Literal["database", "ai_generated"]


# --- Wejście ---------------------------------------------------------------


class FridgeItem(BaseModel):
    """Pozycja z lodówki po ekranie korekty. Ten sam kształt co DetectedItem, bez confidence."""

    ingredient_id: str | None = Field(
        description="Ingredient ID from the dictionary, or null if the product is not in the dictionary.",
    )
    label: str = Field(description="Short description of the product in Polish.")
    quantity: float = Field(gt=0, description="Amount expressed in the unit given in the unit field.")
    unit: Unit


class UserProfile(BaseModel):
    allergens: list[Allergen] = Field(default=[], description="Allergens the user must avoid.")
    excluded_ingredients: list[str] = Field(default=[], description="Ingredient IDs the user does not want.")
    max_difficulty: Difficulty = "hard"
    max_time_min: int | None = Field(default=None, gt=0, description="Maximum total cooking time in minutes.")
    servings: int = Field(default=2, ge=1, le=12, description="How many people the user cooks for.")


class RecipeRequest(BaseModel):
    items: list[FridgeItem] = Field(min_length=1)
    profile: UserProfile = UserProfile()


# --- Odpowiedź API ---------------------------------------------------------


class RecipeIngredient(BaseModel):
    ingredient_id: str
    name_pl: str = Field(description="Polish name from the dictionary.")
    quantity: float | None = Field(description="Amount scaled to the requested servings; null if the source has none.")
    unit: Unit | None
    status: IngredientStatus


class Substitution(BaseModel):
    missing_id: str = Field(description="ID of the missing ingredient.")
    suggestion: str = Field(description="What to use instead, in Polish.")


class Recipe(BaseModel):
    id: str | None = Field(description="Recipe ID in our database; null for an AI-generated recipe.")
    source: RecipeSource
    title: str
    description: str = Field(description="Why this recipe fits the fridge, in Polish (written by the LLM).")
    servings: int
    time_min: int | None
    difficulty: Difficulty
    kcal_per_serving: float | None
    ingredients: list[RecipeIngredient]
    substitutions: list[Substitution] = []
    steps: list[str]
    url: str | None = Field(description="Link to the original recipe.")


class RecipeResponse(BaseModel):
    recipes: list[Recipe] = Field(max_length=3)
    candidates_considered: int = Field(description="How many recipes passed the SQL filter (D-004).")


# --- Odpowiedź LLM tekstowego (structured output, nie wychodzi z API) -----


class RecipePick(BaseModel):
    recipe_id: str = Field(description="ID of one of the candidate recipes given in the prompt.")
    description: str = Field(description="One or two sentences in Polish: why this recipe fits what is in the fridge.")
    substitutions: list[Substitution] = Field(default=[], description="Replacements for missing ingredients, if any.")


class RecipeSelection(BaseModel):
    picks: list[RecipePick] = Field(max_length=3)


class TranslatedRecipe(BaseModel):
    """Osobne wywołanie tylko dla wybranych przepisów (R-6): tytuł i kroki z Food.com po polsku."""

    title_pl: str = Field(description="Recipe title translated into natural Polish.")
    steps_pl: list[str] = Field(
        description="Recipe steps translated into Polish, one entry per original step, in the same order.",
    )
