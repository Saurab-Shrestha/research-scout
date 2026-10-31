from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CandidateProfile
from app.db.session import get_db
from app.schemas.profile import CandidateProfileIn, CandidateProfileOut

router = APIRouter(prefix="/profile", tags=["profile"])


def _to_out(p: CandidateProfile) -> CandidateProfileOut:
    return CandidateProfileOut(
        id=str(p.id),
        name=p.name,
        education=p.education_json,
        experience=p.experience_json,
        skills=p.skills_json,
        test_scores=p.test_scores_json,
        research_interests=p.research_interests,
        career_goals=p.career_goals,
        intended_start_term=p.intended_start_term,
        funding_preferences=p.funding_preferences_json,
        target_degrees=p.target_degrees,
        target_countries=p.target_countries,
    )


def _current(db: Session) -> CandidateProfile | None:
    # Single-user MVP: one profile row.
    return db.scalars(select(CandidateProfile).limit(1)).first()


@router.get("", response_model=CandidateProfileOut)
def get_profile(db: Session = Depends(get_db)):
    profile = _current(db)
    if profile is None:
        raise HTTPException(404, "Profile not created yet")
    return _to_out(profile)


@router.put("", response_model=CandidateProfileOut)
def put_profile(body: CandidateProfileIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    profile = _current(db) or CandidateProfile(name=body.name)
    profile.name = data["name"]
    profile.education_json = data["education"]
    profile.experience_json = data["experience"]
    profile.skills_json = data["skills"]
    profile.test_scores_json = data["test_scores"]
    profile.research_interests = data["research_interests"]
    profile.career_goals = data["career_goals"]
    profile.intended_start_term = data["intended_start_term"]
    profile.funding_preferences_json = data["funding_preferences"]
    profile.target_degrees = data["target_degrees"]
    profile.target_countries = data["target_countries"]
    db.add(profile)
    db.commit()
    return _to_out(profile)
