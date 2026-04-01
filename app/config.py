from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_DB_PATH = DATA_DIR / "program_registry.db"
LEGACY_COMBINED_DB_PATH = DATA_DIR / "studiengang_planner.db"
APP_TITLE = "Studiengang Planner"
