"""
Integration tests — database operations, learning engine, agent helpers.
Uses an in-memory SQLite database — no external services required.
Run: pytest tests/integration/ -v
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def db_engine():
    """In-memory SQLite engine for integration tests."""
    from app.db.models import create_all, get_engine
    engine = get_engine("sqlite:///:memory:")
    create_all(engine)
    return engine


@pytest.fixture(scope="module")
def session_factory(db_engine):
    from app.db.models import get_session_factory
    return get_session_factory(db_engine)


@pytest.fixture
def db_session(session_factory):
    session = session_factory()
    yield session
    session.rollback()
    session.close()


def _make_db_job(db, **kwargs) -> "Job":
    from app.db.models import Job
    job = Job(
        external_id=kwargs.get("external_id", f"test_{datetime.utcnow().timestamp()}"),
        title=kwargs.get("title", "Python Developer"),
        company=kwargs.get("company", "TestCorp"),
        location=kwargs.get("location", "Hyderabad"),
        description=kwargs.get("description", "Build Python services using FastAPI and PostgreSQL"),
        required_skills=json.dumps(kwargs.get("required_skills", ["Python", "FastAPI", "Docker"])),
        preferred_skills="[]",
        apply_url="https://naukri.com/test",
        experience_min=kwargs.get("exp_min", 0.0),
        experience_max=kwargs.get("exp_max", 2.0),
        final_score=kwargs.get("final_score", None),
    )
    db.add(job)
    db.flush()
    return job


def _make_db_profile(db) -> "UserProfile":
    from app.db.models import UserProfile
    profile = UserProfile(
        name="Test User",
        email="test@example.com",
        total_experience_years=1.5,
        resume_text="Python FastAPI React Docker PostgreSQL LangChain RAG developer",
        preferred_locations=json.dumps(["Hyderabad", "Remote"]),
        preferred_roles=json.dumps(["Backend Developer", "AI Engineer"]),
    )
    db.add(profile)
    db.flush()
    return profile


def _make_db_skill(db, profile_id: int, name: str, is_primary: bool = False) -> "UserSkill":
    from app.db.models import UserSkill
    skill = UserSkill(
        profile_id=profile_id,
        name=name,
        category="backend",
        is_primary=is_primary,
        source="resume",
    )
    db.add(skill)
    db.flush()
    return skill


# ─────────────────────────────────────────────────────────────────────────────
# Database CRUD
# ─────────────────────────────────────────────────────────────────────────────


class TestJobCRUD:
    def test_create_job(self, db_session):
        job = _make_db_job(db_session, title="ML Engineer", company="AI Labs")
        assert job.id is not None
        assert job.title == "ML Engineer"

    def test_get_required_skills(self, db_session):
        job = _make_db_job(db_session, required_skills=["Python", "TensorFlow", "Docker"])
        assert "Python" in job.get_required_skills()
        assert "TensorFlow" in job.get_required_skills()

    def test_all_required_skills_deduplicates(self, db_session):
        job = _make_db_job(db_session)
        job.preferred_skills = json.dumps(["Python", "Git"])  # Python duplicated
        all_skills = job.all_required_skills()
        assert all_skills.count("Python") == 1

    def test_unique_external_id_constraint(self, db_session):
        from sqlalchemy.exc import IntegrityError
        _make_db_job(db_session, external_id="unique_id_123")
        db_session.commit()
        with pytest.raises(IntegrityError):
            _make_db_job(db_session, external_id="unique_id_123")

    def test_score_fields_nullable(self, db_session):
        job = _make_db_job(db_session)
        assert job.final_score is None
        assert job.resume_match_score is None


class TestUserProfileCRUD:
    def test_create_profile(self, db_session):
        profile = _make_db_profile(db_session)
        assert profile.id is not None
        assert profile.name == "Test User"

    def test_get_preferred_locations(self, db_session):
        profile = _make_db_profile(db_session)
        locs = profile.get_preferred_locations()
        assert "Hyderabad" in locs
        assert "Remote" in locs

    def test_get_preferred_roles(self, db_session):
        profile = _make_db_profile(db_session)
        roles = profile.get_preferred_roles()
        assert "Backend Developer" in roles

    def test_add_skills_to_profile(self, db_session):
        profile = _make_db_profile(db_session)
        _make_db_skill(db_session, profile.id, "Python", is_primary=True)
        _make_db_skill(db_session, profile.id, "FastAPI")
        db_session.commit()

        from app.db.models import UserSkill
        skills = db_session.query(UserSkill).filter_by(profile_id=profile.id).all()
        assert len(skills) == 2
        primary = [s for s in skills if s.is_primary]
        assert len(primary) == 1
        assert primary[0].name == "Python"


class TestApplicationCRUD:
    def test_create_application(self, db_session):
        from app.db.models import Application, ApplicationStatus
        job = _make_db_job(db_session, external_id="app_test_job")
        db_session.commit()

        app = Application(
            job_id=job.id,
            status=ApplicationStatus.APPLIED,
            applied_at=datetime.utcnow(),
            notes="Applied via Naukri",
        )
        db_session.add(app)
        db_session.flush()
        assert app.id is not None
        assert app.status == ApplicationStatus.APPLIED

    def test_application_status_enum_values(self):
        from app.db.models import ApplicationStatus
        assert ApplicationStatus.APPLIED == "applied"
        assert ApplicationStatus.INTERVIEW_SCHEDULED == "interview_scheduled"
        assert ApplicationStatus.SELECTED == "selected"
        assert ApplicationStatus.REJECTED == "rejected"


class TestSkillGapCRUD:
    def test_create_skill_gap(self, db_session):
        from app.db.models import SkillGap
        job = _make_db_job(db_session, external_id="gap_test_job")
        db_session.commit()

        gap = SkillGap(job_id=job.id, skill_name="Kubernetes", category="devops")
        db_session.add(gap)
        db_session.flush()
        assert gap.id is not None

    def test_query_gaps_by_skill(self, db_session):
        from app.db.models import SkillGap
        job1 = _make_db_job(db_session, external_id="gap_q1")
        job2 = _make_db_job(db_session, external_id="gap_q2")
        db_session.commit()

        db_session.add(SkillGap(job_id=job1.id, skill_name="AWS"))
        db_session.add(SkillGap(job_id=job2.id, skill_name="AWS"))
        db_session.commit()

        from sqlalchemy import func
        rows = (
            db_session.query(SkillGap.skill_name, func.count(SkillGap.id))
            .group_by(SkillGap.skill_name)
            .filter(SkillGap.skill_name == "AWS")
            .all()
        )
        assert rows[0][1] >= 2


# ─────────────────────────────────────────────────────────────────────────────
# Learning Engine Integration
# ─────────────────────────────────────────────────────────────────────────────


class TestLearningEngineIntegration:
    def setup_method(self):
        from app.services.learning_engine import LearningEngine
        self.engine = LearningEngine()

    def test_weights_defined_for_all_signals(self):
        for sig in ["apply", "save", "ignore", "reject"]:
            assert sig in self.engine.WEIGHTS
        assert self.engine.WEIGHTS["apply"] > 0
        assert self.engine.WEIGHTS["ignore"] < 0
        assert self.engine.WEIGHTS["reject"] < self.engine.WEIGHTS["ignore"]

    def test_get_top_positive_signals_returns_dict(self):
        # Patch session_scope to return empty signals
        with patch("app.services.learning_engine.session_scope") as mock_scope:
            mock_db = MagicMock()
            mock_db.query.return_value.all.return_value = []
            mock_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_scope.return_value.__exit__ = MagicMock(return_value=False)

            result = self.engine.get_top_positive_signals(n=5)
            assert "preferred_companies" in result
            assert "preferred_locations" in result
            assert "preferred_skills" in result

    def test_no_boost_when_few_signals(self):
        """Learning boost should be 0 when fewer than 5 signals."""
        with patch.object(self.engine, "get_preferences") as mock_prefs:
            mock_prefs.return_value = {
                "company_scores": {},
                "location_scores": {},
                "skill_scores": {},
                "title_keyword_scores": {},
                "total_signals": 3,  # fewer than 5
            }
            job = MagicMock()
            job.final_score = 70.0
            job.company = "SomeCorp"
            job.location = "Hyderabad"
            job.get_required_skills.return_value = ["Python"]

            boost = self.engine.apply_learning_boost(job)
            assert boost == 0.0

    def test_positive_boost_for_preferred_company(self):
        with patch.object(self.engine, "get_preferences") as mock_prefs:
            mock_prefs.return_value = {
                "company_scores": {"google": 5.0},
                "location_scores": {},
                "skill_scores": {},
                "title_keyword_scores": {},
                "total_signals": 10,
            }
            job = MagicMock()
            job.final_score = 70.0
            job.company = "Google India"
            job.location = "Hyderabad"
            job.get_required_skills.return_value = []

            boost = self.engine.apply_learning_boost(job)
            assert boost > 0

    def test_negative_boost_for_avoided_company(self):
        with patch.object(self.engine, "get_preferences") as mock_prefs:
            mock_prefs.return_value = {
                "company_scores": {"badcorp": -3.0},
                "location_scores": {},
                "skill_scores": {},
                "title_keyword_scores": {},
                "total_signals": 10,
            }
            job = MagicMock()
            job.final_score = 60.0
            job.company = "BadCorp Solutions"
            job.location = "Mumbai"
            job.get_required_skills.return_value = []

            boost = self.engine.apply_learning_boost(job)
            assert boost < 0

    def test_boost_bounded(self):
        with patch.object(self.engine, "get_preferences") as mock_prefs:
            mock_prefs.return_value = {
                "company_scores": {"google": 1000.0},
                "location_scores": {"hyderabad": 1000.0},
                "skill_scores": {"python": 1000.0},
                "title_keyword_scores": {},
                "total_signals": 20,
            }
            job = MagicMock()
            job.final_score = 70.0
            job.company = "Google"
            job.location = "Hyderabad"
            job.get_required_skills.return_value = ["Python"]

            boost = self.engine.apply_learning_boost(job)
            assert boost <= 10.0
            assert boost >= -10.0


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────


class TestConfig:
    def test_ranking_weights_loaded(self):
        from app.core.config import settings
        cfg = settings.ranking
        total = cfg.resume_match + cfg.skill_match + cfg.location_match + cfg.experience_match + cfg.company_reputation
        assert abs(total - 1.0) < 0.001, f"Weights should sum to 1.0, got {total}"

    def test_default_target_roles_not_empty(self):
        from app.core.config import settings
        assert len(settings.search.target_roles) > 0

    def test_default_locations_not_empty(self):
        from app.core.config import settings
        assert len(settings.search.locations) > 0

    def test_reputable_companies_all_returns_dict(self):
        from app.core.config import settings
        company_map = settings.reputable_companies.all_companies()
        assert isinstance(company_map, dict)
        # Tier1 companies should score 100
        if settings.reputable_companies.tier1:
            first_tier1 = settings.reputable_companies.tier1[0].lower()
            assert company_map[first_tier1] == 100

    def test_experience_bounds(self):
        from app.core.config import settings
        assert settings.search.experience_min >= 0
        assert settings.search.experience_max >= settings.search.experience_min
