# TUM Study Planner

Local Python app for importing TUM degree-program requirements and course trees, then tracking progress against them with editable category assignments, wanted/passed course state, and a dashboard.

The app is built around two independent scrapers:
- a requirements scraper for study-plan / requirements pages
- a course-tree scraper for TUMonline curriculum trees

Imported data is stored locally in SQLite and can be re-imported without losing manual course state and manual category overrides.

## What It Does

- Imports a degree program from:
  - a requirements page URL
  - a TUMonline course tree URL
- Scrapes and stores:
  - requirement categories
  - required credits
  - notes / special rules text
  - course hierarchy nodes
  - actual courses
  - raw source paths
- Automatically assigns courses to requirement categories
- Lets you:
  - mark courses as `wanted`
  - mark courses as `passed`
  - manually reassign a course to a different category
  - choose Wahlkatalog focus-area roles
  - choose a Profilbildung option
- Shows:
  - a dashboard with progress rings
  - a course browser with filters
  - category detail pages with assigned courses

## Current TUM Informatik-Specific Support

The app is still generic at the data-model level, but it already contains logic that works well for the TUM Master Informatik structure:

- `Wahlmodulkatalog Informatik`
- child requirement `Theorie`
- focus-area extraction from Wahlkatalog paths
- `Primary`, `Secondary 1`, `Secondary 2`, and `Extra` Wahl breakdown on the dashboard
- separate `Profilbildung` handling

The database model stays generic, but some parser and display logic currently assumes the TUM Informatik requirement layout.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy
- SQLite
- Jinja2 templates
- plain HTML / CSS / JavaScript
- `requests`, `BeautifulSoup4`, `lxml`
- `Playwright` as scraper fallback when needed
- `pywebview` for desktop-wrapper launch mode

## Run

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
playwright install
```

### 3. Start the app

Desktop-wrapper mode:

```bash
python run.py
```

This launches the FastAPI app inside a local `pywebview` desktop window.

Browser/server mode:

```bash
python run.py --web --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## First Use

1. Open the app.
2. Create a program by entering:
   - program name
   - requirements URL
   - course tree URL
3. Wait for the initial import to finish.
4. Open the dashboard.
5. Review automatic assignments.
6. Use the course browser or category pages to correct assignments and mark course state.

## Example Input

Typical TUM Master Informatik example:

- Requirements URL:
  `https://www.cit.tum.de/cit/studium/studiengaenge/master-informatik/studienplaene/`
- Course tree URL:
  `https://campus.tum.de/tumonline/wbstpcs.showSpoTree?pStpStpNr=4731`

If the provided course-tree URL is incomplete, the importer may try to detect a newer tree URL from the requirements page and use that instead.

## Main Screens

### Programs

Route:
- `/`
- `/programs`

Purpose:
- list imported programs
- create or re-import a program

### Dashboard

Route:
- `/programs/{program_id}/dashboard`

Purpose:
- show top-level requirement progress
- show child requirements inside parent cards
- show Wahlkatalog breakdown tabs

### Course Browser

Route:
- `/programs/{program_id}/courses`

Purpose:
- browse imported courses
- search by title / code / path
- filter by state, category, focus area, semester
- toggle wanted/passed
- manually reassign categories

### Category Detail

Route:
- `/programs/{program_id}/categories/{category_id}`

Purpose:
- inspect one requirement category in detail
- see assigned courses
- filter by focus area / semester where applicable
- manage Wahl focus-area roles
- choose Profilbildung option

## Current Filters

Course browser:
- search text
- state
- category
- Wahl focus area
- semester

Category pages:
- focus area
- semester

Filters are designed to apply immediately for dropdown changes. Search remains explicit through the search button to keep the UI responsive.

## Data Storage

The app now uses:

- one small registry database:
  [`data/program_registry.db`](data/program_registry.db)
- one SQLite database per imported program in `data/`, for example:
  [`data/program_001_m-sc-informatik.db`](data/program_001_m-sc-informatik.db)

This means imported programs are no longer combined into one shared content database.

The registry DB stores only:
- program name
- source URLs
- timestamps
- path to the program-specific SQLite file

Each program DB stores:
- the imported degree program row
- requirement categories
- courses
- course nodes
- assignments
- user course state
- focus-area selections
- requirement-option selections

Legacy note:
- if an old combined database exists at [`data/studiengang_planner.db`](data/studiengang_planner.db), startup will split its programs into separate program DB files and register them automatically

## Core Data Model

### DegreeProgram

Stores one imported program:
- name
- requirements URL
- courses URL
- timestamps

### RequirementCategory

Stores imported requirement categories:
- title
- parent category
- required credits
- notes
- source path

### Course

Stores actual courses:
- code
- title
- credits
- source URL
- raw hierarchy path
- semester offering when available

### CourseNode

Stores the full imported course tree, including non-course headings:
- title
- subtitle
- subsubtitle
- course

### CourseCategoryAssignment

Stores the current category assignment for a course:
- automatic
- manual

### UserCourseState

Stores user state per course:
- wanted
- passed
- optional semester / grade / notes fields

### UserFocusAreaSelection

Stores Wahlkatalog focus-area role selection:
- primary
- secondary_1
- secondary_2

### UserRequirementOptionSelection

Stores selected either/or option, currently used for:
- Profilbildung

## Project Structure

```text
app/
├── config.py                  # app title and DB path
├── db.py                      # per-program SQLAlchemy engine/session helpers
├── main.py                    # FastAPI entry point
├── desktop.py                 # pywebview desktop wrapper
├── program_registry.py        # registry DB and program metadata
├── models.py                  # SQLAlchemy models
├── schemas.py                 # parser/progress dataclasses
├── storage_setup.py           # registry init and legacy DB migration
├── routes/
│   ├── programs.py            # program list and import
│   ├── dashboard.py           # dashboard page
│   ├── courses.py             # course browser and course actions
│   └── categories.py          # category detail and focus-area/profile actions
├── services/
│   ├── requirements_parser.py # requirements scraping
│   ├── course_parser.py       # course tree scraping
│   ├── assignment_service.py  # auto assignment logic
│   ├── progress_service.py    # category progress calculation
│   ├── focus_area_service.py  # Wahlkatalog focus-area logic
│   ├── requirement_option_service.py
│   ├── semester_service.py    # semester extraction helpers
│   └── sync_service.py        # repeatable import pipeline
├── static/
│   ├── style.css
│   ├── app.js
│   └── tum-logo.svg
└── templates/
    ├── base.html
    ├── programs.html
    ├── dashboard.html
    ├── courses.html
    └── category_detail.html
```

## Import Pipeline

The importer in `app/services/sync_service.py` does this:

1. Parse requirements page
2. Parse course tree
3. Detect a more complete tree URL if needed
4. Create or refresh the degree program row
5. Replace old categories / nodes / courses for that program
6. Store imported categories and tree nodes
7. Store imported courses
8. Enrich semester offerings where possible
9. Run automatic course-category assignment
10. Restore preserved manual assignments and user course state

Important behavior:
- re-import is supported
- manual assignments are preserved
- wanted/passed state is preserved
- stale SQLAlchemy identity-map issues are cleaned up during re-import
- every imported program writes into its own SQLite file under `data/`

## Progress Rules

- Only `passed` courses count toward completion
- `wanted` courses do not count toward progress
- visual progress is capped at `100%`
- real values are still shown, so overfilled categories remain visible as e.g. `21/15`
- parent categories aggregate child-category progress

For the current TUM Informatik setup:
- `Theorie` is treated as a child of `Wahlmodulkatalog Informatik`
- Theorie credits therefore count inside the Wahlkatalog total

## Automatic Assignment

Version 1 assignment stays intentionally simple and editable.

Matching uses:
- normalized title matches
- path segment matches
- keyword-based fallback rules

Manual assignment always wins after the user changes it.

## Wahlkatalog / Focus Areas

The app derives Wahl focus areas from the imported raw course path.

Example idea:

```text
Wahlmodulkatalog Informatik > Algorithmen (ALG) > Theorie > ...
```

From this, the app can derive:
- focus area: `Algorithmen (ALG)`
- child area under Wahl: `Theorie`

Current UI support includes:
- assigning one `Primary`
- assigning one `Secondary 1`
- assigning one `Secondary 2`
- showing an `Extra` bucket on the dashboard

## Semester Offering Notes

Semester availability is stored on the course row in the database.

Important:
- semester detection is not inferred from the old `pStartSemester` course-tree parameter
- that old parameter was misleading and was intentionally discarded
- semester values depend on the current import/enrichment pipeline, so older imports may need a re-import to populate them

## Architecture Rules

1. Keep scraping separate from database logic.
2. Keep requirements parsing separate from course parsing.
3. Preserve raw hierarchy paths from source pages.
4. Treat automatic assignment as editable, never final.
5. Count only passed courses toward progress.
6. Keep wanted courses separate from progress.
7. Cap visual progress at 100%, but display real values.
8. Make all parsing generic so the app works with other degree programs.
9. Avoid hardcoding Informatik-specific logic into the database model.
10. Build the MVP before trying to support complex rule systems.

## Testing and Verification

Useful local checks:

```bash
python3 -m compileall app run.py
node --check app/static/app.js
```

Typical manual verification:

- import one program successfully
- confirm requirement categories were extracted
- confirm Wahlkatalog and Theorie assignments exist
- mark a course as wanted
- mark a course as passed
- confirm dashboard progress updates
- reassign a course manually
- re-import and confirm manual state survives

## Known Limitations

- Some scraping logic is still tuned to TUM page structure and may need adjustment if the source pages change.
- Semester extraction depends on the current enrichment pipeline and may leave some courses unknown.
- Complex study rules are stored mostly as notes; there is no general rule engine yet.
- The desktop mode is still a local web app inside `pywebview`, not a full native UI rewrite.

## Troubleshooting

### Import is slow

That is expected on first import, especially when:
- the course tree is large
- semester enrichment runs
- the source pages require fallback fetching

Re-imports should be better because some user state and known semester values are preserved.

### SQLite says the database is locked

Usually this means another process is still holding the DB file open.

Try:
- stop other running app/server instances
- restart the app

The app already uses:
- SQLite WAL mode
- a longer connection timeout
- a reduced write-lock window during import

### A page fails because TUM is unreachable

Some operations depend on live scraping during import or requirement-option refresh. If the source pages are unavailable, retry later or re-import when the site is reachable again.

### The UI does not reflect new code

Reload the page, and if needed restart the app process. Template and JS changes are not always visible in an already-open `pywebview` window until refresh.

## License / Assets

The TUM logo SVG used in the top bar is stored in:
- [`app/static/tum-logo.svg`](app/static/tum-logo.svg)

Make sure you use that asset in a way that is appropriate for your local/project context.
