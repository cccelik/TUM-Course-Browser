from __future__ import annotations

import re
from urllib.parse import urljoin
from typing import Iterable

import requests
from bs4 import BeautifulSoup, Tag

from app.schemas import ParsedRequirementCategory


CREDIT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ECTS|Credits|Credit Points)?", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"(20\d{2})")
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "strong", "b"}
STUDY_START_PATTERN = re.compile(r"Studienbeginn ab", re.IGNORECASE)
CODE_TITLE_PATTERN = re.compile(r"\b[A-Z]{2,}\d{4,}\b")
PROFILE_PRACTICUM_PATTERN = re.compile(r"(IN2257\s+Zusätzliches\s+Master-Praktikum|IN2175\s+Vertiefendes\s+Praktikum|IN2169\s+Forschungsarbeit\s+unter\s+Anleitung)", re.IGNORECASE)


def parse_credit_value(text: str) -> float | None:
    if not text:
        return None
    ratio_match = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)", text)
    if ratio_match:
        return float(ratio_match.group(2).replace(",", "."))
    labeled_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(ECTS|Credits|Credit Points)\b", text, re.IGNORECASE)
    if labeled_match:
        return float(labeled_match.group(1).replace(",", "."))
    match = CREDIT_PATTERN.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _fetch_html(url: str, timeout: int = 30) -> str:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _pick_latest_content_root(soup: BeautifulSoup) -> Tag:
    return soup.body or soup


def _latest_study_section(root: Tag) -> tuple[Tag | None, list[Tag]]:
    headings = [tag for tag in root.find_all(["h2", "h3"]) if STUDY_START_PATTERN.search(tag.get_text(" ", strip=True))]
    if not headings:
        return None, []
    heading = max(
        headings,
        key=lambda item: max((int(match.group(1)) for match in YEAR_PATTERN.finditer(item.get_text(" ", strip=True))), default=0),
    )
    section_tags: list[Tag] = []
    for element in heading.find_all_next():
        if element is heading:
            continue
        if element.name in {"h2", "h3"} and STUDY_START_PATTERN.search(element.get_text(" ", strip=True)):
            break
        if isinstance(element, Tag):
            section_tags.append(element)
    return heading, section_tags


def _extract_intro_notes(root: Tag) -> list[ParsedRequirementCategory]:
    notes: list[ParsedRequirementCategory] = []
    for paragraph in root.find_all("p"):
        text = _normalize_whitespace(paragraph.get_text(" ", strip=True))
        if not text:
            continue
        if "Überfachliche Grundlagen" in text:
            notes.append(
                ParsedRequirementCategory(
                    title="Überfachliche Grundlagen",
                    required_credits=6.0,
                    notes=text,
                    parent_title=None,
                    source_path="Überfachliche Grundlagen",
                    sort_order=1,
                )
            )
        if "Interdisziplinäres Projekt" in text:
            notes.append(
                ParsedRequirementCategory(
                    title="Interdisziplinäres Projekt",
                    required_credits=16.0,
                    notes=text,
                    parent_title=None,
                    source_path="Interdisziplinäres Projekt",
                    sort_order=2,
                )
            )
        if "mindestens 10 Credits" in text and "Theorie" in text:
            notes.append(
                ParsedRequirementCategory(
                    title="Theorie",
                    required_credits=10.0,
                    notes=text,
                    parent_title="Wahlmodulkatalog Informatik",
                    source_path="Wahlmodulkatalog Informatik > Theorie",
                    sort_order=3,
                )
            )
    return notes


def _iter_section_blocks(section_tags: list[Tag]) -> Iterable[Tag]:
    for tag in section_tags:
        if tag.name == "table":
            yield tag


def _clean_requirement_title(text: str) -> str:
    value = text
    value = re.sub(r"\*+", "", value)
    value = re.sub(r"\b\d+(?:[.,]\d+)?\s*Credits\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b\d+(?:[.,]\d+)?\s*ECTS\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\d+\s*", "", value)
    value = re.sub(r"\boder\b", "", value, flags=re.IGNORECASE)
    value = _normalize_whitespace(value).strip(" -:")
    return value


def _canonical_requirement_title(text: str) -> str | None:
    normalized = _clean_requirement_title(text)
    lowered = normalized.lower()
    if not normalized:
        return None
    if "wahlfachkatalog informatik" in lowered or "wahlmodulkatalog informatik" in lowered:
        return "Wahlmodulkatalog Informatik"
    if "überfachliche grundlagen" in lowered:
        return "Überfachliche Grundlagen"
    if "interdisziplinäres projekt" in lowered:
        return "Interdisziplinäres Projekt"
    if lowered.startswith("profilbildung"):
        return "Profilbildung"
    if "zusätzliches master-praktikum" in lowered:
        return None
    if "vertiefendes praktikum" in lowered or "forschungsarbeit unter anleitung" in lowered:
        return None
    if "master-praktikum" in lowered:
        return "Master-Praktikum"
    if "master-seminar" in lowered:
        return "Master-Seminar"
    if "master’s thesis" in lowered or "master's thesis" in lowered:
        return "Master's Thesis"
    if "schwerpunktgebiet" in lowered or "angekündigt wird" in lowered:
        return None
    return normalized


def _is_requirement_candidate(text: str) -> bool:
    if not text or parse_credit_value(text) is None:
        return False
    lowered = text.lower()
    if lowered.startswith("sem "):
        return False
    if lowered.isdigit():
        return False
    if "studienbeginn" in lowered:
        return False
    return any(keyword in lowered for keyword in ["credits", "ects", "praktikum", "seminar", "thesis", "wahl", "projekt"])


def parse_requirements(url: str) -> list[ParsedRequirementCategory]:
    html = _fetch_html(url)
    soup = BeautifulSoup(html, "lxml")
    root = _pick_latest_content_root(soup)

    latest_heading, section_tags = _latest_study_section(root)
    categories: list[ParsedRequirementCategory] = _extract_intro_notes(root)
    current_parent: str | None = latest_heading.get_text(" ", strip=True) if latest_heading else None
    aggregated: dict[str, ParsedRequirementCategory] = {category.title: category for category in categories}
    next_sort_order = len(categories) + 1

    for block in _iter_section_blocks(section_tags):
        texts: list[str] = []
        if block.name == "table":
            for row in block.find_all("tr"):
                cells = [_normalize_whitespace(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
                joined_row = _normalize_whitespace(" ".join(cell for cell in cells if cell))
                if joined_row and "Profilbildung" in joined_row:
                    texts.append(joined_row)
                    continue
                texts.extend(cell for cell in cells if cell)
        else:
            texts.append(_normalize_whitespace(block.get_text(" ", strip=True)))

        for text in texts:
            if not _is_requirement_candidate(text):
                continue
            title = _canonical_requirement_title(text)
            if not title or len(title) < 3:
                continue
            credits = parse_credit_value(text)
            existing = aggregated.get(title)
            if existing:
                if existing.required_credits is None:
                    existing.required_credits = credits
                elif credits is not None:
                    existing.required_credits = round(float(existing.required_credits) + float(credits), 2)
                existing.notes = existing.notes or text
                continue
            item = ParsedRequirementCategory(
                title=title,
                required_credits=credits,
                notes=text if text != title else None,
                parent_title=current_parent,
                source_path=" > ".join(part for part in [current_parent, title] if part),
                sort_order=next_sort_order,
            )
            categories.append(item)
            aggregated[title] = item
            next_sort_order += 1

    deduped: list[ParsedRequirementCategory] = []
    seen: set[tuple[str, str | None]] = set()
    for item in categories:
        key = (_normalize_whitespace(item.title).lower(), item.source_path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    if not any(item.title == "Profilbildung" for item in deduped):
        profile_options = parse_profile_options(url)
        if profile_options:
            deduped.append(
                ParsedRequirementCategory(
                    title="Profilbildung",
                    required_credits=10.0,
                    notes="10 credits to choose from the listed Profilbildung alternatives.",
                    parent_title=None,
                    source_path="Profilbildung",
                    sort_order=max((item.sort_order for item in deduped), default=0) + 1,
                )
            )
    _normalize_wahlmodulkatalog_credits(deduped)
    return deduped


def _normalize_wahlmodulkatalog_credits(items: list[ParsedRequirementCategory]) -> None:
    wahl = next((item for item in items if item.title == "Wahlmodulkatalog Informatik"), None)
    profil = next((item for item in items if item.title == "Profilbildung"), None)
    if wahl is None or profil is None:
        return
    if wahl.required_credits is None or profil.required_credits is None:
        return
    if abs(float(wahl.required_credits) - 53.0) > 0.01 or abs(float(profil.required_credits) - 10.0) > 0.01:
        return
    wahl.required_credits = 43.0
    note = "Profilbildung credits are tracked separately."
    wahl.notes = f"{wahl.notes} {note}".strip() if wahl.notes else note


def find_latest_course_tree_url(requirements_url: str) -> str | None:
    html = _fetch_html(requirements_url)
    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[int, str]] = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = _normalize_whitespace(link.get_text(" ", strip=True))
        if "campus.tum.de" not in href or "showSpoTree" not in href:
            continue
        year = max((int(match.group(1)) for match in YEAR_PATTERN.finditer(text)), default=0)
        candidates.append((year, urljoin(requirements_url, href)))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def parse_profile_options(requirements_url: str) -> list[tuple[str, float]]:
    html = _fetch_html(requirements_url)
    soup = BeautifulSoup(html, "lxml")
    root = _pick_latest_content_root(soup)
    _, section_tags = _latest_study_section(root)

    options: list[tuple[str, float]] = []
    for block in _iter_section_blocks(section_tags):
        if block.name != "table":
            continue
        for row in block.find_all("tr"):
            text = _normalize_whitespace(row.get_text(" ", strip=True))
            if "Profilbildung" not in text:
                continue
            if "Wahlfachkatalog Informatik" in text or "Wahlmodulkatalog Informatik" in text:
                options.append(("Module aus dem Wahlmodulkatalog Informatik", 10.0))
            for match in PROFILE_PRACTICUM_PATTERN.finditer(text):
                options.append((_normalize_whitespace(match.group(1)), 10.0))
            deduped: list[tuple[str, float]] = []
            seen: set[str] = set()
            for name, credits in options:
                if name in seen:
                    continue
                seen.add(name)
                deduped.append((name, credits))
            return deduped
    return []
