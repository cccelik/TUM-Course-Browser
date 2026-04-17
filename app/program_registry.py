from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, Text, create_engine, event
from sqlalchemy.orm import Mapped, Session, declarative_base, mapped_column, sessionmaker

from app.config import REGISTRY_DB_PATH


RegistryBase = declarative_base()


class ProgramRecord(RegistryBase):
    __tablename__ = "program_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    requirements_url: Mapped[str] = mapped_column(Text, nullable=False)
    courses_url: Mapped[str] = mapped_column(Text, nullable=False)
    db_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


registry_engine = create_engine(
    f"sqlite:///{REGISTRY_DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 30},
)
RegistrySessionLocal = sessionmaker(bind=registry_engine, autoflush=False, autocommit=False)


@event.listens_for(registry_engine, "connect")
def set_registry_pragmas(dbapi_connection, connection_record):
    del connection_record
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def initialize_registry() -> None:
    RegistryBase.metadata.create_all(bind=registry_engine)
    _normalize_record_paths()


@contextmanager
def registry_session():
    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_registry_db():
    db = RegistrySessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_program_record(db: Session, program_id: int) -> ProgramRecord:
    record = db.query(ProgramRecord).filter(ProgramRecord.id == program_id).one()
    desired_path = str(_normalize_db_path(record.id, record.name, record.db_path))
    if record.db_path != desired_path:
        record.db_path = desired_path
        db.commit()
        db.refresh(record)
    return record


def create_or_update_program_record(
    db: Session,
    name: str,
    requirements_url: str,
    courses_url: str,
) -> ProgramRecord:
    record = db.query(ProgramRecord).filter(ProgramRecord.name == name).one_or_none()
    if record is None:
        record = ProgramRecord(
            name=name,
            requirements_url=requirements_url,
            courses_url=courses_url,
            db_path="",
        )
        db.add(record)
        db.flush()
        record.db_path = str(build_program_db_path(record.id, name))
    else:
        record.requirements_url = requirements_url
        record.courses_url = courses_url
        record.db_path = str(build_program_db_path(record.id, name))
    db.commit()
    db.refresh(record)
    return record


def build_program_db_path(program_id: int, name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "program"
    return Path("data") / f"program_{program_id:03d}_{slug}.db"


def _normalize_db_path(program_id: int, name: str, current_path: str) -> Path:
    if current_path:
        return Path("data") / Path(current_path).name
    return build_program_db_path(program_id, name)


def _normalize_record_paths() -> None:
    with registry_session() as db:
        records = db.query(ProgramRecord).order_by(ProgramRecord.id).all()
        changed = False
        for record in records:
            desired_path = str(_normalize_db_path(record.id, record.name, record.db_path))
            if record.db_path != desired_path:
                record.db_path = desired_path
                changed = True
        if changed:
            db.commit()
