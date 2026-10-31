from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1 import applications, drafts, opportunities, professors, profile, research_jobs, settings, sources
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
api.include_router(applications.router)
api.include_router(drafts.router)
api.include_router(settings.router)
app.include_router(api)

# The React app (web/), when built with `npm run build`, is served from the same origin as the API.
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


@app.get("/{path:path}", include_in_schema=False)
def web_app(path: str):
    if path.startswith("api/") or not (WEB_DIST / "index.html").is_file():
        raise HTTPException(404)
    file = (WEB_DIST / path).resolve()
    if path and file.is_file() and file.is_relative_to(WEB_DIST):
        return FileResponse(file)
    return FileResponse(WEB_DIST / "index.html")  # client-side routes like /tracker
