"""
FastAPI dashboard — REST API for the AI Job Hunter.
Mounted by uvicorn via: app.api.main:app
"""
from __future__ import annotations

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.db.session import get_session
from app.db.models import Job, Application, SkillGap, ApplicationStatus

app = FastAPI(
    title="AI Job Hunter",
    version=settings.app.version,
    description="Autonomous job hunting agent dashboard",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "app": settings.app.name, "version": settings.app.version}


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/jobs", tags=["Jobs"])
def list_jobs(limit: int = 20, db: Session = Depends(get_session)):
    """Return top scored jobs."""
    jobs = (
        db.query(Job)
        .filter(Job.final_score.isnot(None))
        .order_by(Job.final_score.desc())
        .limit(limit)
        .all()
    )
    return [_job_dict(j) for j in jobs]


@app.get("/jobs/{job_id}", tags=["Jobs"])
def get_job(job_id: int, db: Session = Depends(get_session)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(j)


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/stats", tags=["Analytics"])
def stats(db: Session = Depends(get_session)):
    """Application and job statistics."""
    total = db.query(Job).count()
    scored = db.query(Job).filter(Job.final_score.isnot(None)).count()
    alerted = db.query(Job).filter(Job.alert_sent == True).count()

    app_rows = (
        db.query(Application.status, func.count(Application.id))
        .group_by(Application.status)
        .all()
    )
    return {
        "total_jobs_tracked": total,
        "scored_jobs": scored,
        "alerts_sent": alerted,
        "applications": {s: c for s, c in app_rows},
    }


@app.get("/skillgaps", tags=["Analytics"])
def skillgaps(limit: int = 20, db: Session = Depends(get_session)):
    """Top skill gaps across all discovered jobs."""
    rows = (
        db.query(SkillGap.skill_name, func.count(SkillGap.id).label("cnt"))
        .group_by(SkillGap.skill_name)
        .order_by(func.count(SkillGap.id).desc())
        .limit(limit)
        .all()
    )
    return [{"skill": r.skill_name, "jobs_requiring": r.cnt} for r in rows]


# ── Applications ──────────────────────────────────────────────────────────────

@app.get("/applications", tags=["Applications"])
def list_applications(db: Session = Depends(get_session)):
    apps = db.query(Application).order_by(Application.applied_at.desc()).all()
    return [
        {
            "id": a.id,
            "job_id": a.job_id,
            "status": a.status,
            "applied_at": str(a.applied_at) if a.applied_at else None,
            "notes": a.notes,
        }
        for a in apps
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_dict(j: Job) -> dict:
    return {
        "id": j.id,
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "experience": f"{j.experience_min or 0}-{j.experience_max or 0} yrs",
        "required_skills": j.get_required_skills(),
        "scores": {
            "final": j.final_score,
            "resume_match": j.resume_match_score,
            "skill_match": j.skill_match_score,
            "location_match": j.location_match_score,
            "experience_match": j.experience_match_score,
            "company_reputation": j.company_reputation_score,
        },
        "apply_url": j.apply_url,
        "source": j.source,
        "posted_date": str(j.posted_date) if j.posted_date else None,
        "discovered_at": str(j.discovered_at) if j.discovered_at else None,
        "alert_sent": j.alert_sent,
    }
