from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from app.schemas import ParsedCourseNode
from app.services.requirements_parser import parse_credit_value


CODE_PATTERN = re.compile(r"\b[A-Z]{2,}[\w.-]*\s?\d{2,}\b")
LIST_CONTAINER_NAMES = {"ul", "ol"}
BRACKET_CODE_PATTERN = re.compile(r"^\[([A-Z]{2,}[\w.-]*\d{2,})\]\s*(.+)$")
TUMONLINE_PSTP_PATTERN = re.compile(r"pStpStpNr=(\d+)")
TUMONLINE_PSJ_PATTERN = re.compile(r"pSJNr=(\d+)")
LABELED_CREDITS_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ECTS|Credits|Credit Points)\b", re.IGNORECASE)


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _requests_html(url: str, timeout: int = 30) -> str:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _playwright_html(url: str) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        content = page.content()
        browser.close()
        return content


def _load_html(url: str) -> str:
    html = _requests_html(url)
    if "javascript" in html.lower() and len(html) < 3000:
        try:
            return _playwright_html(url)
        except Exception:
            return html
    return html


def _is_probable_course(text: str) -> bool:
    lowered = text.lower()
    return bool(parse_credit_value(text) or CODE_PATTERN.search(text) or "ects" in lowered or "credits" in lowered)


def _extract_course_bits(text: str) -> tuple[str | None, str, float | None]:
    inline_credits = _extract_inline_credits(text)
    bracket_match = BRACKET_CODE_PATTERN.match(text)
    if bracket_match:
        code = bracket_match.group(1)
        title = bracket_match.group(2).strip()
        return code, title, inline_credits
    code_match = CODE_PATTERN.search(text)
    code = code_match.group(0) if code_match else None
    credits = inline_credits
    title = text
    if code:
        title = title.replace(code, "", 1).strip(" -|")
    if credits is not None:
        title = re.sub(r"(\d+(?:[.,]\d+)?)\s*(ECTS|Credits|Credit Points)", "", title, flags=re.IGNORECASE).strip(
            " -|()"
        )
    return code, title or text, credits


def _extract_inline_credits(text: str) -> float | None:
    if not text:
        return None
    match = LABELED_CREDITS_PATTERN.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _parse_generic_tree(container: Tag, base_url: str) -> list[ParsedCourseNode]:
    nodes: list[ParsedCourseNode] = []
    stack: list[tuple[int, str]] = []
    order = 0

    def register(
        node_type: str,
        title: str,
        depth: int,
        href: str | None = None,
        credits: float | None = None,
        code: str | None = None,
        semester_offering: str | None = None,
    ):
        nonlocal order
        order += 1
        while len(stack) > depth:
            stack.pop()
        parent_path = " > ".join(item[1] for item in stack) or None
        nodes.append(
            ParsedCourseNode(
                node_type=node_type,
                title=title,
                parent_path=parent_path,
                sort_order=order,
                course_code=code,
                credits=credits,
                url=urljoin(base_url, href) if href else None,
                semester_offering=semester_offering,
            )
        )
        if node_type != "course":
            stack.append((depth, title))

    def visit(element: Tag, depth: int = 0):
        for child in element.children:
            if not isinstance(child, Tag):
                continue
            if child.name in LIST_CONTAINER_NAMES:
                visit(child, depth + 1)
                continue
            if child.name == "li":
                anchor = child.find("a")
                text = _normalize_whitespace(child.get_text(" ", strip=True))
                if not text:
                    continue
                if _is_probable_course(text):
                    code, title, credits = _extract_course_bits(text)
                    register(
                        "course",
                        title,
                        depth,
                        href=anchor.get("href") if anchor else None,
                        credits=credits,
                        code=code,
                    )
                else:
                    register(_node_type_for_depth(depth), text, depth)
                nested_lists = child.find_all(LIST_CONTAINER_NAMES, recursive=False)
                for nested in nested_lists:
                    visit(nested, depth + 1)
                continue
            if child.name in {"h1", "h2", "h3", "h4"}:
                title = _normalize_whitespace(child.get_text(" ", strip=True))
                if title:
                    register(_node_type_for_depth(max(depth, 0)), title, depth)
                continue
            text = _normalize_whitespace(child.get_text(" ", strip=True))
            if text and _is_probable_course(text):
                code, title, credits = _extract_course_bits(text)
                register("course", title, depth, credits=credits, code=code)

    visit(container)
    return nodes


def _parse_tumonline_tree(html: str, base_url: str) -> list[ParsedCourseNode]:
    soup = BeautifulSoup(html, "lxml")
    rows = _collect_tumonline_rows(soup, base_url)
    if not rows:
        return []

    nodes: list[ParsedCourseNode] = []
    stack: list[str] = []
    order = 0

    for row in rows:
        row_id = row.get("id", "")
        title_span = row.select_one(".KnotenText")
        if not row_id or title_span is None:
            continue

        title_text = _normalize_whitespace(title_span.get_text(" ", strip=True))
        if not title_text:
            continue

        class_tokens = row.get("class", [])
        depth = len([token for token in class_tokens if token.startswith("kn") and token != row_id])
        while len(stack) > depth:
            stack.pop()

        cells = row.find_all("td", recursive=False)
        credits_text = _normalize_whitespace(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else ""
        credits = parse_credit_value(credits_text)

        course_link = None
        for link in row.find_all("a", href=True):
            href = link.get("href", "")
            if "courseFilterResourceId-eq" in href:
                course_link = urljoin(base_url, href)

        code, clean_title, inferred_credits = _extract_course_bits(title_text)
        is_course = code is not None
        node_type = "course" if is_course else _node_type_for_depth(depth)
        parent_path = " > ".join(stack) or None
        order += 1
        nodes.append(
            ParsedCourseNode(
                node_type=node_type,
                title=clean_title,
                parent_path=parent_path,
                sort_order=order,
                course_code=code,
                credits=credits if credits is not None else inferred_credits,
                url=course_link,
                semester_offering=None,
            )
        )
        if not is_course:
            stack.append(clean_title)

    return nodes


def _collect_tumonline_rows(soup: BeautifulSoup, base_url: str) -> list[Tag]:
    table = soup.select_one("table.cotable")
    if table is None:
        return []

    root_rows = list(table.select("tr.coRow.coTableR"))
    context = _extract_tumonline_context(soup, base_url)
    if context is None:
        return root_rows

    session = requests.Session()
    all_rows: list[Tag] = []
    seen_row_ids: set[str] = set()
    fetched_nodes: set[str] = set()

    def add_row(row: Tag) -> None:
        row_id = row.get("id")
        if not row_id or row_id in seen_row_ids:
            return
        seen_row_ids.add(row_id)
        all_rows.append(row)

    def visit(row: Tag) -> None:
        add_row(row)
        row_id = row.get("id", "")
        title_span = row.select_one(".KnotenText")
        if not row_id or title_span is None:
            return
        code, _, _ = _extract_course_bits(_normalize_whitespace(title_span.get_text(" ", strip=True)))
        if code is not None or row_id in fetched_nodes:
            return
        fetched_nodes.add(row_id)
        subtree_rows = _fetch_tumonline_subtree_rows(session, context, row_id)
        for child_row in subtree_rows:
            visit(child_row)

    for row in root_rows:
        visit(row)
    return all_rows


def _extract_tumonline_context(soup: BeautifulSoup, base_url: str) -> dict[str, str] | None:
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)
    p_stp = query.get("pStpStpNr", [None])[0]
    if not p_stp:
        match = TUMONLINE_PSTP_PATTERN.search(base_url)
        p_stp = match.group(1) if match else None
    if not p_stp:
        return None

    p_sj = query.get("pSJNr", [None])[0]
    if not p_sj:
        selected_year = soup.select_one('a.selected[href*="pSJNr="]')
        if selected_year and selected_year.get("href"):
            year_match = TUMONLINE_PSJ_PATTERN.search(selected_year["href"])
            p_sj = year_match.group(1) if year_match else None
    if not p_sj:
        script_text = soup.decode()
        year_match = TUMONLINE_PSJ_PATTERN.search(script_text)
        p_sj = year_match.group(1) if year_match else None
    if not p_sj:
        return None

    return {"pStStudiumNr": query.get("pStStudiumNr", [""])[0], "pStpStpNr": p_stp, "pSJNr": p_sj}


def _fetch_tumonline_subtree_rows(session: requests.Session, context: dict[str, str], row_id: str) -> list[Tag]:
    node_nr = row_id.removeprefix("kn")
    response = session.get(
        "https://campus.tum.de/tumonline/wbStpCs.cbSpoTree",
        params={
            "pStStudiumNr": context["pStStudiumNr"],
            "pStpStpNr": context["pStpStpNr"],
            "pStPersonNr": "",
            "pSJNr": context["pSJNr"],
            "pIsStudSicht": "FALSE",
            "pShowErg": "J",
            "pHideInactive": "TRUE",
            "pCaller": "",
            "pStpKnotenNr": node_nr,
            "pId": row_id,
            "pAction": "0",
        },
        timeout=30,
    )
    response.raise_for_status()

    snippet_match = re.search(
        r'<instruction action="insertAfterElement"[^>]*><!\[CDATA\[(.*?)\]\]></instruction>',
        response.text,
        re.DOTALL,
    )
    if not snippet_match:
        return []

    snippet_soup = BeautifulSoup(snippet_match.group(1), "lxml")
    snippet_table = snippet_soup.select_one("table.cotable")
    if snippet_table is None:
        return []
    return list(snippet_table.select("tr.coRow.coTableR"))


def _node_type_for_depth(depth: int) -> str:
    if depth <= 0:
        return "title"
    if depth == 1:
        return "subtitle"
    return "subsubtitle"


def parse_course_tree(url: str) -> list[ParsedCourseNode]:
    html = _load_html(url)
    if "campus.tum.de" in url and "wbstpcs.showSpoTree" in url:
        tumonline_nodes = _parse_tumonline_tree(html, url)
        if tumonline_nodes:
            return tumonline_nodes
    soup = BeautifulSoup(html, "lxml")
    main_container = soup.find("main") or soup.find(id="content") or soup.body or soup
    nodes = _parse_generic_tree(main_container, url)
    return nodes
