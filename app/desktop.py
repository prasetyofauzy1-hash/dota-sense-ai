"""Windows desktop launcher: GSI receiver + API, the Streamlit dashboard and an app window.

Run from source with `python -m app.desktop`; the installer ships it as DotaSenseAI.exe.
The dashboard opens in a Microsoft Edge app window (no tabs or address bar); closing that
window quits DotaSense AI. Without Edge it opens in the default browser and the sidebar's
"Quit DotaSense AI" button stops it.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

os.environ.setdefault("DOTASENSE_DESKTOP", "1")

from app.config import FROZEN, ROOT_DIR, gsi_token, settings  # noqa: E402
from app.updater import Updater, installed_version  # noqa: E402

log = logging.getLogger("dotasense.desktop")
UI_PORT = int(os.getenv("DOTASENSE_UI_PORT", "47691"))
_window: subprocess.Popen | None = None
updates: Updater | None = None


def request_quit(code: int = 0) -> None:
    if _window is not None and _window.poll() is None:
        _window.terminate()
    log.info("Quitting (exit code %s)", code)
    logging.shutdown()
    os._exit(code)


def _setup_logging() -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.data_dir / "dotasense.log"
    if FROZEN or sys.stdout is None:
        stream = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stderr = stream
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return log_path


def _alert(message: str) -> None:
    log.error(message)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "DotaSense AI", 0x10)
    else:
        print(message, file=sys.__stderr__)


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get_json(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def _wait_http(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _edge_path() -> str | None:
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.getenv(env)
        if base:
            path = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if path.exists():
                return str(path)
    return None


def open_window(url: str, *, wait: bool) -> None:
    """Open the dashboard; with wait=True, quit when the app window is closed."""
    global _window
    edge = _edge_path()
    if edge is None:
        webbrowser.open(url)
        return
    profile = settings.data_dir / "window-profile"
    _window = subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
                                "--no-default-browser-check", "--disable-background-mode",
                                "--window-size=1400,900"])
    if not wait:
        return
    started = time.time()
    _window.wait()
    if time.time() - started < 5:
        # Edge handed the window to an already-running Edge process: keep serving.
        log.info("App window detached; use the sidebar Quit button to stop DotaSense AI")
        return
    request_quit()


def _start_api() -> None:
    import uvicorn

    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host=settings.gsi_host, port=settings.gsi_port,
                                           log_config=None, access_log=False))
    threading.Thread(target=server.run, name="gsi-api", daemon=True).start()


def _run_streamlit(port: int) -> None:
    from streamlit.web import cli as stcli

    os.chdir(ROOT_DIR)  # picks up .streamlit/config.toml (theme)
    sys.argv = ["streamlit", "run", str(ROOT_DIR / "app" / "dashboard.py"),
                "--server.address", "127.0.0.1", "--server.port", str(port), "--server.headless", "true",
                "--global.developmentMode", "false", "--browser.gatherUsageStats", "false",
                "--server.fileWatcherType", "none", "--server.runOnSave", "false",
                "--client.toolbarMode", "minimal"]
    stcli.main(prog_name="streamlit")


def main(argv: list[str] | None = None) -> None:
    global updates
    parser = argparse.ArgumentParser(prog="DotaSenseAI")
    parser.add_argument("--no-window", action="store_true", help="serve only, do not open the app window")
    args = parser.parse_args(argv)
    sys.modules.setdefault("app.desktop", sys.modules[__name__])  # same module for the dashboard's Quit button
    log_path = _setup_logging()
    url_file = settings.data_dir / "desktop_url.txt"
    health_url = f"http://127.0.0.1:{settings.gsi_port}/health"

    running = _get_json(health_url)
    if running and running.get("app") == "dotasense":
        if url_file.exists() and not args.no_window:
            open_window(url_file.read_text(encoding="utf-8").strip(), wait=False)
        return
    if not _port_free(settings.gsi_port, settings.gsi_host):
        _alert(f"Port {settings.gsi_port} is used by another program, so Dota 2 cannot reach DotaSense AI.\n"
               f"Close that program or set DOTASENSE_GSI_PORT. Log: {log_path}")
        sys.exit(1)

    if FROZEN and sys.platform == "win32":
        executable = Path(sys.executable)
        if version := installed_version(executable):
            updates = Updater(version, executable.parent, settings.data_dir / "updates")
            updates.cleanup()
            if not settings.offline:
                updates.start_check()

    ui_port = UI_PORT if _port_free(UI_PORT) else _free_port()
    url = f"http://127.0.0.1:{ui_port}"
    url_file.write_text(url, encoding="utf-8")
    gsi_token()  # create the token before Dota 2 or the dashboard needs it
    log.info("DotaSense AI starting: dashboard %s, GSI %s", url, settings.gsi_url)
    _start_api()

    def _open_when_ready() -> None:
        if not _wait_http(f"{url}/_stcore/health", 120):
            _alert(f"The dashboard did not start. See the log: {log_path}")
            request_quit(1)
        if not args.no_window:
            open_window(url, wait=True)

    threading.Thread(target=_open_when_ready, name="window", daemon=True).start()
    _run_streamlit(ui_port)


if __name__ == "__main__":
    main()
