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


def test_coach_handles_null_benchmark_pct_and_short_match():
    match = {
        "match_id": 999, "duration": 0, "radiant_win": False, "game_mode": 1, "lobby_type": 4,
        "players": [{
            "player_slot": 0, "hero_id": 0, "kills": 0, "deaths": 0, "assists": 0,
            "gold_per_min": 0, "xp_per_min": 0, "last_hits": 0,
            "benchmarks": {
                "gold_per_min": {"raw": 0, "pct": None},
                "last_hits_per_min": {"raw": None},
            },
        }],
    }
    report = build_report(match, hero_id=0)
    assert report["short_match"] is True
    assert report["benchmarks_pct"] == {}
    assert any("under 5 min" in s for s in report["suggestions"])


def test_coach_role_aware_support_vs_core():
    match = {
        "match_id": 555, "duration": 38 * 60, "radiant_win": False, "game_mode": 22, "lobby_type": 7,
        "players": [
            {"player_slot": 0, "hero_id": 8, "net_worth": 22000, "gold_per_min": 610, "kills": 8, "deaths": 3, "assists": 6, "last_hits": 310},
            {"player_slot": 1, "hero_id": 11, "net_worth": 19000, "gold_per_min": 540, "kills": 6, "deaths": 5, "assists": 7, "last_hits": 270},
            {"player_slot": 2, "hero_id": 2, "net_worth": 15000, "gold_per_min": 440, "kills": 3, "deaths": 6, "assists": 10, "last_hits": 190},
            {"player_slot": 3, "hero_id": 86, "net_worth": 8500, "gold_per_min": 260, "kills": 2, "deaths": 6, "assists": 12, "last_hits": 55, "obs_placed": 10, "sen_placed": 14},
            {
                "player_slot": 4, "hero_id": 119, "net_worth": 6200, "gold_per_min": 198, "xp_per_min": 380,
                "kills": 2, "deaths": 11, "assists": 12, "last_hits": 30, "obs_placed": 1, "sen_placed": 4,
                "purchase_log": [
                    {"time": 18 * 60, "key": "arcane_boots"},
                    {"time": 22 * 60, "key": "mithril_hammer"},
                    {"time": 26 * 60, "key": "glimmer_cape"},
                ],
                "benchmarks": {"gold_per_min": {"raw": 198, "pct": 0.05}, "last_hits_per_min": {"raw": 0.8, "pct": 0.1}},
            },
        ],
    }
    report = build_report(match, hero_id=119)
    assert report["role"] == "Support"
    assert report["game_mode"] == "Ranked All Pick"
    assert report["wards"] == {"obs": 1, "sen": 4}
    assert not any("last-hitting" in s.lower() for s in report["suggestions"])
    assert not any("gpm was low" in s.lower() for s in report["suggestions"])
    assert any("Observer Wards" in s for s in report["suggestions"])
    assert any("11 deaths" in s for s in report["suggestions"])
    assert [t["item"] for t in report["item_timings"]] == ["arcane_boots", "glimmer_cape"]


def test_coach_excludes_components_and_checks_mid_plus_late_popularity():
    match = {
        "match_id": 777, "duration": 35 * 60, "radiant_win": True, "game_mode": 22, "lobby_type": 7,
        "players": [{
            "player_slot": 0, "hero_id": 104, "kills": 10, "deaths": 2, "assists": 10,
            "gold_per_min": 600, "xp_per_min": 700, "last_hits": 250,
            "item_0": 1,
            "item_1": 116,
            "purchase_log": [
                {"time": 12 * 60, "key": "blink"},
                {"time": 18 * 60, "key": "hyperstone"},
                {"time": 22 * 60, "key": "black_king_bar"},
            ],
            "benchmarks": {"gold_per_min": {"raw": 600, "pct": 0.75}, "last_hits_per_min": {"raw": 7.1, "pct": 0.8}},
        }],
    }
    popularity = {
        "mid_game_items": {"1": 91, "127": 89},
        "late_game_items": {"116": 42, "55": 12},
    }
    report = build_report(match, hero_id=104, popularity=popularity)
    assert [t["item"] for t in report["item_timings"]] == ["blink", "black_king_bar"]
    assert not any("Less common" in s for s in report["suggestions"])


def test_coach_turbo_mode_skips_standard_gpm_tips():
    match = {
        "match_id": 888, "duration": 18 * 60, "radiant_win": True, "game_mode": 23, "lobby_type": 0,
        "players": [{
            "player_slot": 0, "hero_id": 12, "kills": 10, "deaths": 1, "assists": 8,
            "gold_per_min": 1100, "xp_per_min": 1300, "last_hits": 80,
            "benchmarks": {"gold_per_min": {"raw": 1100, "pct": 0.2}, "last_hits_per_min": {"raw": 4.4, "pct": 0.2}},
        }],
    }
    report = build_report(match, hero_id=12)
    assert report["is_turbo"] is True
    assert report["game_mode"] == "Turbo"
    assert any("Turbo match" in s for s in report["suggestions"])
    assert not any("GPM was low" in s for s in report["suggestions"])


def test_parse_match_id_and_account_id():
    import pytest

    from app.data.opendota import parse_match_id
    from app.engine.coach import parse_account_id

    assert parse_match_id("9104260611") == 9104260611
    assert parse_match_id("https://www.opendota.com/matches/9104260611") == 9104260611
    assert parse_match_id("https://dotabuff.com/matches/9104260611?foo=1") == 9104260611
    for bad in ("", "abc", "0", "-5", "123abc"):
        with pytest.raises(ValueError):
            parse_match_id(bad)

    assert parse_account_id("12345") == 12345
    assert parse_account_id(str(76561197960265728 + 12345)) == 12345
    assert parse_account_id("") is None
    with pytest.raises(ValueError):
        parse_account_id("not_a_number")


def test_opendota_client_retries_429_and_handles_errors(tmp_path):
    from types import SimpleNamespace

    import pytest
    import requests

    from app.data.opendota import OpenDotaClient, OpenDotaError
    from app.database.connection import connect

    conn = connect(tmp_path / "cache.db")
    calls = []

    class FakeSession:
        def __init__(self, responses):
            self._responses = list(responses)

        def get(self, url, params=None, timeout=None):
            calls.append(url)
            item = self._responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    ok_resp = SimpleNamespace(
        status_code=200,
        headers={},
        json=lambda: {"match_id": 100, "players": [{"player_slot": 0, "hero_id": 8, "purchase_log": [{"time": 60, "key": "blink"}]}]},
    )
    rl_resp = SimpleNamespace(status_code=429, headers={"Retry-After": "0"}, json=lambda: {})
    client = OpenDotaClient(conn, offline=False, http=FakeSession([rl_resp, ok_resp]), max_retries=2, backoff_base=0)
    data = client.match(100)
    assert data["match_id"] == 100
    assert len(calls) == 2

    not_found = SimpleNamespace(status_code=404, headers={}, json=lambda: {})
    client_404 = OpenDotaClient(conn, offline=False, http=FakeSession([not_found]), max_retries=2, backoff_base=0)
    with pytest.raises(OpenDotaError) as exc_info:
        client_404.match(999999999999)
    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value).lower()

    client_to = OpenDotaClient(conn, offline=False, http=FakeSession([requests.Timeout("slow"), requests.Timeout("slow")]), max_retries=1, backoff_base=0)
    with pytest.raises(OpenDotaError) as to_info:
        client_to.match(200)
    assert to_info.value.timed_out is True
    assert "timed out" in str(to_info.value).lower()

    bad_json = SimpleNamespace(status_code=200, headers={}, json=lambda: (_ for _ in ()).throw(ValueError("bad json")))
    client_bad = OpenDotaClient(conn, offline=False, http=FakeSession([bad_json]), max_retries=0, backoff_base=0)
    with pytest.raises(OpenDotaError):
        client_bad.match(300)


def test_coach_rejects_mismatched_public_account_on_hero_fallback():
    import pytest

    match = {
        "match_id": 444, "duration": 30 * 60, "radiant_win": True,
        "players": [
            {"player_slot": 0, "hero_id": 8, "account_id": 99999, "kills": 5, "deaths": 2, "assists": 4, "gold_per_min": 550, "xp_per_min": 600, "last_hits": 200},
            {"player_slot": 1, "hero_id": 86, "account_id": None, "kills": 1, "deaths": 4, "assists": 10, "gold_per_min": 300, "xp_per_min": 400, "last_hits": 40},
        ],
    }
    with pytest.raises(ValueError, match="different public account"):
        build_report(match, account_id=12345, hero_id=8)
    # Private profile (account_id=None) still falls back to hero_id cleanly.
    rep = build_report(match, account_id=12345, hero_id=86)
    assert rep["hero"] == "Rubick"
