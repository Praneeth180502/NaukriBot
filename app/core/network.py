"""
Network utilities — health checks and retry helpers.

Provides:
  - is_network_available()  : quick DNS probe to confirm internet connectivity
  - wait_for_network()      : blocks (with exponential backoff) until the network is up
  - with_network_retry()    : decorator / context helper for async callables
"""
from __future__ import annotations

import asyncio
import socket
from typing import Callable, Awaitable, TypeVar

from app.core.logging import logger

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Hosts we probe — if ANY resolves, we consider the network healthy
_PROBE_HOSTS = [
    ("api.telegram.org", 443),
    ("8.8.8.8", 53),          # Google DNS — numeric, no DNS needed
    ("1.1.1.1", 53),          # Cloudflare DNS — numeric, no DNS needed
]

_CONNECT_TIMEOUT = 3.0   # seconds per probe attempt

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# Core probe
# ─────────────────────────────────────────────────────────────────────────────

def is_network_available() -> bool:
    """
    Returns True if at least one probe host is reachable (sync, non-blocking-ish).
    Uses a raw socket with a short timeout so it never hangs the event loop.
    Call from a thread via asyncio.to_thread() when inside async code.
    """
    for host, port in _PROBE_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT):
                return True
        except OSError:
            continue
    return False


async def async_is_network_available() -> bool:
    """Async-safe wrapper — runs the blocking probe in the thread pool."""
    return await asyncio.to_thread(is_network_available)


# ─────────────────────────────────────────────────────────────────────────────
# Wait-with-backoff
# ─────────────────────────────────────────────────────────────────────────────

async def wait_for_network(
    *,
    initial_delay: float = 15.0,
    max_delay: float = 300.0,
    max_attempts: int = 20,
) -> bool:
    """
    Polls for network availability using exponential backoff.

    Returns True once the network is up, False if max_attempts is exceeded.

    Args:
        initial_delay:  seconds to wait before the first retry (default 15 s)
        max_delay:      cap on the wait between retries (default 5 min)
        max_attempts:   give up after this many failed probes (default 20)
    """
    delay = initial_delay
    for attempt in range(1, max_attempts + 1):
        if await async_is_network_available():
            if attempt > 1:
                logger.success(
                    f"[Network] Connectivity restored after {attempt - 1} retries."
                )
            return True

        logger.warning(
            f"[Network] No connectivity (attempt {attempt}/{max_attempts}). "
            f"Retrying in {delay:.0f}s …"
        )
        await asyncio.sleep(delay)
        # Exponential backoff with jitter cap
        delay = min(delay * 2, max_delay)

    logger.error(
        f"[Network] Network still unavailable after {max_attempts} attempts. Giving up."
    )
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Retry decorator for async callables
# ─────────────────────────────────────────────────────────────────────────────

async def with_network_retry(
    coro_fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 3,
    initial_delay: float = 10.0,
    max_delay: float = 120.0,
    label: str = "task",
) -> T | None:
    """
    Calls ``coro_fn()`` up to ``retries`` times, waiting with exponential
    backoff between failures caused by network errors.

    Non-network exceptions are re-raised immediately.

    Args:
        coro_fn:        zero-argument async callable to invoke
        retries:        total attempts (default 3)
        initial_delay:  seconds before the first retry (default 10 s)
        max_delay:      cap on wait between retries (default 2 min)
        label:          human-readable label used in log messages

    Returns:
        The return value of ``coro_fn``, or None if all retries failed.
    """
    import httpx
    try:
        from telegram.error import NetworkError as TelegramNetworkError
        _NETWORK_EXC = (OSError, httpx.ConnectError, httpx.NetworkError, TelegramNetworkError)
    except ImportError:
        _NETWORK_EXC = (OSError, httpx.ConnectError, httpx.NetworkError)

    delay = initial_delay
    for attempt in range(1, retries + 1):
        try:
            return await coro_fn()
        except _NETWORK_EXC as exc:
            if attempt == retries:
                logger.error(
                    f"[Network] {label} failed after {retries} attempts: {exc}"
                )
                return None
            logger.warning(
                f"[Network] {label} attempt {attempt}/{retries} failed "
                f"({type(exc).__name__}). Retrying in {delay:.0f}s …"
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
        except Exception:
            raise  # non-network errors bubble up immediately
