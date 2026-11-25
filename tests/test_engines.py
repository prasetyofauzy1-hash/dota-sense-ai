import pytest

from app.data import constants as C
from app.engine import counter_analyzer, decision_engine, item_recommender
from app.gsi.parser import parse_gsi
from app.gsi.provider import MockProvider
from app.models import ItemRecommendation, Priority
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
    threats = counter_analyzer.analyze_threats(["lion", "abaddon", "dark_willow", "drow_ranger"])
    by_hero = {t.hero: t for t in threats}
    assert by_hero["lion"].tags_source == "curated"
    assert by_hero["abaddon"].tags == ["healing"]
    assert by_hero["dark_willow"].tags_source == "roles"
    assert "role_control" in by_hero["dark_willow"].tags
    assert "disable" not in by_hero["dark_willow"].tags
    assert "physical_burst" not in by_hero["drow_ranger"].tags
    assert not counter_analyzer.counter_items([by_hero["dark_willow"], by_hero["drow_ranger"]])


@pytest.mark.parametrize(("hero", "required", "excluded", "counter"), [
    ("phantom_assassin", "evasion", "illusions", "monkey_king_bar"),
    ("riki", "invisibility", "evasion", "dust"),
    ("bristleback", "passive", "evasion", "silver_edge"),
    ("huskar", "healing", "evasion", "spirit_vessel"),
    ("necrolyte", "dispellable_save", "passive", "nullifier"),
    ("meepo", "clones", "illusions", "shivas_guard"),
    ("alchemist", "healing", "evasion", "spirit_vessel"),
    ("storm_spirit", "mobility", "dispellable", "sheepstick"),
    ("tinker", "magic_burst", "push", "pipe"),
    ("broodmother", "summons", "illusions", "crimson_guard"),
    ("medusa", "mana_shield", "passive", "diffusal_blade"),
    ("phantom_lancer", "illusions", "evasion", "mjollnir"),
    ("antimage", "mobility", "passive", "orchid"),
    ("silencer", "dispellable", "disable", "manta"),
    ("doom_bringer", "piercing_disable", "dispellable", "sphere"),
    ("faceless_void", "piercing_disable", "evasion", "aeon_disk"),
    ("enigma", "piercing_disable", "illusions", "aeon_disk"),
    ("pugna", "dispellable_save", "passive", "nullifier"),
    ("chen", "healing", "illusions", "spirit_vessel"),
])
def test_curated_mechanics_and_counters(hero, required, excluded, counter):
    threats = counter_analyzer.analyze_threats([hero])
    assert required in threats[0].tags
    assert excluded not in threats[0].tags
    assert counter in {c.item for c in counter_analyzer.counter_items(threats)}


def test_counter_rules_use_bundled_heroes_and_items():
    assert C.CURATED_HERO_THREATS.keys() <= C.heroes_by_name().keys()
    assert all(i in C.items() for options in C.COUNTER_ITEMS.values() for i, _, _ in options)
    assert not counter_analyzer.analyze_threats(["unknown_hero"])


def test_counter_shortlist_covers_distinct_threats_and_deduplicates():
    threats = counter_analyzer.analyze_threats([
        "phantom_assassin", "riki", "bristleback", "huskar", "necrolyte", "npc_dota_hero_riki",
    ])
    counters = counter_analyzer.counter_items(threats)
    assert len(threats) == 5
    assert len({c.item for c in counters}) == len(counters)
    assert {"dust", "monkey_king_bar", "silver_edge", "spirit_vessel", "nullifier"} <= {
        c.item for c in counters[:8]
    }


def test_disable_counters_match_how_the_spell_works():
    threats = counter_analyzer.analyze_threats(["lion", "silencer", "enigma", "faceless_void", "doom_bringer"])
    counters = {c.item: c for c in counter_analyzer.counter_items(threats)}
    assert set(counters["sphere"].against_heroes) == {"Lion", "Doom"}
    assert counters["manta"].against_heroes == ["Silencer"]
    assert set(counters["black_king_bar"].against_heroes) == {"Lion", "Silencer"}
    assert {"Enigma", "Faceless Void", "Doom"} <= set(counters["aeon_disk"].against_heroes)
    assert "does not block" in counters["lotus_orb"].explanation and "Basic dispel" in counters["lotus_orb"].explanation


def test_counter_items_respect_owned_upgrades_and_ranged_fit():
    state = _state(
        hero={"name": "npc_dota_hero_lina", "level": 20},
        items={"slot0": {"name": "item_disperser"}, "slot1": {"name": "item_dust"}},
        dotasense_mock={"is_mock": True, "enemy_heroes": ["phantom_lancer", "medusa", "riki"]},
    )
    counters = {c.item for c in analyze(state, use_history=False)["counters"]}
    assert not {"bfury", "diffusal_blade", "dust"} & counters
    assert {"mjollnir", "ward_sentry"} <= counters


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


def test_strategic_calls_distinguish_snapshot_facts_from_fight_advice():
    state = _state(player={"gold": 4500, "kills": 7, "deaths": 1, "assists": 5})
    threats = counter_analyzer.analyze_threats(["faceless_void", "shadow_shaman"])
    rec = ItemRecommendation(item="black_king_bar", item_name="Black King Bar",
                             cost=C.item_cost("black_king_bar"), priority=Priority.HIGH, affordable=True,
                             remaining_gold=4500 - C.item_cost("black_king_bar"),
                             reason="snapshot item", benefit="test recommendation")
    suggestions = {s.category: s for s in decision_engine.suggest(state, threats, [rec])}
    assert all("uncertain" in s.confidence for s in suggestions.values())
    assert "enough gold" in suggestions["power_spike"].text and "once delivered" in suggestions["power_spike"].text
    assert "does not establish a team lead" in suggestions["stance"].reasons[0]
    assert "Don't count on BKB" in suggestions["team_fight"].text
    assert "tower status are unknown" in suggestions["push_defend"].reasons[0]

    state.hero.health_percent = 24
    suggestions = {s.category: s for s in decision_engine.suggest(state, threats, [rec])}
    assert suggestions["stance"].confidence == "high"
    assert "Recover HP first" in suggestions["power_spike"].text

    state.hero.alive = False
    suggestions = decision_engine.suggest(state, threats, [rec])
    assert len(suggestions) == 1 and "hero is dead" in suggestions[0].reasons


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


def test_nested_components_and_spike_tip_use_gold_needed():
    from app.engine.item_recommender import _gold_needed

    assert _gold_needed("octarine_core", ["point_booster"]) == 5100 - 1200
    state = parse_gsi({"map": {"clock_time": 300}, "player": {"gold": 640},
                       "hero": {"name": "npc_dota_hero_juggernaut", "level": 5, "health_percent": 90},
                       "items": {"slot0": {"name": "item_boots"}}})
    recs = [r for r in item_recommender.recommend_items(state, [], limit=20) if r.item == "power_treads"]
    tips = [s.text for s in decision_engine.suggest(state, [], recs) if s.category == "power_spike"]
    assert tips and "260 gold away" in tips[0]


def test_strategic_timing_uses_component_adjusted_gold():
    state = _state(player={"gold": 2800}, items={"slot0": {"name": "item_ogre_axe"}})
    threats = counter_analyzer.analyze_threats(state.enemy_heroes)
    bkb = next(r for r in item_recommender.recommend_items(state, threats) if r.item == "black_king_bar")
    assert state.gold < bkb.cost and 0 < -bkb.remaining_gold <= 800
    suggestion = next(s for s in decision_engine.suggest(state, threats, [bkb]) if s.category == "power_spike")
    assert f"{-bkb.remaining_gold} gold away" in suggestion.text

    state.gold = bkb.cost - C.item_cost("ogre_axe")
    bkb = next(r for r in item_recommender.recommend_items(state, threats) if r.item == "black_king_bar")
    suggestion = next(s for s in decision_engine.suggest(state, threats, [bkb]) if s.category == "power_spike")
    assert "enough gold" in suggestion.text and "uncertain" in suggestion.confidence
