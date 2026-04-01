from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import (
    Course,
    CourseCategoryAssignment,
    CourseNode,
    DegreeProgram,
    RequirementCategory,
    UserCourseState,
)
from app.services.assignment_service import auto_assign_courses
from app.services.course_parser import parse_course_tree
from app.services.requirements_parser import find_latest_course_tree_url, parse_requirements
from app.services.semester_service import enrich_semester_offerings


def import_degree_program(db: Session, name: str, requirements_url: str, courses_url: str) -> DegreeProgram:
    requirements = parse_requirements(requirements_url)
    effective_courses_url = courses_url
    course_nodes = parse_course_tree(courses_url)
    if _looks_like_incomplete_tree(course_nodes):
        latest_tree_url = find_latest_course_tree_url(requirements_url)
        if latest_tree_url and latest_tree_url != courses_url:
            fallback_nodes = parse_course_tree(latest_tree_url)
            if not _looks_like_incomplete_tree(fallback_nodes):
                effective_courses_url = latest_tree_url
                course_nodes = fallback_nodes

    preserved: dict[str, dict] | None = None
    program = db.query(DegreeProgram).filter(DegreeProgram.name == name).one_or_none()
    if program is None:
        program = DegreeProgram(name=name, requirements_url=requirements_url, courses_url=effective_courses_url)
        db.add(program)
        db.flush()
    else:
        program.requirements_url = requirements_url
        program.courses_url = effective_courses_url
        preserved = _capture_existing_state(program)
        _delete_program_content(db, program.id)
        db.flush()
        # Bulk deletes bypass ORM bookkeeping, so clear the identity map before
        # inserting fresh rows that may reuse SQLite primary keys.
        program_id = program.id
        db.expunge_all()
        program = db.get(DegreeProgram, program_id)
        if program is None:
            raise RuntimeError(f"Degree program {program_id} disappeared during re-import.")

    categories_by_path: dict[str, RequirementCategory] = {}
    pending_children: defaultdict[str, list[RequirementCategory]] = defaultdict(list)

    for parsed in requirements:
        category = RequirementCategory(
            degree_program_id=program.id,
            title=parsed.title,
            required_credits=parsed.required_credits,
            notes=parsed.notes,
            sort_order=parsed.sort_order,
            source_path=parsed.source_path,
        )
        db.add(category)
        db.flush()
        if parsed.source_path:
            categories_by_path[parsed.source_path] = category
        if parsed.parent_title:
            parent = _find_category_by_title(categories_by_path, parsed.parent_title)
            if parent:
                category.parent_id = parent.id
            else:
                pending_children[parsed.parent_title].append(category)

    for parent_title, children in pending_children.items():
        parent = _find_category_by_title(categories_by_path, parent_title)
        if not parent:
            continue
        for child in children:
            child.parent_id = parent.id

    node_id_by_path: dict[str, int] = {}
    courses_by_key: dict[str, Course] = {}

    for parsed in course_nodes:
        parent_id = node_id_by_path.get(parsed.parent_path or "")
        course = None
        path = " > ".join(part for part in [parsed.parent_path, parsed.title] if part)
        if parsed.node_type == "course":
            course = Course(
                degree_program_id=program.id,
                code=parsed.course_code,
                title=parsed.title,
                credits=parsed.credits,
                url=parsed.url,
                raw_path=path,
                semester_offering=parsed.semester_offering,
            )
            db.add(course)
            db.flush()
            courses_by_key[_course_key(parsed.course_code, parsed.title)] = course
        node = CourseNode(
            degree_program_id=program.id,
            parent_id=parent_id,
            node_type=parsed.node_type,
            title=parsed.title,
            sort_order=parsed.sort_order,
            course_id=course.id if course else None,
        )
        db.add(node)
        db.flush()
        node_id_by_path[path] = node.id

    enrich_semester_offerings(db, list(courses_by_key.values()), commit=False)
    auto_assign_courses(db, program.id)

    if preserved:
        _restore_existing_state(db, program.id, courses_by_key, preserved)

    db.commit()
    db.refresh(program)
    return program


def _capture_existing_state(program: DegreeProgram) -> dict[str, dict]:
    manual_assignments: dict[str, str] = {}
    user_states: dict[str, dict] = {}
    semester_offerings: dict[str, str] = {}
    for course in program.courses:
        key = _course_key(course.code, course.title)
        if course.semester_offering:
            semester_offerings[key] = course.semester_offering
        if course.user_state:
            user_states[key] = {
                "wanted": course.user_state.wanted,
                "passed": course.user_state.passed,
                "semester": course.user_state.semester,
                "grade": course.user_state.grade,
                "notes": course.user_state.notes,
            }
        for assignment in course.assignments:
            if assignment.assignment_type == "manual":
                manual_assignments[key] = assignment.requirement_category.title
    return {
        "manual_assignments": manual_assignments,
        "user_states": user_states,
        "semester_offerings": semester_offerings,
    }


def _delete_program_content(db: Session, degree_program_id: int) -> None:
    db.query(UserCourseState).filter(
        UserCourseState.course_id.in_(db.query(Course.id).filter(Course.degree_program_id == degree_program_id))
    ).delete(synchronize_session=False)
    db.query(CourseCategoryAssignment).filter(
        CourseCategoryAssignment.course_id.in_(db.query(Course.id).filter(Course.degree_program_id == degree_program_id))
    ).delete(synchronize_session=False)
    db.query(CourseNode).filter(CourseNode.degree_program_id == degree_program_id).delete(synchronize_session=False)
    db.query(Course).filter(Course.degree_program_id == degree_program_id).delete(synchronize_session=False)
    db.query(RequirementCategory).filter(RequirementCategory.degree_program_id == degree_program_id).delete(
        synchronize_session=False
    )


def _restore_existing_state(
    db: Session,
    degree_program_id: int,
    courses_by_key: dict[str, Course],
    preserved: dict[str, dict],
) -> None:
    categories = db.query(RequirementCategory).filter(RequirementCategory.degree_program_id == degree_program_id).all()
    categories_by_title = {category.title: category for category in categories}

    for key, state_values in preserved["user_states"].items():
        course = courses_by_key.get(key)
        if not course:
            continue
        db.add(UserCourseState(course_id=course.id, **state_values))

    for key, semester_offering in preserved.get("semester_offerings", {}).items():
        course = courses_by_key.get(key)
        if not course or course.semester_offering:
            continue
        course.semester_offering = semester_offering

    for key, category_title in preserved["manual_assignments"].items():
        course = courses_by_key.get(key)
        category = categories_by_title.get(category_title)
        if not course or not category:
            continue
        existing = db.query(CourseCategoryAssignment).filter(CourseCategoryAssignment.course_id == course.id).one_or_none()
        if existing:
            existing.requirement_category_id = category.id
            existing.assignment_type = "manual"
        else:
            db.add(
                CourseCategoryAssignment(
                    course_id=course.id,
                    requirement_category_id=category.id,
                    assignment_type="manual",
                )
            )


def _find_category_by_title(categories_by_path: dict[str, RequirementCategory], title: str) -> RequirementCategory | None:
    normalized = title.strip().lower()
    for category in categories_by_path.values():
        if category.title.strip().lower() == normalized:
            return category
    return None


def _course_key(code: str | None, title: str) -> str:
    return f"{(code or '').strip().lower()}::{title.strip().lower()}"


def _looks_like_incomplete_tree(course_nodes) -> bool:
    if not course_nodes:
        return True
    titles = {node.title for node in course_nodes}
    course_count = sum(1 for node in course_nodes if node.node_type == "course")
    return "Wahlmodulkatalog Informatik" not in titles and course_count < 400


def normalize_existing_requirement_data(db: Session) -> int:
    updated = 0
    programs = db.query(DegreeProgram).all()
    for program in programs:
        categories = (
            db.query(RequirementCategory)
            .filter(RequirementCategory.degree_program_id == program.id)
            .all()
        )
        by_title = {category.title: category for category in categories}
        wahl = by_title.get("Wahlmodulkatalog Informatik")
        profil = by_title.get("Profilbildung")
        theorie = by_title.get("Theorie")

        if theorie and wahl and theorie.parent_id != wahl.id:
            theorie.parent_id = wahl.id
            updated += 1

        if (
            wahl
            and profil
            and wahl.required_credits is not None
            and profil.required_credits is not None
            and abs(float(wahl.required_credits) - 53.0) <= 0.01
            and abs(float(profil.required_credits) - 10.0) <= 0.01
        ):
            wahl.required_credits = 43.0
            note = "Profilbildung credits are tracked separately."
            wahl.notes = f"{wahl.notes} {note}".strip() if wahl.notes and note not in wahl.notes else (wahl.notes or note)
            updated += 1

    if updated:
        db.commit()
    return updated


def clear_invalid_semester_offerings(db: Session) -> int:
    updated = (
        db.query(Course)
        .filter(Course.semester_offering.in_(["Winter semester", "Summer semester"]))
        .update({Course.semester_offering: None}, synchronize_session=False)
    )
    if updated:
        db.commit()
    return updated
