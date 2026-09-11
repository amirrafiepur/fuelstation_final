"""
Native desktop entrypoint for the Fuel Station Management App.

Normal mode:
    Starts a local Waitress server as a child process and opens it in a
    PySide6 QWebEngineView window.

Server mode:
    The same executable/interpreter is re-launched with --server and runs
    Waitress only. This keeps the Django server separate from the Qt GUI
    process while still allowing a single executable to be packaged by
    PyInstaller.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
WINDOW_TITLE = "سامانه حسابداری جایگاه ۱۴۰ جهان‌پور"


def _project_root() -> Path:
    """Return the source/bundle root used by Django."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def _configure_environment() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.desktop")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")


def _run_server(port: int) -> int:
    """Run Waitress in the child process."""
    _configure_environment()

    # Import Django/Waitress only in server mode so the GUI process does not
    # carry Django server startup imports unnecessarily.
    import django
    from waitress import serve

    django.setup()

    # A packaged installation has its mutable SQLite database under
    # LocalAppData. Run migrations automatically on startup so a fresh
    # installation is structurally ready before the GUI opens. The fixed
    # station/nozzle configuration is safe to seed idempotently. We do NOT
    # silently create a license or operator account because those are
    # business/security decisions outside the approved architecture.
    from django.core.management import call_command
    call_command("migrate", interactive=False, verbosity=0)
    call_command("seed_station", verbosity=0)

    from config.wsgi import application

    print(f"Fuel Station server listening on http://{HOST}:{port}", flush=True)
    serve(application, host=HOST, port=port, threads=4)
    return 0


def _find_free_port() -> int:
    """Ask Windows for an unused localhost TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _server_command(port: int) -> list[str]:
    """
    Build the child-process command.

    In a PyInstaller build, sys.executable is the packaged application and
    --server switches that executable into server mode. In source mode,
    python -m desktop.main does the same thing.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--server", str(port)]
    return [sys.executable, "-m", "desktop.main", "--server", str(port)]


def _start_server(port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.desktop"

    creationflags = 0
    startupinfo = None

    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    return subprocess.Popen(
        _server_command(port),
        cwd=str(_project_root()),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )


def _wait_for_server(port: int, process: subprocess.Popen, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False

        try:
            with socket.create_connection((HOST, port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.1)

    return False


def _stop_server(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _run_gui(port: int) -> int:
    # Qt imports stay out of server mode.
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication, QMainWindow
    from PySide6.QtWebEngineWidgets import QWebEngineView

    server = _start_server(port)
    if not _wait_for_server(port, server):
        _stop_server(server)
        raise RuntimeError(
            "Django/Waitress could not be started on localhost. "
            "Run the application from a terminal once to inspect the "
            "startup error if this persists."
        )

    class MainWindow(QMainWindow):
        def closeEvent(self, event):  # noqa: N802 - Qt API name
            _stop_server(server)
            event.accept()

    app = QApplication(sys.argv)
    app.setApplicationName(WINDOW_TITLE)
    app.setOrganizationName("140 Jahan Pour")

    window = MainWindow()
    window.setWindowTitle(WINDOW_TITLE)
    window.resize(1200, 760)
    window.setMinimumSize(900, 600)
    class CustomWebEnginePage(QWebEnginePage):
        def createWindow(self, window_type):
            return self
    view = QWebEngineView()
    page = CustomWebEnginePage(view)
    view.setPage(page)
    view.setUrl(QUrl(f"http://{HOST}:{port}/"))
    view.settings().setAttribute(
    QWebEngineSettings.WebAttribute.PdfViewerEnabled,True)
    window.setCentralWidget(view)
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("_server_port", nargs="?", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.server:
        port = args.port or args._server_port or DEFAULT_PORT
        return _run_server(port)

    port = args.port or _find_free_port()
    return _run_gui(port)


if __name__ == "__main__":
    raise SystemExit(main())
