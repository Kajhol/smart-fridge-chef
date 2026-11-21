import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from smart_fridge_chef.recipes import llm
from smart_fridge_chef.recipes.schema import RecipeSelection

SELECTION = {"picks": [{"recipe_id": "fc_1001", "description": "Masz jajka i masło."}]}


class FakeGeminiModels:
    def __init__(self, text: str):
        self.text = text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


class FakeGroqCompletions:
    def __init__(self, text: str):
        self.text = text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))])


def test_gemini_returns_validated_schema():
    models = FakeGeminiModels(json.dumps(SELECTION))
    result = llm.generate("prompt", "system", RecipeSelection, "gemini-3.1-flash-lite", SimpleNamespace(models=models))

    assert result.picks[0].recipe_id == "fc_1001"
    config = models.calls[0]["config"]
    assert config.temperature == 0
    assert config.response_json_schema == RecipeSelection.model_json_schema()


def test_groq_strips_prefix_and_sends_schema():
    completions = FakeGroqCompletions(json.dumps(SELECTION))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = llm.generate("prompt", "system", RecipeSelection, "groq/openai/gpt-oss-120b", client)

    assert result.picks[0].description == "Masz jajka i masło."
    call = completions.calls[0]
    assert call["model"] == "openai/gpt-oss-120b"
    assert call["temperature"] == 0
    assert call["response_format"]["json_schema"]["schema"] == RecipeSelection.model_json_schema()
    assert call["messages"][0] == {"role": "system", "content": "system"}


def test_invalid_response_raises():
    models = FakeGeminiModels('{"picks": "nie lista"}')
    with pytest.raises(ValidationError):
        llm.generate("p", "s", RecipeSelection, "gemini-3.1-flash-lite", SimpleNamespace(models=models))


def test_unknown_provider():
    with pytest.raises(ValueError):
        llm.generate("p", "s", RecipeSelection, "mistral-large", object())


def test_model_from_env(monkeypatch):
    monkeypatch.setenv("RECIPE_MODEL", "groq/openai/gpt-oss-120b")
    assert llm.recipe_model() == "groq/openai/gpt-oss-120b"
    monkeypatch.delenv("RECIPE_MODEL")
    assert llm.recipe_model() == llm.DEFAULT_MODEL


def test_usage_is_recorded_for_both_providers():
    usage: list[dict] = []
    models = FakeGeminiModels(json.dumps(SELECTION))
    models.generate_content = lambda **kw: SimpleNamespace(
        text=json.dumps(SELECTION),
        usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=20, thoughts_token_count=5),
    )
    llm.generate("p", "s", RecipeSelection, "gemini-3.1-flash-lite", SimpleNamespace(models=models), usage)

    completions = FakeGroqCompletions(json.dumps(SELECTION))
    completions.create = lambda **kw: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(SELECTION)))],
        usage=SimpleNamespace(prompt_tokens=80, completion_tokens=10),
    )
    llm.generate("p", "s", RecipeSelection, "groq/x", SimpleNamespace(chat=SimpleNamespace(completions=completions)), usage)

    assert usage == [
        {"model": "gemini-3.1-flash-lite", "input_tokens": 100, "output_tokens": 25},
        {"model": "groq/x", "input_tokens": 80, "output_tokens": 10},
    ]


def test_ollama_uses_openai_compatible_api(monkeypatch):
    completions = FakeGroqCompletions(json.dumps(SELECTION))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = llm.generate("prompt", "system", RecipeSelection, "ollama/qwen2.5:3b", client)

    assert result.picks[0].recipe_id == "fc_1001"
    assert completions.calls[0]["model"] == "qwen2.5:3b"


def test_ollama_needs_no_api_key(monkeypatch):
    from smart_fridge_chef.recipes import router

    monkeypatch.setenv("RECIPE_MODEL", "ollama/qwen2.5:3b")
    assert router.get_llm() is not None


def test_transient_errors_are_retried(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_DELAY_S", 0)
    attempts = []

    class Overloaded(Exception):
        code = 503

    def generate_content(**kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise Overloaded("high demand")
        return SimpleNamespace(text=json.dumps(SELECTION))

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    assert llm.generate("p", "s", RecipeSelection, "gemini-3.1-flash-lite", client).picks
    assert len(attempts) == 3


def test_permanent_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_DELAY_S", 0)
    attempts = []

    class BadKey(Exception):
        code = 400

    def generate_content(**kwargs):
        attempts.append(1)
        raise BadKey("invalid key")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    with pytest.raises(BadKey):
        llm.generate("p", "s", RecipeSelection, "gemini-3.1-flash-lite", client)
    assert len(attempts) == 1


def test_timeouts_are_retried(monkeypatch):
    import httpx

    monkeypatch.setattr(llm, "RETRY_DELAY_S", 0)
    attempts = []

    def generate_content(**kwargs):
        attempts.append(1)
        if len(attempts) < 2:
            raise httpx.ReadTimeout("slow")
        return SimpleNamespace(text=json.dumps(SELECTION))

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    assert llm.generate("p", "s", RecipeSelection, "gemini-3.1-flash-lite", client).picks
    assert len(attempts) == 2


def test_no_call_after_the_request_budget_is_spent():
    import time

    attempts = []
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: attempts.append(1)))
    with pytest.raises(llm.BudgetExceeded):
        llm.generate("p", "s", RecipeSelection, "gemini-3.1-flash-lite", client, deadline=time.monotonic() - 1)
    assert attempts == []


def test_retry_is_skipped_when_the_wait_would_pass_the_budget(monkeypatch):
    import time

    monkeypatch.setattr(llm, "RETRY_DELAY_S", 30)
    attempts = []

    class Overloaded(Exception):
        code = 503

    def generate_content(**kwargs):
        attempts.append(1)
        raise Overloaded("high demand")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    with pytest.raises(Overloaded):
        llm.generate("p", "s", RecipeSelection, "gemini-3.1-flash-lite", client, deadline=time.monotonic() + 10)
    assert len(attempts) == 1


def test_call_timeout_is_capped_by_the_budget(monkeypatch):
    import time

    monkeypatch.delenv("LLM_TIMEOUT_S", raising=False)
    assert llm.remaining_timeout("gemini-3.1-flash-lite", None) == llm.CALL_TIMEOUT_S
    assert llm.remaining_timeout("ollama/qwen2.5:7b", None) == llm.LOCAL_CALL_TIMEOUT_S
    assert llm.remaining_timeout("gemini-3.1-flash-lite", time.monotonic() + 5) <= 5
    monkeypatch.setenv("LLM_TIMEOUT_S", "7")
    assert llm.call_timeout("gemini-3.1-flash-lite") == 7
    monkeypatch.setenv("RECIPES_BUDGET_S", "12")
    assert llm.request_budget("groq/x") == 12


def test_groq_rate_limit_is_retried_after_the_wait_it_asks_for(monkeypatch):
    import openai

    waits = []
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    response = SimpleNamespace(status_code=429, headers={}, request=None)
    limit = openai.RateLimitError(
        "Error code: 429 - Rate limit reached ... Please try again in 4.3875s.",
        response=SimpleNamespace(**vars(response), json=dict),
        body={"error": {"code": "rate_limit_exceeded"}},
    )
    attempts = []

    def create(**kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise limit
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(SELECTION)))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert llm.generate("p", "s", RecipeSelection, "groq/openai/gpt-oss-120b", client).picks
    assert len(attempts) == 2 and waits and waits[0] >= 4.3875
    assert llm.error_kind(limit) == "RateLimitError 429"


def test_retry_after_reads_gemini_retry_delay_and_header():
    assert llm.retry_after(Exception("429 RESOURCE_EXHAUSTED ... 'retryDelay': '17s'")) == 17
    headers = {"retry-after": "3"}
    assert llm.retry_after(SimpleNamespace(response=SimpleNamespace(headers=headers))) == 3
    assert llm.retry_after(Exception("bad json")) is None
