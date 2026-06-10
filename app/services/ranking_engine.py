"""
Job Ranking Engine
Computes weighted final score for each job.
Formula: 40% resume_match + 20% skill_match + 15% location + 15% experience + 10% company
"""
from __future__ import annotations

import re
from typing import List, Optional

from app.core.config import settings
from app.core.logging import logger
from app.db.models import Job, UserProfile, UserSkill
from app.services.embedding_engine import get_embedding_engine
from app.services.skill_taxonomy import normalize_skill, ALL_SKILLS_LOWER


class RankingEngine:

    def __init__(self):
        self.cfg = settings.ranking
        self.company_scores = settings.reputable_companies.all_companies()
        self.embedding = get_embedding_engine()

    # ── Main entry point ──────────────────────────────────────────────────

    def score_job(
        self,
        job: Job,
        profile: UserProfile,
        user_skills: List[UserSkill],
    ) -> Job:
        """Compute all component scores and final_score on the Job object."""
        job_text = self._build_job_text(job)
        user_skills_lower = {s.name.lower() for s in user_skills}
        user_locs_lower = {loc.lower() for loc in profile.get_preferred_locations()}

        # Component scores
        resume_score = self.embedding.score_job_against_resume(job_text)
        skill_score = self._skill_match(job, user_skills_lower)
        location_score = self._location_match(job, user_locs_lower)
        exp_score = self._experience_match(job, profile.total_experience_years)
        company_score = self._company_reputation(job.company or "")

        job.resume_match_score = round(resume_score, 2)
        job.skill_match_score = round(skill_score, 2)
        job.location_match_score = round(location_score, 2)
        job.experience_match_score = round(exp_score, 2)
        job.company_reputation_score = round(company_score, 2)

        job.final_score = round(
            resume_score * self.cfg.resume_match
            + skill_score * self.cfg.skill_match
            + location_score * self.cfg.location_match
            + exp_score * self.cfg.experience_match
            + company_score * self.cfg.company_reputation,
            2,
        )
        return job

    def rank_jobs(
        self,
        jobs: List[Job],
        profile: UserProfile,
        user_skills: List[UserSkill],
    ) -> List[Job]:
        """Score and rank all jobs, return top N."""
        scored = [self.score_job(j, profile, user_skills) for j in jobs]
        ranked = sorted(scored, key=lambda j: j.final_score or 0, reverse=True)
        return ranked[:self.cfg.top_n]

    # ── Component scorers ─────────────────────────────────────────────────

    def _skill_match(self, job: Job, user_skills_lower: set[str]) -> float:
        required = {s.lower() for s in job.get_required_skills()}
        if not required:
            return 50.0  # No requirements = neutral score
        matched = required & user_skills_lower
        return round(len(matched) / len(required) * 100, 2)

    def _location_match(self, job: Job, preferred_locs: set[str]) -> float:
        if not job.location:
            return 50.0
        job_loc = job.location.lower()
        if "remote" in job_loc:
            return 100.0
        for loc in preferred_locs:
            if loc in job_loc or job_loc in loc:
                return 100.0
        return 0.0

    def _experience_match(self, job: Job, user_exp: float) -> float:
        exp_min = job.experience_min or 0
        exp_max = job.experience_max or 99
        if exp_min <= user_exp <= exp_max:
            return 100.0
        if user_exp < exp_min:
            diff = exp_min - user_exp
            return max(0.0, 100.0 - diff * 25)
        # Overqualified — small penalty
        return 80.0

    def _company_reputation(self, company_name: str) -> float:
        name_lower = company_name.lower()
        for known, score in self.company_scores.items():
            if known in name_lower or name_lower in known:
                return float(score)
        return 30.0  # Unknown company gets baseline

    # ── Helpers ───────────────────────────────────────────────────────────

    def _build_job_text(self, job: Job) -> str:
        parts = [
            job.title or "",
            job.company or "",
            " ".join(job.get_required_skills()),
            job.description or "",
        ]
        return " ".join(p for p in parts if p)


class SkillGapAnalyzer:
    """Identifies skills a job requires that the user doesn't have."""

    def analyze(self, job: Job, user_skills: List[UserSkill]) -> List[str]:
        user_skills_lower = {s.name.lower() for s in user_skills}
        required = [normalize_skill(s) for s in job.all_required_skills()]
        gaps = []
        for skill in required:
            if skill.lower() not in user_skills_lower:
                gaps.append(skill)
        return list(set(gaps))

    def aggregate_gaps(self, jobs: List[Job], user_skills: List[UserSkill]) -> dict[str, int]:
        """Returns {skill: frequency_across_jobs} sorted by frequency."""
        gap_counts: dict[str, int] = {}
        for job in jobs:
            gaps = self.analyze(job, user_skills)
            for g in gaps:
                gap_counts[g] = gap_counts.get(g, 0) + 1
        return dict(sorted(gap_counts.items(), key=lambda x: x[1], reverse=True))
