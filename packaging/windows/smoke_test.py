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
    upgrade_installer = os.getenv("SMOKE_UPGRADE_INSTALLER")
    if upgrade_installer:
        marker = Path(exe).with_name("release.ini")
        version = os.environ["VERSION"]
        assert f"Version={version}" in marker.read_text(encoding="utf-8-sig")
        marker.write_text("[DotaSense]\nVersion=0.0.0\n", encoding="ascii")
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
                run_ui(page, dota, token, payload, out)
                if upgrade_installer:
                    check_upgrade(page, proc, Path(exe).resolve().parent, Path(upgrade_installer),
                                  version, env, data, out, token)
                else:
                    quit_app(page)
                    assert proc.wait(timeout=30) == 0, proc.returncode
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


def run_ui(page, dota: Path, token: str, payload: dict, out: Path) -> None:
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
    page.get_by_text("Enemy lineup not available").first.wait_for(timeout=30_000)
    picker = page.locator("[data-testid=stMultiSelect] input").first
    picker.click()
    picker.fill("Phantom Assassin")
    picker.press("Enter")
    page.keyboard.press("Escape")
    page.locator(".ds-glance").get_by_text("Phantom Assassin").first.wait_for(timeout=30_000)
    assert page.get_by_text("Missing data:").count() == 0, "enemy lineup still reported missing"
    time.sleep(2)
    page.screenshot(path=str(out / "2-live-gsi.png"), full_page=True)
    assert "MOCK DATA" not in page.content()

    page.get_by_role("tab", name="Pro Counter Intel").click()
    page.get_by_text("Pro tournament counter items", exact=True).wait_for()
    page.get_by_text("selected pro tournaments", exact=False).wait_for()
    page.get_by_text("Juggernaut across all opponents").or_(page.get_by_text("Juggernaut against")).wait_for()


def quit_app(page) -> None:
    expand = page.locator("[data-testid=stExpandSidebarButton]")
    if expand.count() and expand.first.is_visible():
        expand.first.click()
    page.get_by_role("button", name="Quit DotaSense AI").click()


def check_upgrade(page, proc, app_dir: Path, installer: Path, version: str, env: dict,
                  data: Path, out: Path, token: str) -> None:
    sys.path.insert(0, str(ROOT))
    from app.updater import installer_command

    page.get_by_text("App updates · v0.0.0", exact=True).wait_for()
    command = installer_command(installer.resolve(), app_dir, proc.pid)
    command.append(f"/LOG={out.resolve() / 'upgrade.log'}")
    setup = subprocess.Popen(command, env=env)
    try:
        quit_app(page)
        assert proc.wait(timeout=30) == 0, proc.returncode
        assert setup.wait(timeout=120) == 0, setup.returncode
        assert wait_json(f"{GSI}/health", timeout=120)["app"] == "dotasense"
        page.goto((data / "desktop_url.txt").read_text(encoding="utf-8").strip())
        page.get_by_text(f"App updates · v{version}", exact=True).wait_for(timeout=60_000)
        assert (data / ".dotasense_gsi_token").read_text(encoding="utf-8").strip() == token
        quit_app(page)
    finally:
        if setup.poll() is None:
            setup.kill()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
