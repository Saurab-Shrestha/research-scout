from typing import Literal

from pydantic import BaseModel, model_validator


class IngestRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    source_type: Literal["web_page", "social_post", "alert_email"] = "web_page"

    @model_validator(mode="after")
    def _url_or_text(self):
        if not (self.url or (self.text and self.text.strip())):
            raise ValueError("provide a url, text, or both")
        if self.text and self.source_type == "web_page":
            self.source_type = "social_post"
        return self


class IngestResponse(BaseModel):
    source_id: str
    canonical_url: str
    content_hash: str
    created: bool


class ExtractResponse(BaseModel):
    source_id: str
    professor_id: str | None
    page_kind: str
    verified_fields: int
    unverified_fields: int
    warnings: list[str]
    input_tokens: int
    output_tokens: int
