"""AI provider settings, editable in the app. Keys are stored in the local database and never returned."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import AppSetting, CandidateProfile, Publication
from app.db.session import get_db
from app.services import llm

router = APIRouter(prefix="/settings", tags=["settings"])

Provider = Literal["gemini", "openai", "anthropic", "openai_compatible"]
EmbeddingProvider = Literal["gemini", "openai", "openai_compatible"]


class ProviderInfo(BaseModel):
    id: str
    label: str
    default_model: str
    web_search: bool
    embeddings: bool
    default_embedding_model: str | None
    key_saved: bool  # saved in the app
    key_in_env: bool  # set in .env (used when nothing is saved)


class LLMSettingsOut(BaseModel):
    provider: Provider
    model: str
    base_url: str
    vertexai: bool
    embedding_provider: EmbeddingProvider
    embedding_model: str
    usd_per_million_input: float
    usd_per_million_output: float
    usd_per_search: float
    providers: list[ProviderInfo]


class LLMSettingsIn(BaseModel):
    provider: Provider | None = None
    model: str | None = None  # "" = the provider's default
    base_url: str | None = None
    vertexai: bool | None = None
    embedding_provider: EmbeddingProvider | None = None
    embedding_model: str | None = None
    usd_per_million_input: float | None = None
    usd_per_million_output: float | None = None
    usd_per_search: float | None = None
    keys: dict[Provider, str] = {}  # "" removes the saved key


class LLMSettingsSaved(LLMSettingsOut):
    embeddings_reset: bool  # embedding model changed: stored vectors were cleared, re-run evaluation


class TestResult(BaseModel):
    chat: str  # "ok" or the error
    embeddings: str


def _saved(db: Session) -> dict:
    row = db.get(AppSetting, "llm")
    return dict(row.value) if row else {}


def _out(saved: dict) -> LLMSettingsOut:
    cfg, env = llm.merge(saved), llm.env_config()
    return LLMSettingsOut(
        provider=cfg.provider, model=cfg.model, base_url=cfg.base_url, vertexai=cfg.vertexai,
        embedding_provider=cfg.embedding_provider, embedding_model=cfg.embedding_model,
        usd_per_million_input=cfg.usd_per_million_input, usd_per_million_output=cfg.usd_per_million_output,
        usd_per_search=cfg.usd_per_search,
        providers=[ProviderInfo(id=p, label=label, default_model=model, web_search=search, embeddings=emb,
                                default_embedding_model=emb_model, key_saved=bool((saved.get("keys") or {}).get(p)),
                                key_in_env=bool(env.keys.get(p)))
                   for p, (label, model, search, emb, emb_model) in llm.PROVIDERS.items()],
    )


@router.get("/llm", response_model=LLMSettingsOut)
def get_llm_settings(db: Session = Depends(get_db)):
    return _out(_saved(db))


@router.put("/llm", response_model=LLMSettingsSaved)
def put_llm_settings(body: LLMSettingsIn, db: Session = Depends(get_db)):
    saved = _saved(db)
    before = llm.merge(saved)
    changes = body.model_dump(exclude_unset=True, exclude={"keys"})
    keys = (saved.get("keys") or {}) | {k: v.strip() for k, v in body.keys.items()}
    saved = saved | changes | {"keys": {k: v for k, v in keys.items() if v}}
    after = llm.merge(saved)
    if after.provider == "openai_compatible" and not after.base_url:
        raise HTTPException(422, "Set the server URL for the OpenAI-compatible provider")

    reset = (before.embedding_provider, before.embed_model) != (after.embedding_provider, after.embed_model)
    if reset:  # vectors from different models are not comparable; matching re-embeds on the next evaluation
        db.execute(update(Publication).values(embedding=None))
        db.execute(update(CandidateProfile).values(interest_embeddings=None))
    row = db.get(AppSetting, "llm") or AppSetting(key="llm")
    row.value = saved
    db.add(row)
    db.commit()
    llm.reset_config()
    return LLMSettingsSaved(**_out(saved).model_dump(), embeddings_reset=reset)


class _Ping(BaseModel):
    ok: bool


@router.post("/llm/test", response_model=TestResult)
def test_llm_settings():
    """One tiny structured call and one embedding with the saved settings. Web search is not tested (it is billed)."""
    llm.reset_config()
    try:
        llm.generate_structured("Reply with ok set to true.", "ping", _Ping)
        chat = "ok"
    except llm.LLMError as e:
        chat = str(e)
    try:
        llm.embed(["ping"])
        embeddings = "ok"
    except llm.LLMError as e:
        embeddings = str(e)
    return TestResult(chat=chat, embeddings=embeddings)
