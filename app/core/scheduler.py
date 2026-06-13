"""
Scheduler — APScheduler wrapper.
Runs the job hunter cycle on a cron-like interval.
Also runs daily snapshot at midnight.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging import logger
from app.core.network import async_is_network_available, wait_for_network


class JobScheduler:
    def __init__(self, agent):
        self._agent = agent
        self._scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    def start(self):
        interval = settings.naukri.crawl_interval_minutes

        # Main discovery cycle
        self._scheduler.add_job(
            self._run_cycle,
            trigger=IntervalTrigger(minutes=interval),
            id="discovery_cycle",
            name="Job discovery cycle",
            replace_existing=True,
            misfire_grace_time=120,
        )

        # Daily snapshot at midnight
        self._scheduler.add_job(
            self._daily_snapshot,
            trigger=CronTrigger(hour=0, minute=0),
            id="daily_snapshot",
            name="Daily analytics snapshot",
            replace_existing=True,
        )

        # Profile refresh every 24 hours
        self._scheduler.add_job(
            self._refresh_profile,
            trigger=IntervalTrigger(hours=24),
            id="profile_refresh",
            name="Profile refresh",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.success(
            f"Scheduler started: discovery every {interval} min, "
            f"snapshot at midnight, profile refresh every 24h"
        )

    def stop(self):
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def _run_cycle(self):
        logger.info(f"[Scheduler] Starting discovery cycle at {datetime.now().strftime('%H:%M:%S')}")

        # ── Network health check ──────────────────────────────────────────────
        if not await async_is_network_available():
            logger.warning("[Scheduler] No network detected before cycle. Waiting for connectivity …")
            recovered = await wait_for_network(
                initial_delay=15.0,
                max_delay=300.0,
                max_attempts=20,
            )
            if not recovered:
                logger.error("[Scheduler] Skipping this cycle — network unavailable.")
                return
        # ─────────────────────────────────────────────────────────────────────

        try:
            # Limit the entire cycle duration to 20 minutes to prevent infinite hangs
            await asyncio.wait_for(self._agent.run_cycle(), timeout=1200.0)
        except asyncio.TimeoutError:
            logger.error("[Scheduler] Cycle timed out after 20 minutes! Cancelled to prevent resources hanging.")
        except Exception as e:
            logger.error(f"[Scheduler] Cycle error: {e}")

    async def _daily_snapshot(self):
        logger.info("[Scheduler] Taking daily snapshot")
        try:
            from app.services.analytics_service import AnalyticsService
            AnalyticsService().take_snapshot()
        except Exception as e:
            logger.error(f"[Scheduler] Snapshot error: {e}")

    async def _refresh_profile(self):
        logger.info("[Scheduler] Refreshing user profile")
        try:
            profile, skills = await self._agent.profile_engine.build_or_refresh_profile()
            self._agent._profile_cache = profile
            self._agent._skills_cache = skills
            if profile.resume_text:
                self._agent.embedding.set_resume_embedding(profile.resume_text)
            logger.success("[Scheduler] Profile refreshed")
        except Exception as e:
            logger.error(f"[Scheduler] Profile refresh error: {e}")
