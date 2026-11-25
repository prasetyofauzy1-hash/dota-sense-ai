"""Counter intelligence: threat analysis of the visible enemy lineup (Phase 3)."""
from __future__ import annotations

from app.data import constants as C
from app.models import CounterItem, Threat


def hero_tags(hero: str) -> tuple[list[str], str]:
    """Threat tags for a hero (short name), from curated table or OpenDota roles."""
    short = C.hero_short(hero) or ""
    if short in C.CURATED_HERO_THREATS:
        return C.CURATED_HERO_THREATS[short], "curated"
    info = C.heroes_by_name().get(short)
    roles = info.get("roles", []) if info else []
    tags = [C.ROLE_THREATS[r] for r in roles if r in C.ROLE_THREATS]
    return list(dict.fromkeys(tags)), "roles"


def hero_abilities(hero: str) -> list[str]:
    """Display names of a hero's abilities (from the OpenDota constants snapshot)."""
    from app.data.opendota import _load_snapshot

    full = f"{C.HERO_PREFIX}{C.hero_short(hero)}"
    raw = _load_snapshot("hero_abilities").get(full, {}).get("abilities", [])
    prefix = f"{C.hero_short(hero)}_"
    names = [a for a in raw if a and a != "generic_hidden"]
    return [a.removeprefix(prefix).replace("_", " ").title() for a in names]


def analyze_threats(enemy_heroes: list[str], *, my_hero_id: int | None = None,
                    matchups: list[dict] | None = None) -> list[Threat]:
    """Rank enemy heroes by threat. `matchups` is OpenDota /heroes/{id}/matchups for
    the player's hero; when given, a low historical win rate raises severity."""
    winrates: dict[int, tuple[float, int]] = {}
    for m in matchups or []:
        if m.get("games_played"):
            winrates[m["hero_id"]] = (m["wins"] / m["games_played"], m["games_played"])

    threats: list[Threat] = []
    for enemy in enemy_heroes:
        short = C.hero_short(enemy)
        info = C.heroes_by_name().get(short or "")
        tags, source = hero_tags(enemy)
        severity = 1.0 + 0.5 * len(tags)
        parts = [", ".join(C.THREAT_LABELS[t] for t in tags) or "No known threat tags"]
        if info and info["id"] in winrates:
            wr, games = winrates[info["id"]]
            if games >= 20:
                severity += max(0.0, (0.5 - wr) * 10)
                parts.append(f"your hero won {wr:.0%} of {games} recent public games against it (OpenDota)")
        threats.append(Threat(
            hero=short or enemy, hero_name=C.hero_display(enemy), tags=tags,
            severity=round(severity, 2), explanation="; ".join(parts), tags_source=source,
        ))
    return sorted(threats, key=lambda t: t.severity, reverse=True)


def counter_items(threats: list[Threat], owned: list[str] | None = None,
                  my_hero: str | None = None) -> list[CounterItem]:
    from app.engine.item_recommender import _fit_weight

    owned_set = set(owned or [])
    hero = C.heroes_by_name().get(C.hero_short(my_hero) or "") if my_hero else None
    merged: dict[str, CounterItem] = {}
    for threat in threats:
        for tag in threat.tags:
            for item, why, defensive in C.COUNTER_ITEMS.get(tag, []):
                if item in owned_set or (hero and _fit_weight(item, hero) == 0.0):
                    continue
                entry = merged.get(item)
                if entry is None:
                    entry = merged[item] = CounterItem(
                        item=item, item_name=C.item_display(item), counters=[], against_heroes=[],
                        explanation=why, defensive=defensive,
                    )
                if C.THREAT_LABELS[tag] not in entry.counters:
                    entry.counters.append(C.THREAT_LABELS[tag])
                if threat.hero_name not in entry.against_heroes:
                    entry.against_heroes.append(threat.hero_name)
    return sorted(merged.values(), key=lambda c: len(c.against_heroes) + len(c.counters), reverse=True)
