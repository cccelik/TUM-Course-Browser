from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models import Course, CourseCategoryAssignment, RequirementCategory
from app.schemas import CategoryProgress


def build_category_progress(db: Session, degree_program_id: int) -> list[CategoryProgress]:
    categories = (
        db.query(RequirementCategory)
        .options(
            joinedload(RequirementCategory.assignments)
            .joinedload(CourseCategoryAssignment.course)
            .joinedload(Course.user_state)
        )
        .filter(RequirementCategory.degree_program_id == degree_program_id)
        .order_by(RequirementCategory.sort_order, RequirementCategory.title)
        .all()
    )

    own_totals: dict[int, tuple[float, float]] = {}
    for category in categories:
        passed_credits = 0.0
        wanted_credits = 0.0
        for assignment in category.assignments:
            course = assignment.course
            state = course.user_state
            credits = float(course.credits or 0)
            if state and state.passed:
                passed_credits += credits
            if state and state.wanted:
                wanted_credits += credits
        own_totals[category.id] = (round(passed_credits, 2), round(wanted_credits, 2))

    children_by_parent: dict[int, list[int]] = {}
    for category in categories:
        if category.parent_id is not None:
            children_by_parent.setdefault(category.parent_id, []).append(category.id)

    totals_cache: dict[int, tuple[float, float]] = {}

    def aggregate_totals(category_id: int) -> tuple[float, float]:
        cached = totals_cache.get(category_id)
        if cached is not None:
            return cached
        own_passed, own_wanted = own_totals.get(category_id, (0.0, 0.0))
        total_passed = own_passed
        total_wanted = own_wanted
        for child_id in children_by_parent.get(category_id, []):
            child_passed, child_wanted = aggregate_totals(child_id)
            total_passed += child_passed
            total_wanted += child_wanted
        totals_cache[category_id] = (round(total_passed, 2), round(total_wanted, 2))
        return totals_cache[category_id]

    progress_items: list[CategoryProgress] = []
    for category in categories:
        passed_credits, wanted_credits = aggregate_totals(category.id)

        required = float(category.required_credits) if category.required_credits is not None else None
        remaining = max((required or 0) - passed_credits, 0.0)
        fulfilled = bool(required is not None and passed_credits >= required)
        percent = min((passed_credits / required) * 100, 100.0) if required else 0.0
        progress_items.append(
            CategoryProgress(
                category_id=category.id,
                parent_category_id=category.parent_id,
                title=category.title,
                required_credits=required,
                passed_credits=round(passed_credits, 2),
                wanted_credits=round(wanted_credits, 2),
                remaining_credits=round(remaining, 2),
                fulfilled=fulfilled,
                progress_percent=round(percent, 2),
                notes=category.notes,
            )
        )
    return progress_items
