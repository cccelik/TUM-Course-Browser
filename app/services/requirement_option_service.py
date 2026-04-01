from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import DegreeProgram, UserRequirementOptionSelection
from app.services.requirements_parser import parse_profile_options


@dataclass
class RequirementOptionSummary:
    requirement_name: str
    option_name: str
    required_credits: float
    selected: bool


def build_profile_option_summaries(db: Session, degree_program: DegreeProgram) -> list[RequirementOptionSummary]:
    selected = (
        db.query(UserRequirementOptionSelection)
        .filter(
            UserRequirementOptionSelection.degree_program_id == degree_program.id,
            UserRequirementOptionSelection.requirement_name == "Profilbildung",
        )
        .one_or_none()
    )
    try:
        options = parse_profile_options(degree_program.requirements_url)
    except Exception:
        options = []
    if not options and selected:
        options = [(selected.option_name, 10.0)]
    return [
        RequirementOptionSummary(
            requirement_name="Profilbildung",
            option_name=name,
            required_credits=credits,
            selected=bool(selected and selected.option_name == name),
        )
        for name, credits in options
    ]


def select_requirement_option(db: Session, degree_program_id: int, requirement_name: str, option_name: str) -> None:
    existing = (
        db.query(UserRequirementOptionSelection)
        .filter(
            UserRequirementOptionSelection.degree_program_id == degree_program_id,
            UserRequirementOptionSelection.requirement_name == requirement_name,
        )
        .one_or_none()
    )
    if existing is None:
        db.add(
            UserRequirementOptionSelection(
                degree_program_id=degree_program_id,
                requirement_name=requirement_name,
                option_name=option_name,
            )
        )
    else:
        existing.option_name = option_name
    db.commit()




def get_selected_requirement_option(
    db: Session, degree_program_id: int, requirement_name: str
) -> UserRequirementOptionSelection | None:
    return (
        db.query(UserRequirementOptionSelection)
        .filter(
            UserRequirementOptionSelection.degree_program_id == degree_program_id,
            UserRequirementOptionSelection.requirement_name == requirement_name,
        )
        .one_or_none()
    )
