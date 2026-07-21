"""
Resume Parser
Extracts structured data from a PDF resume using PyMuPDF + regex + keyword matching.
No paid APIs — fully local.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF

from app.core.logging import logger
from app.services.skill_taxonomy import SKILL_TAXONOMY, categorize_skill


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Education:
    degree: str
    institution: str
    year: Optional[str] = None
    grade: Optional[str] = None


@dataclass
class Experience:
    title: str
    company: str
    duration: str
    description: str = ""
    start_year: Optional[int] = None
    end_year: Optional[int] = None


@dataclass
class ParsedResume:
    raw_text: str
    name: str = ""
    email: str = ""
    phone: str = ""
    total_experience_years: float = 0.0
    summary: str = ""
    skills: Dict[str, List[str]] = field(default_factory=dict)   # category → [skill]
    all_skills: List[str] = field(default_factory=list)
    primary_skills: List[str] = field(default_factory=list)
    education: List[Education] = field(default_factory=list)
    experience: List[Experience] = field(default_factory=list)
    target_roles: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

class ResumeParser:
    """Extracts structured information from a PDF resume."""

    SECTION_PATTERNS = {
        "contact": r"^\s*(contact|personal\s+info)\s*$",
        "summary": r"^\s*(professional\s+)?(summary|objective|profile|about\s+me)\s*$",
        "skills": r"^\s*(technical\s+)?(skills?|competencies|expertise)\s*$",
        "experience": r"^\s*(work\s+)?(experience|history|employment|positions?)\s*$",
        "education": r"^\s*(education|academics?|qualification)\s*$",
        "projects": r"^\s*(projects?|portfolio)\s*$",
        "certifications": r"^\s*(certifications?|courses?|training)\s*$",
    }

    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    PHONE_RE = re.compile(r"[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}")
    YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

    def parse(self, resume_path: str) -> ParsedResume:
        path = Path(resume_path)
        if not path.exists():
            raise FileNotFoundError(f"Resume not found: {resume_path}")

        logger.info(f"Parsing resume: {resume_path}")
        raw_text = self._extract_text(path)
        result = ParsedResume(raw_text=raw_text)

        result.email = self._extract_email(raw_text)
        result.phone = self._extract_phone(raw_text)
        result.name = self._extract_name(raw_text)
        result.skills, result.all_skills = self._extract_skills(raw_text)
        result.primary_skills = self._identify_primary_skills(result.all_skills, raw_text)
        result.education = self._extract_education(raw_text)
        result.experience = self._extract_experience(raw_text)
        result.total_experience_years = self._calculate_experience(result.experience, raw_text)
        result.summary = self._extract_summary(raw_text)
        result.target_roles = self._infer_target_roles(result.all_skills, result.experience)

        logger.success(
            f"Resume parsed: {len(result.all_skills)} skills, "
            f"{len(result.experience)} roles, "
            f"{result.total_experience_years:.1f} yrs exp"
        )
        return result

    # ── Text extraction ────────────────────────────────────────────────────

    def _extract_text(self, path: Path) -> str:
        doc = fitz.open(str(path))
        pages = []
        for page in doc:
            pages.append(page.get_text("text"))
        doc.close()
        text = "\n".join(pages)
        # Normalize whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    # ── Contact info ──────────────────────────────────────────────────────

    def _extract_email(self, text: str) -> str:
        match = self.EMAIL_RE.search(text)
        return match.group(0) if match else ""

    def _extract_phone(self, text: str) -> str:
        match = self.PHONE_RE.search(text)
        return match.group(0) if match else ""

    def _extract_name(self, text: str) -> str:
        """Heuristic: first non-empty line that's not contact info"""
        for line in text.split("\n")[:10]:
            line = line.strip()
            if (
                line
                and len(line) > 3
                and len(line) < 60
                and "@" not in line
                and not any(c.isdigit() for c in line[:3])
                and not any(kw in line.lower() for kw in ["resume", "cv", "curriculum"])
            ):
                return line
        return ""

    # ── Skills ────────────────────────────────────────────────────────────

    def _extract_skills(self, text: str) -> tuple[dict, list]:
        text_lower = text.lower()
        found: dict[str, list[str]] = {}
        all_skills: list[str] = []

        for skill, category in SKILL_TAXONOMY.items():
            # Whole-word match
            pattern = r"\b" + re.escape(skill.lower()) + r"\b"
            if re.search(pattern, text_lower):
                cat = category
                if cat not in found:
                    found[cat] = []
                # Preserve original casing from taxonomy
                found[cat].append(skill)
                all_skills.append(skill)

        return found, list(set(all_skills))

    def _identify_primary_skills(self, skills: list[str], text: str) -> list[str]:
        """Skills mentioned multiple times or in prominent positions = primary."""
        text_lower = text.lower()
        skill_counts: dict[str, int] = {}
        for skill in skills:
            count = len(re.findall(r"\b" + re.escape(skill.lower()) + r"\b", text_lower))
            skill_counts[skill] = count

        # Top 10 by frequency
        sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
        return [s for s, _ in sorted_skills[:10]]

    # ── Education ─────────────────────────────────────────────────────────

    def _extract_education(self, text: str) -> list[Education]:
        education = []
        edu_section = self._get_section(text, "education")
        if not edu_section:
            return education

        degree_patterns = [
            r"(B\.?Tech|B\.?E|Bachelor[s]?|B\.?Sc|B\.?Com)",
            r"(M\.?Tech|M\.?E|Master[s]?|MBA|M\.?Sc)",
            r"(Ph\.?D|Doctorate)",
            r"(Diploma|HSC|SSC|10th|12th|Intermediate)",
        ]

        lines = edu_section.split("\n")
        for line in lines:
            for pattern in degree_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    years = self.YEAR_RE.findall(line)
                    education.append(Education(
                        degree=line.strip()[:100],
                        institution="",
                        year=years[-1] if years else None,
                    ))
                    break

        return education

    # ── Experience ────────────────────────────────────────────────────────

    def _extract_experience(self, text: str) -> list[Experience]:
        experiences = []
        exp_section = self._get_section(text, "experience")
        if not exp_section:
            return experiences

        # Look for intern/developer/engineer patterns
        role_pattern = re.compile(
            r"(intern|developer|engineer|analyst|architect|lead|manager|consultant)",
            re.IGNORECASE,
        )

        current_exp = None
        for line in exp_section.split("\n"):
            line = line.strip()
            if not line:
                continue
            if role_pattern.search(line) and len(line) < 150:
                if current_exp:
                    experiences.append(current_exp)
                years = self.YEAR_RE.findall(line)
                current_exp = Experience(
                    title=line[:100],
                    company="",
                    duration=" - ".join(years) if years else "",
                    start_year=int(years[0]) if years else None,
                    end_year=int(years[-1]) if len(years) > 1 else None,
                )
            elif current_exp and len(line) > 10:
                current_exp.description += line + " "

        if current_exp:
            experiences.append(current_exp)

        return experiences

    def _calculate_experience(self, experiences: list[Experience], text: str) -> float:
        """Calculate total years of professional experience."""
        # Try parsing from explicit mentions first
        exp_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:years?|yrs?|yr)\s+(?:of\s+)?(?:[a-z\s]+)?(?:experience|exp)",
            text,
            re.IGNORECASE,
        )
        if exp_match:
            return float(exp_match.group(1))

        # Fall back to computing from experience dates
        if not experiences:
            return 0.0

        total = 0.0
        for exp in experiences:
            if exp.start_year and exp.end_year:
                total += exp.end_year - exp.start_year
            elif exp.start_year:
                from datetime import datetime
                total += datetime.now().year - exp.start_year

        return min(total, 30.0)  # cap at 30 years

    # ── Summary ───────────────────────────────────────────────────────────

    def _extract_summary(self, text: str) -> str:
        section = self._get_section(text, "summary")
        if section:
            return section[:500].strip()
        # Fallback: first substantial paragraph
        for para in text.split("\n\n"):
            para = para.strip()
            if len(para) > 100 and "@" not in para:
                return para[:500]
        return ""

    # ── Target roles ──────────────────────────────────────────────────────

    def _infer_target_roles(self, skills: list[str], experience: list[Experience]) -> list[str]:
        roles = set()
        skills_lower = {s.lower() for s in skills}

        if any(s in skills_lower for s in ["react", "next.js", "typescript", "javascript"]):
            roles.add("Frontend Developer")
            roles.add("Full Stack Developer")

        if any(s in skills_lower for s in ["fastapi", "django", "flask", "python"]):
            roles.add("Backend Developer")
            roles.add("Python Developer")

        if any(s in skills_lower for s in ["langchain", "llamaindex", "rag", "llm", "openai"]):
            roles.add("AI Engineer")
            roles.add("GenAI Engineer")
            roles.add("LLM Engineer")

        if any(s in skills_lower for s in ["machine learning", "scikit-learn", "pytorch", "tensorflow"]):
            roles.add("Machine Learning Engineer")

        if any(s in skills_lower for s in ["docker", "kubernetes", "ci/cd", "github actions"]):
            roles.add("DevOps Engineer")

        # Also add from experience titles
        for exp in experience:
            title_lower = exp.title.lower()
            if "full stack" in title_lower:
                roles.add("Full Stack Developer")
            elif "backend" in title_lower:
                roles.add("Backend Developer")
            elif "ai" in title_lower or "ml" in title_lower:
                roles.add("AI/ML Engineer")

        return list(roles)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _get_section(self, text: str, section: str) -> str:
        pattern = self.SECTION_PATTERNS.get(section, "")
        if not pattern:
            return ""
        lines = text.split("\n")
        start = -1
        end = len(lines)

        for i, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE) and len(line.strip()) < 50:
                start = i + 1
                break

        if start == -1:
            return ""

        # Find next section
        all_patterns = "|".join(self.SECTION_PATTERNS.values())
        for i in range(start, len(lines)):
            if (
                re.search(all_patterns, lines[i], re.IGNORECASE)
                and len(lines[i].strip()) < 50
                and i > start
            ):
                end = i
                break

        return "\n".join(lines[start:end])
