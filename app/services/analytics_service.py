"""
Analytics Service
Aggregates data for the dashboard and takes daily snapshots.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import func

from app.core.logging import logger
from app.db.models import Application, DailySnapshot, Job, SkillGap
from app.db.session import session_scope


class AnalyticsService:

    def take_snapshot(self):
        """Record a DailySnapshot for yesterday."""
        today = datetime.utcnow().date()
        date_str = today.strftime("%Y-%m-%d")

        with session_scope() as db:
            existing = db.query(DailySnapshot).filter_by(snapshot_date=date_str).first()
            if existing:
                return

            yesterday_start = datetime.utcnow().replace(hour=0, minute=0, second=0) - timedelta(days=1)
            yesterday_end = yesterday_start + timedelta(days=1)

            total = db.query(Job).filter(
                Job.discovered_at >= yesterday_start,
                Job.discovered_at < yesterday_end,
            ).count()

            high_match = db.query(Job).filter(
                Job.discovered_at >= yesterday_start,
                Job.discovered_at < yesterday_end,
                Job.final_score >= 70,
            ).count()

            apps_sent = db.query(Application).filter(
                Application.applied_at >= yesterday_start,
                Application.applied_at < yesterday_end,
            ).count()

            avg = db.query(func.avg(Job.final_score)).filter(
                Job.discovered_at >= yesterday_start,
                Job.discovered_at < yesterday_end,
                Job.final_score.isnot(None),
            ).scalar()

            # Top skills demanded
            skill_rows = (
                db.query(SkillGap.skill_name, func.count(SkillGap.id).label("cnt"))
                .group_by(SkillGap.skill_name)
                .order_by(func.count(SkillGap.id).desc())
                .limit(10)
                .all()
            )

            # Top companies
            company_rows = (
                db.query(Job.company, func.count(Job.id).label("cnt"))
                .filter(Job.company.isnot(None))
                .group_by(Job.company)
                .order_by(func.count(Job.id).desc())
                .limit(10)
                .all()
            )

            # Top locations
            loc_rows = (
                db.query(Job.location, func.count(Job.id).label("cnt"))
                .filter(Job.location.isnot(None))
                .group_by(Job.location)
                .order_by(func.count(Job.id).desc())
                .limit(10)
                .all()
            )

            snap = DailySnapshot(
                snapshot_date=date_str,
                total_jobs_found=total,
                high_match_jobs=high_match,
                applications_sent=apps_sent,
                avg_match_score=round(avg or 0, 2),
                top_skills_demanded=json.dumps([r.skill_name for r in skill_rows]),
                top_companies=json.dumps([r.company for r in company_rows]),
                top_locations=json.dumps([r.location for r in loc_rows]),
            )
            db.add(snap)
            logger.success(f"Daily snapshot saved for {date_str}: {total} jobs")

    def get_trend(self, days: int = 30) -> List[Dict]:
        with session_scope() as db:
            snaps = (
                db.query(DailySnapshot)
                .order_by(DailySnapshot.snapshot_date.desc())
                .limit(days)
                .all()
            )
        return [
            {
                "date": s.snapshot_date,
                "total_jobs": s.total_jobs_found,
                "high_match": s.high_match_jobs,
                "applications": s.applications_sent,
                "avg_score": s.avg_match_score,
            }
            for s in reversed(snaps)
        ]
