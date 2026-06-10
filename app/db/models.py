"""
Database models — AI Job Hunter Agent
Full schema: jobs, applications, profile, skills, embeddings, learning signals
"""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class ApplicationStatus(str, PyEnum):
    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_DONE = "interview_done"
    REJECTED = "rejected"
    SELECTED = "selected"
    IGNORED = "ignored"


class SkillCategory(str, PyEnum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    AI_ML = "ai_ml"
    DEVOPS = "devops"
    DATABASE = "database"
    CLOUD = "cloud"
    LANGUAGE = "language"
    OTHER = "other"


# ─────────────────────────────────────────────────────────────────────────────
# Profile & Skills
# ─────────────────────────────────────────────────────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    email = Column(String(200))
    phone = Column(String(50))
    current_title = Column(String(200))
    total_experience_years = Column(Float, default=0.0)
    summary = Column(Text)
    education = Column(Text)          # JSON list
    certifications = Column(Text)     # JSON list
    preferred_locations = Column(Text)  # JSON list
    preferred_roles = Column(Text)    # JSON list
    target_salary_min = Column(Integer)
    target_salary_max = Column(Integer)
    resume_text = Column(Text)        # raw extracted text
    profile_scraped_at = Column(DateTime)
    resume_parsed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    skills = relationship("UserSkill", back_populates="profile", cascade="all, delete-orphan")

    def get_education(self):
        return json.loads(self.education or "[]")

    def get_preferred_locations(self):
        return json.loads(self.preferred_locations or "[]")

    def get_preferred_roles(self):
        return json.loads(self.preferred_roles or "[]")


class UserSkill(Base):
    __tablename__ = "user_skills"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    name = Column(String(100), nullable=False)
    category = Column(String(50), default=SkillCategory.OTHER)
    proficiency = Column(String(50))   # beginner / intermediate / expert
    years_experience = Column(Float, default=0.0)
    is_primary = Column(Boolean, default=False)
    source = Column(String(50))        # resume / profile / inferred

    profile = relationship("UserProfile", back_populates="skills")

    __table_args__ = (
        UniqueConstraint("profile_id", "name", name="uq_profile_skill"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(100), unique=True, nullable=False)  # Naukri job ID
    title = Column(String(300), nullable=False)
    company = Column(String(200))
    location = Column(String(200))
    experience_min = Column(Float)
    experience_max = Column(Float)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    description = Column(Text)
    required_skills = Column(Text)    # JSON list
    preferred_skills = Column(Text)   # JSON list
    job_type = Column(String(50))     # full_time / contract / remote
    posted_date = Column(DateTime)
    apply_url = Column(String(500))
    source = Column(String(50), default="naukri")
    is_active = Column(Boolean, default=True)

    # Scores (computed after ingestion)
    resume_match_score = Column(Float)
    skill_match_score = Column(Float)
    location_match_score = Column(Float)
    experience_match_score = Column(Float)
    company_reputation_score = Column(Float)
    final_score = Column(Float)

    # Meta
    discovered_at = Column(DateTime, default=datetime.utcnow)
    last_scored_at = Column(DateTime)
    alert_sent = Column(Boolean, default=False)

    embedding = relationship("JobEmbedding", back_populates="job", uselist=False, cascade="all, delete-orphan")
    application = relationship("Application", back_populates="job", uselist=False)
    skill_gaps = relationship("SkillGap", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_jobs_final_score", "final_score"),
        Index("idx_jobs_discovered_at", "discovered_at"),
        Index("idx_jobs_company", "company"),
        Index("idx_jobs_location", "location"),
    )

    def get_required_skills(self) -> list[str]:
        return json.loads(self.required_skills or "[]")

    def get_preferred_skills(self) -> list[str]:
        return json.loads(self.preferred_skills or "[]")

    def all_required_skills(self) -> list[str]:
        return list(set(self.get_required_skills() + self.get_preferred_skills()))


class JobEmbedding(Base):
    __tablename__ = "job_embeddings"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), unique=True, nullable=False)
    faiss_index = Column(Integer)      # position in FAISS index
    embedding_model = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="embedding")


# ─────────────────────────────────────────────────────────────────────────────
# Applications & Tracking
# ─────────────────────────────────────────────────────────────────────────────

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), unique=True, nullable=False)
    status = Column(String(50), default=ApplicationStatus.SAVED)
    applied_at = Column(DateTime)
    interview_date = Column(DateTime)
    notes = Column(Text)
    resume_version = Column(String(100))
    cover_letter = Column(Text)
    hr_contact = Column(String(200))
    offer_amount = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("Job", back_populates="application")
    events = relationship("ApplicationEvent", back_populates="application", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_applications_status", "status"),
        Index("idx_applications_applied_at", "applied_at"),
    )


class ApplicationEvent(Base):
    """Audit trail for each status change"""
    __tablename__ = "application_events"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    from_status = Column(String(50))
    to_status = Column(String(50), nullable=False)
    note = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="events")


# ─────────────────────────────────────────────────────────────────────────────
# Skill Gaps
# ─────────────────────────────────────────────────────────────────────────────

class SkillGap(Base):
    __tablename__ = "skill_gaps"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    skill_name = Column(String(100), nullable=False)
    category = Column(String(50))
    frequency = Column(Integer, default=1)   # how often this gap appears across jobs
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="skill_gaps")

    __table_args__ = (
        Index("idx_skill_gaps_skill", "skill_name"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Learning Signals
# ─────────────────────────────────────────────────────────────────────────────

class LearningSignal(Base):
    """
    Records implicit feedback: apply = positive, ignore = negative.
    Used by the learning engine to re-weight recommendations.
    """
    __tablename__ = "learning_signals"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    signal_type = Column(String(20), nullable=False)  # apply / ignore / save / reject
    job_title = Column(String(300))
    company = Column(String(200))
    required_skills = Column(Text)   # snapshot at signal time
    location = Column(String(200))
    score_at_signal = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_learning_signal_type", "signal_type"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Analytics Snapshots
# ─────────────────────────────────────────────────────────────────────────────

class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"

    id = Column(Integer, primary_key=True)
    snapshot_date = Column(String(10), unique=True)   # YYYY-MM-DD
    total_jobs_found = Column(Integer, default=0)
    high_match_jobs = Column(Integer, default=0)
    applications_sent = Column(Integer, default=0)
    interviews = Column(Integer, default=0)
    avg_match_score = Column(Float)
    top_skills_demanded = Column(Text)    # JSON list
    top_companies = Column(Text)          # JSON list
    top_locations = Column(Text)          # JSON list
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# DB setup helper
# ─────────────────────────────────────────────────────────────────────────────

def get_engine(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    # Enable WAL mode for better concurrent reads
    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return engine


def create_all(engine):
    Base.metadata.create_all(engine)


def get_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
