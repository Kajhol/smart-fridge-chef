"""Prompt dla Vision LLM: stała instrukcja + lista składników ze słownika."""

from smart_fridge_chef.dictionary import Ingredient

SYSTEM_PROMPT_TEMPLATE = """\
You are analysing photos of the inside of one fridge. Each photo shows a different zone \
(door, upper shelves, lower shelves, extra).

List every food product you can see.

Rules:
- ingredient_id: use an id from the dictionary below. If the product is not in the dictionary, use null.
- label: short description in Polish of what you see, with brand and package size if readable, \
e.g. "mleko Łaciate 3,2% 1 l".
- quantity and unit: use the unit given for that ingredient in the dictionary. \
For products outside the dictionary choose pcs, g or ml.
- If a package is clearly partly used, estimate the amount left, not the package size.
- Identical items (e.g. 6 eggs) go into one entry with the total quantity. \
Different products with the same id (e.g. two brands of milk) are separate entries.
- If the same item is visible in two photos, count it once.
- Only list what you can actually see. Do not guess products hidden behind others.
- confidence: high = label readable or product unmistakable, medium = recognised by shape or colour, \
low = uncertain.
- Ignore non-food items.

Dictionary (id | Polish name | unit):
{dictionary}
"""


def format_dictionary(ingredients: dict[str, Ingredient]) -> str:
    return "\n".join(f"{i.id} | {i.name_pl} | {i.unit}" for i in ingredients.values())


def build_system_prompt(ingredients: dict[str, Ingredient]) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(dictionary=format_dictionary(ingredients))
