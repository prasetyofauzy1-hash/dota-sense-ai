from fastapi.testclient import TestClient

from app.engine.coach import build_report


def test_gsi_receiver_disabled_by_default():
    from app.main import app

    client = TestClient(app)
    assert client.post("/gsi", json={"map": {}}).status_code == 403
    assert client.get("/health").json()["live_integration_enabled"] is False
    assert client.get("/state").json()["is_mock"] is True
    body = client.get("/analysis", params={"history": "false"}).json()
    assert body["recommendations"]


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
