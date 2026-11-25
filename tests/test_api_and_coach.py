from fastapi.testclient import TestClient

from app.engine.coach import build_report


def test_live_gsi_on_by_default_and_needs_token():
    import json
    from pathlib import Path

    from app.config import gsi_token
    from app.main import app

    client = TestClient(app)
    health = client.get("/health").json()
    assert health["live_integration_enabled"] is True
    assert health["provider"]["connected"] is False

    payload = json.loads((Path(__file__).resolve().parent.parent / "config" / "mock_scenarios"
                          / "01_laning_juggernaut.json").read_text(encoding="utf-8"))
    payload.pop("dotasense_mock")
    assert client.post("/gsi", json=payload).status_code == 401
    assert client.post("/gsi", json={**payload, "auth": {"token": "wrong"}}).status_code == 401
    assert client.post("/gsi", json={**payload, "auth": {"token": gsi_token()}}).status_code == 200

    assert client.get("/state").status_code == 401
    live = client.get("/state", headers={"X-DotaSense-Token": gsi_token()}).json()
    assert live["source"] == "live_gsi" and live["is_mock"] is False
    assert live["hero"]["name"] == "npc_dota_hero_juggernaut"
    assert client.get("/health").json()["provider"]["connected"] is True
    body = client.get("/analysis", params={"history": "false"}, headers={"X-DotaSense-Token": gsi_token()}).json()
    assert body["recommendations"]
    assert client.get("/state", params={"scenario": "01_laning_juggernaut"}).json()["is_mock"] is True


def test_dota_cfg_install_into_steam_library(tmp_path, monkeypatch):
    from app.gsi import dota_cfg

    steam = tmp_path / "Steam"
    library = tmp_path / "Games" / "SteamLibrary"
    (library / dota_cfg.DOTA_DIR / "game" / "dota").mkdir(parents=True)
    (steam / "steamapps").mkdir(parents=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n'
        % (str(steam).replace("\\", "\\\\"), str(library).replace("\\", "\\\\")), encoding="utf-8")
    monkeypatch.setenv("DOTASENSE_STEAM_DIR", str(steam))
    monkeypatch.delenv("DOTASENSE_DOTA_DIR", raising=False)

    assert dota_cfg.find_dota_dir() == library / dota_cfg.DOTA_DIR
    assert not dota_cfg.is_installed()
    path = dota_cfg.install()
    assert path.parent.name == "gamestate_integration"
    text = path.read_text(encoding="utf-8")
    assert '"uri"           "http://127.0.0.1:' in text and dota_cfg.gsi_token() in text
    assert dota_cfg.is_installed()


def test_coach_report_from_match_payload():
    # Minimal payload with the same shape as OpenDota /matches/{id} (test fixture, not real data).
    match = {
        "match_id": 123, "duration": 40 * 60, "radiant_win": True,
        "players": [{
            "player_slot": 0, "hero_id": 8, "account_id": 42, "kills": 5, "deaths": 11, "assists": 3,
            "gold_per_min": 400, "xp_per_min": 500, "last_hits": 150,
            "item_0": 116, "purchase_log": [{"time": 25 * 60, "key": "black_king_bar"}],
            "benchmarks": {"gold_per_min": {"raw": 400, "pct": 0.2}, "last_hits_per_min": {"raw": 3.7, "pct": 0.3}},
        }],
    }
    report = build_report(match, account_id=42)
    assert report["result"] == "Win" and report["hero"] == "Juggernaut"
    assert report["item_timings"][0]["minute"] == 25.0
    assert len(report["suggestions"]) >= 3


def test_unknown_scenario_is_404():
    from app.main import app

    client = TestClient(app)
    assert client.get("/analysis", params={"scenario": "nope"}).status_code == 404


def test_reports_kept_per_player(tmp_path):
    from app.database import models as db
    from app.database.connection import connect

    conn = connect(tmp_path / "t.db")
    db.save_report(conn, {"match_id": "1", "hero": "Juggernaut"})
    db.save_report(conn, {"match_id": "1", "hero": "Lina"})
    assert {r["hero"] for r in db.list_reports(conn)} == {"Juggernaut", "Lina"}


def test_request_error_hides_api_key():
    import requests

    from app.data.opendota import OpenDotaClient, OpenDotaError

    class Boom:
        def get(self, url, params=None, timeout=None):
            raise requests.ConnectionError(f"failed {url}?api_key={params['api_key']}")

    try:
        OpenDotaClient(api_key="SECRETKEY", offline=False, http=Boom()).match(1)
    except OpenDotaError as exc:
        assert "SECRETKEY" not in str(exc)
