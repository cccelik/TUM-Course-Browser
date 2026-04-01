from __future__ import annotations

import re

from sqlalchemy.orm import Session, joinedload

from app.models import Course, CourseCategoryAssignment, RequirementCategory


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _path_segments(path: str | None) -> list[str]:
    if not path:
        return []
    return [segment.strip() for segment in path.split(">") if segment.strip()]


def auto_assign_courses(db: Session, degree_program_id: int) -> None:
    categories = (
        db.query(RequirementCategory)
        .filter(RequirementCategory.degree_program_id == degree_program_id)
        .order_by(RequirementCategory.sort_order, RequirementCategory.id)
        .all()
    )
    if not categories:
        return

    category_norms = [(category, normalize_text(category.title)) for category in categories]
    courses = (
        db.query(Course)
        .options(joinedload(Course.assignments))
        .filter(Course.degree_program_id == degree_program_id)
        .all()
    )

    for course in courses:
        existing = course.assignments[0] if course.assignments else None
        if existing and existing.assignment_type == "manual":
            continue

        match = _match_course_to_category(course, category_norms)
        if not match:
            if existing:
                db.delete(existing)
            continue

        if existing:
            existing.requirement_category_id = match.id
            existing.assignment_type = "automatic"
        else:
            db.add(
                CourseCategoryAssignment(
                    course_id=course.id,
                    requirement_category_id=match.id,
                    assignment_type="automatic",
                )
            )
    db.flush()


def _match_course_to_category(
    course: Course, category_norms: list[tuple[RequirementCategory, str]]
) -> RequirementCategory | None:
    path_segments = [normalize_text(segment) for segment in _path_segments(course.raw_path)]
    title = normalize_text(course.title)
    path_blob = " ".join(path_segments + [title])

    for category, normalized in category_norms:
        if normalized and normalized in path_segments:
            return category

    for category, normalized in category_norms:
        if normalized and normalized in path_blob:
            return category

    title_words = set(title.split())
    for category, normalized in category_norms:
        normalized_words = set(normalized.split())
        if normalized_words and normalized_words.issubset(title_words):
            return category
    return None
