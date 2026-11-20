"""LLM tekstowy dla przepisów: wybór dostawcy po nazwie modelu, odpowiedź zawsze walidowana schematem Pydantic."""

import os
import time
from typing import Any, TypeVar

from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel

DEFAULT_MODEL = "gemini-3.1-flash-lite"
GROQ_PREFIX = "groq/"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OLLAMA_PREFIX = "ollama/"
OLLAMA_BASE_URL = "http://localhost:11434/v1"  # lokalny model, np. ollama/qwen2.5:3b; adres zmienia OLLAMA_BASE_URL

Schema = TypeVar("Schema", bound=BaseModel)

RETRIES = 3  # przy przeciążeniu dostawcy (429, 5xx) ponawiamy z rosnącą przerwą
RETRY_DELAY_S = 2.0


def transient(error: Exception) -> bool:
    """Błąd chwilowy: limit albo przeciążenie po stronie dostawcy. Zły JSON czy zły klucz nie są chwilowe."""
    status = getattr(error, "code", None) or getattr(error, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def recipe_model() -> str:
    return os.getenv("RECIPE_MODEL", DEFAULT_MODEL)


def record(usage: list[dict] | None, model: str, input_tokens: Any, output_tokens: Any) -> None:
    """Tokeny jednego wywołania do listy `usage` (ewaluacja kosztu, M4). Brak danych od dostawcy liczymy jako 0."""
    if usage is not None:
        usage.append({"model": model, "input_tokens": input_tokens or 0, "output_tokens": output_tokens or 0})


def call_gemini(
    prompt: str, system_prompt: str, schema: type[Schema], model: str, client: Any = None,
    usage: list[dict] | None = None,
) -> Schema:
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
    meta = getattr(response, "usage_metadata", None)
    # tokeny „myślenia” są płatne jak wyjście
    output = (getattr(meta, "candidates_token_count", 0) or 0) + (getattr(meta, "thoughts_token_count", 0) or 0)
    record(usage, model, getattr(meta, "prompt_token_count", 0), output)
    return schema.model_validate_json(response.text)


def call_openai_compatible(
    prompt: str, system_prompt: str, schema: type[Schema], model: str, client: Any,
    usage: list[dict] | None = None,
) -> Schema:
    """Groq i Ollama mają API zgodne z OpenAI: ten sam kod, inny adres i prefiks modelu."""
    response = client.chat.completions.create(
        model=model.split("/", 1)[1],
        temperature=0,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        },
    )
    tokens = getattr(response, "usage", None)
    record(usage, model, getattr(tokens, "prompt_tokens", 0), getattr(tokens, "completion_tokens", 0))
    return schema.model_validate_json(response.choices[0].message.content)


def call_groq(
    prompt: str, system_prompt: str, schema: type[Schema], model: str, client: Any = None,
    usage: list[dict] | None = None,
) -> Schema:
    client = client or OpenAI(base_url=GROQ_BASE_URL, api_key=os.getenv("GROQ_API_KEY"))
    return call_openai_compatible(prompt, system_prompt, schema, model, client, usage)


def call_ollama(
    prompt: str, system_prompt: str, schema: type[Schema], model: str, client: Any = None,
    usage: list[dict] | None = None,
) -> Schema:
    # Ollama nie sprawdza klucza, ale klient OpenAI wymaga niepustego
    client = client or OpenAI(base_url=os.getenv("OLLAMA_BASE_URL") or OLLAMA_BASE_URL, api_key="ollama")
    return call_openai_compatible(prompt, system_prompt, schema, model, client, usage)


def generate(
    prompt: str,
    system_prompt: str,
    schema: type[Schema],
    model: str | None = None,
    client: Any = None,
    usage: list[dict] | None = None,
) -> Schema:
    """Jedno wywołanie LLM. `gemini-*` idzie do Gemini, `groq/<model>` do Groq (np. groq/openai/gpt-oss-120b),
    `ollama/<model>` do lokalnej Ollamy (np. ollama/qwen2.5:3b)."""
    model = model or recipe_model()
    if model.startswith("gemini-"):
        call = call_gemini
    elif model.startswith(GROQ_PREFIX):
        call = call_groq
    elif model.startswith(OLLAMA_PREFIX):
        call = call_ollama
    else:
        raise ValueError(f"Unknown provider for model: {model}")
    for attempt in range(RETRIES):
        try:
            return call(prompt, system_prompt, schema, model, client, usage)
        except Exception as error:
            if attempt == RETRIES - 1 or not transient(error):
                raise
            time.sleep(RETRY_DELAY_S * 2**attempt)
    raise AssertionError("unreachable")
