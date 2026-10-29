"""Milestone 1 tables. Opportunities, funding, matching, applications and drafts arrive in later migrations."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), dict: JSONB, list: JSONB}


class Entity:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CandidateProfile(Entity, Base):
    __tablename__ = "candidate_profiles"

    name: Mapped[str]
    education_json: Mapped[list] = mapped_column(default=list)
    experience_json: Mapped[list] = mapped_column(default=list)
    skills_json: Mapped[list] = mapped_column(default=list)
    test_scores_json: Mapped[list] = mapped_column(default=list)
    research_interests: Mapped[list] = mapped_column(default=list)
    career_goals: Mapped[str | None] = mapped_column(Text)
    intended_start_term: Mapped[str | None]
    funding_preferences_json: Mapped[dict] = mapped_column(default=dict)


class University(Entity, Base):
    __tablename__ = "universities"

    name: Mapped[str]
    normalized_name: Mapped[str] = mapped_column(index=True)
    country: Mapped[str | None] = mapped_column(String(2))
    website_url: Mapped[str | None]
    graduate_admissions_url: Mapped[str | None]
    openalex_id: Mapped[str | None] = mapped_column(unique=True)
    ror_id: Mapped[str | None] = mapped_column(unique=True)
    aliases: Mapped[list | None]  # acronyms and alternative names from OpenAlex, e.g. ["MIT"]


class Department(Entity, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("university_id", "name"),)

    university_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("universities.id"))
    name: Mapped[str]
    website_url: Mapped[str | None]


class Professor(Entity, Base):
    __tablename__ = "professors"

    university_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("universities.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    name: Mapped[str] = mapped_column(index=True)
    title: Mapped[str | None]
    email: Mapped[str | None]
    faculty_url: Mapped[str | None] = mapped_column(unique=True)
    orcid: Mapped[str | None] = mapped_column(unique=True)
    openalex_id: Mapped[str | None] = mapped_column(unique=True)
    research_summary: Mapped[str | None] = mapped_column(Text)
    accepting_students: Mapped[bool | None]
    last_verified_at: Mapped[datetime | None]


class Publication(Entity, Base):
    __tablename__ = "publications"

    doi: Mapped[str | None] = mapped_column(unique=True)
    openalex_id: Mapped[str | None] = mapped_column(unique=True)
    arxiv_id: Mapped[str | None] = mapped_column(unique=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    publication_year: Mapped[int | None]
    url: Mapped[str | None]
    open_access_url: Mapped[str | None]


class ProfessorPublication(Base):
    __tablename__ = "professor_publications"

    professor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("professors.id"), primary_key=True)
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), primary_key=True)
    author_position: Mapped[str | None]
    identity_confidence: Mapped[float | None]


class Source(Entity, Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("canonical_url", "content_hash"),)

    url: Mapped[str | None]
    # Pasted text without a URL uses "urn:sha256:<hash>" so dedup still works.
    canonical_url: Mapped[str]
    domain: Mapped[str | None] = mapped_column(index=True)
    source_type: Mapped[str]  # web_page | social_post | alert_email
    fetched_at: Mapped[datetime] = mapped_column(server_default=func.now())
    content_hash: Mapped[str] = mapped_column(String(64))
    http_status: Mapped[int | None]
    content_type: Mapped[str | None]
    raw_content: Mapped[str] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text)


class Evidence(Entity, Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_entity", "entity_type", "entity_id"),)

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    entity_type: Mapped[str]
    entity_id: Mapped[uuid.UUID]
    field_name: Mapped[str]
    excerpt: Mapped[str] = mapped_column(Text)
    claim_value_json: Mapped[dict | list | None] = mapped_column(JSONB)
    verification_status: Mapped[str]
    confidence: Mapped[float | None]
    extractor_version: Mapped[str]


class ResearchJob(Entity, Base):
    __tablename__ = "research_jobs"

    job_type: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True)
    input_json: Mapped[dict] = mapped_column(default=dict)
    result_json: Mapped[dict | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    locked_at: Mapped[datetime | None]
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    tokens_used: Mapped[int] = mapped_column(default=0)
    completed_at: Mapped[datetime | None]


class JobEvent(Entity, Base):
    __tablename__ = "job_events"

    research_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_jobs.id"), index=True)
    event_type: Mapped[str]
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(default=dict)
