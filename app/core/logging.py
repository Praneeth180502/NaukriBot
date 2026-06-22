"""
Logging — structured JSON logs with loguru.
Import `logger` everywhere.
"""
import sys
from pathlib import Path
from loguru import logger as _logger

from app.core.config import settings

_configured = False


import logging

class PollingErrorFilter(logging.Filter):
    """Filter out the loud PTB polling network errors."""
    def filter(self, record):
        if record.name == "telegram.ext.Updater" and "Exception happened while polling for updates" in record.getMessage():
            return False
        return True

def setup_logging():
    global _configured
    if _configured:
        return
    _configured = True

    _logger.remove()

    # Console — human-readable
    _logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> — <level>{message}</level>",
        level=settings.app.log_level,
        colorize=True,
    )

    # File — JSON for analysis
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    _logger.add(
        log_dir / "job_hunter_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        level="DEBUG",
        serialize=True,
        enqueue=True,
    )

    # Mute the noisy telegram polling traceback
    updater_logger = logging.getLogger("telegram.ext.Updater")
    updater_logger.addFilter(PollingErrorFilter())
    logging.getLogger("httpx").setLevel(logging.WARNING)


setup_logging()
logger = _logger
