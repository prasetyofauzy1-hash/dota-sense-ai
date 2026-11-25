"""End-to-end check of a built DotaSenseAI.exe (used by CI on Windows).

Starts the app without its window, pushes a GSI payload the way Dota 2 does, renders the
dashboard in a real browser, installs the GSI config into a fake Dota 2 folder from the UI
and quits with the sidebar button. Usage: python smoke_test.py <exe> <out_dir>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
GSI = "http://127.0.0.1:47690"


def wait_json(url: str, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return json.loads(r.read())
        except OSError:
            time.sleep(1)
    raise TimeoutError(url)


def main(exe: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix="dotasense-smoke-"))
    dota = data / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    env = {**os.environ, "DOTASENSE_DATA_DIR": str(data), "DOTASENSE_OFFLINE": "true",
           "DOTASENSE_DOTA_DIR": str(dota)}
    proc = subprocess.Popen([exe, "--no-window"], env=env)
    try:
        health = wait_json(f"{GSI}/health")
        assert health["app"] == "dotasense" and health["live_integration_enabled"] is True, health
        ui = (data / "desktop_url.txt").read_text(encoding="utf-8").strip()
        token = (data / ".dotasense_gsi_token").read_text(encoding="utf-8").strip()

        payload = json.loads((ROOT / "config" / "mock_scenarios" / "02_midgame_juggernaut.json").read_text("utf-8"))
        payload.pop("dotasense_mock")
        bad = urllib.request.Request(f"{GSI}/gsi", json.dumps(payload).encode(), {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(bad, timeout=5)
            raise AssertionError("GSI push without token was accepted")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401, exc.code

        with sync_playwright() as pw:
            if os.getenv("SMOKE_BROWSER_PATH"):
                browser = pw.chromium.launch(executable_path=os.environ["SMOKE_BROWSER_PATH"])
            else:
                browser = pw.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.goto(ui)
            try:
                run_ui(page, proc, dota, token, payload, out)
            except Exception:
                page.screenshot(path=str(out / "failure.png"), full_page=True)
                raise
            browser.close()
        print("Smoke test passed")
    finally:
        if proc.poll() is None:
            proc.kill()
        log = data / "dotasense.log"
        if log.exists():
            (out / "dotasense.log").write_text(log.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")


def run_ui(page, proc, dota: Path, token: str, payload: dict, out: Path) -> None:
    page.get_by_text("Connect Dota 2").first.wait_for(timeout=120_000)
    page.get_by_role("button", name="Install config into Dota 2").click()
    page.get_by_text("Config installed").or_(page.get_by_text("Config written to")).first.wait_for(timeout=30_000)
    cfg = dota / "game" / "dota" / "cfg" / "gamestate_integration" / "gamestate_integration_dotasense.cfg"
    assert token in cfg.read_text(encoding="utf-8"), "GSI config not written"
    page.screenshot(path=str(out / "1-waiting-for-dota.png"), full_page=True)

    payload["auth"] = {"token": token}
    req = urllib.request.Request(f"{GSI}/gsi", json.dumps(payload).encode(), {"Content-Type": "application/json"})
    assert json.loads(urllib.request.urlopen(req, timeout=5).read())["ok"] is True
    page.get_by_text("Receiving").first.wait_for(timeout=30_000)
    page.get_by_text("Juggernaut").first.wait_for(timeout=30_000)
    time.sleep(2)
    page.screenshot(path=str(out / "2-live-gsi.png"), full_page=True)
    assert "MOCK DATA" not in page.content()

    quit_button = page.get_by_role("button", name="Quit DotaSense AI")
    expand = page.locator("[data-testid=stExpandSidebarButton]")
    if expand.count() and expand.first.is_visible():
        expand.first.click()
    quit_button.click()
    assert proc.wait(timeout=30) == 0, proc.returncode


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
