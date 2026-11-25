"""Parse Dota 2 Game State Integration (GSI) style JSON into a GameState.

The format follows Valve's documented GSI payload (map/player/hero/abilities/items).
Fields the payload does not contain are recorded in `missing_fields` instead of guessed.
"""
from __future__ import annotations

from typing import Any

from app.data.constants import heroes_by_name, hero_short
from app.models import Ability, DataSource, GameState, HeroState

ACTIVE_STATES = {
    "DOTA_GAMERULES_STATE_PRE_GAME",
    "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
    "DOTA_GAMERULES_STATE_STRATEGY_TIME",
    "DOTA_GAMERULES_STATE_HERO_SELECTION",
}


def _pct(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def parse_gsi(payload: dict, *, source: DataSource = DataSource.LIVE_GSI) -> GameState:
    mock_meta = payload.get("dotasense_mock") or {}
    is_mock = bool(mock_meta.get("is_mock")) or source == DataSource.MOCK
    game_map = payload.get("map") or {}
    player = payload.get("player") or {}
    hero = payload.get("hero") or {}
    missing: list[str] = []

    hero_name = hero.get("name")
    short = hero_short(hero_name)
    hero_info = heroes_by_name().get(short) if short else None
    hero_state = HeroState(
        name=hero_name,
        hero_id=hero.get("id") or (hero_info["id"] if hero_info else None),
        level=hero.get("level"),
        health_percent=_pct(hero.get("health_percent")),
        mana_percent=_pct(hero.get("mana_percent")),
        alive=hero.get("alive"),
    )
    if not hero_name:
        missing.append("hero")

    items: list[str] = []
    raw_items = payload.get("items")
    if raw_items is None:
        missing.append("items")
    else:
        for slot, data in raw_items.items():
            if not slot.startswith(("slot", "neutral")):
                continue
            name = (data or {}).get("name", "empty")
            if name and name != "empty":
                items.append(name.removeprefix("item_"))

    abilities: list[Ability] = []
    raw_abilities = payload.get("abilities")
    if raw_abilities is None:
        missing.append("abilities")
    else:
        for data in raw_abilities.values():
            if not isinstance(data, dict) or not data.get("name"):
                continue
            abilities.append(Ability(
                name=data["name"], level=data.get("level", 0), cooldown=data.get("cooldown"),
                can_cast=data.get("can_cast"), ultimate=bool(data.get("ultimate")),
            ))

    for field, value in (("gold", player.get("gold")), ("game_time", game_map.get("clock_time"))):
        if value is None:
            missing.append(field)
    enemies = list(mock_meta.get("enemy_heroes") or [])
    if not enemies:
        missing.append("enemy_heroes")

    state_name = game_map.get("game_state")
    return GameState(
        source=DataSource.MOCK if is_mock else source,
        is_mock=is_mock,
        scenario_name=mock_meta.get("scenario_name"),
        match_id=str(game_map["matchid"]) if game_map.get("matchid") else None,
        match_active=state_name in ACTIVE_STATES,
        game_state=state_name,
        game_time=game_map.get("clock_time"),
        is_daytime=game_map.get("daytime"),
        team=player.get("team_name"),
        gold=player.get("gold"),
        gpm=player.get("gpm"),
        xpm=player.get("xpm"),
        kills=player.get("kills"),
        deaths=player.get("deaths"),
        assists=player.get("assists"),
        last_hits=player.get("last_hits"),
        hero=hero_state,
        items=items,
        abilities=abilities,
        enemy_heroes=enemies,
        ally_heroes=list(mock_meta.get("ally_heroes") or []),
        missing_fields=missing,
    )
