from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.db import get_session
from app.models import Course, CourseCategoryAssignment, DegreeProgram, RequirementCategory, UserCourseState
from app.program_registry import get_program_record, get_registry_db
from app.services.focus_area_service import WAHL_PARENT_TITLE, build_focus_area_summaries, extract_child_under, extract_focus_area
from app.storage_setup import prepare_program_database
from app.templates import templates


router = APIRouter()


@router.get("/programs/{program_id}/courses")
def course_browser(
    program_id: int,
    request: Request,
    filter_state: str = Query("all"),
    category_id: str = Query(default=""),
    focus_area: str = Query(default=""),
    semester: str = Query(default=""),
    search: str = Query(default=""),
    registry_db: Session = Depends(get_registry_db),
):
    selected_category_id = int(category_id) if category_id.strip() else None
    program = get_program_record(registry_db, program_id)
    prepare_program_database(program.db_path)
    with get_session(program.db_path) as db:
        local_program = db.query(DegreeProgram).one()
        categories = (
            db.query(RequirementCategory)
            .filter(RequirementCategory.degree_program_id == local_program.id)
            .order_by(RequirementCategory.title)
            .all()
        )
        courses = (
            db.query(Course)
            .options(
                joinedload(Course.user_state),
                joinedload(Course.assignments).joinedload(CourseCategoryAssignment.requirement_category),
            )
            .filter(Course.degree_program_id == local_program.id)
            .order_by(Course.title)
            .all()
        )
        focus_areas = build_focus_area_summaries(db, local_program.id)

    def include(course: Course) -> bool:
        state = course.user_state
        assignment = course.assignments[0] if course.assignments else None
        if filter_state == "wanted" and not (state and state.wanted):
            return False
        if filter_state == "passed" and not (state and state.passed):
            return False
        if filter_state == "unassigned" and assignment is not None:
            return False
        if selected_category_id and (assignment is None or assignment.requirement_category_id != selected_category_id):
            return False
        if focus_area and extract_focus_area(course.raw_path) != focus_area:
            return False
        if search:
            haystack = " ".join(
                value for value in [course.title, course.code or "", course.raw_path or ""] if value
            ).lower()
            if search.lower() not in haystack:
                return False
        return True

    filtered_courses = [course for course in courses if include(course)]
    if semester:
        filtered_courses = [
            course
            for course in filtered_courses
            if (semester == "unknown" and not course.semester_offering) or course.semester_offering == semester
        ]
    theory_focus_areas = {course.id: extract_child_under(course.raw_path, WAHL_PARENT_TITLE) for course in filtered_courses}
    return templates.TemplateResponse(
        request,
        "courses.html",
        {
            "request": request,
            "program": program,
            "courses": filtered_courses,
            "categories": categories,
            "filter_state": filter_state,
            "search": search,
            "selected_category_id": selected_category_id,
            "focus_areas": focus_areas,
            "selected_focus_area": focus_area,
            "selected_semester": semester,
            "theory_focus_areas": theory_focus_areas,
        },
    )


@router.get("/programs/{program_id}/courses/wanted")
def wanted_courses(program_id: int):
    return RedirectResponse(url=f"/programs/{program_id}/courses?filter_state=wanted", status_code=307)


@router.get("/programs/{program_id}/courses/passed")
def passed_courses(program_id: int):
    return RedirectResponse(url=f"/programs/{program_id}/courses?filter_state=passed", status_code=307)


@router.post("/programs/{program_id}/courses/{course_id}/toggle-wanted")
def toggle_wanted(
    program_id: int,
    course_id: int,
    next_url: str = Form(...),
    registry_db: Session = Depends(get_registry_db),
):
    program = get_program_record(registry_db, program_id)
    prepare_program_database(program.db_path)
    with get_session(program.db_path) as db:
        state = db.query(UserCourseState).filter(UserCourseState.course_id == course_id).one_or_none()
        if state is None:
            state = UserCourseState(course_id=course_id, wanted=True, passed=False)
            db.add(state)
        else:
            state.wanted = not state.wanted
        db.commit()
    return RedirectResponse(url=next_url, status_code=303)


@router.post("/programs/{program_id}/courses/{course_id}/toggle-passed")
def toggle_passed(
    program_id: int,
    course_id: int,
    next_url: str = Form(...),
    registry_db: Session = Depends(get_registry_db),
):
    program = get_program_record(registry_db, program_id)
    prepare_program_database(program.db_path)
    with get_session(program.db_path) as db:
        state = db.query(UserCourseState).filter(UserCourseState.course_id == course_id).one_or_none()
        if state is None:
            state = UserCourseState(course_id=course_id, passed=True, wanted=False)
            db.add(state)
        else:
            state.passed = not state.passed
        db.commit()
    return RedirectResponse(url=next_url, status_code=303)


@router.post("/programs/{program_id}/courses/{course_id}/assign-category")
def assign_category(
    program_id: int,
    course_id: int,
    requirement_category_id: int = Form(...),
    next_url: str = Form(...),
    registry_db: Session = Depends(get_registry_db),
):
    program = get_program_record(registry_db, program_id)
    prepare_program_database(program.db_path)
    with get_session(program.db_path) as db:
        assignment = db.query(CourseCategoryAssignment).filter(CourseCategoryAssignment.course_id == course_id).one_or_none()
        if assignment is None:
            assignment = CourseCategoryAssignment(
                course_id=course_id,
                requirement_category_id=requirement_category_id,
                assignment_type="manual",
            )
            db.add(assignment)
        else:
            assignment.requirement_category_id = requirement_category_id
            assignment.assignment_type = "manual"
        db.commit()
    return RedirectResponse(url=next_url, status_code=303)
