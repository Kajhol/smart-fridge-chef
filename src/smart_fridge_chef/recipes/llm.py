"""LLM tekstowy dla przepisów: wybór dostawcy po nazwie modelu, odpowiedź zawsze walidowana schematem Pydantic."""

import os
from typing import Any, TypeVar

from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel

DEFAULT_MODEL = "gemini-3.1-flash-lite"
GROQ_PREFIX = "groq/"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

Schema = TypeVar("Schema", bound=BaseModel)


def recipe_model() -> str:
    return os.getenv("RECIPE_MODEL", DEFAULT_MODEL)


def call_gemini(prompt: str, system_prompt: str, schema: type[Schema], model: str, client: Any = None) -> Schema:
    client = client or genai.Client()
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        ),
    )
    return schema.model_validate_json(response.text)


def call_groq(prompt: str, system_prompt: str, schema: type[Schema], model: str, client: Any = None) -> Schema:
    client = client or OpenAI(base_url=GROQ_BASE_URL, api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model=model.removeprefix(GROQ_PREFIX),
        temperature=0,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        },
    )
    return schema.model_validate_json(response.choices[0].message.content)


def generate(
    prompt: str,
    system_prompt: str,
    schema: type[Schema],
    model: str | None = None,
    client: Any = None,
) -> Schema:
    """Jedno wywołanie LLM. `gemini-*` idzie do Gemini, `groq/<model>` do Groq (np. groq/openai/gpt-oss-120b)."""
    model = model or recipe_model()
    if model.startswith("gemini-"):
        return call_gemini(prompt, system_prompt, schema, model, client)
    if model.startswith(GROQ_PREFIX):
        return call_groq(prompt, system_prompt, schema, model, client)
    raise ValueError(f"Unknown provider for model: {model}")
