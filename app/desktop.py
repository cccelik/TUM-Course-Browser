from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass

import requests
import uvicorn

from app.config import APP_TITLE


@dataclass
class DesktopServer:
    host: str
    port: int
    server: uvicorn.Server
    thread: threading.Thread

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def launch_desktop_app() -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "Desktop mode requires 'pywebview'. Install it with 'pip install -r requirements.txt'."
        ) from exc

    desktop_server = start_embedded_server()
    try:
        wait_for_server(desktop_server.url)
        webview.create_window(APP_TITLE, desktop_server.url, width=1440, height=980, min_size=(1100, 760))
        webview.start()
    finally:
        stop_embedded_server(desktop_server)


def start_embedded_server() -> DesktopServer:
    host = "127.0.0.1"
    port = _find_free_port()
    config = uvicorn.Config("app.main:app", host=host, port=port, reload=False, log_level="info")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="studiengang-planner-server", daemon=True)
    thread.start()
    return DesktopServer(host=host, port=port, server=server, thread=thread)


def stop_embedded_server(desktop_server: DesktopServer) -> None:
    desktop_server.server.should_exit = True
    desktop_server.thread.join(timeout=5)


def wait_for_server(base_url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/healthz", timeout=1.5)
            if response.ok:
                return
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(0.15)
    raise RuntimeError(f"Embedded server did not start in time: {last_error}")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
