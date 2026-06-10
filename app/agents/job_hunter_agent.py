"""
Job Hunter Agent — main orchestrator.
Runs on APScheduler, coordinates: scraping → parsing → scoring → alerting.

SESSION BUG FIX (v2):
  SQLAlchemy ORM objects become "detached" once their session closes.
  Accessing any attribute on a detached object raises:
    sqlalchemy.orm.exc.DetachedInstanceError

  Fix strategy:
    - Introduce JobData / ProfileData plain dataclasses.
    - Every session_scope block converts ORM → dataclass before returning.
    - ORM objects never leave a session_scope block.
    - Profile/skills cache stores dataclasses, not ORM objects.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.models import (
    Application,
    ApplicationStatus,
    Job,
    JobEmbedding,
    SkillGap,
    UserProfile,
    UserSkill,
)
from app.db.session import session_scope
from app.scrapers.naukri_scraper import NaukriScraper, RawJob
from app.services.embedding_engine import get_embedding_engine
from app.services.learning_engine import LearningEngine
from app.services.profile_engine import ProfileEngine
from app.services.ranking_engine import RankingEngine, SkillGapAnalyzer
from app.services.telegram_service import TelegramService


# ─────────────────────────────────────────────────────────────────────────────
# Plain dataclasses — safe to pass around outside sessions
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class JobData:
    """Detached, session-safe snapshot of a Job row."""
    id: int
    external_id: str
    title: str
    company: str
    location: str
    description: str
    required_skills: List[str]
    apply_url: str
    experience_min: float
    experience_max: float
    final_score: Optional[float]
    resume_match_score: Optional[float]
    skill_match_score: Optional[float]
    location_match_score: Optional[float]
    experience_match_score: Optional[float]
    company_reputation_score: Optional[float]
    alert_sent: bool
    discovered_at: Optional[datetime]

    @classmethod
    def from_orm(cls, job: Job) -> "JobData":
        return cls(
            id=job.id,
            external_id=job.external_id or "",
            title=job.title or "",
            company=job.company or "",
            location=job.location or "",
            description=job.description or "",
            required_skills=job.get_required_skills(),
            apply_url=job.apply_url or "",
            experience_min=job.experience_min or 0.0,
            experience_max=job.experience_max or 5.0,
            final_score=job.final_score,
            resume_match_score=job.resume_match_score,
            skill_match_score=job.skill_match_score,
            location_match_score=job.location_match_score,
            experience_match_score=job.experience_match_score,
            company_reputation_score=job.company_reputation_score,
            alert_sent=job.alert_sent or False,
            discovered_at=job.discovered_at,
        )


@dataclass
class ProfileData:
    """Detached, session-safe snapshot of UserProfile + skills."""
    id: int
    name: str
    email: str
    total_experience_years: float
    resume_text: str
    preferred_locations: List[str]
    preferred_roles: List[str]
    skills: List[str]           # skill names only
    primary_skills: List[str]

    @classmethod
    def from_orm(cls, profile: UserProfile, skills: List[UserSkill]) -> "ProfileData":
        return cls(
            id=profile.id,
            name=profile.name or "",
            email=profile.email or "",
            total_experience_years=profile.total_experience_years or 0.0,
            resume_text=profile.resume_text or "",
            preferred_locations=profile.get_preferred_locations(),
            preferred_roles=profile.get_preferred_roles(),
            skills=[s.name for s in skills],
            primary_skills=[s.name for s in skills if s.is_primary],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Thin ORM adapters so ranking / gap services work with ProfileData
# ─────────────────────────────────────────────────────────────────────────────

class _ProfileAdapter:
    """Makes ProfileData look like UserProfile to RankingEngine."""
    def __init__(self, pd: ProfileData):
        self.total_experience_years = pd.total_experience_years
        self._locs = pd.preferred_locations
        self._roles = pd.preferred_roles

    def get_preferred_locations(self): return self._locs
    def get_preferred_roles(self):     return self._roles


class _SkillAdapter:
    """Makes a string skill name look like UserSkill to RankingEngine."""
    def __init__(self, name: str):
        self.name = name


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class JobHunterAgent:
    """
    Central orchestrator. Called by APScheduler every N minutes.
    All inter-method communication uses plain dataclasses, never raw ORM objects.
    """

    def __init__(self):
        self.embedding    = get_embedding_engine()
        self.ranking      = RankingEngine()
        self.gap_analyzer = SkillGapAnalyzer()
        self.learning     = LearningEngine()
        self.telegram     = TelegramService()
        self.profile_engine = ProfileEngine()
        self._profile_cache: Optional[ProfileData] = None

    # ── Bootstrap ─────────────────────────────────────────────────────────

    async def bootstrap(self):
        logger.info("Agent bootstrap starting...")
        self.embedding.load()
        self._profile_cache = await self._load_profile()
        if self._profile_cache and self._profile_cache.resume_text:
            self.embedding.set_resume_embedding(self._profile_cache.resume_text)
        logger.success("Agent bootstrap complete")

    async def _load_profile(self) -> Optional[ProfileData]:
        """Build/refresh profile and return a session-safe ProfileData."""
        try:
            profile_orm, skills_orm = await self.profile_engine.build_or_refresh_profile()
            pd = ProfileData.from_orm(profile_orm, skills_orm)
            logger.info(
                f"Profile loaded: {pd.name}, "
                f"{len(pd.skills)} skills, "
                f"{pd.total_experience_years} yrs exp"
            )
            return pd
        except Exception as e:
            logger.error(f"Profile load failed: {e}")
            return None

    # ── Main cycle ────────────────────────────────────────────────────────

    async def run_cycle(self):
        logger.info("=== Job hunter cycle starting ===")

        if self._profile_cache is None:
            await self.bootstrap()

        profile = self._profile_cache
        if not profile:
            logger.error("No profile available — skipping cycle")
            return

        # 1. Scrape & Auto-apply (same session, no re-login)
        all_raw: List[RawJob] = []
        async with NaukriScraper() as scraper:
            for role in settings.search.target_roles:
                for location in settings.search.locations:
                    try:
                        raw = await scraper.search_jobs(
                            role, location,
                            settings.search.experience_min,
                            settings.search.experience_max,
                        )
                        all_raw.extend(raw)
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"Scrape error ({role}/{location}): {e}")

            logger.info(f"Raw jobs collected: {len(all_raw)}")

            # 2. Persist new jobs → get back safe JobData list
            new_job_data = self._persist_new_jobs(all_raw)
            logger.info(f"New jobs persisted: {len(new_job_data)}")
            if not new_job_data:
                logger.info("No new jobs this cycle")
                return

            # 3. Score → returns new JobData list with scores filled in
            scored = self._score_jobs(new_job_data, profile)

            # Apply to jobs meeting the overall threshold OR having a skill match score >= 50%
            high_match = [
                j for j in scored
                if (j.final_score or 0) >= settings.ranking.alert_threshold
                or (j.skill_match_score or 0) >= 50.0
            ]
            if high_match:
                applied_count = 0
                # Attempt auto-apply for top 5 high-match jobs per cycle
                for job in high_match[:5]:
                    try:
                        success = await scraper.auto_apply(job.apply_url)
                        if success:
                            self.mark_applied(
                                job.id,
                                notes="Auto-applied via Naukri direct apply",
                            )
                            await self.telegram.send_message(
                                f"✅ *Auto-Applied!* Just applied to *{job.title}* at *{job.company}*."
                            )
                            applied_count += 1
                    except Exception as e:
                        logger.error(f"Auto-apply pipeline error for job {job.id}: {e}")

                logger.info(f"Auto-apply phase done: {applied_count} applied out of {len(high_match[:5])} attempted")

                # Send Telegram alerts after apply attempts
                await self._send_alerts(high_match[:5], profile)

        # 5. Skill gaps
        self._update_skill_gaps(new_job_data, profile)

        # 6. Persist FAISS
        self.embedding.save_index()

        logger.success(f"Cycle done: {len(new_job_data)} new, {len(high_match)} alerts sent")

    # ── Persist new jobs ──────────────────────────────────────────────────

    def _persist_new_jobs(self, raw_jobs: List[RawJob]) -> List[JobData]:
        """
        Write new jobs to DB. Returns List[JobData] (session-safe).
        All ORM work happens inside the with block.
        """
        result: List[JobData] = []
        with session_scope() as db:
            for raw in raw_jobs:
                try:
                    existing = db.query(Job).filter_by(external_id=raw.external_id).first()
                    if existing:
                        continue
                    job = Job(
                        external_id=raw.external_id,
                        title=raw.title,
                        company=raw.company,
                        location=raw.location,
                        description=raw.description,
                        required_skills=json.dumps(raw.required_skills),
                        preferred_skills="[]",
                        apply_url=raw.apply_url,
                        job_type=raw.job_type,
                        source=raw.source,
                        posted_date=self._parse_date(raw.posted_date),
                        **self._parse_experience(raw.experience),
                    )
                    db.add(job)
                    db.flush()             # assigns job.id
                    result.append(JobData.from_orm(job))   # snapshot while session alive
                except Exception as e:
                    logger.error(f"Persist error for '{raw.title}': {e}")
        return result

    # ── Score jobs ────────────────────────────────────────────────────────

    def _score_jobs(self, jobs: List[JobData], profile: ProfileData) -> List[JobData]:
        """
        Load each job fresh, score it, save scores, return updated JobData list.
        Each job is re-fetched, modified, and snapshot-ed inside its own
        mini session to avoid DetachedInstanceError.
        """
        profile_adapter  = _ProfileAdapter(profile)
        skill_adapters   = [_SkillAdapter(s) for s in profile.skills]
        scored: List[JobData] = []

        for jd in jobs:
            try:
                with session_scope() as db:
                    job = db.query(Job).get(jd.id)
                    if not job:
                        continue

                    # Score using ORM obj (still live inside session)
                    job = self.ranking.score_job(job, profile_adapter, skill_adapters)

                    # Learning boost
                    boost = self.learning.apply_learning_boost_from_data(jd)
                    job.final_score = round(min(100.0, (job.final_score or 0) + boost), 2)
                    job.last_scored_at = datetime.utcnow()

                    # FAISS
                    if not self.embedding.job_in_index(job.id):
                        job_text = (
                            f"{job.title} {job.company} "
                            f"{' '.join(job.get_required_skills())} "
                            f"{job.description or ''}"
                        )
                        position = self.embedding.add_job(job.id, job_text)
                        db.add(JobEmbedding(
                            job_id=job.id,
                            faiss_index=position,
                            embedding_model=settings.models.embedding_model,
                        ))

                    # Snapshot BEFORE session closes
                    snapshot = JobData.from_orm(job)
                    scored.append(snapshot)

            except Exception as e:
                logger.error(f"Score error for job id={jd.id}: {e}")

        return sorted(scored, key=lambda j: j.final_score or 0, reverse=True)

    # ── Alerts ────────────────────────────────────────────────────────────

    async def _send_alerts(self, jobs: List[JobData], profile: ProfileData):
        for jd in jobs:
            if jd.alert_sent:
                continue
            # Compute gaps from the dataclass directly
            gaps = self._compute_gaps(jd, profile)
            await self.telegram.send_job_alert_data(jd, gaps)
            # Mark alert_sent in DB
            with session_scope() as db:
                job = db.query(Job).get(jd.id)
                if job:
                    job.alert_sent = True

    def _compute_gaps(self, jd: JobData, profile: ProfileData) -> List[str]:
        user_lower = {s.lower() for s in profile.skills}
        return [s for s in jd.required_skills if s.lower() not in user_lower]

    # ── Skill gaps ────────────────────────────────────────────────────────

    def _update_skill_gaps(self, jobs: List[JobData], profile: ProfileData):
        user_lower = {s.lower() for s in profile.skills}
        with session_scope() as db:
            for jd in jobs:
                gaps = [s for s in jd.required_skills if s.lower() not in user_lower]
                for gap in gaps:
                    db.add(SkillGap(job_id=jd.id, skill_name=gap))

    # ── Application tracker ───────────────────────────────────────────────

    def mark_applied(self, job_id: int, notes: str = ""):
        with session_scope() as db:
            app = db.query(Application).filter_by(job_id=job_id).first()
            if not app:
                db.add(Application(
                    job_id=job_id,
                    status=ApplicationStatus.APPLIED,
                    applied_at=datetime.utcnow(),
                    notes=notes,
                ))
            else:
                app.status = ApplicationStatus.APPLIED
                app.applied_at = datetime.utcnow()
            # Learning signal
            job = db.query(Job).get(job_id)
            if job:
                self.learning.record_signal(job, "apply")

    def mark_ignored(self, job_id: int):
        with session_scope() as db:
            job = db.query(Job).get(job_id)
            if job:
                self.learning.record_signal(job, "ignore")

    # ── Query helpers (API / Telegram bot) ────────────────────────────────

    def get_top_jobs(self, n: int = 20) -> List[JobData]:
        with session_scope() as db:
            jobs = (
                db.query(Job)
                .filter(Job.final_score.isnot(None))
                .order_by(Job.final_score.desc())
                .limit(n)
                .all()
            )
            return [JobData.from_orm(j) for j in jobs]   # snapshot inside session

    def get_new_jobs(self, hours: int = 1) -> List[JobData]:
        since = datetime.utcnow() - timedelta(hours=hours)
        with session_scope() as db:
            jobs = (
                db.query(Job)
                .filter(Job.discovered_at >= since)
                .order_by(Job.final_score.desc())
                .limit(20)
                .all()
            )
            return [JobData.from_orm(j) for j in jobs]

    def get_application_stats(self) -> dict:
        from sqlalchemy import func
        with session_scope() as db:
            stats  = db.query(Application.status, func.count(Application.id)).group_by(Application.status).all()
            total  = db.query(Job).count()
            scored = db.query(Job).filter(Job.final_score.isnot(None)).count()
            return {
                "total_jobs_tracked": total,
                "scored_jobs": scored,
                "applications": {s: c for s, c in stats},
            }

    # ── Helpers ───────────────────────────────────────────────────────────

    def _parse_experience(self, exp_str: str) -> dict:
        match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", exp_str or "")
        if match:
            return {"experience_min": float(match.group(1)), "experience_max": float(match.group(2))}
        match = re.search(r"(\d+(?:\.\d+)?)", exp_str or "")
        if match:
            v = float(match.group(1))
            return {"experience_min": v, "experience_max": v + 2}
        return {"experience_min": 0.0, "experience_max": 5.0}

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        match = re.search(r"(\d+)\s*(day|hour|week|month)", date_str.lower())
        if not match:
            return datetime.utcnow()
        val, unit = int(match.group(1)), match.group(2)
        delta = {
            "hour": timedelta(hours=val),
            "day": timedelta(days=val),
            "week": timedelta(weeks=val),
            "month": timedelta(days=val * 30),
        }.get(unit, timedelta(days=1))
        return datetime.utcnow() - delta
