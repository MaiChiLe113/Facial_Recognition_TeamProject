"""SQLite database (SQLAlchemy Core). The tables are defined in schema.sql.

    from app.db import connect
    with connect() as conn:            # one transaction; commits on success
        conn.execute(text("SELECT ..."), {...})

The file is config.DB_PATH (default data/hawkeye.sqlite3, git-ignored). init_db() creates the tables and,
when the database is new, seeds it from data/mock/ (see seed.py). Re-seed: python -m app.db.seed --reset
"""
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text

from ..config import DB_PATH

SCHEMA = Path(__file__).with_name("schema.sql")
_engines = {}


def get_engine(path=None):
    path = Path(path or DB_PATH)
    if path not in _engines:
        path.parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(f"sqlite:///{path.as_posix()}")

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys = ON")

        _engines[path] = eng
    return _engines[path]


@contextmanager
def connect(path=None):
    with get_engine(path).begin() as conn:
        yield conn


def init_db(path=None, seed=True):
    """Create missing tables; seed from data/mock/ if there are no students yet. Returns True if it seeded."""
    raw = get_engine(path).raw_connection()
    try:
        raw.driver_connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    finally:
        raw.close()
    with connect(path) as conn:
        empty = conn.execute(text("SELECT COUNT(*) FROM students")).scalar() == 0
    if seed and empty:
        from .seed import seed_all
        seed_all(path)
        return True
    return False
