from typing import Literal

from pydantic import BaseModel, Field


class Education(BaseModel):
    degree: str
    field: str
    university: str
    country: str | None = None
    graduation_year: int | None = None
    gpa: float | None = None
    gpa_scale: float | None = None
    relevant_courses: list[str] = []


class Experience(BaseModel):
    kind: Literal["project", "research", "publication", "work"]
    title: str
    description: str | None = None
    url: str | None = None
    year: int | None = None


class TestScore(BaseModel):
    test: str  # e.g. "IELTS", "TOEFL", "GRE"
    score: str
    taken_on: str | None = None


class FundingPreferences(BaseModel):
    needs_tuition_coverage: bool = True
    needs_living_stipend: bool = True
    requires_funding_at_admission: bool = True
    max_unfunded_cost_usd: float | None = None


class CandidateProfileIn(BaseModel):
    name: str = Field(min_length=1)
    education: list[Education] = []
    experience: list[Experience] = []
    skills: list[str] = []
    test_scores: list[TestScore] = []
    research_interests: list[str] = []
    career_goals: str | None = None
    intended_start_term: str | None = None  # e.g. "Fall 2027"
    funding_preferences: FundingPreferences = FundingPreferences()


class CandidateProfileOut(CandidateProfileIn):
    id: str
