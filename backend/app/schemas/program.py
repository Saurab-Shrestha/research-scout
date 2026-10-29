"""Extraction schema for admissions/funding pages. Every claim carries a verbatim quote."""

from pydantic import BaseModel

from app.schemas.extraction import Claim, PageKind


class EnglishRequirement(BaseModel):
    test: str  # e.g. "TOEFL iBT", "IELTS Academic", "PTE Academic", "Duolingo"
    minimum: str | None
    evidence_quote: str | None


class ProgramExtraction(BaseModel):
    page_kind: PageKind
    university: Claim
    program_name: Claim  # e.g. "PhD in Computer Science"
    degree_types: list[Claim]  # values: phd | thesis_masters | course_masters

    guaranteed_funding: Claim  # "yes" when all admitted students in this program are funded
    tuition_coverage: Claim  # "full" | "partial" | "none"
    stipend_amount: Claim  # number only, e.g. "45000"
    stipend_currency: Claim  # "USD" | "CAD"
    stipend_period: Claim  # "year" | "month" | "term"
    funding_duration_years: Claim  # number only
    funding_sources: list[Claim]  # e.g. "research assistantship", "teaching assistantship", "fellowship"
    funding_for_international_students: Claim  # "yes" | "no"
    funding_conditions: list[Claim]

    application_deadline: Claim  # value as YYYY-MM-DD when the date is stated; quote keeps original wording
    deadline_term: Claim  # e.g. "Fall 2027"
    english_tests: list[EnglishRequirement]
    pte_accepted: Claim  # "yes" | "no"
    minimum_gpa: Claim  # as stated, e.g. "3.0/4.0"
    requires_masters_for_phd: Claim  # "yes" | "no"
    supervisor_required_before_admission: Claim  # "yes" | "no"
    prerequisites: list[Claim]
    warnings: list[str]
