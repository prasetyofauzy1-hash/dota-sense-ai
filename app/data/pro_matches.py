"""Read-only OpenDota sample and matchup-level final-inventory comparisons."""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache

from app.data import constants as C
from app.data.opendota import SNAPSHOT_DIR

MIN_ITEM_GROUP = 10


def utc_day(timestamp: int) -> date:
    return datetime.fromtimestamp(timestamp, tz=UTC).date()


@dataclass(frozen=True)
class Appearance:
    match_id: int
    league_id: int
    enemy_ids: frozenset[int]
    item_ids: frozenset[int]
    won: bool


@dataclass(frozen=True)
class Record:
    wins: int
    games: int

    @property
    def rate(self) -> float | None:
        return self.wins / self.games if self.games else None


@dataclass(frozen=True)
class ItemComparison:
    with_item: Record
    without_item: Record

    @property
    def gap_pp(self) -> float | None:
        with_rate, without_rate = self.with_item.rate, self.without_item.rate
        if (min(self.with_item.games, self.without_item.games) < MIN_ITEM_GROUP
                or with_rate is None or without_rate is None):
            return None
        return 100 * (with_rate - without_rate)


@dataclass(frozen=True)
class ItemCohorts:
    with_item: tuple[Appearance, ...]
    without_item: tuple[Appearance, ...]
    excluded: int

    def compare(self) -> ItemComparison:
        return ItemComparison(win_record(self.with_item), win_record(self.without_item))


@dataclass(frozen=True)
class ProMatches:
    league_names: dict[int, str]
    league_counts: dict[int, int]
    start: date
    end: date
    by_hero: dict[int, tuple[Appearance, ...]]

    @property
    def match_count(self) -> int:
        return sum(self.league_counts.values())

    def for_hero(self, hero_id: int, enemy_id: int | None = None) -> tuple[Appearance, ...]:
        games = self.by_hero.get(hero_id, ())
        return games if enemy_id is None else tuple(g for g in games if enemy_id in g.enemy_ids)


def win_record(games: tuple[Appearance, ...]) -> Record:
    return Record(sum(game.won for game in games), len(games))


def item_cohorts(games: tuple[Appearance, ...], item_id: int) -> ItemCohorts:
    catalog = C.items()
    combined_ward = catalog["ward_dispenser"]["id"]
    ward_types = (catalog["ward_sentry"]["id"], catalog["ward_observer"]["id"])
    with_item = []
    without_item = []
    excluded = 0
    for game in games:
        if item_id in game.item_ids:
            with_item.append(game)
        elif item_id in ward_types and combined_ward in game.item_ids:
            excluded += 1
        else:
            without_item.append(game)
    return ItemCohorts(tuple(with_item), tuple(without_item), excluded)


@lru_cache(maxsize=1)
def load_pro_matches() -> ProMatches:
    with gzip.open(SNAPSHOT_DIR / "pro_matches.json.gz", "rt", encoding="utf-8") as file:
        sample = json.load(file)
    counts: Counter[int] = Counter()
    index = defaultdict(list)
    rows = sample["matches"]
    for match, league, _, radiant_win, radiant, dire in rows:
        counts[league] += 1
        for team, opponents, won in ((radiant, dire, radiant_win), (dire, radiant, not radiant_win)):
            enemy_ids = frozenset(hero for hero, _ in opponents)
            for hero, items in team:
                index[hero].append(Appearance(match, league, enemy_ids, frozenset(items), won))
    return ProMatches(
        {int(k): v for k, v in sample["leagues"].items()}, dict(counts),
        utc_day(rows[0][2]), utc_day(rows[-1][2]),
        {hero: tuple(games) for hero, games in index.items()},
    )
