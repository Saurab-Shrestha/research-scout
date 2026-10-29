from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1 import opportunities, professors, profile, research_jobs, sources
from app.db.session import get_db

app = FastAPI(title="Research Scout", version="0.1.0")

api = APIRouter(prefix="/api/v1")


@api.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


api.include_router(profile.router)
api.include_router(sources.router)
api.include_router(professors.router)
api.include_router(research_jobs.router)
api.include_router(opportunities.router)
app.include_router(api)
