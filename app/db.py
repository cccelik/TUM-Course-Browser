from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker


Base = declarative_base()

_engines: dict[str, object] = {}
_sessionmakers: dict[str, sessionmaker] = {}
_initialized_paths: set[str] = set()


def _sqlite_url(db_path: str | Path) -> str:
    return f"sqlite:///{Path(db_path).resolve().as_posix()}"


def _set_sqlite_pragmas(dbapi_connection, connection_record):
    del connection_record
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(db_path: str | Path):
    key = str(Path(db_path).resolve())
    engine = _engines.get(key)
    if engine is not None:
        return engine
    Path(key).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        _sqlite_url(key),
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
    )
    event.listen(engine, "connect", _set_sqlite_pragmas)
    _engines[key] = engine
    _sessionmakers[key] = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine


def get_session(db_path: str | Path) -> Session:
    key = str(Path(db_path).resolve())
    get_engine(key)
    return _sessionmakers[key]()


def initialize_program_database(db_path: str | Path) -> None:
    key = str(Path(db_path).resolve())
    if key in _initialized_paths:
        return
    engine = get_engine(key)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(courses)"))}
        if "semester_offering" not in columns:
            connection.execute(text("ALTER TABLE courses ADD COLUMN semester_offering VARCHAR(32)"))
    _initialized_paths.add(key)


def close_session(db: Session) -> None:
    db.close()
