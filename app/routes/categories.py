from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.db import get_session
from app.models import Course, CourseCategoryAssignment, DegreeProgram, RequirementCategory
from app.program_registry import get_program_record, get_registry_db
from app.services.focus_area_service import (
    WAHL_PARENT_TITLE,
    build_focus_area_summaries,
    extract_child_under,
    extract_focus_area,
    upsert_focus_area_selection,
)
from app.services.progress_service import build_category_progress
from app.services.requirement_option_service import build_profile_option_summaries, select_requirement_option
from app.storage_setup import prepare_program_database
from app.templates import templates


router = APIRouter()


@router.get("/programs/{program_id}/categories/{category_id}")
def category_detail(
    program_id: int,
    category_id: int,
    request: Request,
    focus_area: str = Query(default=""),
    semester: str = Query(default=""),
    registry_db: Session = Depends(get_registry_db),
):
    program = get_program_record(registry_db, program_id)
    prepare_program_database(program.db_path)
    with get_session(program.db_path) as db:
        local_program = db.query(DegreeProgram).one()
        category = (
            db.query(RequirementCategory)
            .options(
                joinedload(RequirementCategory.assignments)
                .joinedload(CourseCategoryAssignment.course)
                .joinedload(Course.user_state)
            )
            .filter(RequirementCategory.id == category_id)
            .one()
        )
        program_progress = {item.category_id: item for item in build_category_progress(db, local_program.id)}
        progress = program_progress[category.id]

        theory_focus_area_options = sorted(
            {
                extract_child_under(assignment.course.raw_path, WAHL_PARENT_TITLE)
                for assignment in category.assignments
                if assignment.course and extract_child_under(assignment.course.raw_path, WAHL_PARENT_TITLE)
            }
        ) if category.title == "Theorie" else []

        passed_courses = []
        wanted_courses = []
        unmarked_courses = []
        assigned_courses = []
        for assignment in category.assignments:
            course = assignment.course
            current_focus_area = extract_child_under(course.raw_path, WAHL_PARENT_TITLE)
            if focus_area and current_focus_area != focus_area:
                continue
            state = course.user_state
            assigned_courses.append(course)
            if state and state.passed:
                passed_courses.append(course)
            elif state and state.wanted:
                wanted_courses.append(course)
            else:
                unmarked_courses.append(course)
        if semester:
            assigned_courses = [
                course
                for course in assigned_courses
                if (semester == "unknown" and not course.semester_offering) or course.semester_offering == semester
            ]
            passed_courses = [
                course
                for course in passed_courses
                if (semester == "unknown" and not course.semester_offering) or course.semester_offering == semester
            ]
            wanted_courses = [
                course
                for course in wanted_courses
                if (semester == "unknown" and not course.semester_offering) or course.semester_offering == semester
            ]
            unmarked_courses = [
                course
                for course in unmarked_courses
                if (semester == "unknown" and not course.semester_offering) or course.semester_offering == semester
            ]

        categories = (
            db.query(RequirementCategory)
            .filter(RequirementCategory.degree_program_id == local_program.id)
            .order_by(RequirementCategory.title)
            .all()
        )
        theory_focus_areas = (
            {course.id: extract_child_under(course.raw_path, WAHL_PARENT_TITLE) for course in assigned_courses}
            if category.title == "Theorie"
            else {}
        )
        focus_areas = build_focus_area_summaries(db, local_program.id) if category.title == WAHL_PARENT_TITLE else []
        profile_options = build_profile_option_summaries(db, category.degree_program) if category.title == "Profilbildung" else []

    return templates.TemplateResponse(
        request,
        "category_detail.html",
        {
            "request": request,
            "program": program,
            "category": category,
            "progress": progress,
            "passed_courses": passed_courses,
            "wanted_courses": wanted_courses,
            "unmarked_courses": unmarked_courses,
            "assigned_courses": assigned_courses,
            "categories": categories,
            "theory_focus_areas": theory_focus_areas,
            "theory_focus_area_options": theory_focus_area_options,
            "focus_areas": focus_areas,
            "selected_focus_area": focus_area,
            "selected_semester": semester,
            "profile_options": profile_options,
        },
    )


@router.post("/programs/{program_id}/focus-areas/select")
def select_focus_area(
    program_id: int,
    area_name: str = Form(...),
    selection_type: str = Form(...),
    next_url: str = Form(...),
    registry_db: Session = Depends(get_registry_db),
):
    program = get_program_record(registry_db, program_id)
    prepare_program_database(program.db_path)
    with get_session(program.db_path) as db:
        local_program = db.query(DegreeProgram).one()
        upsert_focus_area_selection(db, degree_program_id=local_program.id, area_name=area_name, selection_type=selection_type)
    return RedirectResponse(url=next_url, status_code=303)


@router.post("/programs/{program_id}/requirement-options/select")
def choose_requirement_option(
    program_id: int,
    requirement_name: str = Form(...),
    option_name: str = Form(...),
    next_url: str = Form(...),
    registry_db: Session = Depends(get_registry_db),
):
    program = get_program_record(registry_db, program_id)
    prepare_program_database(program.db_path)
    with get_session(program.db_path) as db:
        local_program = db.query(DegreeProgram).one()
        select_requirement_option(db, degree_program_id=local_program.id, requirement_name=requirement_name, option_name=option_name)
    return RedirectResponse(url=next_url, status_code=303)
