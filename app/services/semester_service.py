from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

import requests
from sqlalchemy.orm import Session

from app.models import Course


REST_BASE_URL = "https://campus.tum.de/tumonline/ee/rest"
SEMESTER_LOOKBACK_LIMIT = 8
SEMESTER_LOOKUP_WORKERS = 8
_thread_local = threading.local()


def enrich_semester_offerings(db: Session, courses: list[Course], *, commit: bool = True) -> None:
    pending = [course for course in courses if course.url and course.semester_offering is None]
    if not pending:
        return

    session = requests.Session()
    try:
        session.get(f"{REST_BASE_URL}/auth/token/refresh", timeout=30)
        terms = _fetch_recent_terms(session)
    except (requests.RequestException, ET.ParseError):
        return
    if not terms:
        return

    refs_to_courses: dict[tuple[str, str], list[Course]] = {}
    updated = False
    for course in pending:
        course_ref = _extract_course_reference(course.url)
        if course_ref is None:
            continue
        refs_to_courses.setdefault(course_ref, []).append(course)

    if not refs_to_courses:
        return

    availabilities = _resolve_ref_availabilities(refs_to_courses.keys(), terms)
    for course_ref, linked_courses in refs_to_courses.items():
        availability = availabilities.get(course_ref)
        if availability is None:
            continue
        for course in linked_courses:
            course.semester_offering = availability
            updated = True

    if updated and commit:
        db.commit()


def _resolve_ref_availabilities(
    refs: list[tuple[str, str]] | tuple[tuple[str, str], ...] | set[tuple[str, str]],
    terms: list[tuple[str, str]],
) -> dict[tuple[str, str], str | None]:
    ref_list = list(refs)
    if not ref_list:
        return {}

    results: dict[tuple[str, str], str | None] = {}
    worker_count = min(SEMESTER_LOOKUP_WORKERS, len(ref_list))
    if worker_count <= 1:
        for curriculum_version_id, resource_id in ref_list:
            try:
                results[(curriculum_version_id, resource_id)] = _detect_semester_offering_with_worker_session(
                    curriculum_version_id, resource_id, terms
                )
            except (requests.RequestException, ET.ParseError):
                results[(curriculum_version_id, resource_id)] = None
        return results

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(_detect_semester_offering_with_worker_session, curriculum_version_id, resource_id, terms): (
                curriculum_version_id,
                resource_id,
            )
            for curriculum_version_id, resource_id in ref_list
        }
        for future in as_completed(future_map):
            ref = future_map[future]
            try:
                results[ref] = future.result()
            except (requests.RequestException, ET.ParseError):
                results[ref] = None
    return results


def _fetch_recent_terms(session: requests.Session) -> list[tuple[str, str]]:
    response = session.get(f"{REST_BASE_URL}/slc.lib.tm/semesters/student?$language=", timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.text)

    terms: list[tuple[str, str]] = []
    for semester in root.findall(".//semesters")[:SEMESTER_LOOKBACK_LIMIT]:
        term_id = semester.findtext("id")
        semester_type = semester.findtext("semesterType")
        if term_id and semester_type in {"W", "S"}:
            terms.append((term_id, semester_type))
    return terms


def _get_worker_session() -> requests.Session:
    session = getattr(_thread_local, "semester_session", None)
    if session is not None:
        return session
    session = requests.Session()
    session.get(f"{REST_BASE_URL}/auth/token/refresh", timeout=30)
    _thread_local.semester_session = session
    return session


def _extract_course_reference(course_url: str) -> tuple[str, str] | None:
    parsed = urlparse(course_url)
    query_string = parsed.fragment.split("?", 1)[1] if "?" in parsed.fragment else parsed.query
    params = parse_qs(query_string, keep_blank_values=True)

    curriculum_version_id = (params.get("curriculumVersionId") or [None])[0]
    filter_value = (params.get("$filter") or [None])[0]
    if not curriculum_version_id or not filter_value:
        return None

    prefix = "courseFilterResourceId-eq="
    if not filter_value.startswith(prefix):
        return None
    return curriculum_version_id, filter_value.removeprefix(prefix)


def _detect_semester_offering(
    session: requests.Session,
    curriculum_version_id: str,
    resource_id: str,
    terms: list[tuple[str, str]],
) -> str | None:
    semester_types: set[str] = set()
    for term_id, semester_type in terms:
        if _course_exists_for_term(session, curriculum_version_id, resource_id, term_id):
            semester_types.add(semester_type)
        if semester_types == {"W", "S"}:
            break

    if semester_types == {"W", "S"}:
        return "Summer and winter"
    if semester_types == {"W"}:
        return "Winter"
    if semester_types == {"S"}:
        return "Summer"
    return None


def _detect_semester_offering_with_worker_session(
    curriculum_version_id: str,
    resource_id: str,
    terms: list[tuple[str, str]],
) -> str | None:
    return _detect_semester_offering(_get_worker_session(), curriculum_version_id, resource_id, terms)


def _course_exists_for_term(
    session: requests.Session,
    curriculum_version_id: str,
    resource_id: str,
    term_id: str,
) -> bool:
    filter_value = (
        f"courseFilterResourceId-eq={resource_id};"
        f"curriculumVersionId-eq={curriculum_version_id};"
        f"termId-eq={term_id}"
    )
    response = session.get(
        f"{REST_BASE_URL}/slc.tm.cp/student/courses",
        params={"$filter": filter_value, "$orderBy": "title=ascnf", "$skip": "0", "$top": "20"},
        timeout=30,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    return root.find(".//courses") is not None
