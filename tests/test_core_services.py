"""
Unit tests — Resume Parser, Ranking Engine, Skill Gap Analyzer.
Run: pytest tests/unit/ -v
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# Skill Taxonomy
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillTaxonomy:
    def test_known_skill_returns_category(self):
        from app.utils.skill_taxonomy import categorize_skill
        assert categorize_skill("Python") == "language"
        assert categorize_skill("FastAPI") == "backend"
        assert categorize_skill("React") == "frontend"
        assert categorize_skill("LangChain") == "ai_ml"
        assert categorize_skill("Docker") == "devops"
        assert categorize_skill("PostgreSQL") == "database"
        assert categorize_skill("AWS") == "cloud"

    def test_unknown_skill_returns_other(self):
        from app.utils.skill_taxonomy import categorize_skill
        assert categorize_skill("SomeMadeUpThing") == "other"

    def test_case_insensitive_categorize(self):
        from app.utils.skill_taxonomy import categorize_skill
        assert categorize_skill("python") == "language"
        assert categorize_skill("FASTAPI") == "backend"

    def test_normalize_skill(self):
        from app.utils.skill_taxonomy import normalize_skill
        assert normalize_skill("python") == "Python"
        assert normalize_skill("fastapi") == "FastAPI"
        assert normalize_skill("react") == "React"

    def test_all_skills_lower_populated(self):
        from app.utils.skill_taxonomy import ALL_SKILLS_LOWER
        assert "python" in ALL_SKILLS_LOWER
        assert "fastapi" in ALL_SKILLS_LOWER
        assert len(ALL_SKILLS_LOWER) > 50


# ─────────────────────────────────────────────────────────────────────────────
# Resume Parser
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_RESUME_TEXT = """
John Doe
john.doe@email.com
+91 9876543210

SUMMARY
Experienced Full Stack Developer with 2 years of experience in Python, FastAPI, React.js
and modern AI/ML frameworks. Worked on RAG systems and LangChain applications.

SKILLS
Python, FastAPI, React.js, Next.js, TypeScript, JavaScript, Java, SQL, PostgreSQL
Docker, GitHub Actions, WebSockets, JWT, LangChain, LlamaIndex, Pydantic AI
RAG, Agentic AI, Vector Databases, Supabase pgvector, Machine Learning

EXPERIENCE
Full Stack Developer Intern | DRDO | 2023-2024
- Built FastAPI microservices for internal data pipelines
- Developed React.js dashboards with WebSocket integration

Software Development Intern | Cognitbotz | 2022-2023
- Implemented LangChain-based RAG system for document Q&A
- Used PostgreSQL with pgvector for semantic search

EDUCATION
B.Tech Computer Science | JNTU Hyderabad | 2024
CGPA: 8.5/10
"""


class TestResumeParser:
    def setup_method(self):
        from app.services.resume_parser import ResumeParser
        self.parser = ResumeParser()

    def test_extract_email(self):
        email = self.parser._extract_email(SAMPLE_RESUME_TEXT)
        assert email == "john.doe@email.com"

    def test_extract_phone(self):
        phone = self.parser._extract_phone(SAMPLE_RESUME_TEXT)
        assert "9876543210" in phone

    def test_extract_name(self):
        name = self.parser._extract_name(SAMPLE_RESUME_TEXT)
        assert "John" in name

    def test_extract_skills(self):
        skills_by_cat, all_skills = self.parser._extract_skills(SAMPLE_RESUME_TEXT)
        all_lower = [s.lower() for s in all_skills]
        assert "python" in all_lower
        assert "fastapi" in all_lower
        assert "react.js" in all_lower or "react" in all_lower
        assert "docker" in all_lower
        assert "postgresql" in all_lower
        assert "langchain" in all_lower

    def test_skills_categorized(self):
        skills_by_cat, _ = self.parser._extract_skills(SAMPLE_RESUME_TEXT)
        assert "backend" in skills_by_cat
        assert "devops" in skills_by_cat
        assert "ai_ml" in skills_by_cat

    def test_calculate_experience(self):
        exp_text = "2 years of experience"
        years = self.parser._calculate_experience([], exp_text)
        assert years == 2.0

    def test_extract_summary(self):
        summary = self.parser._extract_summary(SAMPLE_RESUME_TEXT)
        assert len(summary) > 20

    def test_infer_target_roles(self):
        skills = ["Python", "FastAPI", "React.js", "LangChain", "RAG"]
        roles = self.parser._infer_target_roles(skills, [])
        role_set = set(r.lower() for r in roles)
        assert any("python" in r or "backend" in r or "full stack" in r for r in role_set)
        assert any("ai" in r or "genai" in r for r in role_set)

    def test_primary_skills_limited_to_10(self):
        skills = ["Python", "FastAPI", "React.js", "Docker", "PostgreSQL",
                  "LangChain", "RAG", "TypeScript", "Next.js", "JWT",
                  "WebSockets", "SQLAlchemy", "Redis"]
        primary = self.parser._identify_primary_skills(skills, SAMPLE_RESUME_TEXT)
        assert len(primary) <= 10


# ─────────────────────────────────────────────────────────────────────────────
# Ranking Engine
# ─────────────────────────────────────────────────────────────────────────────

def _make_job(**kwargs):
    """Create a mock Job with defaults."""
    job = MagicMock()
    job.id = kwargs.get("id", 1)
    job.title = kwargs.get("title", "Python Developer")
    job.company = kwargs.get("company", "TechCorp")
    job.location = kwargs.get("location", "Hyderabad")
    job.description = kwargs.get("description", "")
    job.experience_min = kwargs.get("experience_min", 0.0)
    job.experience_max = kwargs.get("experience_max", 2.0)
    job.get_required_skills = lambda: kwargs.get("required_skills", ["Python", "FastAPI"])
    job.get_preferred_skills = lambda: []
    job.all_required_skills = lambda: kwargs.get("required_skills", ["Python", "FastAPI"])
    job.final_score = kwargs.get("final_score", None)
    job.resume_match_score = None
    job.skill_match_score = None
    job.location_match_score = None
    job.experience_match_score = None
    job.company_reputation_score = None
    return job


def _make_profile(**kwargs):
    profile = MagicMock()
    profile.total_experience_years = kwargs.get("exp", 1.0)
    profile.get_preferred_locations = lambda: kwargs.get("locations", ["Hyderabad", "Remote"])
    profile.get_preferred_roles = lambda: []
    return profile


def _make_skill(name):
    skill = MagicMock()
    skill.name = name
    return skill


class TestRankingEngine:
    def setup_method(self):
        with patch("app.services.ranking_engine.get_embedding_engine") as mock_emb:
            mock_emb.return_value.score_job_against_resume.return_value = 75.0
            from app.services.ranking_engine import RankingEngine
            self.engine = RankingEngine()
            self.engine.embedding.score_job_against_resume.return_value = 75.0

    def test_skill_match_perfect(self):
        job = _make_job(required_skills=["Python", "FastAPI", "Docker"])
        user_skills = {"python", "fastapi", "docker"}
        score = self.engine._skill_match(job, user_skills)
        assert score == 100.0

    def test_skill_match_partial(self):
        job = _make_job(required_skills=["Python", "FastAPI", "Kubernetes", "AWS"])
        user_skills = {"python", "fastapi"}
        score = self.engine._skill_match(job, user_skills)
        assert score == 50.0

    def test_skill_match_empty_requirements(self):
        job = _make_job(required_skills=[])
        score = self.engine._skill_match(job, {"python"})
        assert score == 50.0  # Neutral score

    def test_location_match_exact(self):
        job = _make_job(location="Hyderabad")
        pref = {"hyderabad", "remote"}
        score = self.engine._location_match(job, pref)
        assert score == 100.0

    def test_location_match_remote(self):
        job = _make_job(location="Remote / Work from Home")
        score = self.engine._location_match(job, {"hyderabad"})
        assert score == 100.0

    def test_location_match_miss(self):
        job = _make_job(location="Mumbai")
        score = self.engine._location_match(job, {"hyderabad", "remote"})
        assert score == 0.0

    def test_experience_match_within_range(self):
        job = _make_job(experience_min=0, experience_max=2)
        profile = _make_profile(exp=1.0)
        score = self.engine._experience_match(job, 1.0)
        assert score == 100.0

    def test_experience_match_overqualified(self):
        score = self.engine._experience_match(_make_job(experience_min=0, experience_max=2), 5.0)
        assert score == 80.0

    def test_experience_match_underqualified_penalty(self):
        score = self.engine._experience_match(_make_job(experience_min=3, experience_max=5), 0.0)
        assert score < 100.0 and score >= 0.0

    def test_company_reputation_tier1(self):
        score = self.engine._company_reputation("Google India")
        assert score == 100.0

    def test_company_reputation_unknown(self):
        score = self.engine._company_reputation("XYZ Startup Pvt Ltd")
        assert score == 30.0

    def test_final_score_bounded(self):
        job = _make_job(required_skills=["Python", "FastAPI"])
        profile = _make_profile(exp=1.0, locations=["Hyderabad"])
        skills = [_make_skill("Python"), _make_skill("FastAPI")]
        scored = self.engine.score_job(job, profile, skills)
        assert scored.final_score is not None
        assert 0 <= scored.final_score <= 100

    def test_rank_jobs_returns_top_n(self):
        jobs = [_make_job(id=i, required_skills=["Python"]) for i in range(30)]
        profile = _make_profile()
        skills = [_make_skill("Python")]
        ranked = self.engine.rank_jobs(jobs, profile, skills)
        assert len(ranked) <= 20  # top_n from config


# ─────────────────────────────────────────────────────────────────────────────
# Skill Gap Analyzer
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillGapAnalyzer:
    def setup_method(self):
        from app.services.ranking_engine import SkillGapAnalyzer
        self.analyzer = SkillGapAnalyzer()

    def test_gaps_identified(self):
        job = _make_job(required_skills=["Python", "AWS", "Kubernetes", "Docker"])
        user_skills = [_make_skill("Python"), _make_skill("Docker")]
        gaps = self.analyzer.analyze(job, user_skills)
        assert "AWS" in gaps or "aws" in [g.lower() for g in gaps]
        assert "Kubernetes" in gaps or "kubernetes" in [g.lower() for g in gaps]

    def test_no_gaps_when_all_matched(self):
        job = _make_job(required_skills=["Python", "FastAPI"])
        user_skills = [_make_skill("Python"), _make_skill("FastAPI")]
        gaps = self.analyzer.analyze(job, user_skills)
        assert len(gaps) == 0

    def test_aggregate_gaps_sorted_by_frequency(self):
        jobs = [
            _make_job(id=1, required_skills=["AWS", "Kubernetes"]),
            _make_job(id=2, required_skills=["AWS", "Terraform"]),
            _make_job(id=3, required_skills=["AWS"]),
        ]
        user_skills = [_make_skill("Python")]
        agg = self.analyzer.aggregate_gaps(jobs, user_skills)
        keys = list(agg.keys())
        # AWS should appear most (3 times)
        aws_key = next((k for k in keys if k.lower() == "aws"), None)
        assert aws_key is not None
        assert agg[aws_key] == 3
