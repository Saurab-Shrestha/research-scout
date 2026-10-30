from pydantic import BaseModel, Field


class EmailDraft(BaseModel):
    subject: str
    body: str
    cited_papers: list[str] = Field(description="Exact titles, copied from the supplied paper list, that the body mentions")


class SopSection(BaseModel):
    heading: str
    points: list[str]


class SopOutline(BaseModel):
    sections: list[SopSection]
    cited_papers: list[str] = Field(description="Exact titles, copied from the supplied paper list, that the outline mentions")
