import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"  # repo root, regardless of working directory


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/research_scout"
    contact_email: str = ""
    openalex_api_key: str = ""  # free key: https://openalex.org/settings/api

    google_api_key: str = ""
    google_genai_use_vertexai: bool = True  # Vertex AI express mode
    extraction_model: str = "gemini-3.8-flash"
    extraction_max_chars: int = 60_000

    fetch_timeout_s: float = 20.0
    fetch_max_bytes: int = 2_000_000
    fetch_max_redirects: int = 5

    @property
    def user_agent(self) -> str:
        contact = f"; mailto:{self.contact_email}" if self.contact_email else ""
        return f"ResearchScout/0.1 (personal academic research tool{contact})"


settings = Settings()

# httpx logs full request URLs at INFO, which would leak the OpenAlex api_key query parameter.
logging.getLogger("httpx").setLevel(logging.WARNING)
