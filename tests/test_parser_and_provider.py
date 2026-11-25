from app.gsi.parser import parse_gsi
from app.gsi.provider import MockProvider
from app.models import DataSource, GamePhase


def test_mock_scenarios_are_labeled_mock():
    provider = MockProvider()
    assert provider.scenario_names()
    for name in provider.scenario_names():
        state = MockProvider(scenario=name).current_state()
        assert state.is_mock and state.source == DataSource.MOCK
        assert state.hero.hero_id is not None
        assert state.items and state.abilities


def test_parser_records_missing_fields():
    state = parse_gsi({"map": {"game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"}})
    assert state.match_active
    assert state.phase == GamePhase.PRE_GAME
    for field in ("hero", "items", "abilities", "gold", "game_time", "enemy_heroes"):
        assert field in state.missing_fields


def test_parser_reads_items_and_phase():
    state = parse_gsi({
        "map": {"clock_time": 20 * 60, "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"},
        "player": {"gold": 1000},
        "hero": {"name": "npc_dota_hero_juggernaut", "level": 12},
        "items": {"slot0": {"name": "item_power_treads"}, "slot1": {"name": "empty"}},
        "abilities": {},
    })
    assert state.items == ["power_treads"]
    assert state.hero.hero_id == 8
    assert state.phase == GamePhase.MID
