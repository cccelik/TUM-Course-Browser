from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DegreeProgram(Base):
    __tablename__ = "degree_programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    requirements_url: Mapped[str] = mapped_column(Text, nullable=False)
    courses_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    categories: Mapped[list["RequirementCategory"]] = relationship(
        back_populates="degree_program", cascade="all, delete-orphan"
    )
    courses: Mapped[list["Course"]] = relationship(back_populates="degree_program", cascade="all, delete-orphan")
    course_nodes: Mapped[list["CourseNode"]] = relationship(
        back_populates="degree_program", cascade="all, delete-orphan"
    )
    focus_area_selections: Mapped[list["UserFocusAreaSelection"]] = relationship(
        back_populates="degree_program", cascade="all, delete-orphan"
    )
    requirement_option_selections: Mapped[list["UserRequirementOptionSelection"]] = relationship(
        back_populates="degree_program", cascade="all, delete-orphan"
    )


class RequirementCategory(Base):
    __tablename__ = "requirement_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    degree_program_id: Mapped[int] = mapped_column(ForeignKey("degree_programs.id"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_categories.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    required_credits: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    degree_program: Mapped["DegreeProgram"] = relationship(back_populates="categories")
    parent: Mapped["RequirementCategory | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["RequirementCategory"]] = relationship(back_populates="parent")
    assignments: Mapped[list["CourseCategoryAssignment"]] = relationship(
        back_populates="requirement_category", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("degree_program_id", "title", "source_path", name="uq_requirement_category_identity"),
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    degree_program_id: Mapped[int] = mapped_column(ForeignKey("degree_programs.id"), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    credits: Mapped[float | None] = mapped_column(Float, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    semester_offering: Mapped[str | None] = mapped_column(String(32), nullable=True)

    degree_program: Mapped["DegreeProgram"] = relationship(back_populates="courses")
    course_nodes: Mapped[list["CourseNode"]] = relationship(back_populates="course")
    assignments: Mapped[list["CourseCategoryAssignment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    user_state: Mapped["UserCourseState | None"] = relationship(
        back_populates="course", uselist=False, cascade="all, delete-orphan"
    )


class CourseNode(Base):
    __tablename__ = "course_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    degree_program_id: Mapped[int] = mapped_column(ForeignKey("degree_programs.id"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("course_nodes.id"), nullable=True)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)

    degree_program: Mapped["DegreeProgram"] = relationship(back_populates="course_nodes")
    parent: Mapped["CourseNode | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["CourseNode"]] = relationship(back_populates="parent")
    course: Mapped["Course | None"] = relationship(back_populates="course_nodes")


class CourseCategoryAssignment(Base):
    __tablename__ = "course_category_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    requirement_category_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_categories.id"), nullable=False, index=True
    )
    assignment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="automatic")

    course: Mapped["Course"] = relationship(back_populates="assignments")
    requirement_category: Mapped["RequirementCategory"] = relationship(back_populates="assignments")

    __table_args__ = (UniqueConstraint("course_id", name="uq_primary_course_assignment"),)


class UserCourseState(Base):
    __tablename__ = "user_course_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, unique=True, index=True)
    wanted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    semester: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grade: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    course: Mapped["Course"] = relationship(back_populates="user_state")


class UserFocusAreaSelection(Base):
    __tablename__ = "user_focus_area_selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    degree_program_id: Mapped[int] = mapped_column(ForeignKey("degree_programs.id"), nullable=False, index=True)
    area_name: Mapped[str] = mapped_column(String(255), nullable=False)
    selection_type: Mapped[str] = mapped_column(String(32), nullable=False)

    degree_program: Mapped["DegreeProgram"] = relationship(back_populates="focus_area_selections")

    __table_args__ = (UniqueConstraint("degree_program_id", "area_name", name="uq_focus_area_selection"),)


class UserRequirementOptionSelection(Base):
    __tablename__ = "user_requirement_option_selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    degree_program_id: Mapped[int] = mapped_column(ForeignKey("degree_programs.id"), nullable=False, index=True)
    requirement_name: Mapped[str] = mapped_column(String(255), nullable=False)
    option_name: Mapped[str] = mapped_column(String(255), nullable=False)

    degree_program: Mapped["DegreeProgram"] = relationship(back_populates="requirement_option_selections")

    __table_args__ = (
        UniqueConstraint("degree_program_id", "requirement_name", name="uq_requirement_option_selection"),
    )
