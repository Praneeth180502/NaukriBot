"""
Learning Engine
Observes which jobs the user applies for vs ignores,
and produces a preference model for re-ranking.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.db.models import Job, LearningSignal
from app.db.session import session_scope


class LearningEngine:
    """
    Simple preference learning based on explicit signals:
    - apply → strong positive
    - save → weak positive
    - ignore → weak negative
    - reject → strong negative

    Computes preference scores for:
    - Companies (apply history)
    - Locations (apply history)
    - Skills (jobs applied for require these)
    - Title keywords (jobs applied for had these)
    """

    WEIGHTS = {
        "apply": 2.0,
        "save": 0.5,
        "ignore": -0.5,
        "reject": -1.5,
    }

    def __init__(self):
        self._preferences: Optional[dict] = None

    def record_signal(self, job: Job, signal_type: str):
        """Record a user interaction signal."""
        with session_scope() as db:
            signal = LearningSignal(
                job_id=job.id,
                signal_type=signal_type,
                job_title=job.title,
                company=job.company,
                required_skills=json.dumps(job.get_required_skills()),
                location=job.location,
                score_at_signal=job.final_score,
            )
            db.add(signal)
            logger.debug(f"Learning signal: {signal_type} for '{job.title}' at {job.company}")
        self._preferences = None  # Invalidate cache

    def compute_preferences(self) -> dict:
        """
        Returns:
            {
                company_scores: {company: float},
                location_scores: {location: float},
                skill_scores: {skill: float},
                title_keyword_scores: {keyword: float},
            }
        """
        with session_scope() as db:
            signals: List[LearningSignal] = db.query(LearningSignal).all()

        company_scores: Dict[str, float] = {}
        location_scores: Dict[str, float] = {}
        skill_scores: Dict[str, float] = {}
        keyword_scores: Dict[str, float] = {}

        for sig in signals:
            weight = self.WEIGHTS.get(sig.signal_type, 0.0)

            # Company
            if sig.company:
                comp = sig.company.lower()
                company_scores[comp] = company_scores.get(comp, 0.0) + weight

            # Location
            if sig.location:
                loc = sig.location.lower()
                location_scores[loc] = location_scores.get(loc, 0.0) + weight

            # Skills from the job
            try:
                skills = json.loads(sig.required_skills or "[]")
                for skill in skills:
                    sk = skill.lower()
                    skill_scores[sk] = skill_scores.get(sk, 0.0) + weight
            except Exception:
                pass

            # Title keywords
            if sig.job_title:
                for word in sig.job_title.lower().split():
                    if len(word) > 3:
                        keyword_scores[word] = keyword_scores.get(word, 0.0) + weight

        prefs = {
            "company_scores": company_scores,
            "location_scores": location_scores,
            "skill_scores": skill_scores,
            "title_keyword_scores": keyword_scores,
            "total_signals": len(signals),
        }
        self._preferences = prefs
        return prefs

    def get_preferences(self) -> dict:
        if self._preferences is None:
            self._preferences = self.compute_preferences()
        return self._preferences

    def apply_learning_boost(self, job: Job) -> float:
        """
        Returns a boost value [-10, +10] to add to final_score based on learned preferences.
        Works with a live ORM Job object (must be inside a session).
        """
        if not job.final_score:
            return 0.0
        return self._compute_boost(
            company=job.company or "",
            location=job.location or "",
            skills=job.get_required_skills(),
        )

    def apply_learning_boost_from_data(self, jd) -> float:
        """
        Same as apply_learning_boost but accepts a JobData dataclass.
        Safe to call outside any session.
        """
        return self._compute_boost(
            company=jd.company,
            location=jd.location,
            skills=jd.required_skills,
        )

    def _compute_boost(self, company: str, location: str, skills: list) -> float:
        prefs = self.get_preferences()
        if prefs["total_signals"] < 5:
            return 0.0

        boost = 0.0

        if company:
            comp = company.lower()
            comp_score = 0.0
            for pref_comp, score in prefs["company_scores"].items():
                if pref_comp in comp or comp in pref_comp:
                    comp_score = score
                    break
            boost += min(5.0, max(-5.0, comp_score * 2))

        if location:
            loc = location.lower()
            for pref_loc, score in prefs["location_scores"].items():
                if pref_loc in loc or loc in pref_loc:
                    boost += min(3.0, max(-3.0, score * 1.5))
                    break

        if skills:
            skill_boosts = [prefs["skill_scores"].get(s.lower(), 0.0) for s in skills]
            boost += min(2.0, max(-2.0, sum(skill_boosts) / len(skill_boosts)))

        return round(min(10.0, max(-10.0, boost)), 2)

    def get_top_positive_signals(self, n: int = 5) -> dict:
        """Useful for /stats command."""
        prefs = self.get_preferences()
        return {
            "preferred_companies": sorted(
                prefs["company_scores"].items(), key=lambda x: x[1], reverse=True
            )[:n],
            "preferred_locations": sorted(
                prefs["location_scores"].items(), key=lambda x: x[1], reverse=True
            )[:n],
            "preferred_skills": sorted(
                prefs["skill_scores"].items(), key=lambda x: x[1], reverse=True
            )[:n],
        }
