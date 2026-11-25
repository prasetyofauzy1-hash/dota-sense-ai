from app.engine import counter_analyzer, decision_engine, item_recommender
from app.gsi.parser import parse_gsi
from app.gsi.provider import MockProvider
from app.models import Priority
from app.services import analyze


def _state(**overrides):
    payload = {
        "map": {"clock_time": 22 * 60, "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"},
        "player": {"gold": 4500, "kills": 3, "deaths": 2, "assists": 4},
        "hero": {"name": "npc_dota_hero_juggernaut", "level": 15, "health_percent": 80},
        "items": {"slot0": {"name": "item_power_treads"}},
        "abilities": {},
        "dotasense_mock": {"is_mock": True, "enemy_heroes": ["lion", "zuus", "lina"]},
    }
    payload.update(overrides)
    return parse_gsi(payload)


def test_threats_use_curated_then_roles():
    threats = counter_analyzer.analyze_threats(["lion", "abaddon"])
    by_hero = {t.hero: t for t in threats}
    assert by_hero["lion"].tags_source == "curated"
    assert by_hero["abaddon"].tags_source == "roles"


def test_matchup_history_raises_severity():
    base = counter_analyzer.analyze_threats(["lion"])[0].severity
    bad = counter_analyzer.analyze_threats(["lion"], matchups=[{"hero_id": 26, "games_played": 100, "wins": 30}])[0]
    assert bad.severity > base


def test_magic_lineup_recommends_bkb_with_all_fields():
    state = _state()
    threats = counter_analyzer.analyze_threats(state.enemy_heroes)
    recs = item_recommender.recommend_items(state, threats)
    assert recs[0].item == "black_king_bar"
    top = recs[0]
    assert top.priority == Priority.HIGH
    assert top.reason and top.benefit and top.alternative
    assert top.remaining_gold == 4500 - top.cost and top.affordable


def test_owned_items_not_recommended():
    state = _state(items={"slot0": {"name": "item_black_king_bar"}})
    recs = item_recommender.recommend_items(state, counter_analyzer.analyze_threats(state.enemy_heroes))
    assert all(r.item != "black_king_bar" for r in recs)


def test_popularity_alone_does_not_create_recommendations():
    state = _state()
    pop = {"mid_game_items": {"1": 999}}  # item id 1 = Blink Dagger, not in rules for this hero/phase
    recs = item_recommender.recommend_items(state, [], popularity=pop)
    assert all(r.item != "blink" for r in recs)


def test_ranged_hero_never_gets_battle_fury():
    state = _state(hero={"name": "npc_dota_hero_lina", "level": 20})
    threats = counter_analyzer.analyze_threats(["phantom_lancer", "naga_siren"])
    assert all(r.item != "bfury" for r in item_recommender.recommend_items(state, threats, limit=20))


def test_decisions_need_data_and_label_uncertainty():
    empty = parse_gsi({})
    out = decision_engine.suggest(empty, [], [])
    assert len(out) == 1 and "uncertain" in out[0].confidence
    state = _state()
    out = decision_engine.suggest(state, [], [])
    roshan = [s for s in out if s.category == "roshan"]
    assert roshan and "uncertain" in roshan[0].confidence


def test_analyze_runs_offline_on_all_mock_scenarios(tmp_path):
    from app.data.opendota import OpenDotaClient
    from app.database.connection import connect

    conn = connect(tmp_path / "t.db")
    client = OpenDotaClient(conn, offline=True)
    for name in MockProvider().scenario_names():
        result = analyze(MockProvider(scenario=name).current_state(), conn, client)
        assert result["recommendations"]
        assert not result["used_history"]
    assert conn.execute("SELECT COUNT(*) FROM game_snapshots").fetchone()[0] == 3


def test_ranged_hero_gets_no_melee_only_alternatives_or_counters():
    state = MockProvider(scenario="03_late_lina").current_state()
    threats = counter_analyzer.analyze_threats(["npc_dota_hero_phantom_lancer"])
    for r in item_recommender.recommend_items(state, threats, limit=20):
        assert r.alternative != "bfury"
        assert r.alternative is not None, r.item
    counters = counter_analyzer.counter_items(threats, my_hero=state.hero.name)
    assert "bfury" not in {c.item for c in counters}


def test_owned_components_reduce_gold_needed():
    state = parse_gsi({"map": {"clock_time": 300}, "player": {"gold": 0},
                       "hero": {"name": "npc_dota_hero_juggernaut"},
                       "items": {"slot0": {"name": "item_boots"}}})
    treads = next(r for r in item_recommender.recommend_items(state, [], limit=20) if r.item == "power_treads")
    assert treads.remaining_gold == -(1400 - 500)
    assert treads.upgrade_cost == 900
    assert treads.owned_components == ["Boots of Speed"]


def test_nested_components_and_spike_tip_use_gold_needed():
    from app.engine.item_recommender import _gold_needed

    assert _gold_needed("octarine_core", ["point_booster"]) == 5100 - 1200
    state = parse_gsi({"map": {"clock_time": 300}, "player": {"gold": 640},
                       "hero": {"name": "npc_dota_hero_juggernaut", "level": 5, "health_percent": 90},
                       "items": {"slot0": {"name": "item_boots"}}})
    recs = [r for r in item_recommender.recommend_items(state, [], limit=20) if r.item == "power_treads"]
    tips = [s.text for s in decision_engine.suggest(state, [], recs) if s.category == "power_spike"]
    assert tips and "260 gold away" in tips[0]


def test_laning_phase_prioritizes_laning_core_over_expensive_counters():
    state = MockProvider(scenario="01_laning_juggernaut").current_state()
    threats = counter_analyzer.analyze_threats(state.enemy_heroes)
    recs = item_recommender.recommend_items(state, threats)
    top_two = {r.item for r in recs[:2]}
    assert "power_treads" in top_two and "wraith_band" in top_two
    assert all(r.item not in {"eternal_shroud", "ghost", "heavens_halberd"} for r in recs)


def test_midgame_carry_avoids_tank_caster_and_duplicate_farming_items():
    state = MockProvider(scenario="02_midgame_juggernaut").current_state()
    threats = counter_analyzer.analyze_threats(state.enemy_heroes)
    recs = item_recommender.recommend_items(state, threats)
    items = [r.item for r in recs]
    assert items[0] == "black_king_bar"
    assert "ghost" not in items
    assert "eternal_shroud" not in items
    assert "maelstrom" not in items


def test_late_lina_avoids_crimson_guard_and_melee_alternatives():
    state = MockProvider(scenario="03_late_lina").current_state()
    threats = counter_analyzer.analyze_threats(state.enemy_heroes)
    recs = item_recommender.recommend_items(state, threats)
    items = [r.item for r in recs]
    assert "crimson_guard" not in items
    assert all(r.alternative not in {"bfury", "abyssal_blade"} for r in recs)


def test_benefits_are_specific_and_popularity_hides_zero_percent():
    state = MockProvider(scenario="03_late_lina").current_state()
    pop = {"late_game_items": {"110": 1, "96": 1000}}  # refresher share ~0.1% -> would round to 0%
    recs = item_recommender.recommend_items(state, [], popularity=pop)
    refresher = next(r for r in recs if r.item == "refresher")
    assert "0%" not in refresher.reason
    assert "Completes your core build" not in refresher.benefit
    assert "(int)" not in refresher.reason and "Intelligence" in refresher.reason


def test_invisibility_lineup_shows_at_most_one_detection_item():
    state = MockProvider(scenario="01_laning_juggernaut").current_state()
    state.enemy_heroes = ["riki", "bounty_hunter", "clinkz"]
    threats = counter_analyzer.analyze_threats(state.enemy_heroes)
    recs = item_recommender.recommend_items(state, threats)
    detection = [r.item for r in recs if r.item in {"dust", "ward_sentry", "gem"}]
    assert detection == ["dust"]


def test_counter_alternatives_also_counter_the_threat():
    state = MockProvider(scenario="02_midgame_juggernaut").current_state()
    state.enemy_heroes = ["necrolyte", "silencer"]
    threats = counter_analyzer.analyze_threats(state.enemy_heroes)
    recs = item_recommender.recommend_items(state, threats, limit=20)
    by_item = {r.item: r for r in recs}
    assert by_item["skadi"].alternative in {"spirit_vessel", "shivas_guard"}
    assert by_item["manta"].alternative in {"black_king_bar", "cyclone"}


def test_power_treads_still_allows_boots_of_travel_vs_pushers():
    state = MockProvider(scenario="02_midgame_juggernaut").current_state()
    state.enemy_heroes = ["furion", "naga_siren", "lycan"]
    threats = counter_analyzer.analyze_threats(state.enemy_heroes)
    recs = item_recommender.recommend_items(state, threats, limit=20)
    items = {r.item for r in recs}
    assert "travel_boots" in items
    assert "phase_boots" not in items
