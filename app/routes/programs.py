from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.program_registry import ProgramRecord, create_or_update_program_record, get_registry_db
from app.services.sync_service import import_degree_program
from app.storage_setup import prepare_program_database
from app.templates import templates


router = APIRouter()


@router.get("/")
@router.get("/programs")
def list_programs(request: Request, db: Session = Depends(get_registry_db)):
    programs = db.query(ProgramRecord).order_by(ProgramRecord.updated_at.desc()).all()
    return templates.TemplateResponse(
        request,
        "programs.html",
        {
            "request": request,
            "programs": programs,
        },
    )


@router.post("/programs")
def create_program(
    name: str = Form(...),
    requirements_url: str = Form(...),
    courses_url: str = Form(...),
    registry_db: Session = Depends(get_registry_db),
):
    record = create_or_update_program_record(
        registry_db,
        name=name.strip(),
        requirements_url=requirements_url.strip(),
        courses_url=courses_url.strip(),
    )
    prepare_program_database(record.db_path)
    with get_session(record.db_path) as program_db:
        local_program = import_degree_program(
            program_db,
            name=name.strip(),
            requirements_url=requirements_url.strip(),
            courses_url=courses_url.strip(),
        )
        record.requirements_url = local_program.requirements_url
        record.courses_url = local_program.courses_url
    registry_db.add(record)
    registry_db.commit()
    return RedirectResponse(url=f"/programs/{record.id}/dashboard", status_code=303)
