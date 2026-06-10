"""
Telegram Service
Sends job alerts and handles bot commands.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from app.core.config import settings
from app.core.logging import logger
from app.db.models import Job, UserSkill


class TelegramService:
    """
    Dual role:
      1. Proactive sender: push job alerts to user
      2. Bot server: handle /commands
    """

    def __init__(self):
        self._bot: Optional[Bot] = None
        self._app: Optional[Application] = None

    def _get_bot(self) -> Optional[Bot]:
        if not settings.telegram.bot_token:
            return None
        if self._bot is None:
            self._bot = Bot(token=settings.telegram.bot_token)
        return self._bot

    # ── Alerts ────────────────────────────────────────────────────────────

    async def send_job_alert(self, job: Job, skill_gaps: List[str]):
        """Send alert from a live ORM Job (kept for backward compat)."""
        from app.agents.job_hunter_agent import JobData
        await self.send_job_alert_data(JobData.from_orm(job), skill_gaps)

    async def send_job_alert_data(self, job, skill_gaps: List[str]):
        """Send alert from a JobData dataclass — session-safe."""
        bot = self._get_bot()
        if not bot:
            logger.warning("Telegram not configured — skipping alert")
            return

        score = job.final_score or 0
        emoji = "🔥" if score >= 80 else "🚀" if score >= 65 else "💡"

        gaps_text = (
            "\n".join(f"  • {g}" for g in skill_gaps[:5]) if skill_gaps else "  None — you match!"
        )
        required_text = ", ".join((job.required_skills or [])[:6]) or "Not specified"

        message = (
            f"{emoji} *High Match Job Found!*\n\n"
            f"*Role:* {self._esc(job.title)}\n"
            f"*Company:* {self._esc(job.company or 'Unknown')}\n"
            f"*Location:* {self._esc(job.location or 'Unknown')}\n\n"
            f"📊 *Scores*\n"
            f"  Overall: *{score:.0f}/100*\n"
            f"  Resume match: {job.resume_match_score or 0:.0f}%\n"
            f"  Skill match: {job.skill_match_score or 0:.0f}%\n\n"
            f"🛠 *Required Skills:* {self._esc(required_text)}\n\n"
            f"📚 *Missing Skills:*\n{gaps_text}\n\n"
            f"🔗 [Apply Now]({job.apply_url})"
        )

        try:
            await bot.send_message(
                chat_id=settings.telegram.chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
            logger.info(f"Alert sent: {job.title} @ {job.company} ({score:.0f})")
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    async def send_message(self, text: str):
        bot = self._get_bot()
        if not bot:
            return
        try:
            await bot.send_message(
                chat_id=settings.telegram.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    # ── Bot command server ────────────────────────────────────────────────

    def build_application(self, agent) -> Application:
        """Build the python-telegram-bot Application with all handlers."""
        app = (
            Application.builder()
            .token(settings.telegram.bot_token)
            .build()
        )
        self._app = app

        # Inject agent reference via closure
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("jobs", lambda u, c: self._cmd_jobs(u, c, agent)))
        app.add_handler(CommandHandler("topjobs", lambda u, c: self._cmd_topjobs(u, c, agent)))
        app.add_handler(CommandHandler("newjobs", lambda u, c: self._cmd_newjobs(u, c, agent)))
        app.add_handler(CommandHandler("stats", lambda u, c: self._cmd_stats(u, c, agent)))
        app.add_handler(CommandHandler("companies", lambda u, c: self._cmd_companies(u, c, agent)))
        app.add_handler(CommandHandler("skillgaps", lambda u, c: self._cmd_skillgaps(u, c, agent)))

        return app

    # ── Command handlers ──────────────────────────────────────────────────

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 *AI Job Hunter is running!*\n\n"
            "Commands:\n"
            "/jobs — latest matched jobs\n"
            "/topjobs — top 20 by score\n"
            "/newjobs — jobs in last 1 hour\n"
            "/stats — application statistics\n"
            "/companies — top hiring companies\n"
            "/skillgaps — your skill gaps\n",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_jobs(self, update: Update, context, agent):
        jobs = agent.get_top_jobs(n=5)
        await update.message.reply_text(
            self._format_job_list(jobs, "🔍 Latest Top Jobs"),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    async def _cmd_topjobs(self, update: Update, context, agent):
        jobs = agent.get_top_jobs(n=20)
        await update.message.reply_text(
            self._format_job_list(jobs, "🏆 Top 20 Jobs"),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    async def _cmd_newjobs(self, update: Update, context, agent):
        jobs = agent.get_new_jobs(hours=1)
        await update.message.reply_text(
            self._format_job_list(jobs, "🆕 New Jobs (Last Hour)"),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    async def _cmd_stats(self, update: Update, context, agent):
        stats = agent.get_application_stats()
        app_stats = stats.get("applications", {})
        lines = [
            "📊 *Application Statistics*\n",
            f"Total jobs tracked: {stats['total_jobs_tracked']}",
            f"Scored: {stats['scored_jobs']}",
            "",
            "*Application status:*",
        ]
        for status, count in app_stats.items():
            lines.append(f"  {status}: {count}")

        prefs = agent.learning.get_top_positive_signals()
        lines += [
            "",
            "*Preferred companies (learned):*",
            *[f"  {c}: {s:+.1f}" for c, s in prefs["preferred_companies"]],
            "",
            "*Preferred skills (learned):*",
            *[f"  {s}: {sc:+.1f}" for s, sc in prefs["preferred_skills"][:5]],
        ]
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_companies(self, update: Update, context, agent):
        from app.db.session import session_scope
        from sqlalchemy import func
        from app.db.models import Job as JobModel

        with session_scope() as db:
            rows = (
                db.query(JobModel.company, func.count(JobModel.id).label("cnt"))
                .filter(JobModel.company.isnot(None))
                .group_by(JobModel.company)
                .order_by(func.count(JobModel.id).desc())
                .limit(15)
                .all()
            )

        lines = ["🏢 *Top Hiring Companies*\n"]
        for i, (company, cnt) in enumerate(rows, 1):
            lines.append(f"{i}. {self._esc(company)} — {cnt} jobs")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    async def _cmd_skillgaps(self, update: Update, context, agent):
        from app.db.session import session_scope
        from sqlalchemy import func
        from app.db.models import SkillGap

        with session_scope() as db:
            rows = (
                db.query(SkillGap.skill_name, func.count(SkillGap.id).label("cnt"))
                .group_by(SkillGap.skill_name)
                .order_by(func.count(SkillGap.id).desc())
                .limit(20)
                .all()
            )

        lines = ["📚 *Your Skill Gaps (most demanded)*\n"]
        for i, (skill, cnt) in enumerate(rows, 1):
            lines.append(f"{i}. {self._esc(skill)} — required in {cnt} jobs")

        if not rows:
            lines.append("No gaps found yet — run a discovery cycle first.")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    # ── Formatting ────────────────────────────────────────────────────────

    def _format_job_list(self, jobs, title: str) -> str:
        if not jobs:
            return f"{title}\n\nNo jobs found yet. Waiting for next discovery cycle."
        lines = [f"{title}\n"]
        for i, job in enumerate(jobs, 1):
            score = job.final_score or 0
            bar = self._score_bar(score)
            # Support both JobData (required_skills list) and ORM Job
            skills = job.required_skills if hasattr(job, "required_skills") and isinstance(job.required_skills, list) \
                     else job.get_required_skills()
            lines.append(
                f"{i}. *{self._esc(job.title)}*\n"
                f"   {self._esc(job.company or 'Unknown')} · {self._esc(job.location or '')}\n"
                f"   {bar} {score:.0f}/100\n"
                f"   [Apply]({job.apply_url})\n"
            )
        return "\n".join(lines)

    def _score_bar(self, score: float) -> str:
        filled = int(score // 10)
        return "🟢" * min(filled, 10) + "⚪" * (10 - min(filled, 10))

    def _esc(self, text: str) -> str:
        """Escape Markdown special chars."""
        if not text:
            return ""
        for ch in ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]:
            text = text.replace(ch, f"\\{ch}")
        return text
