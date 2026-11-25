"""Check public GitHub releases and verify the Windows installer before launching it."""
from __future__ import annotations

import configparser
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path

REPO = "prasetyofauzy1-hash/dota-sense-ai"
RELEASE_ROOT = f"https://github.com/{REPO}/releases"
MANIFEST_URL = f"{RELEASE_ROOT}/latest/download/dotasense-update.json"
INSTALLER_NAME = "DotaSenseAI-Setup.exe"
MAX_INSTALLER_BYTES = 1024**3
_MANIFEST_LIMIT = 4096
_RELEASE_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
log = logging.getLogger(__name__)


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class UpdateStatus:
    checking: bool = False
    checked: bool = False
    installing: bool = False
    release: Release | None = None
    error: str | None = None


def version_key(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,9}){2,3}", version):
        raise ValueError("Invalid release version")
    parts = tuple(map(int, version.split(".")))
    return parts + (0,) * (4 - len(parts))


def installed_version(executable: Path) -> str | None:
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read(executable.with_name("release.ini"), encoding="utf-8-sig")
        version = config["DotaSense"]["Version"]
        version_key(version)
        return version
    except (OSError, ValueError, configparser.Error, KeyError):
        return None


def parse_manifest(data: object, current_version: str) -> Release | None:
    version = data.get("version") if isinstance(data, dict) else None
    try:
        if not isinstance(version, str):
            raise ValueError("Missing version")
        newer = version_key(version) > version_key(current_version)
    except ValueError as exc:
        raise UpdateError("The release has an invalid version.") from exc
    if not newer:
        return None

    digest, size = data.get("sha256"), data.get("size")
    if (type(size) is not int or not 0 < size <= MAX_INSTALLER_BYTES
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise UpdateError("This release has no verifiable Windows installer.")
    url = f"{RELEASE_ROOT}/download/v{version}/{INSTALLER_NAME}"
    return Release(version, url, size, digest)


class _ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != "https" or target.hostname not in _RELEASE_HOSTS:
            raise UpdateError("GitHub sent an unexpected download redirect.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, timeout: int):
    request = urllib.request.Request(url, headers={"User-Agent": "DotaSenseAI"})
    return urllib.request.build_opener(_ReleaseRedirects()).open(request, timeout=timeout)


def check_for_update(current_version: str) -> Release | None:
    try:
        with _open(MANIFEST_URL, timeout=10) as response:
            data = response.read(_MANIFEST_LIMIT + 1)
        if len(data) > _MANIFEST_LIMIT:
            raise UpdateError("The release response was too large.")
        return parse_manifest(json.loads(data), current_version)
    except (OSError, ValueError, HTTPException) as exc:
        log.info("GitHub update check failed: %s", exc)
        raise UpdateError("Could not check GitHub for updates. Try again later.") from exc


def download_installer(release: Release, update_dir: Path) -> Path:
    partial = None
    try:
        update_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        received = 0
        with tempfile.NamedTemporaryFile(dir=update_dir, prefix="download-", suffix=".part", delete=False) as output:
            partial = Path(output.name)
            with _open(release.url, timeout=20) as response:
                while chunk := response.read(256 * 1024):
                    received += len(chunk)
                    if received > release.size:
                        raise UpdateError("The installer did not match the release size.")
                    digest.update(chunk)
                    output.write(chunk)
        if received != release.size or digest.hexdigest() != release.sha256:
            raise UpdateError("The installer did not match the release checksum.")
        installer = update_dir / INSTALLER_NAME
        os.replace(partial, installer)
        return installer
    except (OSError, HTTPException) as exc:
        log.info("Installer download failed: %s", exc)
        raise UpdateError("Could not download the update. Try again later.") from exc
    finally:
        if partial is not None:
            _remove(partial)


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.debug("Could not remove %s", path)


def installer_command(installer: Path, app_dir: Path, pid: int) -> list[str]:
    return [str(installer), "/SILENT", "/NOCANCEL", "/NORESTART",
            f"/DIR={app_dir}", f"/DOTASENSEUPDATEPID={pid}"]


def launch_installer(installer: Path, app_dir: Path) -> None:
    import ctypes

    # PyInstaller's DLL search path is inherited by subprocesses on Windows.
    set_dll_directory = ctypes.windll.kernel32.SetDllDirectoryW
    set_dll_directory.argtypes = [ctypes.c_wchar_p]
    if not set_dll_directory(None):
        raise OSError("Could not reset the DLL search path")
    try:
        subprocess.Popen(installer_command(installer, app_dir, os.getpid()), cwd=installer.parent,
                         env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
    finally:
        set_dll_directory(sys._MEIPASS)


class Updater:
    def __init__(self, version: str, app_dir: Path, update_dir: Path):
        self.version = version
        self._app_dir = app_dir
        self._update_dir = update_dir.resolve()
        self._lock = threading.Lock()
        self.status = UpdateStatus()

    def cleanup(self) -> None:
        _remove(self._update_dir / INSTALLER_NAME)
        for partial in self._update_dir.glob("download-*.part"):
            _remove(partial)

    def start_check(self) -> None:
        with self._lock:
            if self.status.checking or self.status.installing:
                return
            self.status = UpdateStatus(checking=True)
        threading.Thread(target=self._check, name="update-check", daemon=True).start()

    def _check(self) -> None:
        try:
            self.status = UpdateStatus(checked=True, release=check_for_update(self.version))
        except UpdateError as exc:
            self.status = UpdateStatus(checked=True, error=str(exc))

    def install(self, release: Release) -> bool:
        with self._lock:
            if self.status.checking or self.status.installing or self.status.release != release:
                return False
            self.status = UpdateStatus(checked=True, installing=True, release=release)
        try:
            installer = download_installer(release, self._update_dir)
            launch_installer(installer, self._app_dir)
        except (OSError, UpdateError) as exc:
            log.warning("Could not install update: %s", exc)
            message = str(exc) if isinstance(exc, UpdateError) else "Could not start the installer. Try again."
            self.status = UpdateStatus(checked=True, release=release, error=message)
            return False
        return True
