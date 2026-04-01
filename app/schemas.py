from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedRequirementCategory:
    title: str
    required_credits: Optional[float]
    notes: Optional[str]
    parent_title: Optional[str]
    source_path: Optional[str]
    sort_order: int


@dataclass
class ParsedCourseNode:
    node_type: str
    title: str
    parent_path: Optional[str]
    sort_order: int
    course_code: Optional[str] = None
    credits: Optional[float] = None
    url: Optional[str] = None
    semester_offering: Optional[str] = None


@dataclass
class CategoryProgress:
    category_id: int
    parent_category_id: int | None
    title: str
    required_credits: Optional[float]
    passed_credits: float
    wanted_credits: float
    remaining_credits: float
    fulfilled: bool
    progress_percent: float
    notes: Optional[str]
