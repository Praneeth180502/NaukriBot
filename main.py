"""
Application entry point.
Starts:
  1. Database (SQLite)
  2. Agent bootstrap (resume parse + profile scrape + model load)
  3. APScheduler (discovery cycles)
  4. Telegram bot (polling)
  5. FastAPI server (uvicorn)

Usage:
    python main.py
    python main.py --no-telegram
    python main.py --once          # Run one cycle then exit
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
import uvicorn

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings
from app.core.logging import logger
from app.core.scheduler import JobScheduler
from app.db.session import init_db
from app.agents.job_hunter_agent import JobHunterAgent

cli = typer.Typer(add_completion=False)


@cli.command()
def main(
    no_telegram: bool = typer.Option(False, "--no-telegram", help="Disable Telegram bot"),
    once: bool = typer.Option(False, "--once", help="Run one discovery cycle then exit"),
    bootstrap_only: bool = typer.Option(False, "--bootstrap-only", help="Bootstrap profile and exit"),
):
    asyncio.run(_run(no_telegram=no_telegram, once=once, bootstrap_only=bootstrap_only))


async def _run(no_telegram: bool = False, once: bool = False, bootstrap_only: bool = False):
    logger.info(f"Starting {settings.app.name} v{settings.app.version}")

    # 1. Database
    logger.info("Initialising database...")
    init_db()
    logger.success("Database ready")

    # 2. Agent
    agent = JobHunterAgent()
    await agent.bootstrap()

    if bootstrap_only:
        logger.success("Bootstrap complete. Exiting.")
        return

    if once:
        logger.info("Running one discovery cycle...")
        await agent.run_cycle()
        logger.success("Single cycle done. Exiting.")
        return

    # 3. Scheduler
    scheduler = JobScheduler(agent)
    scheduler.start()

    # 4. Telegram bot (in background task)
    telegram_task = None
    if not no_telegram and settings.telegram.bot_token:
        telegram_task = asyncio.create_task(_run_telegram(agent))
        logger.success("Telegram bot started")
    else:
        logger.warning("Telegram bot disabled or not configured")

    # 5. FastAPI (blocking — runs until Ctrl+C)
    logger.info(f"Dashboard: http://{settings.api.host}:{settings.api.port}")
    config = uvicorn.Config(
        "app.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
    finally:
        scheduler.stop()
        if telegram_task:
            telegram_task.cancel()
        logger.info("Goodbye.")


async def _run_telegram(agent):
    """Run Telegram bot in polling mode with network-aware retry."""
    from app.services.telegram_service import TelegramService
    from app.core.network import async_is_network_available, wait_for_network
    from telegram.error import NetworkError as TelegramNetworkError

    svc = TelegramService()
    app = svc.build_application(agent)

    # Robust startup retry loop
    while True:
        try:
            if not await async_is_network_available():
                logger.warning("No network detected at startup. Waiting for connectivity before starting Telegram...")
                if not await wait_for_network(initial_delay=10.0, max_delay=120.0, max_attempts=40):
                    logger.error("Network still unavailable. Retrying Telegram bot startup in 60s...")
                    await asyncio.sleep(60)
                    continue

            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            logger.success("Telegram polling started")
            break
        except (TelegramNetworkError, Exception) as e:
            logger.warning(f"Error starting Telegram bot ({type(e).__name__}): {e}. Retrying in 15s...")
            try:
                await app.updater.stop()
            except Exception:
                pass
            try:
                await app.stop()
            except Exception:
                pass
            try:
                await app.shutdown()
            except Exception:
                pass
            await asyncio.sleep(15)

    # Keep alive — detect network drops and pause polling until restored
    try:
        while True:
            await asyncio.sleep(30)
            if not await async_is_network_available():
                logger.warning("Network drop detected. Pausing Telegram polling to avoid log spam...")
                try:
                    await app.updater.stop()
                except Exception as e:
                    logger.warning(f"Error while stopping updater: {e}")
                
                # Block until network restores
                if await wait_for_network(initial_delay=15.0, max_delay=300.0, max_attempts=40):
                    logger.success("Network restored. Resuming Telegram polling...")
                    try:
                        await app.updater.start_polling(drop_pending_updates=True)
                    except Exception as e:
                        logger.error(f"Error while restarting polling: {e}")
                else:
                    logger.error("Network could not be restored. Giving up on Telegram polling.")
                    break
    except asyncio.CancelledError:
        try:
            await app.updater.stop()
        except Exception:
            pass
        try:
            await app.stop()
        except Exception:
            pass
        try:
            await app.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    cli()
