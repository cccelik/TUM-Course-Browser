from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import APP_TITLE
from app.routes import categories, courses, dashboard, programs
from app.storage_setup import initialize_storage


initialize_storage()

app = FastAPI(title=APP_TITLE)
APP_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}

app.include_router(programs.router)
app.include_router(dashboard.router)
app.include_router(courses.router)
app.include_router(categories.router)
