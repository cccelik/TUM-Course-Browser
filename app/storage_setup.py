from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.config import LEGACY_COMBINED_DB_PATH
from app.db import Base, get_engine, get_session, initialize_program_database
from app.models import (
    Course,
    CourseCategoryAssignment,
    CourseNode,
    DegreeProgram,
    RequirementCategory,
    UserCourseState,
    UserFocusAreaSelection,
    UserRequirementOptionSelection,
)
from app.program_registry import create_or_update_program_record, initialize_registry, registry_session
from app.services.sync_service import clear_invalid_semester_offerings, normalize_existing_requirement_data


def initialize_storage() -> None:
    initialize_registry()
    migrate_legacy_combined_database()


def prepare_program_database(db_path: str | Path) -> None:
    initialize_program_database(db_path)
    with get_session(db_path) as db:
        normalize_existing_requirement_data(db)
        clear_invalid_semester_offerings(db)


def migrate_legacy_combined_database() -> None:
    if not LEGACY_COMBINED_DB_PATH.exists():
        return

    legacy_engine = get_engine(LEGACY_COMBINED_DB_PATH)
    Base.metadata.create_all(bind=legacy_engine)
    LegacySession = sessionmaker(bind=legacy_engine, autoflush=False, autocommit=False)
    with LegacySession() as legacy_db:
        programs = legacy_db.query(DegreeProgram).order_by(DegreeProgram.id).all()
        if not programs:
            return
        with registry_session() as registry_db:
            for legacy_program in programs:
                record = create_or_update_program_record(
                    registry_db,
                    name=legacy_program.name,
                    requirements_url=legacy_program.requirements_url,
                    courses_url=legacy_program.courses_url,
                )
                prepare_program_database(record.db_path)
                with get_session(record.db_path) as target_db:
                    if target_db.query(DegreeProgram).filter(DegreeProgram.name == legacy_program.name).count():
                        continue
                    _copy_program_data(legacy_db, target_db, legacy_program.id)
                    normalize_existing_requirement_data(target_db)
                    clear_invalid_semester_offerings(target_db)
                    target_db.commit()


def _copy_program_data(source_db: Session, target_db: Session, degree_program_id: int) -> None:
    program = source_db.query(DegreeProgram).filter(DegreeProgram.id == degree_program_id).one()
    target_db.add(
        DegreeProgram(
            id=program.id,
            name=program.name,
            requirements_url=program.requirements_url,
            courses_url=program.courses_url,
            created_at=program.created_at,
            updated_at=program.updated_at,
        )
    )
    target_db.flush()

    categories = (
        source_db.query(RequirementCategory)
        .filter(RequirementCategory.degree_program_id == degree_program_id)
        .order_by(RequirementCategory.parent_id.is_not(None), RequirementCategory.sort_order, RequirementCategory.id)
    )
    for category in categories:
        target_db.add(
            RequirementCategory(
                id=category.id,
                degree_program_id=category.degree_program_id,
                parent_id=category.parent_id,
                title=category.title,
                required_credits=category.required_credits,
                notes=category.notes,
                sort_order=category.sort_order,
                source_path=category.source_path,
            )
        )
        target_db.flush()

    for course in source_db.query(Course).filter(Course.degree_program_id == degree_program_id).order_by(Course.id):
        target_db.add(
            Course(
                id=course.id,
                degree_program_id=course.degree_program_id,
                code=course.code,
                title=course.title,
                credits=course.credits,
                url=course.url,
                raw_path=course.raw_path,
                semester_offering=course.semester_offering,
            )
        )
    target_db.flush()

    nodes = (
        source_db.query(CourseNode)
        .filter(CourseNode.degree_program_id == degree_program_id)
        .order_by(CourseNode.parent_id.is_not(None), CourseNode.id)
    )
    for node in nodes:
        target_db.add(
            CourseNode(
                id=node.id,
                degree_program_id=node.degree_program_id,
                parent_id=node.parent_id,
                node_type=node.node_type,
                title=node.title,
                sort_order=node.sort_order,
                course_id=node.course_id,
            )
        )
        target_db.flush()

    course_ids = [row[0] for row in source_db.query(Course.id).filter(Course.degree_program_id == degree_program_id).all()]
    for assignment in source_db.query(CourseCategoryAssignment).filter(CourseCategoryAssignment.course_id.in_(course_ids)):
        target_db.add(
            CourseCategoryAssignment(
                id=assignment.id,
                course_id=assignment.course_id,
                requirement_category_id=assignment.requirement_category_id,
                assignment_type=assignment.assignment_type,
            )
        )

    for state in source_db.query(UserCourseState).filter(UserCourseState.course_id.in_(course_ids)):
        target_db.add(
            UserCourseState(
                id=state.id,
                course_id=state.course_id,
                wanted=state.wanted,
                passed=state.passed,
                semester=state.semester,
                grade=state.grade,
                notes=state.notes,
            )
        )

    for selection in source_db.query(UserFocusAreaSelection).filter(UserFocusAreaSelection.degree_program_id == degree_program_id):
        target_db.add(
            UserFocusAreaSelection(
                id=selection.id,
                degree_program_id=selection.degree_program_id,
                area_name=selection.area_name,
                selection_type=selection.selection_type,
            )
        )

    for selection in source_db.query(UserRequirementOptionSelection).filter(
        UserRequirementOptionSelection.degree_program_id == degree_program_id
    ):
        target_db.add(
            UserRequirementOptionSelection(
                id=selection.id,
                degree_program_id=selection.degree_program_id,
                requirement_name=selection.requirement_name,
                option_name=selection.option_name,
            )
        )
