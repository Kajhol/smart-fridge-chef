"""LLM tekstowy dla przepisów: wybór dostawcy po nazwie modelu, odpowiedź zawsze walidowana schematem Pydantic."""

import os
import re
import time
from typing import Any, TypeVar

import httpx
import openai
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

RETRIES = 3  # przy przeciążeniu dostawcy (429, 5xx) albo timeoucie ponawiamy z rosnącą przerwą
RETRY_DELAY_S = 2.0

# M5.5: żadne wywołanie nie wisi dłużej niż CALL_TIMEOUT_S, a całe zapytanie /recipes nie dłużej niż budżet.
# Jedno wywołanie trwa zwykle 1–2 s, więc 15 s to już zawieszenie (wartość Kajtka z b6d6609).
# Lokalny model (Ollama) jest wolniejszy i pierwsze wywołanie ładuje go do pamięci, więc ma dłuższe limity.
CALL_TIMEOUT_S = 15.0
LOCAL_CALL_TIMEOUT_S = 120.0
REQUEST_BUDGET_S = 45.0  # apka czeka na /recipes 60 s
LOCAL_REQUEST_BUDGET_S = 300.0
MIN_CALL_TIMEOUT_S = 1.0


class BudgetExceeded(TimeoutError):
    """Skończył się czas na całe zapytanie: kolejnego wywołania LLM już nie robimy."""


def transient(error: Exception) -> bool:
    """Błąd chwilowy: limit, przeciążenie dostawcy albo timeout. Zły JSON czy zły klucz nie są chwilowe."""
    if isinstance(error, BudgetExceeded):
        return False
    if isinstance(error, (TimeoutError, httpx.TimeoutException, httpx.NetworkError, openai.APIConnectionError)):
        return True
    code = status(error)
    return code is not None and (code == 429 or code >= 500)


def status(error: Exception) -> int | None:
    """Kod HTTP błędu. Gemini trzyma go w `code`, OpenAI/Groq w `status_code` (ich `code` to napis, np.
    "rate_limit_exceeded", więc nie wolno go brać jako pierwszego)."""
    for name in ("status_code", "code"):
        value = getattr(error, name, None)
        if isinstance(value, int):
            return value
    return None


# Dostawcy mówią, ile poczekać: Groq „Please try again in 4.38s”, Gemini „retryDelay: 17s”, nagłówek retry-after.
RETRY_AFTER = re.compile(r"(?:try again in|retryDelay['\"]?:\s*['\"]?)\s*([0-9.]+)\s*s", re.IGNORECASE)
MAX_RETRY_AFTER_S = 60.0


def retry_after(error: Exception) -> float | None:
    """Ile sekund dostawca każe czekać przed kolejną próbą (429), jeśli to mówi."""
    response = getattr(error, "response", None)
    header = getattr(getattr(response, "headers", None), "get", lambda _: None)("retry-after")
    try:
        if header is not None:
            return min(float(header), MAX_RETRY_AFTER_S)
    except ValueError:
        pass
    match = RETRY_AFTER.search(str(error))
    return min(float(match.group(1)), MAX_RETRY_AFTER_S) if match else None


def error_kind(error: Exception) -> str:
    """Krótki rodzaj błędu do raportu, bez treści (np. „RateLimitError 429”, „ReadTimeout”)."""
    code = status(error)
    return f"{type(error).__name__} {code}" if code is not None else type(error).__name__


def local(model: str) -> bool:
    return model.startswith(OLLAMA_PREFIX)


def call_timeout(model: str) -> float:
    """Limit jednego wywołania w sekundach; LLM_TIMEOUT_S w .env nadpisuje domyślny."""
    default = LOCAL_CALL_TIMEOUT_S if local(model) else CALL_TIMEOUT_S
    return float(os.getenv("LLM_TIMEOUT_S") or default)


def request_budget(model: str) -> float:
    """Czas na wszystkie wywołania LLM jednego zapytania; RECIPES_BUDGET_S w .env nadpisuje domyślny."""
    default = LOCAL_REQUEST_BUDGET_S if local(model) else REQUEST_BUDGET_S
    return float(os.getenv("RECIPES_BUDGET_S") or default)


def remaining_timeout(model: str, deadline: float | None) -> float:
    """Limit dla następnego wywołania: zwykły, ale nie dłuższy niż czas do końca budżetu."""
    timeout = call_timeout(model)
    if deadline is None:
        return timeout
    left = deadline - time.monotonic()
    if left < MIN_CALL_TIMEOUT_S:
        raise BudgetExceeded(f"request budget exhausted before calling {model}")
    return min(timeout, left)


def recipe_model() -> str:
    return os.getenv("RECIPE_MODEL", DEFAULT_MODEL)


def record(usage: list[dict] | None, model: str, input_tokens: Any, output_tokens: Any) -> None:
    """Tokeny jednego wywołania do listy `usage` (ewaluacja kosztu, M4). Brak danych od dostawcy liczymy jako 0."""
    if usage is not None:
        usage.append({"model": model, "input_tokens": input_tokens or 0, "output_tokens": output_tokens or 0})


def call_gemini(
    prompt: str, system_prompt: str, schema: type[Schema], model: str, client: Any = None,
    usage: list[dict] | None = None, timeout: float = CALL_TIMEOUT_S,
) -> Schema:
    # timeout w milisekundach; SDK samo nie ponawia, ponawia generate()
    client = client or genai.Client(http_options=types.HttpOptions(timeout=int(timeout * 1000)))
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
    usage: list[dict] | None = None, timeout: float = CALL_TIMEOUT_S,
) -> Schema:
    # max_retries=0: SDK OpenAI domyślnie ponawia 2 razy po cichu, a ponawianie robi generate()
    client = client or OpenAI(base_url=GROQ_BASE_URL, api_key=os.getenv("GROQ_API_KEY"), timeout=timeout, max_retries=0)
    return call_openai_compatible(prompt, system_prompt, schema, model, client, usage)


def ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL") or OLLAMA_BASE_URL


def call_ollama(
    prompt: str, system_prompt: str, schema: type[Schema], model: str, client: Any = None,
    usage: list[dict] | None = None, timeout: float = LOCAL_CALL_TIMEOUT_S,
) -> Schema:
    # Ollama nie sprawdza klucza, ale klient OpenAI wymaga niepustego
    client = client or OpenAI(base_url=ollama_base_url(), api_key="ollama", timeout=timeout, max_retries=0)
    return call_openai_compatible(prompt, system_prompt, schema, model, client, usage)


def generate(
    prompt: str,
    system_prompt: str,
    schema: type[Schema],
    model: str | None = None,
    client: Any = None,
    usage: list[dict] | None = None,
    deadline: float | None = None,
) -> Schema:
    """Jedno wywołanie LLM. `gemini-*` idzie do Gemini, `groq/<model>` do Groq (np. groq/openai/gpt-oss-120b),
    `ollama/<model>` do lokalnej Ollamy (np. ollama/qwen2.5:3b).

    `deadline` (time.monotonic()) to koniec budżetu całego zapytania: po nim nie zaczynamy kolejnej próby,
    a limit pojedynczej próby jest przycinany do pozostałego czasu."""
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
        timeout = remaining_timeout(model, deadline)
        try:
            return call(prompt, system_prompt, schema, model, client, usage, timeout)
        except Exception as error:
            if attempt == RETRIES - 1 or not transient(error):
                raise
            delay = max(RETRY_DELAY_S * 2**attempt, (retry_after(error) or 0) + 0.5)
            if deadline is not None and time.monotonic() + delay + MIN_CALL_TIMEOUT_S > deadline:
                raise
            time.sleep(delay)
    raise AssertionError("unreachable")
