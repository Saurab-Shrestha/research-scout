"""Thin LLM adapter. Gemini today; keep the signature provider-neutral (ADR-09)."""

from dataclasses import dataclass
from functools import cache

from google import genai
from google.genai import types
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


@cache
def _client() -> genai.Client:
    if not settings.google_api_key:
        raise LLMError("GOOGLE_API_KEY is not set")
    return genai.Client(vertexai=settings.google_genai_use_vertexai, api_key=settings.google_api_key)


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


def search_text(prompt: str, model: str) -> tuple[str, list[str]]:
    """Ask Gemini with Google Search grounding. Returns (answer text, search queries it ran).

    Grounded searches are billed separately from tokens; callers should cap how often this runs.
    """
    response = _client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0),
    )
    metadata = response.candidates[0].grounding_metadata if response.candidates else None
    return response.text or "", list((metadata.web_search_queries or []) if metadata else [])


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768


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
