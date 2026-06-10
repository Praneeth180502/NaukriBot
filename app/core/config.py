"""
Central configuration — loads config/config.yaml
All components import `settings` from here.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings


# ─────────────────────────────────────────────────────────────────────────────
# Sub-models
# ─────────────────────────────────────────────────────────────────────────────

class AppConfig(BaseModel):
    name: str = "AI Job Hunter"
    version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"


class NaukriConfig(BaseModel):
    email: str = ""
    password: str = ""
    profile_url: str = "https://www.naukri.com/mnjuser/profile"
    resume_path: str = "data/resume.pdf"
    crawl_interval_minutes: int = 15
    max_jobs_per_cycle: int = 100
    headless: bool = True


class SearchConfig(BaseModel):
    target_roles: List[str] = [
        "Full Stack Developer", "Software Engineer", "Backend Developer",
        "Python Developer", "AI Engineer", "GenAI Engineer",
        "LLM Engineer", "RAG Engineer", "Machine Learning Engineer",
    ]
    locations: List[str] = ["Hyderabad", "Bangalore", "Chennai", "Pune", "Remote"]
    experience_min: int = 0
    experience_max: int = 2


class RankingConfig(BaseModel):
    resume_match: float = 0.40
    skill_match: float = 0.20
    location_match: float = 0.15
    experience_match: float = 0.15
    company_reputation: float = 0.10
    top_n: int = 20
    alert_threshold: float = 65.0


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class ModelsConfig(BaseModel):
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    faiss_index_path: str = "data/faiss_index"
    models_cache_dir: str = "data/models"


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///data/job_hunter.db"


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False


class ReputableCompanies(BaseModel):
    tier1: List[str] = []
    tier2: List[str] = []
    tier3: List[str] = []

    def all_companies(self) -> dict[str, int]:
        """Returns {company_name: tier_score}"""
        result = {}
        for c in self.tier1:
            result[c.lower()] = 100
        for c in self.tier2:
            result[c.lower()] = 70
        for c in self.tier3:
            result[c.lower()] = 50
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Root settings
# ─────────────────────────────────────────────────────────────────────────────

class Settings(BaseModel):
    app: AppConfig = AppConfig()
    naukri: NaukriConfig = NaukriConfig()
    search: SearchConfig = SearchConfig()
    ranking: RankingConfig = RankingConfig()
    telegram: TelegramConfig = TelegramConfig()
    models: ModelsConfig = ModelsConfig()
    database: DatabaseConfig = DatabaseConfig()
    api: ApiConfig = ApiConfig()
    reputable_companies: ReputableCompanies = ReputableCompanies()


def _load_yaml(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def load_settings(config_path: str = None) -> Settings:
    if config_path is None:
        config_path = os.environ.get("CONFIG_PATH", "config/config.yaml")
    data = _load_yaml(config_path)
    # Allow env overrides for secrets
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        data.setdefault("telegram", {})["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    if os.environ.get("TELEGRAM_CHAT_ID"):
        data.setdefault("telegram", {})["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]
    if os.environ.get("NAUKRI_EMAIL"):
        data.setdefault("naukri", {})["email"] = os.environ["NAUKRI_EMAIL"]
    if os.environ.get("NAUKRI_PASSWORD"):
        data.setdefault("naukri", {})["password"] = os.environ["NAUKRI_PASSWORD"]
    return Settings(**data)


# Singleton
settings: Settings = load_settings()
