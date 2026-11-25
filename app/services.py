"""Glue between providers, OpenDota data and the engines. Used by the API and dashboard."""
from __future__ import annotations

import logging
import sqlite3

from app.data import constants as C
from app.data.opendota import OpenDotaClient, OpenDotaError
from app.database import models as db
from app.engine import counter_analyzer, decision_engine, item_recommender
from app.models import GameState

log = logging.getLogger(__name__)


def analyze(state: GameState, conn: sqlite3.Connection | None = None,
            client: OpenDotaClient | None = None, *, use_history: bool = True) -> dict:
    notes: list[str] = []
    popularity = matchups = None
    hero_id = state.hero.hero_id
    if use_history and hero_id and client is not None:
        try:
            popularity = client.hero_item_popularity(hero_id)
            matchups = client.hero_matchups(hero_id)
        except OpenDotaError as exc:
            notes.append(f"Historical data unavailable ({exc}); using rules only.")
    elif not use_history:
        notes.append("Historical data off; using rules only.")

    threats = counter_analyzer.analyze_threats(state.enemy_heroes, my_hero_id=hero_id, matchups=matchups)
    counters = counter_analyzer.counter_items(threats, owned=state.items)
    recs = item_recommender.recommend_items(state, threats, popularity=popularity)
    suggestions = decision_engine.suggest(state, threats, recs)

    if conn is not None:
        sid = db.save_snapshot(conn, state.model_dump_json(), source=state.source.value, is_mock=state.is_mock,
                               match_id=state.match_id, game_time=state.game_time)
        db.log_recommendations(conn, sid, [(r.item, r.priority.value, r.score) for r in recs])

    return {
        "state": state,
        "hero_name": C.hero_display(state.hero.name),
        "phase": state.phase.value,
        "threats": threats,
        "counters": counters,
        "recommendations": recs,
        "suggestions": suggestions,
        "enemy_abilities": {t.hero_name: counter_analyzer.hero_abilities(t.hero) for t in threats},
        "notes": notes,
        "used_history": popularity is not None,
    }
