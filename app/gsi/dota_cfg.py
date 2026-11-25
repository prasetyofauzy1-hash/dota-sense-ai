"""Find the Dota 2 install and write the Game State Integration config file.

Dota 2 reads `game/dota/cfg/gamestate_integration/*.cfg` at start and pushes the
player's own game state to the URI in that file. This is the only file DotaSense AI
writes outside its own data folder; it never touches game binaries or memory.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from app.config import gsi_token, settings

CFG_NAME = "gamestate_integration_dotasense.cfg"
DOTA_DIR = Path("steamapps") / "common" / "dota 2 beta"
CFG_SUBDIR = Path("game") / "dota" / "cfg" / "gamestate_integration"
LAUNCH_OPTION = "-gamestateintegration"


def cfg_text(uri: str | None = None, token: str | None = None) -> str:
    uri = uri or settings.gsi_url
    token = token or gsi_token()
    return f'''"DotaSense AI"
{{
    "uri"           "{uri}"
    "timeout"       "5.0"
    "buffer"        "0.5"
    "throttle"      "1.0"
    "heartbeat"     "10.0"
    "data"
    {{
        "provider"  "1"
        "map"       "1"
        "player"    "1"
        "hero"      "1"
        "abilities" "1"
        "items"     "1"
    }}
    "auth"
    {{
        "token"     "{token}"
    }}
}}
'''


def _registry_steam_paths() -> list[Path]:
    if sys.platform != "win32":
        return []
    import winreg

    found = []
    for hive, key, value in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ):
        try:
            with winreg.OpenKey(hive, key) as k:
                found.append(Path(winreg.QueryValueEx(k, value)[0]))
        except OSError:
            continue
    return found


def steam_roots() -> list[Path]:
    roots = _registry_steam_paths()
    if env := os.getenv("DOTASENSE_STEAM_DIR"):
        roots.insert(0, Path(env))
    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        if base := os.getenv(env_name):
            roots.append(Path(base) / "Steam")
    roots += [Path.home() / ".steam" / "steam", Path.home() / ".local" / "share" / "Steam"]
    unique: list[Path] = []
    for r in roots:
        if r not in unique:
            unique.append(r)
    return unique


def library_folders(steam_root: Path) -> list[Path]:
    """Steam library folders listed in steamapps/libraryfolders.vdf (plus the Steam root)."""
    folders = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return folders
    for raw in re.findall(r'"path"\s+"([^"]+)"', text):
        path = Path(raw.replace("\\\\", "\\"))
        if path not in folders:
            folders.append(path)
    return folders


def find_dota_dir() -> Path | None:
    if env := os.getenv("DOTASENSE_DOTA_DIR"):
        return Path(env)
    for root in steam_roots():
        for lib in library_folders(root):
            candidate = lib / DOTA_DIR
            if (candidate / "game" / "dota").is_dir():
                return candidate
    return None


def cfg_path(dota_dir: Path | None = None) -> Path | None:
    dota_dir = dota_dir or find_dota_dir()
    return dota_dir / CFG_SUBDIR / CFG_NAME if dota_dir else None


def is_installed(dota_dir: Path | None = None) -> bool:
    path = cfg_path(dota_dir)
    try:
        return bool(path) and path.read_text(encoding="utf-8") == cfg_text()
    except OSError:
        return False


def install(dota_dir: Path | None = None) -> Path:
    """Write the config file; raises FileNotFoundError when Dota 2 is not found."""
    path = cfg_path(dota_dir)
    if path is None:
        raise FileNotFoundError("Dota 2 install not found. Copy the config file manually (see below).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cfg_text(), encoding="utf-8")
    return path
