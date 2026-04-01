from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from app.models import Course, DegreeProgram, UserFocusAreaSelection


WAHL_PARENT_TITLE = "Wahlmodulkatalog Informatik"
PRIMARY_REQUIRED_CREDITS = 18.0
SECONDARY_REQUIRED_CREDITS = 8.0
FREE_CREDITS_BASE = 9.0
SECONDARY_ONE_ROLE = "secondary_1"
SECONDARY_TWO_ROLE = "secondary_2"


@dataclass
class FocusAreaSummary:
    name: str
    total_courses: int
    total_credits: float
    passed_credits: float
    wanted_credits: float
    selected_role: str | None
    required_credits: float | None
    remaining_credits: float
    fulfilled: bool
    progress_percent: float


@dataclass
class WahlCreditsBucket:
    title: str
    required_credits: float
    passed_credits: float
    wanted_credits: float
    remaining_credits: float
    fulfilled: bool
    progress_percent: float
    note: str | None = None


def build_focus_area_summaries(db: Session, degree_program_id: int) -> list[FocusAreaSummary]:
    selections = {
        row.area_name: row.selection_type
        for row in db.query(UserFocusAreaSelection).filter(UserFocusAreaSelection.degree_program_id == degree_program_id)
    }
    courses = (
        db.query(Course)
        .options(joinedload(Course.user_state))
        .filter(Course.degree_program_id == degree_program_id)
        .all()
    )

    summaries: dict[str, FocusAreaSummary] = {}
    for course in courses:
        area_name = _extract_focus_area(course.raw_path)
        if not area_name:
            continue
        summary = summaries.setdefault(
            area_name,
            FocusAreaSummary(
                name=area_name,
                total_courses=0,
                total_credits=0.0,
                passed_credits=0.0,
                wanted_credits=0.0,
                selected_role=selections.get(area_name),
                required_credits=None,
                remaining_credits=0.0,
                fulfilled=False,
                progress_percent=0.0,
            ),
        )
        credits = float(course.credits or 0.0)
        summary.total_courses += 1
        summary.total_credits += credits
        if course.user_state and course.user_state.passed:
            summary.passed_credits += credits
        if course.user_state and course.user_state.wanted:
            summary.wanted_credits += credits

    for summary in summaries.values():
        summary.required_credits = _required_credits_for_role(summary.selected_role)
        if summary.required_credits is None:
            summary.remaining_credits = 0.0
            summary.fulfilled = False
            summary.progress_percent = 0.0
            continue
        summary.remaining_credits = max(summary.required_credits - summary.passed_credits, 0.0)
        summary.fulfilled = summary.passed_credits >= summary.required_credits
        summary.progress_percent = min((summary.passed_credits / summary.required_credits) * 100.0, 100.0)

    return sorted(summaries.values(), key=lambda item: item.name)


def build_wahl_dashboard_buckets(
    db: Session, degree_program_id: int, selected_profile_option: str | None
) -> dict[str, object]:
    focus_areas = build_focus_area_summaries(db, degree_program_id)
    primary_areas = [area for area in focus_areas if area.selected_role == "primary"]
    secondary_one_areas = [area for area in focus_areas if area.selected_role in {SECONDARY_ONE_ROLE, "secondary"}]
    secondary_two_areas = [area for area in focus_areas if area.selected_role == SECONDARY_TWO_ROLE]

    all_courses = (
        db.query(Course)
        .options(joinedload(Course.user_state))
        .filter(Course.degree_program_id == degree_program_id)
        .all()
    )
    wahl_passed_total = 0.0
    wahl_wanted_total = 0.0
    for course in all_courses:
        if not _extract_focus_area(course.raw_path) or not course.user_state:
            continue
        credits = float(course.credits or 0.0)
        if course.user_state.passed:
            wahl_passed_total += credits
        if course.user_state.wanted:
            wahl_wanted_total += credits

    allocated = sum(
        min(area.passed_credits, area.required_credits or 0.0)
        for area in primary_areas + secondary_one_areas + secondary_two_areas
    )
    allocated_wanted = sum(
        min(area.wanted_credits, area.required_credits or 0.0)
        for area in primary_areas + secondary_one_areas + secondary_two_areas
    )
    extra_required = FREE_CREDITS_BASE
    extra_passed = max(wahl_passed_total - allocated, 0.0)
    extra_wanted = max(wahl_wanted_total - allocated_wanted, 0.0)
    extra_bucket = WahlCreditsBucket(
        title="Extra Wahl credits",
        required_credits=extra_required,
        passed_credits=round(extra_passed, 2),
        wanted_credits=round(extra_wanted, 2),
        remaining_credits=round(max(extra_required - extra_passed, 0.0), 2),
        fulfilled=extra_passed >= extra_required,
        progress_percent=round(min((extra_passed / extra_required) * 100.0, 100.0), 2) if extra_required else 0.0,
        note="Free-choice credits beyond primary and secondary areas. Profilbildung is tracked separately.",
    )

    return {
        "primary_areas": primary_areas,
        "secondary_one_areas": secondary_one_areas,
        "secondary_two_areas": secondary_two_areas,
        "extra_bucket": extra_bucket,
        "selected_profile_option": selected_profile_option,
    }


def upsert_focus_area_selection(db: Session, degree_program_id: int, area_name: str, selection_type: str) -> None:
    area_name = area_name.strip()
    existing = (
        db.query(UserFocusAreaSelection)
        .filter(
            UserFocusAreaSelection.degree_program_id == degree_program_id,
            UserFocusAreaSelection.area_name == area_name,
        )
        .one_or_none()
    )
    if selection_type == "none":
        if existing:
            db.delete(existing)
        db.commit()
        return

    if selection_type == "primary":
        db.query(UserFocusAreaSelection).filter(
            UserFocusAreaSelection.degree_program_id == degree_program_id,
            UserFocusAreaSelection.selection_type == "primary",
            UserFocusAreaSelection.area_name != area_name,
        ).delete(synchronize_session=False)
    elif selection_type == SECONDARY_ONE_ROLE:
        db.query(UserFocusAreaSelection).filter(
            UserFocusAreaSelection.degree_program_id == degree_program_id,
            UserFocusAreaSelection.selection_type.in_([SECONDARY_ONE_ROLE, "secondary"]),
            UserFocusAreaSelection.area_name != area_name,
        ).delete(synchronize_session=False)
    elif selection_type == SECONDARY_TWO_ROLE:
        db.query(UserFocusAreaSelection).filter(
            UserFocusAreaSelection.degree_program_id == degree_program_id,
            UserFocusAreaSelection.selection_type == SECONDARY_TWO_ROLE,
            UserFocusAreaSelection.area_name != area_name,
        ).delete(synchronize_session=False)

    if existing is None:
        db.add(
            UserFocusAreaSelection(
                degree_program_id=degree_program_id,
                area_name=area_name,
                selection_type=selection_type,
            )
        )
    else:
        existing.selection_type = selection_type
    db.commit()




def get_program(db: Session, degree_program_id: int) -> DegreeProgram:
    return db.query(DegreeProgram).filter(DegreeProgram.id == degree_program_id).one()


def _extract_focus_area(raw_path: str | None) -> str | None:
    if not raw_path:
        return None
    parts = [segment.strip() for segment in raw_path.split(">") if segment.strip()]
    try:
        index = parts.index(WAHL_PARENT_TITLE)
    except ValueError:
        return None
    if index + 1 >= len(parts):
        return None
    return parts[index + 1]


def extract_focus_area(raw_path: str | None) -> str | None:
    return _extract_focus_area(raw_path)


def extract_child_under(raw_path: str | None, parent_title: str) -> str | None:
    if not raw_path:
        return None
    parts = [segment.strip() for segment in raw_path.split(">") if segment.strip()]
    try:
        index = parts.index(parent_title)
    except ValueError:
        return None
    if index + 1 >= len(parts):
        return None
    return parts[index + 1]


def _required_credits_for_role(selection_type: str | None) -> float | None:
    if selection_type == "primary":
        return PRIMARY_REQUIRED_CREDITS
    if selection_type in {"secondary", SECONDARY_ONE_ROLE, SECONDARY_TWO_ROLE}:
        return SECONDARY_REQUIRED_CREDITS
    return None
