"""
CLI management tool — ai_job_hunter admin commands.

Usage:
    python scripts/manage.py profile          # Show current profile
    python scripts/manage.py jobs [--n 20]    # Show top N jobs
    python scripts/manage.py gaps             # Show skill gaps
    python scripts/manage.py stats            # Application statistics
    python scripts/manage.py export-jobs      # Export jobs to CSV
    python scripts/manage.py reset-alerts     # Reset alert_sent flags
    python scripts/manage.py run-once         # Trigger one discovery cycle
"""
from __future__ import annotations

import asyncio
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich import box

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
os.environ.setdefault("CONFIG_PATH", "config/config.yaml")

from app.db.session import init_db, session_scope
from app.db.models import (
    Application, Job, SkillGap, UserProfile, UserSkill,
    ApplicationStatus,
)

cli = typer.Typer(help="AI Job Hunter — management CLI")
console = Console()


def _init():
    init_db()


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

@cli.command()
def profile():
    """Show the current user profile and skills."""
    _init()
    with session_scope() as db:
        p = db.query(UserProfile).first()
        if not p:
            console.print("[red]No profile found. Run the agent first.[/red]")
            return

        skills = db.query(UserSkill).filter_by(profile_id=p.id).all()

    console.rule("[bold cyan]User Profile[/bold cyan]")
    console.print(f"[bold]Name:[/bold] {p.name}")
    console.print(f"[bold]Email:[/bold] {p.email}")
    console.print(f"[bold]Experience:[/bold] {p.total_experience_years} years")
    console.print(f"[bold]Preferred Locations:[/bold] {', '.join(p.get_preferred_locations())}")
    console.print(f"[bold]Target Roles:[/bold] {', '.join(p.get_preferred_roles())}")
    console.print()

    # Skills by category
    cats: dict[str, list[str]] = {}
    for sk in skills:
        cat = sk.category or "other"
        cats.setdefault(cat, []).append(f"{'★ ' if sk.is_primary else ''}{sk.name}")

    table = Table(title="Skills by Category", box=box.SIMPLE_HEAVY)
    table.add_column("Category", style="cyan", width=12)
    table.add_column("Skills", style="white")
    for cat, sk_list in sorted(cats.items()):
        table.add_row(cat, ", ".join(sk_list))
    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────

@cli.command()
def jobs(n: int = typer.Option(20, "--n", "-n", help="Number of jobs to show")):
    """Show top N matched jobs sorted by score."""
    _init()
    with session_scope() as db:
        top_jobs = (
            db.query(Job)
            .filter(Job.final_score.isnot(None))
            .order_by(Job.final_score.desc())
            .limit(n)
            .all()
        )

    if not top_jobs:
        console.print("[yellow]No scored jobs found. Run a discovery cycle first.[/yellow]")
        return

    table = Table(title=f"Top {n} Jobs", box=box.SIMPLE_HEAVY, show_lines=True)
    table.add_column("#", width=3)
    table.add_column("Title", style="bold white", width=30)
    table.add_column("Company", style="cyan", width=20)
    table.add_column("Location", style="green", width=12)
    table.add_column("Score", style="yellow", width=7)
    table.add_column("Resume%", width=8)
    table.add_column("Skill%", width=7)
    table.add_column("Skills", width=30)

    for i, job in enumerate(top_jobs, 1):
        score = job.final_score or 0
        color = "green" if score >= 70 else "yellow" if score >= 50 else "red"
        table.add_row(
            str(i),
            job.title[:28],
            (job.company or "—")[:18],
            (job.location or "—")[:10],
            f"[{color}]{score:.0f}[/{color}]",
            f"{job.resume_match_score or 0:.0f}%",
            f"{job.skill_match_score or 0:.0f}%",
            ", ".join(job.get_required_skills()[:4]),
        )
    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Skill Gaps
# ─────────────────────────────────────────────────────────────────────────────

@cli.command()
def gaps(n: int = typer.Option(25, "--n")):
    """Show your most demanded skill gaps."""
    _init()
    from sqlalchemy import func
    with session_scope() as db:
        rows = (
            db.query(SkillGap.skill_name, func.count(SkillGap.id).label("cnt"))
            .group_by(SkillGap.skill_name)
            .order_by(func.count(SkillGap.id).desc())
            .limit(n)
            .all()
        )

    if not rows:
        console.print("[yellow]No skill gaps recorded yet.[/yellow]")
        return

    table = Table(title="Skill Gaps (Most Demanded)", box=box.SIMPLE_HEAVY)
    table.add_column("#", width=4)
    table.add_column("Skill", style="bold red", width=25)
    table.add_column("# Jobs Requiring It", style="yellow", width=20)
    table.add_column("Bar", width=30)

    max_cnt = rows[0][1] if rows else 1
    for i, (skill, cnt) in enumerate(rows, 1):
        bar_len = int(cnt / max_cnt * 25)
        bar = "█" * bar_len + "░" * (25 - bar_len)
        table.add_row(str(i), skill, str(cnt), f"[red]{bar}[/red]")
    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

@cli.command()
def stats():
    """Show application and discovery statistics."""
    _init()
    from sqlalchemy import func
    with session_scope() as db:
        total_jobs = db.query(Job).count()
        scored_jobs = db.query(Job).filter(Job.final_score.isnot(None)).count()
        high_match = db.query(Job).filter(Job.final_score >= 70).count()
        avg_score = db.query(func.avg(Job.final_score)).filter(Job.final_score.isnot(None)).scalar()
        app_rows = (
            db.query(Application.status, func.count(Application.id))
            .group_by(Application.status)
            .all()
        )
        top_companies = (
            db.query(Job.company, func.count(Job.id).label("cnt"))
            .filter(Job.company.isnot(None))
            .group_by(Job.company)
            .order_by(func.count(Job.id).desc())
            .limit(5)
            .all()
        )

    console.rule("[bold cyan]Discovery Stats[/bold cyan]")
    console.print(f"  Total jobs tracked  : [bold]{total_jobs}[/bold]")
    console.print(f"  Scored jobs         : [bold]{scored_jobs}[/bold]")
    console.print(f"  High match (≥70)    : [bold green]{high_match}[/bold green]")
    console.print(f"  Average score       : [bold yellow]{(avg_score or 0.0):.1f}[/bold yellow]")

    console.rule("[bold cyan]Applications[/bold cyan]")
    for status, count in app_rows:
        console.print(f"  {status:<25}: [bold]{count}[/bold]")

    console.rule("[bold cyan]Top Companies[/bold cyan]")
    for company, cnt in top_companies:
        console.print(f"  {(company or 'Unknown'):<30}: {cnt} jobs")


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@cli.command()
def export_jobs(
    output: str = typer.Option("data/exports/jobs.csv", "--output", "-o"),
    min_score: float = typer.Option(0, "--min-score"),
):
    """Export jobs to CSV."""
    _init()
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    with session_scope() as db:
        query = db.query(Job)
        if min_score > 0:
            query = query.filter(Job.final_score >= min_score)
        all_jobs = query.order_by(Job.final_score.desc()).all()

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "title", "company", "location", "final_score",
            "resume_match", "skill_match", "required_skills",
            "apply_url", "discovered_at",
        ])
        writer.writeheader()
        for job in all_jobs:
            writer.writerow({
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "final_score": job.final_score,
                "resume_match": job.resume_match_score,
                "skill_match": job.skill_match_score,
                "required_skills": "|".join(job.get_required_skills()),
                "apply_url": job.apply_url,
                "discovered_at": job.discovered_at,
            })

    console.print(f"[green]Exported {len(all_jobs)} jobs to {output}[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# Reset alerts
# ─────────────────────────────────────────────────────────────────────────────

@cli.command()
def reset_alerts():
    """Reset alert_sent flag — re-trigger Telegram alerts on next cycle."""
    _init()
    with session_scope() as db:
        count = db.query(Job).filter_by(alert_sent=True).update({"alert_sent": False})
    console.print(f"[green]Reset {count} alert flags.[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# Run once
# ─────────────────────────────────────────────────────────────────────────────

@cli.command()
def run_once():
    """Trigger one job discovery cycle immediately."""
    asyncio.run(_run_once_async())


async def _run_once_async():
    _init()
    console.print("[cyan]Running single discovery cycle...[/cyan]")
    from app.agents.job_hunter_agent import JobHunterAgent
    agent = JobHunterAgent()
    await agent.bootstrap()
    await agent.run_cycle()
    console.print("[green]Cycle complete.[/green]")


if __name__ == "__main__":
    cli()
