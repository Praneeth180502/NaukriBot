"""
Profile Intelligence Engine
Builds and refreshes the user's profile from:
  1. Resume PDF (primary)
  2. Naukri.com profile (supplement)
  3. Previous application history (inferred preferences)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from app.core.config import settings
from app.core.logging import logger
from app.db.models import SkillCategory, UserProfile, UserSkill
from app.db.session import session_scope
from app.scrapers.naukri_scraper import NaukriScraper, NaukriProfileData
from app.services.resume_parser import ParsedResume, ResumeParser
from app.services.skill_taxonomy import categorize_skill, normalize_skill


class ProfileEngine:
    """Maintains a single UserProfile record, updated from multiple sources."""

    def __init__(self):
        self._parser = ResumeParser()

    async def build_or_refresh_profile(self) -> Tuple[UserProfile, List[UserSkill]]:
        """
        Build or refresh profile. Returns (profile, skills).
        Safe to call repeatedly — will not duplicate.
        """
        with session_scope() as db:
            profile = db.query(UserProfile).first()
            if profile is None:
                profile = UserProfile()
                db.add(profile)
                db.flush()
            profile_id = profile.id

        # Parse resume
        parsed = self._parse_resume()

        # Scrape Naukri profile
        naukri_data = await self._scrape_naukri_profile()

        # Merge and persist
        return self._merge_and_persist(profile_id, parsed, naukri_data)

    def _parse_resume(self) -> Optional[ParsedResume]:
        resume_path = settings.naukri.resume_path
        if not Path(resume_path).exists():
            logger.warning(f"Resume not found at {resume_path}. Skipping resume parse.")
            return None
        try:
            return self._parser.parse(resume_path)
        except Exception as e:
            logger.error(f"Resume parse failed: {e}")
            return None

    async def _scrape_naukri_profile(self) -> Optional[NaukriProfileData]:
        if not settings.naukri.email or not settings.naukri.password:
            logger.warning("Naukri credentials not set — skipping profile scrape")
            return None
        try:
            async with NaukriScraper() as scraper:
                return await scraper.scrape_profile()
        except Exception as e:
            logger.error(f"Naukri profile scrape failed: {e}")
            return None

    def _merge_and_persist(
        self,
        profile_id: int,
        parsed: Optional[ParsedResume],
        naukri: Optional[NaukriProfileData],
    ) -> Tuple[UserProfile, List[UserSkill]]:
        with session_scope() as db:
            profile = db.query(UserProfile).get(profile_id)

            # Populate from resume (primary source)
            if parsed:
                profile.resume_text = parsed.raw_text
                profile.resume_parsed_at = datetime.utcnow()
                if parsed.name:
                    profile.name = parsed.name
                if parsed.email:
                    profile.email = parsed.email
                if parsed.phone:
                    profile.phone = parsed.phone
                if parsed.summary:
                    profile.summary = parsed.summary
                profile.total_experience_years = parsed.total_experience_years
                if parsed.education:
                    profile.education = json.dumps([
                        {"degree": e.degree, "institution": e.institution, "year": e.year}
                        for e in parsed.education
                    ])
                if parsed.target_roles:
                    profile.preferred_roles = json.dumps(parsed.target_roles)

                # Add skills from resume
                for skill in parsed.all_skills:
                    self._upsert_skill(
                        db, profile.id, skill,
                        is_primary=(skill in parsed.primary_skills),
                        source="resume",
                    )

            # Supplement from Naukri
            if naukri:
                profile.profile_scraped_at = datetime.utcnow()
                if naukri.name and not profile.name:
                    profile.name = naukri.name
                if naukri.total_experience:
                    import re
                    m = re.search(r"(\d+(?:\.\d+)?)", naukri.total_experience)
                    if m:
                        profile.total_experience_years = max(
                            profile.total_experience_years or 0,
                            float(m.group(1)),
                        )
                if naukri.preferred_locations:
                    profile.preferred_locations = json.dumps(naukri.preferred_locations)
                for skill in naukri.skills:
                    self._upsert_skill(db, profile.id, skill, source="naukri_profile")

            # Ensure preferred locations fall back to config
            if not profile.preferred_locations:
                profile.preferred_locations = json.dumps(settings.search.locations)

            profile.updated_at = datetime.utcnow()
            db.flush()
            profile_id = profile.id

        # Return fresh objects
        with session_scope() as db:
            profile = db.query(UserProfile).get(profile_id)
            skills = db.query(UserSkill).filter_by(profile_id=profile_id).all()
            # Detach so they're usable outside session
            db.expunge_all()
            return profile, skills

    def _upsert_skill(
        self, db, profile_id: int, skill: str, is_primary: bool = False, source: str = "resume"
    ):
        norm = normalize_skill(skill)
        existing = (
            db.query(UserSkill)
            .filter_by(profile_id=profile_id, name=norm)
            .first()
        )
        if existing:
            if is_primary:
                existing.is_primary = True
            return
        cat = categorize_skill(norm)
        us = UserSkill(
            profile_id=profile_id,
            name=norm,
            category=cat,
            is_primary=is_primary,
            source=source,
        )
        db.add(us)

    def get_profile(self) -> Optional[Tuple[UserProfile, List[UserSkill]]]:
        with session_scope() as db:
            profile = db.query(UserProfile).first()
            if not profile:
                return None
            skills = db.query(UserSkill).filter_by(profile_id=profile.id).all()
            db.expunge_all()
            return profile, skills

    def get_profile_summary(self) -> dict:
        result = self.get_profile()
        if not result:
            return {}
        profile, skills = result
        cats: dict[str, list[str]] = {}
        for sk in skills:
            cat = sk.category or "other"
            cats.setdefault(cat, []).append(sk.name)
        return {
            "name": profile.name,
            "email": profile.email,
            "total_experience_years": profile.total_experience_years,
            "summary": profile.summary,
            "skills_by_category": cats,
            "primary_skills": [s.name for s in skills if s.is_primary],
            "target_roles": profile.get_preferred_roles(),
            "preferred_locations": profile.get_preferred_locations(),
        }
