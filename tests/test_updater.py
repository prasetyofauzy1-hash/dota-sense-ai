import hashlib
import io
import json
from urllib.error import URLError
from urllib.request import Request

import pytest

from app import updater

INSTALLER = b"installer bytes"
DIGEST = hashlib.sha256(INSTALLER).hexdigest()


def release_data(version="0.2.0.10"):
    return {"version": version, "size": len(INSTALLER), "sha256": DIGEST}


@pytest.mark.parametrize(("installed", "latest", "available"), [
    ("0.2.0.9", "0.2.0.10", True),
    ("0.2.0.10", "0.2.0.10", False),
    ("0.2.0.11", "0.2.0.10", False),
    ("0.2.0.999", "0.2.1.1", True),
    ("0.2.0", "0.2.0.0", False),
])
def test_version_comparison(installed, latest, available):
    release = updater.parse_manifest(release_data(latest), installed)
    assert (release is not None) == available


@pytest.mark.parametrize("version", ["1.0", "1.0.0-beta", "1.0.0/elsewhere", None])
def test_rejects_invalid_versions(version):
    with pytest.raises(updater.UpdateError, match="invalid version"):
        updater.parse_manifest(release_data(version), "0.0.0")


@pytest.mark.parametrize(("field", "value"), [
    ("sha256", None),
    ("sha256", "not-a-digest"),
    ("size", 0),
    ("size", True),
    ("size", updater.MAX_INSTALLER_BYTES + 1),
])
def test_rejects_untrusted_installer_metadata(field, value):
    data = release_data()
    data[field] = value
    with pytest.raises(updater.UpdateError, match="no verifiable Windows installer"):
        updater.parse_manifest(data, "0.0.0")


@pytest.mark.parametrize("target", ["http://github.com/file", "https://not-github.com/file"])
def test_rejects_untrusted_release_redirects(target):
    with pytest.raises(updater.UpdateError, match="unexpected download redirect"):
        updater._ReleaseRedirects().redirect_request(Request(updater.MANIFEST_URL), None, 302, "", {}, target)


def test_check_uses_public_manifest_and_versioned_installer(monkeypatch):
    def manifest(url, timeout):
        assert url == updater.MANIFEST_URL
        return io.BytesIO(json.dumps(release_data()).encode())

    monkeypatch.setattr(updater, "_open", manifest)
    release = updater.check_for_update("0.2.0.1")
    assert release.url == f"{updater.RELEASE_ROOT}/download/v0.2.0.10/{updater.INSTALLER_NAME}"


def test_reads_installer_version_only_from_valid_marker(tmp_path):
    exe = tmp_path / "DotaSenseAI.exe"
    assert updater.installed_version(exe) is None
    marker = tmp_path / "release.ini"
    marker.write_text("[DotaSense]\nVersion=bad\n")
    assert updater.installed_version(exe) is None
    marker.write_text("[DotaSense]\nVersion=0.2.0.12\n")
    assert updater.installed_version(exe) == "0.2.0.12"


def test_download_verifies_and_renames_installer(tmp_path, monkeypatch):
    release = updater.parse_manifest(release_data(), "0.0.0")
    monkeypatch.setattr(updater, "_open", lambda *_a, **_kw: io.BytesIO(INSTALLER))
    path = updater.download_installer(release, tmp_path)
    assert path.name == updater.INSTALLER_NAME
    assert path.read_bytes() == INSTALLER
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("contents", [b"", INSTALLER + b"!", b"x" * len(INSTALLER)])
def test_bad_download_is_not_left_on_disk(tmp_path, monkeypatch, contents):
    release = updater.parse_manifest(release_data(), "0.0.0")
    monkeypatch.setattr(updater, "_open", lambda *_a, **_kw: io.BytesIO(contents))
    with pytest.raises(updater.UpdateError, match="did not match"):
        updater.download_installer(release, tmp_path)
    assert not list(tmp_path.iterdir())


def test_check_network_error_is_actionable(monkeypatch):
    def fail(*_args, **_kwargs):
        raise URLError("offline")

    monkeypatch.setattr(updater, "_open", fail)
    with pytest.raises(updater.UpdateError, match="Could not check GitHub"):
        updater.check_for_update("0.0.0")


def test_upgrade_disallows_cancellation(tmp_path):
    installer = tmp_path / updater.INSTALLER_NAME
    command = updater.installer_command(installer, tmp_path / "DotaSense AI", 123)
    assert command == [str(installer), "/SILENT", "/NOCANCEL", "/NORESTART",
                       f"/DIR={tmp_path / 'DotaSense AI'}", "/DOTASENSEUPDATEPID=123"]


def test_failed_installer_launch_can_be_retried(tmp_path, monkeypatch):
    release = updater.parse_manifest(release_data(), "0.0.0")
    manager = updater.Updater("0.0.0", tmp_path, tmp_path / "updates")
    assert manager.install(release) is False
    monkeypatch.setattr(updater, "check_for_update", lambda _version: release)
    manager._check()
    monkeypatch.setattr(updater, "_open", lambda *_a, **_kw: io.BytesIO(INSTALLER))

    def blocked(*_args, **_kwargs):
        raise OSError("blocked")

    monkeypatch.setattr(updater, "launch_installer", blocked)
    assert manager.install(release) is False
    assert manager.status.error and manager.status.release == release
    calls = []
    monkeypatch.setattr(updater, "launch_installer", lambda *args: calls.append(args))
    assert manager.install(release) is True
    assert manager.install(release) is False
    assert calls == [(tmp_path / "updates" / updater.INSTALLER_NAME, tmp_path)]
