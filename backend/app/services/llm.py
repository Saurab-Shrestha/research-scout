"""Thin LLM adapter over four providers (ADR-09): Gemini, OpenAI, Anthropic and any OpenAI-compatible
server (Ollama, LM Studio, OpenRouter...). Callers see three functions: generate_structured, search_text, embed.

The provider, model and keys come from Settings → AI provider (the app_settings row "llm"), falling back to .env.
"""

import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from functools import cache, wraps

import anthropic
import httpx
import openai
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.core.config import settings


class LLMError(Exception):
    pass


@dataclass
class LLMResult[T: BaseModel]:
    parsed: T
    model: str
    input_tokens: int
    output_tokens: int


PROVIDERS = {
    # name: (label, default model, can search the web, can embed, default embedding model)
    "gemini": ("Google Gemini", "gemini-3.8-flash", True, True, "gemini-embedding-001"),
    "openai": ("OpenAI", "gpt-5-mini", True, True, "text-embedding-3-small"),
    "anthropic": ("Anthropic Claude", "claude-opus-5-5", True, False, None),
    "openai_compatible": ("OpenAI-compatible (Ollama, LM Studio, OpenRouter)", "llama3.1", False, True, "nomic-embed-text"),
}
EMBEDDING_DIM = 768


@dataclass(frozen=True)
class Config:
    provider: str = "gemini"
    model: str = ""
    keys: dict = field(default_factory=dict)  # provider -> API key
    base_url: str = ""  # openai_compatible only
    vertexai: bool = True  # gemini only
    embedding_provider: str = "gemini"
    embedding_model: str = ""
    usd_per_million_input: float = 0.0
    usd_per_million_output: float = 0.0
    usd_per_search: float = 0.0

    @property
    def chat_model(self) -> str:
        return self.model or PROVIDERS[self.provider][1]

    @property
    def embed_model(self) -> str:
        return self.embedding_model or PROVIDERS[self.embedding_provider][4] or ""


def env_config() -> Config:
    return Config(
        provider=settings.llm_provider, model=settings.extraction_model,
        keys={"gemini": settings.google_api_key, "openai": settings.openai_api_key,
              "anthropic": settings.anthropic_api_key, "openai_compatible": settings.openai_compatible_api_key},
        base_url=settings.openai_compatible_base_url, vertexai=settings.google_genai_use_vertexai,
        embedding_provider=settings.embedding_provider, embedding_model=settings.embedding_model,
        usd_per_million_input=settings.llm_usd_per_million_input,
        usd_per_million_output=settings.llm_usd_per_million_output, usd_per_search=settings.grounded_search_usd_each,
    )


def merge(saved: dict) -> Config:
    """Settings saved in the app win over .env; a key saved as "" falls back to .env."""
    base = env_config()
    keys = base.keys | {k: v for k, v in (saved.get("keys") or {}).items() if v}
    fields = {k: v for k, v in saved.items() if k in Config.__dataclass_fields__ and k != "keys" and v is not None}
    # A model or embedding model from .env belongs to the .env provider, not to one picked in the app.
    if fields.get("provider", base.provider) != base.provider:
        fields.setdefault("model", "")
    if fields.get("embedding_provider", base.embedding_provider) != base.embedding_provider:
        fields.setdefault("embedding_model", "")
    return Config(**(base.__dict__ | fields | {"keys": keys}))


_config_cache: tuple[float, Config] | None = None
_config_lock = threading.Lock()


def config() -> Config:
    # ponytail: re-read every 5 s so the worker picks up Settings changes without a restart.
    global _config_cache
    with _config_lock:
        if _config_cache and time.monotonic() - _config_cache[0] < 5:
            return _config_cache[1]
        from app.db.models import AppSetting  # local import: models are not needed to use the adapter in tests
        from app.db.session import SessionLocal
        try:
            with SessionLocal() as db:
                row = db.get(AppSetting, "llm")
                cfg = merge(row.value if row else {})
        except Exception:  # database unavailable (scripts, evals): .env only
            cfg = env_config()
        _config_cache = (time.monotonic(), cfg)
        return cfg


def reset_config() -> None:
    global _config_cache
    with _config_lock:
        _config_cache = None


def _wrap_errors(fn):
    """Network and API failures become LLMError so callers can skip one item instead of crashing a job."""
    @wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (errors.APIError, httpx.HTTPError, openai.OpenAIError, anthropic.AnthropicError) as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
    return inner


# ponytail: process-wide meter; correct because a worker runs one job at a time. Key by job if that changes.
USAGE: Counter = Counter()
_usage_lock = threading.Lock()


def _meter(input_tokens: int, output_tokens: int, searches: int = 0) -> None:
    with _usage_lock:
        USAGE["input_tokens"] += input_tokens or 0
        USAGE["output_tokens"] += output_tokens or 0
        USAGE["searches"] += searches


def usage_cost(usage: Counter) -> float:
    cfg = config()
    return round(usage["input_tokens"] / 1e6 * cfg.usd_per_million_input
                 + usage["output_tokens"] / 1e6 * cfg.usd_per_million_output
                 + usage["searches"] * cfg.usd_per_search, 4)


# One shared client per provider and credentials. Without the lock, parallel first calls each build a client;
# the extras are garbage-collected mid-request and genai.Client.__del__ closes their connection pool.
_client_lock = threading.Lock()


@cache
def _make_client(provider: str, key: str, base_url: str, vertexai: bool):
    if provider == "gemini":
        return genai.Client(vertexai=vertexai, api_key=key)
    if provider == "anthropic":
        return anthropic.Anthropic(api_key=key)
    return openai.OpenAI(api_key=key or "not-needed", base_url=base_url or None)  # local servers take any key


def _client(provider: str | None = None):
    cfg = config()
    provider = provider or cfg.provider
    key = cfg.keys.get(provider, "")
    if provider == "openai_compatible" and not cfg.base_url:
        raise LLMError("Set the server URL for the OpenAI-compatible provider in Settings → AI provider")
    if not key and provider != "openai_compatible":
        raise LLMError(f"No API key for {PROVIDERS[provider][0]}. Add one in Settings → AI provider.")
    with _client_lock:
        return _make_client(provider, key, cfg.base_url if provider == "openai_compatible" else "", cfg.vertexai)


@_wrap_errors
def generate_structured[T: BaseModel](system: str, user: str, schema: type[T], model: str | None = None) -> LLMResult[T]:
    cfg = config()
    model = model or cfg.chat_model
    client = _client()
    if cfg.provider == "gemini":
        r = client.models.generate_content(model=model, contents=user, config=types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json", response_schema=schema, temperature=0))
        usage = r.usage_metadata
        tokens = ((usage.prompt_token_count or 0) if usage else 0, (usage.candidates_token_count or 0) if usage else 0)
        try:
            parsed = schema.model_validate_json(r.text)
        except Exception as e:  # malformed or truncated JSON
            raise LLMError(f"invalid structured output: {e}") from e
    elif cfg.provider == "anthropic":
        r = client.messages.parse(model=model, max_tokens=16000, system=system,
                                  messages=[{"role": "user", "content": user}], output_format=schema)
        if r.stop_reason == "refusal" or r.parsed_output is None:
            raise LLMError(f"no structured output (stop reason: {r.stop_reason})")
        parsed, tokens = r.parsed_output, (r.usage.input_tokens, r.usage.output_tokens)
    else:
        r = client.chat.completions.parse(model=model, response_format=schema, messages=[
            {"role": "system", "content": system}, {"role": "user", "content": user}])
        message = r.choices[0].message
        if message.parsed is None:
            raise LLMError(f"no structured output: {message.refusal or r.choices[0].finish_reason}")
        parsed = message.parsed
        tokens = (r.usage.prompt_tokens, r.usage.completion_tokens) if r.usage else (0, 0)
    _meter(*tokens)
    return LLMResult(parsed=parsed, model=model, input_tokens=tokens[0], output_tokens=tokens[1])


# Claude models that take the dynamic-filtering web search tool; others use the basic variant.
_DYNAMIC_SEARCH = ("claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-5",
                   "claude-sonnet-4-6")


@_wrap_errors
def search_text(prompt: str, model: str | None = None) -> tuple[str, list[str]]:
    """Answer a prompt with live web search. Returns (answer text, search queries it ran).

    Searches are billed separately from tokens; callers should cap how often this runs.
    """
    cfg = config()
    model = model or cfg.chat_model
    if not PROVIDERS[cfg.provider][2]:
        raise LLMError(f"{PROVIDERS[cfg.provider][0]} has no web search; pick another provider in Settings → AI provider")
    client = _client()
    if cfg.provider == "gemini":
        r = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0))
        usage = r.usage_metadata
        _meter((usage.prompt_token_count or 0) if usage else 0, (usage.candidates_token_count or 0) if usage else 0, 1)
        metadata = r.candidates[0].grounding_metadata if r.candidates else None
        return r.text or "", list((metadata.web_search_queries or []) if metadata else [])
    if cfg.provider == "anthropic":
        tool = "web_search_20260209" if model.startswith(_DYNAMIC_SEARCH) else "web_search_20250305"
        messages, queries = [{"role": "user", "content": prompt}], []
        for _ in range(3):  # a long search turn can pause; send it back so the server continues
            r = client.messages.create(model=model, max_tokens=8000, messages=messages,
                                       tools=[{"type": tool, "name": "web_search", "max_uses": 5}])
            server = getattr(r.usage, "server_tool_use", None)
            _meter(r.usage.input_tokens, r.usage.output_tokens, getattr(server, "web_search_requests", 0) or 0)
            queries += [b.input.get("query", "") for b in r.content if b.type == "server_tool_use"]
            if r.stop_reason != "pause_turn":
                break
            messages = [*messages, {"role": "assistant", "content": r.content}]
        return "".join(b.text for b in r.content if b.type == "text"), queries
    r = client.responses.create(model=model, input=prompt, tools=[{"type": "web_search"}])
    calls = [o for o in r.output if o.type == "web_search_call"]
    _meter(r.usage.input_tokens if r.usage else 0, r.usage.output_tokens if r.usage else 0, len(calls))
    return r.output_text or "", [q for c in calls if (q := getattr(getattr(c, "action", None), "query", None))]


@_wrap_errors
def embed(texts: list[str]) -> list[list[float]]:
    """Semantic-similarity embeddings, batched. Vectors from different models are not comparable."""
    cfg = config()
    model, vectors = cfg.embed_model, []
    client = _client(cfg.embedding_provider)
    for i in range(0, len(texts), 100):
        batch = texts[i:i + 100]
        if cfg.embedding_provider == "gemini":
            r = client.models.embed_content(model=model, contents=batch, config=types.EmbedContentConfig(
                task_type="SEMANTIC_SIMILARITY", output_dimensionality=EMBEDDING_DIM))
            vectors += [e.values for e in r.embeddings]
        else:
            extra = {"dimensions": EMBEDDING_DIM} if model.startswith("text-embedding-3") else {}
            r = client.embeddings.create(model=model, input=batch, **extra)
            vectors += [d.embedding for d in r.data]
    return vectors
