"""Thin LLM adapter. Gemini today; keep the signature provider-neutral (ADR-09)."""

import threading
from collections import Counter
from dataclasses import dataclass
from functools import cache, wraps

import httpx

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


def _wrap_errors(fn):
    """Network and API failures become LLMError so callers can skip one item instead of crashing a job."""
    @wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (errors.APIError, httpx.HTTPError) as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
    return inner


_client_lock = threading.Lock()

# ponytail: process-wide meter; correct because a worker runs one job at a time. Key by job if that changes.
USAGE: Counter = Counter()
_usage_lock = threading.Lock()


def _meter(response, searches: int = 0) -> None:
    usage = getattr(response, "usage_metadata", None)
    with _usage_lock:
        USAGE["input_tokens"] += (usage.prompt_token_count or 0) if usage else 0
        USAGE["output_tokens"] += (usage.candidates_token_count or 0) if usage else 0
        USAGE["searches"] += searches


def usage_cost(usage: Counter) -> float:
    return round(usage["input_tokens"] / 1e6 * settings.llm_usd_per_million_input
                 + usage["output_tokens"] / 1e6 * settings.llm_usd_per_million_output
                 + usage["searches"] * settings.grounded_search_usd_each, 4)


@cache
def _make_client() -> genai.Client:
    if not settings.google_api_key:
        raise LLMError("GOOGLE_API_KEY is not set")
    return genai.Client(vertexai=settings.google_genai_use_vertexai, api_key=settings.google_api_key)


def _client() -> genai.Client:
    # One shared client. Without the lock, parallel first calls each build a client; the extras are
    # garbage-collected mid-request and genai.Client.__del__ closes their connection pool.
    with _client_lock:
        return _make_client()


@_wrap_errors
def generate_structured[T: BaseModel](system: str, user: str, schema: type[T], model: str) -> LLMResult[T]:
    response = _client().models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
        ),
    )
    _meter(response)
    try:
        parsed = schema.model_validate_json(response.text)
    except Exception as e:  # malformed or truncated JSON
        raise LLMError(f"invalid structured output: {e}") from e
    usage = response.usage_metadata
    return LLMResult(
        parsed=parsed,
        model=model,
        input_tokens=(usage.prompt_token_count or 0) if usage else 0,
        output_tokens=(usage.candidates_token_count or 0) if usage else 0,
    )


@_wrap_errors
def search_text(prompt: str, model: str) -> tuple[str, list[str]]:
    """Ask Gemini with Google Search grounding. Returns (answer text, search queries it ran).

    Grounded searches are billed separately from tokens; callers should cap how often this runs.
    """
    response = _client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0),
    )
    _meter(response, searches=1)
    metadata = response.candidates[0].grounding_metadata if response.candidates else None
    return response.text or "", list((metadata.web_search_queries or []) if metadata else [])


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768


@_wrap_errors
def embed(texts: list[str]) -> list[list[float]]:
    """Semantic-similarity embeddings, batched."""
    vectors = []
    for i in range(0, len(texts), 100):
        response = _client().models.embed_content(
            model=EMBEDDING_MODEL, contents=texts[i:i + 100],
            config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY", output_dimensionality=EMBEDDING_DIM),
        )
        vectors += [e.values for e in response.embeddings]
    return vectors
