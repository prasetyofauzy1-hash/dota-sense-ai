from math import isclose

from app.data import constants as C
from app.data.pro_matches import Appearance, ItemComparison, Record, item_cohorts, load_pro_matches, win_record


def test_matchup_and_final_item_cohorts():
    sample = load_pro_matches()
    all_games = sample.for_hero(42)
    medusa_games = sample.for_hero(42, 93)
    assert {game.match_id for game in medusa_games} == {8743150103}
    assert not sample.for_hero(42, 42)
    assert win_record(all_games) == Record(1, 5)
    radiance_id = C.items()["radiance"]["id"]
    assert item_cohorts(all_games, radiance_id).compare() == ItemComparison(Record(1, 4), Record(0, 1))
    assert item_cohorts(medusa_games, radiance_id).compare().gap_pp is None


def test_snapshot_has_one_winner_per_match_and_no_duplicate_hero_appearances():
    sample = load_pro_matches()
    games_by_id: dict[int, list[Appearance]] = {}
    for games in sample.by_hero.values():
        assert len({game.match_id for game in games}) == len(games)
        for game in games:
            games_by_id.setdefault(game.match_id, []).append(game)
    assert len(games_by_id) == sample.match_count == 2774
    assert all(len(games) == 10 and sum(game.won for game in games) == 5 for games in games_by_id.values())


def test_gap_is_a_difference_in_percentage_points_and_requires_both_samples():
    enough = ItemComparison(Record(3, 10), Record(11, 20))
    assert isclose(enough.gap_pp, -25)
    assert ItemComparison(Record(9, 9), Record(0, 20)).gap_pp is None
    assert ItemComparison(Record(9, 20), Record(1, 1)).gap_pp is None
    assert Record(0, 0).rate is None
    assert item_cohorts((), 137).compare() == ItemComparison(Record(0, 0), Record(0, 0))


def test_combined_ward_stacks_are_unknown_unless_the_individual_ward_is_also_visible():
    stack = Appearance(1, 1, frozenset(), frozenset({218}), True)
    no_wards = Appearance(2, 1, frozenset(), frozenset(), False)
    for item in (42, 43):
        visible = Appearance(3, 1, frozenset(), frozenset({218, item}), False)
        cohorts = item_cohorts((stack, no_wards, visible), item)
        assert cohorts.with_item == (visible,)
        assert cohorts.without_item == (no_wards,)
        assert cohorts.excluded == 1
