from __future__ import annotations

import argparse

import uvicorn

from app.desktop import launch_desktop_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Studiengang Planner launcher")
    parser.add_argument("--web", action="store_true", help="Run as a local web server instead of a desktop app")
    parser.add_argument("--host", default="127.0.0.1", help="Web mode host")
    parser.add_argument("--port", type=int, default=8000, help="Web mode port")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload in web mode")
    args = parser.parse_args()

    if args.web:
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
        return

    launch_desktop_app()


if __name__ == "__main__":
    main()
