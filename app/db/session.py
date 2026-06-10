"""Database session management"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import create_all, get_engine, get_session_factory

_engine = None
_SessionFactory = None


def init_db():
    global _engine, _SessionFactory
    _engine = get_engine(settings.database.url)
    _SessionFactory = get_session_factory(_engine)
    create_all(_engine)
    return _engine


def get_engine_instance():
    global _engine
    if _engine is None:
        init_db()
    return _engine


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency"""
    if _SessionFactory is None:
        init_db()
    db = _SessionFactory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for non-FastAPI code (agents, scheduler)"""
    if _SessionFactory is None:
        init_db()
    db = _SessionFactory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
