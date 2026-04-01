from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import DegreeProgram
from app.program_registry import get_program_record, get_registry_db
from app.services.focus_area_service import WAHL_PARENT_TITLE, build_wahl_dashboard_buckets
from app.services.progress_service import build_category_progress
from app.services.requirement_option_service import get_selected_requirement_option
from app.storage_setup import prepare_program_database
from app.templates import templates


router = APIRouter()


@router.get("/programs/{program_id}/dashboard")
def dashboard(
    program_id: int,
    request: Request,
    wahl_tab: str = Query(default="primary"),
    registry_db: Session = Depends(get_registry_db),
):
    program = get_program_record(registry_db, program_id)
    prepare_program_database(program.db_path)
    with get_session(program.db_path) as db:
        local_program = db.query(DegreeProgram).one()
        progress_items = build_category_progress(db, local_program.id)
        top_level_progress = [item for item in progress_items if item.parent_category_id is None]
        child_progress_by_parent: dict[int, list] = {}
        for item in progress_items:
            if item.parent_category_id is None:
                continue
            child_progress_by_parent.setdefault(item.parent_category_id, []).append(item)
        selected_profile = get_selected_requirement_option(db, local_program.id, "Profilbildung")
        wahl_dashboard = build_wahl_dashboard_buckets(
            db,
            local_program.id,
            selected_profile.option_name if selected_profile else None,
        )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "program": program,
            "progress_items": top_level_progress,
            "child_progress_by_parent": child_progress_by_parent,
            "wahl_parent_title": WAHL_PARENT_TITLE,
            "wahl_dashboard": wahl_dashboard,
            "selected_wahl_tab": wahl_tab,
        },
    )
