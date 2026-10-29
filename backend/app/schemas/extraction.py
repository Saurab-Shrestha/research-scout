"""Output schema for page extraction (prompt 13.2). Every claim carries a verbatim quote."""

from typing import Literal

from pydantic import BaseModel


class Claim(BaseModel):
    value: str | None
    evidence_quote: str | None  # verbatim text from the page supporting the value


PageKind = Literal[
    "faculty_profile", "lab_page", "faculty_directory", "funding_page",
    "admissions_page", "vacancy", "social_post", "other",
]


class PageExtraction(BaseModel):
    page_kind: PageKind
    university: Claim
    department: Claim
    professor_name: Claim
    professor_title: Claim
    institutional_email: Claim
    accepting_students: Claim  # value: "yes" | "no" | null
    research_topics: list[Claim]
    degree_types: list[Claim]
    eligibility_requirements: list[Claim]
    funding_details: list[Claim]
    application_deadline: Claim
    application_url: Claim
    warnings: list[str]  # contradictions, stale-looking content, ambiguity
